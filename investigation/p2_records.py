"""Problem 2, Part A: record-level measurements (A1, A2, A4) on the raw site JSON.

The live SPARQL endpoint only answers POST (nginx drops the GET query string),
and this run is GET-only, so this reads the same records the ETL loads:
ta2-minmod-data/data/mineral-sites/*/*/*.json.

The state and country lists are built by MinMod's own code
(LocationInfo.from_dict -> LocationView.from_location, coordinates skipped),
and every repair decision is made by the unmodified reference implementation
(reference/state_repair.py), with the index built exactly as reference/verify.py
builds it.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2_records.py data-p2/data
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))
from state_repair import StateCountryIndex  # noqa: E402

DATA = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data-p2/data")
ENT = DATA / "entities"
OUT = ROOT / "reports/p2"


@dataclass
class S:  # same shape as reference/verify.py
    id: str
    name: str
    country: Optional[str]


countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
cname2id = {c["name"]: c["minmod_id"] for c in countries}
cid2name = {c["minmod_id"]: c["name"] for c in countries}
raw_states = list(csv.DictReader(open(ENT / "state_or_province.csv", newline="", encoding="utf-8")))
states = [S(r["minmod_id"], r["name"], cname2id[r["country_name"]]) for r in raw_states]
by_id = {s.id: s for s in states}
idx = StateCountryIndex.build(states)


def repair(state_id, observed_name, country_ids):
    """reference/verify.py's repair(), verbatim."""
    if not idx.conflicts(state_id, country_ids):
        return ("keep", state_id)
    fixed = idx.resolve(observed_name, country_ids)
    return ("repoint", fixed) if fixed else ("drop", None)


def scan(path: str) -> list[dict]:
    """One row per (record, state candidate carrying a normalized_uri)."""
    from minmodkg.models.kg.base import NS_MR
    from minmodkg.models.kg.location_info import LocationInfo
    from minmodkg.models.kg.mineral_site import MineralSiteIdent
    from minmodkg.models.kgrel.custom_types.location import Location, LocationView

    rows = []
    for r in json.load(open(path)):
        if not r.get("location_info"):
            continue
        li = LocationInfo.from_dict(r["location_info"])
        view = LocationView.from_location(
            Location(country=li.country, state_or_province=li.state_or_province), {}
        )
        cands = [c for c in li.state_or_province if c.normalized_uri is not None]
        assert [NS_MR.id(c.normalized_uri) for c in cands] == view.state_or_province
        # highest-confidence country, ties broken by list order (for A4)
        top = max(
            (c for c in li.country if c.normalized_uri is not None),
            key=lambda c: c.confidence,
            default=None,
        )
        for c in cands:
            rows.append(
                {
                    "site_id": MineralSiteIdent.from_dict(r).id,
                    "file": path.split("mineral-sites/")[1],
                    "source": c.source,
                    "observed_name": c.observed_name,
                    "state": NS_MR.id(c.normalized_uri),
                    "countries": view.country,
                    "top_country": NS_MR.id(top.normalized_uri) if top else None,
                }
            )
    return rows


def obs_kind(o) -> str:
    if o is None:
        return "missing"
    return "empty" if not o.strip() else "present"


def main():
    files = sorted(glob.glob(str(DATA / "mineral-sites/*/*/*.json")))
    with ProcessPoolExecutor() as ex:
        rows = [row for part in ex.map(scan, files, chunksize=8) for row in part]
    OUT.mkdir(parents=True, exist_ok=True)
    summary: dict = {"files": len(files), "state_candidates": len(rows),
                     "sites_with_a_state": len({r["site_id"] for r in rows})}

    # ---- A1: observed_name coverage by matcher, all candidates and conflicted ones
    for r in rows:
        r["obs"] = obs_kind(r["observed_name"])
        cset = list(dict.fromkeys(r["countries"]))
        r["conflict"] = idx.conflicts(r["state"], cset)
        r["unknown_state"] = r["state"] not in idx.state_country
        r["action"], r["new"] = repair(r["state"], r["observed_name"], cset)
        fallback_key = r["observed_name"] if r["obs"] == "present" else by_id[r["state"]].name if r["state"] in by_id else None
        r["action_fb"], r["new_fb"] = repair(r["state"], fallback_key, cset)

    a1 = collections.defaultdict(collections.Counter)
    for r in rows:
        a1[r["source"]]["nodes"] += 1
        a1[r["source"]][r["obs"]] += 1
        if r["conflict"]:
            a1[r["source"]]["conflicted"] += 1
            a1[r["source"]]["conflicted_" + r["obs"]] += 1
    summary["a1_by_source"] = {k: dict(v) for k, v in sorted(a1.items(), key=lambda x: -x[1]["nodes"])}
    conf = [r for r in rows if r["conflict"]]
    summary["unknown_state_ids"] = sum(r["unknown_state"] for r in rows)
    summary["conflicted_candidates"] = len(conf)
    summary["conflicted_sites"] = len({r["site_id"] for r in conf})
    summary["conflicted_obs"] = dict(collections.Counter(r["obs"] for r in conf))

    # ---- A2: distinct (observed_name, chosen state, recorded countries) triples, weighted
    trip = collections.Counter(
        (r["observed_name"], r["state"], " ".join(sorted(set(r["countries"])))) for r in conf
    )
    summary["conflicted_distinct_triples"] = len(trip)
    top = trip.most_common()
    covered = 0
    for i, (_, n) in enumerate(top, 1):
        covered += n
        if covered >= 0.9 * len(conf):
            summary["triples_covering_90pct"] = i
            break
    summary["a2_actions"] = dict(collections.Counter(r["action"] for r in conf))
    summary["a2_actions_fallback"] = dict(collections.Counter(r["action_fb"] for r in conf))
    summary["a2_actions_by_obs"] = {
        k: dict(collections.Counter(r["action"] for r in conf if r["obs"] == k))
        for k in ("present", "missing", "empty")
    }
    summary["a2_fallback_rescues"] = sum(
        1 for r in conf if r["action"] == "drop" and r["action_fb"] == "repoint"
    )
    with open(OUT / "conflicted_triples.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["records", "observed_name", "state_id", "state_name", "state_country",
                    "recorded_country_ids", "recorded_countries", "action", "new_state_id",
                    "new_state_name", "action_with_name_fallback", "new_state_id_fallback"])
        for (obs, sid, cs), n in top:
            cset = cs.split()
            act, new = repair(sid, obs, cset)
            key = obs if obs_kind(obs) == "present" else by_id[sid].name
            act_fb, new_fb = repair(sid, key, cset)
            w.writerow([n, obs, sid, by_id[sid].name, cid2name.get(by_id[sid].country),
                        cs, "|".join(cid2name.get(c, c) for c in cset), act, new,
                        by_id[new].name if new else "", act_fb, new_fb or ""])

    # ---- A4: how many countries do records carry
    def bucket(n):
        return "0" if n == 0 else "1" if n == 1 else "2" if n == 2 else "3+"

    summary["a4_conflicted_country_count"] = dict(collections.Counter(bucket(len(set(r["countries"]))) for r in conf))
    multi = [r for r in rows if len(set(r["countries"])) >= 2 and not r["unknown_state"]]
    m = collections.Counter()
    for r in multi:
        owner = idx.state_country[r["state"]]
        m["records"] += 1
        if owner == r["top_country"]:
            m["state_in_top_confidence_country"] += 1
        elif owner in r["countries"]:
            m["state_only_in_a_lower_confidence_country"] += 1
        else:
            m["state_in_none (conflict)"] += 1
    summary["a4_all_multi_country_candidates"] = dict(m)
    summary["a4_all_country_count"] = dict(collections.Counter(bucket(len(set(r["countries"]))) for r in rows))

    with open(OUT / "records_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(OUT / "conflicted_candidates.jsonl", "w", encoding="utf-8") as f:
        for r in conf:
            f.write(json.dumps({k: r[k] for k in ("site_id", "file", "source", "observed_name", "state",
                                                     "countries", "top_country", "action", "new",
                                                     "action_fb", "new_fb")}, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
