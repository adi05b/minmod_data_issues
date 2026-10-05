"""Problem 2, Part B: the final rule, measured before any pipeline code changes.

Rule = reference/state_repair.py as revised for Part B: tiers exact name ->
admin/stop words dropped -> state_code, Turkish dotless i folded, and the
chosen state's own name used when observed_name is missing.

  records  record-level outcome on the raw JSON (expect 5,421 / 737 of 6,158),
           the country-name repeats, and what still drops (sizes B6)
  gates    gate 1 (regression) and gate 2 (self-resolution)
  merged   repair-only rebuild of the merged entities (gate 3 for the rule),
           with MinMod's own election code; run it before B3 is applied

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2b_measure.py records|gates|merged
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
from state_repair import StateCountryIndex, drop_admin_words, fold_name  # noqa: E402

ENT = ROOT / "data-p2/data/entities"
OUT = ROOT / "reports/p2b"


@dataclass
class S:
    id: str
    name: str
    country: Optional[str]
    state_code: str


countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
cname2id = {c["name"]: c["minmod_id"] for c in countries}
cid2name = {c["minmod_id"]: c["name"] for c in countries}
states = [
    S(r["minmod_id"], r["name"], cname2id[r["country_name"]], r["state_code"])
    for r in csv.DictReader(open(ENT / "state_or_province.csv", newline="", encoding="utf-8"))
]
by_id = {s.id: s for s in states}
idx = StateCountryIndex.build(states)


def tier_of(key: Optional[str], cids: list[str]) -> tuple[str, Optional[str]]:
    """Which tier resolve() stops at (reporting only; checked against resolve())."""
    if not key or not cids:
        return ("no key", None)
    f = fold_name(key)
    for name, index, k in (("1 exact name", idx._exact, f),
                           ("2 admin/stop words dropped", idx._folded, drop_admin_words(f)),
                           ("3 state_code", idx._code, key.strip().upper())):
        hits = list(dict.fromkeys(h for c in cids for h in index.get(c, {}).get(k, ())))
        if len(hits) == 1:
            return (name, hits[0])
        if len(hits) > 1:
            return (f"ambiguous at tier {name[0]}", None)
    return ("no hit", None)


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%"


def records() -> dict:
    sys.argv = sys.argv[:1] + [str(ROOT / "data-p2/data")]
    sys.path.insert(0, str(ROOT / "investigation"))
    from p2_records import scan

    files = sorted(glob.glob(str(ROOT / "data-p2/data/mineral-sites/*/*/*.json")))
    with ProcessPoolExecutor() as ex:
        rows = [r for part in ex.map(scan, files, chunksize=8) for r in part]
    conf = []
    for r in rows:
        cs = list(dict.fromkeys(r["countries"]))
        if not idx.conflicts(r["state"], cs):
            assert idx.repair(r["state"], r["observed_name"], cs) == ("keep", r["state"])
            continue
        r["cs"] = cs
        r["action"], r["new"] = idx.repair(r["state"], r["observed_name"], cs)
        has_obs = bool(r["observed_name"] and r["observed_name"].strip())
        key = r["observed_name"] if has_obs else by_id[r["state"]].name
        r["tier"], hit = tier_of(key, cs)
        assert hit == r["new"], (r, hit)
        if not has_obs and r["action"] == "repoint":
            r["tier"] = "fallback: own name, " + r["tier"]
        conf.append(r)
    n = len(conf)
    act = collections.Counter(r["action"] for r in conf)
    out = {
        "state_candidates": len(rows),
        "conflicted_candidates": n,
        "conflicted_records": len({r["site_id"] for r in conf}),
        "repointed": act["repoint"], "repointed_pct": pct(act["repoint"], n),
        "dropped": act["drop"], "dropped_pct": pct(act["drop"], n),
        "repointed_by_tier": dict(collections.Counter(r["tier"] for r in conf if r["action"] == "repoint").most_common()),
        "dropped_by_reason": dict(collections.Counter(r["tier"] for r in conf if r["action"] == "drop").most_common()),
    }
    # country-name repeats: the "state" is the recorded country's own name
    rep = [r for r in conf if r["observed_name"]
           and fold_name(r["observed_name"]) in {fold_name(cid2name[c]) for c in r["cs"]}]
    out["country_name_repeats"] = len(rep)
    out["country_name_repeats_by_outcome"] = [
        {"records": k, "observed_name": o, "country": c, "action": a, "to": t}
        for (o, c, a, t), k in collections.Counter(
            (r["observed_name"], cid2name[r["cs"][0]], r["action"],
             f"{r['new']} {by_id[r['new']].name}" if r["new"] else "") for r in rep).most_common()]
    # what still drops, for B6
    drops = collections.Counter(
        (r["observed_name"], "|".join(cid2name[c] for c in r["cs"]), r["tier"]) for r in conf if r["action"] == "drop")
    out["top_drops"] = [{"records": k, "observed_name": o, "country": c, "why": w}
                        for (o, c, w), k in drops.most_common(40)]
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "country_name_repeats.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "source_file", "matcher", "observed_name", "recorded_country",
                    "stored_state", "repointed_to"])
        for r in sorted(rep, key=lambda r: (r["observed_name"], r["site_id"])):
            w.writerow([r["site_id"], r["file"], r["source"], r["observed_name"], cid2name[r["cs"][0]],
                        f"{r['state']} {by_id[r['state']].name} ({cid2name[by_id[r['state']].country]})",
                        f"{r['new']} {by_id[r['new']].name}" if r["new"] else "dropped"])
    with open(OUT / "conflicted_outcomes.jsonl", "w", encoding="utf-8") as f:
        for r in conf:
            f.write(json.dumps({k: r[k] for k in ("site_id", "file", "source", "observed_name", "state",
                                                     "cs", "action", "new", "tier")}, ensure_ascii=False) + "\n")
    return out


def gates() -> dict:
    # gate 1: every assignment ProcMine already gets right stays untouched
    pm: dict[str, str] = {}
    for s in states:
        pm.setdefault(s.name.lower(), s.id)
    correct = [s for s in states if pm[s.name.lower()] == s.id]
    altered = [s.id for s in correct if idx.repair(s.id, s.name, [s.country]) != ("keep", s.id)]
    # gate 2: each state's own name, in its own country, must find itself or nothing
    self_ok, amb, wrong, nohit = [], [], [], []
    for s in states:
        got = idx.resolve(s.name, [s.country])
        if got == s.id:
            self_ok.append(s.id)
        elif got is None:
            (amb if tier_of(s.name, [s.country])[0].startswith("ambiguous") else nohit).append(s.id)
        else:
            wrong.append((s.id, s.name, got, by_id[got].name))
    return {
        "gate1_correct_assignments": len(correct), "gate1_altered": len(altered),
        "gate2_states": len(states), "gate2_self_resolve": len(self_ok),
        "gate2_ambiguous_drops": len(amb), "gate2_no_hit": len(nohit), "gate2_wrong_entity": len(wrong),
        "gate2_wrong_examples": wrong[:10],
        "gate2_ambiguous": [f"{by_id[i].name} ({cid2name[by_id[i].country]})" for i in amb],
    }


def merged() -> dict:
    """Repair-only rebuild of every merged entity with a conflicted member, using
    MinMod's own from_sites / from_dedup_sites (as investigation/p2_merged.py)."""
    sys.argv = sys.argv[:1] + [str(ROOT / "kgdata-p2/data")]
    sys.path.insert(0, str(ROOT / "investigation"))
    import serde.json
    from minmodkg.misc.utils import group_by
    from minmodkg.models.kgrel.dedup_mineral_site import DedupMineralSite
    from minmodkg.models.kgrel.mineral_site import MineralSiteAndInventory

    KG = ROOT / "kgdata-p2/data"

    def bad(sids, cids):
        return [s for s in sids if idx.conflicts(s, cids)]

    kg = serde.json.deser(KG / "mineral-sites/kgrel/dedup_sites.json.lz4")
    base = {d["id"]: d for d in kg["DedupMineralSite"]}
    del kg
    before = {i for i, d in base.items() if bad(d["state_or_province"]["value"], d["country"]["value"])}
    files = sorted(glob.glob(str(KG / "mineral-sites/merged/*/*.json*")))
    affected: set[str] = set()
    for f in files:
        for x in serde.json.deser(f)["MineralSiteAndInventory"]:
            lv = x["ms"].get("location_view") or {}
            if bad(lv.get("state_or_province", []), lv.get("country", [])):
                affected.add(x["ms"]["dedup_site_id"])
    per_file = {}
    for f in files:
        keep = [x for x in serde.json.deser(f)["MineralSiteAndInventory"] if x["ms"]["dedup_site_id"] in affected]
        if keep:
            per_file[f] = keep

    def rebuild(apply: bool) -> dict[str, dict]:
        partials = collections.defaultdict(list)
        id2site = {}
        for f, xs in per_file.items():
            msis = [MineralSiteAndInventory.from_dict(x) for x in xs]
            for m in msis if apply else ():
                view, loc = m.ms.location_view, m.ms.location
                if loc is None or not view.state_or_province:
                    continue
                cands = [c for c in loc.state_or_province if c.normalized_uri is not None]
                assert len(cands) == len(view.state_or_province)
                new = [idx.repair(sid, c.observed_name, view.country)[1]
                       for sid, c in zip(view.state_or_province, cands)]
                view.state_or_province = [s for s in new if s is not None]
            for _, grp in group_by(msis, lambda s: s.ms.dedup_site_id).items():
                d = DedupMineralSite.from_dict(DedupMineralSite.from_sites(grp).dms.to_dict())
                partials[d.id].append(d)
            for m in msis:
                id2site[m.ms.site_id] = MineralSiteAndInventory.from_dict(m.to_dict())
        return {i: json.loads(json.dumps(DedupMineralSite.from_dedup_sites(
            lst, [id2site[r.site_id] for d in lst for r in d.ranked_sites], is_site_ranked=True).dms.to_dict()))
            for i, lst in partials.items()}

    check = rebuild(False)
    mism = [i for i, d in check.items()
            if any(d[k] != base[i][k] for k in ("country", "state_or_province"))]
    assert not mism, mism[:5]
    after = {**base, **rebuild(True)}
    outcome = collections.Counter()
    for i in before:
        d = after[i]
        if bad(d["state_or_province"]["value"], d["country"]["value"]):
            outcome["still conflicted"] += 1
        elif not d["state_or_province"]["value"]:
            outcome["fixed: state dropped (empty)"] += 1
        else:
            outcome["fixed: state repointed"] += 1
    n = len(before)
    return {
        "merged_entities": len(base),
        "conflicted_before": n,
        "harness_rebuilt": len(check), "harness_country_state_mismatches": len(mism),
        "outcome": {k: f"{v} ({pct(v, n)})" for k, v in outcome.most_common()},
        "conflicted_after": sum(1 for d in after.values() if bad(d["state_or_province"]["value"], d["country"]["value"])),
        "gate3_newly_conflicted": sum(1 for i in affected - before
                                      if bad(after[i]["state_or_province"]["value"], after[i]["country"]["value"])),
        "gate3_non_conflicted_state_changed": sum(1 for i in affected - before
                                                  if after[i]["state_or_province"] != base[i]["state_or_province"]),
        "still_conflicted": [{"id": i, "country": after[i]["country"], "state": after[i]["state_or_province"]}
                             for i in sorted(before) if bad(after[i]["state_or_province"]["value"],
                                                            after[i]["country"]["value"])],
    }


if __name__ == "__main__":
    what = sys.argv[1]
    res = {"records": records, "gates": gates, "merged": merged}[what]()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{what}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))
