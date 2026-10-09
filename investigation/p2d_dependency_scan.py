"""Option A, investigation only: state names that name a country.

For every record with a recorded country, every state candidate's observed
name is matched against country.csv (name and alt names; ISO codes left out:
"CO" is a Mexican abbreviation, not Colombia). Matches to a recorded country
of the same record are ignored. Levels, strictest first:

  1 exact     fold_name(observed) == fold_name(country name)
  2 admin     the same after drop_admin_words on both sides
              ("Territory Of Christmas Island" -> Christmas Island)
  3 tokens    the same set of words after that ("British Virgin Islands" vs
              "Virgin Islands (British)")
  4 contains  a country name of two or more words appears inside the
              observed name ("... New Caledonia And Dependencies")

Each group also records what the repair does with it today (the code on
fix/p2-state-repair, the table on the fork branch: rows and aliases).

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2d_dependency_scan.py <entities dir>

Writes reports/p2d/dependency_scan.csv.
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data-p2/data"
ENT = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "entities"
OUT = ROOT / "reports/p2d"

from minmodkg.etl.kgrel_entity import EntityDeserFn  # noqa: E402
from minmodkg.misc.state_repair import StateCountryIndex, drop_admin_words, fold_name  # noqa: E402

countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
cid2name = {c["minmod_id"]: c["name"] for c in countries}
states = EntityDeserFn.read_state_or_province(ENT / "state_or_province.csv")
aliases = EntityDeserFn.read_state_or_province_aliases(ENT / "state_or_province.csv")
by_id = {s.id: s for s in states}
idx = StateCountryIndex.build(states, aliases)

EXACT, ADMIN, TOKENS, CONTAINS = {}, {}, {}, []
for c in countries:
    for n in [c["name"]] + [a.strip() for a in c["alt names"].split("|") if a.strip()]:
        f = fold_name(n)
        a = drop_admin_words(f)
        EXACT.setdefault(f, set()).add(c["minmod_id"])
        ADMIN.setdefault(a, set()).add(c["minmod_id"])
        TOKENS.setdefault(frozenset(a.split()), set()).add(c["minmod_id"])
        if len(a.split()) >= 2:
            CONTAINS.append((a.split(), c["minmod_id"]))


def match(observed: str) -> list[tuple[str, str]]:
    f = fold_name(observed)
    a = drop_admin_words(f)
    for level, hits in (("1 exact", EXACT.get(f)), ("2 admin", ADMIN.get(a)),
                        ("3 tokens", TOKENS.get(frozenset(a.split())))):
        if hits:
            return [(level, h) for h in sorted(hits)]
    words = a.split()
    found = []
    for seq, cid in CONTAINS:
        n = len(seq)
        if any(words[i:i + n] == seq for i in range(len(words) - n + 1)):
            found.append(("4 contains", cid))
    return found


def today(state_id, observed, cs) -> str:
    if state_id is None:
        return "no state chosen"
    action, sid = idx.repair(state_id, observed, cs)
    if sid is None:
        return "dropped"
    return f"{action} {sid} {by_id[sid].name}"


def scan(path: str) -> tuple[list[dict], int]:
    from minmodkg.models.kg.base import NS_MR
    from minmodkg.models.kg.mineral_site import MineralSiteIdent

    rows, no_country = [], 0
    for r in json.load(open(path, encoding="utf-8")):
        li = r.get("location_info") or {}
        cs = list(dict.fromkeys(NS_MR.id(c["normalized_uri"]) for c in li.get("country") or []
                                if c.get("normalized_uri")))
        sps = [s for s in li.get("state_or_province") or [] if (s.get("observed_name") or "").strip()]
        if not sps:
            continue
        if not cs:
            no_country += 1
            continue
        for s in sps:
            hits = [(lvl, cid) for lvl, cid in match(s["observed_name"]) if cid not in cs]
            if not hits:
                continue
            sid = NS_MR.id(s["normalized_uri"]) if s.get("normalized_uri") else None
            for lvl, cid in hits:
                rows.append({"site_id": MineralSiteIdent.from_dict(r).id, "observed": s["observed_name"],
                             "recorded": " | ".join(cid2name[c] for c in cs), "target": cid2name[cid],
                             "level": lvl, "today": today(sid, s["observed_name"], cs)})
    return rows, no_country


def main() -> None:
    files = sorted(glob.glob(str(DATA / "mineral-sites/*/*/*.json")))
    with ProcessPoolExecutor() as ex:
        parts = list(ex.map(scan, files, chunksize=8))
    rows = [r for p, _ in parts for r in p]
    groups: dict[tuple, dict] = {}
    for r in rows:
        g = groups.setdefault((r["recorded"], r["observed"], r["target"], r["level"]),
                              {"records": set(), "today": collections.Counter()})
        g["records"].add(r["site_id"])
        g["today"][r["today"]] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "dependency_scan.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["recorded_country", "observed_name", "target_country", "match", "records", "today"])
        for (rec, obs, tgt, lvl), g in sorted(groups.items(), key=lambda kv: (kv[0][3], -len(kv[1]["records"]), kv[0])):
            w.writerow([rec, obs, tgt, lvl, len(g["records"]),
                        "; ".join(f"{k} x{v}" for k, v in g["today"].most_common())])
    print(json.dumps({"groups": len(groups), "records": len({r["site_id"] for r in rows}),
                      "by_level": dict(collections.Counter(k[3] for k in groups)),
                      "records_with_a_state_name_but_no_recorded_country": sum(n for _, n in parts)}, indent=2))


if __name__ == "__main__":
    main()
