"""Problem 2, Part A: merged-entity measurements (A3, and A2 at the merged level).

Merged rows live in Postgres (kgrel), which this run cannot reach. Instead this
reads a local ETL output built from the same pinned data by p2_run_etl.py
(kgdata-p2/), i.e. the exact JSON the ETL hands to the Postgres loader.

1. A3 on the ETL's own rows: for every merged entity whose state's country is in
   none of the entity's countries, compare country.refid with state_or_province.refid.
2. The repair, simulated: each site's location_view is repaired in memory with the
   reference rule, then the merged rows are rebuilt with MinMod's own
   DedupMineralSite.from_sites (per bucket file, as MergeFn does) and
   from_dedup_sites (across files, as prep_kgrel_input does). Only merged entities
   with at least one record-level-conflicted member can change, so only those are
   rebuilt. Mode "none" rebuilds them with the repair off and must reproduce the
   ETL's rows exactly; that checks the harness. No upstream file is modified.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2_merged.py kgdata-p2/data
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import serde.json
from minmodkg.misc.utils import group_by
from minmodkg.models.kgrel.dedup_mineral_site import DedupMineralSite
from minmodkg.models.kgrel.mineral_site import MineralSiteAndInventory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))
from state_repair import StateCountryIndex  # noqa: E402

KG = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "kgdata-p2/data")
ENT = ROOT / "data-p2/data/entities"
OUT = ROOT / "reports/p2"


@dataclass
class S:  # same shape as reference/verify.py
    id: str
    name: str
    country: Optional[str]


countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
cname2id = {c["name"]: c["minmod_id"] for c in countries}
states = [
    S(r["minmod_id"], r["name"], cname2id[r["country_name"]])
    for r in csv.DictReader(open(ENT / "state_or_province.csv", newline="", encoding="utf-8"))
]
by_id = {s.id: s for s in states}
idx = StateCountryIndex.build(states)


def repair(state_id, observed_name, country_ids):
    """reference/verify.py's repair(), verbatim."""
    if not idx.conflicts(state_id, country_ids):
        return ("keep", state_id)
    fixed = idx.resolve(observed_name, country_ids)
    return ("repoint", fixed) if fixed else ("drop", None)


def bad_states(state_ids, country_ids) -> list[str]:
    return [s for s in state_ids if idx.conflicts(s, country_ids)]


def repair_view(msi: MineralSiteAndInventory, fallback: bool) -> None:
    """Apply the rule per state candidate to ms.location_view, in memory."""
    ms = msi.ms
    view, loc = ms.location_view, ms.location
    if loc is None or not view.state_or_province:
        return
    cands = [c for c in loc.state_or_province if c.normalized_uri is not None]
    assert len(cands) == len(view.state_or_province), ms.site_id
    out = []
    for sid, cand in zip(view.state_or_province, cands):
        key = cand.observed_name
        if fallback and not (key and key.strip()):
            key = by_id[sid].name if sid in by_id else None
        act, new = repair(sid, key, view.country)
        if new is not None:
            out.append(new)
    view.state_or_province = list(dict.fromkeys(out))


def main():
    # ---------------- 1. the ETL's own merged rows ----------------
    kg = serde.json.deser(KG / "mineral-sites/kgrel/dedup_sites.json.lz4")
    dms_rows = {d["id"]: d for d in kg["DedupMineralSite"]}
    site_view = {
        s["site_id"]: s.get("location_view") or {} for s in kg["MineralSite"]
    }
    del kg

    def conflicted(d) -> bool:
        return bool(bad_states(d["state_or_province"]["value"], d["country"]["value"]))

    before = {i for i, d in dms_rows.items() if conflicted(d)}
    a3 = collections.Counter()
    a3_detail = collections.Counter()
    for i in before:
        d = dms_rows[i]
        c_ref, s_ref = d["country"]["refid"], d["state_or_province"]["refid"]
        if c_ref == s_ref:
            a3["same site (conflict asserted by one record: upstream)"] += 1
            continue
        a3["different sites (pairing invented by the merge)"] += 1
        sv = site_view.get(s_ref, {})
        own = sv.get("country", [])
        if not own:
            a3_detail["state's site records no country"] += 1
        elif bad_states(d["state_or_province"]["value"], own):
            a3_detail["state's site is itself conflicted"] += 1
        else:
            a3_detail["state's site is consistent with its own country"] += 1
        # could a "both from one site" election (B3) help? use the global site ranking
        both = [
            r["site_id"] for r in d["ranked_sites"]
            if site_view.get(r["site_id"], {}).get("country")
            and site_view.get(r["site_id"], {}).get("state_or_province")
        ]
        if not both:
            a3_detail["B3: no member site carries both country and state"] += 1
        else:
            top = site_view[both[0]]
            ok = not bad_states(top["state_or_province"], top["country"])
            a3_detail["B3: top site with both is consistent" if ok else
                      "B3: top site with both is itself conflicted"] += 1

    summary: dict = {
        "merged_entities": len(dms_rows),
        "merged_with_state": sum(1 for d in dms_rows.values() if d["state_or_province"]["value"]),
        "merged_conflicted_before": len(before),
        "a3_split": dict(a3),
        "a3_merge_invented_detail": dict(a3_detail),
    }

    # ---------------- 2. rebuild affected merged rows with the repair ----------------
    files = sorted(glob.glob(str(KG / "mineral-sites/merged/*/*.json*")))
    affected: set[str] = set()
    for f in files:
        for x in serde.json.deser(f)["MineralSiteAndInventory"]:
            lv = x["ms"].get("location_view") or {}
            if bad_states(lv.get("state_or_province", []), lv.get("country", [])):
                affected.add(x["ms"]["dedup_site_id"])
    per_file: dict[str, list[dict]] = {}
    for f in files:
        keep = [x for x in serde.json.deser(f)["MineralSiteAndInventory"]
                if x["ms"]["dedup_site_id"] in affected]
        if keep:
            per_file[f] = keep
    summary["merged_entities_with_a_conflicted_member"] = len(affected)
    summary["merged_conflicted_without_a_conflicted_member"] = len(before - affected)

    def rebuild(mode: str) -> dict[str, dict]:
        partials: dict[str, list[DedupMineralSite]] = collections.defaultdict(list)
        id2site: dict[str, MineralSiteAndInventory] = {}
        for f, xs in per_file.items():
            msis = [MineralSiteAndInventory.from_dict(x) for x in xs]
            if mode != "none":
                for m in msis:
                    repair_view(m, fallback=(mode == "repair+name_fallback"))
            # MergeFn.invoke: one DedupMineralSite per dedup id per bucket file, then serialised
            for _, grp in group_by(msis, lambda s: s.ms.dedup_site_id).items():
                dms = DedupMineralSite.from_dict(DedupMineralSite.from_sites(grp).dms.to_dict())
                partials[dms.id].append(dms)
            for m in msis:
                id2site[m.ms.site_id] = MineralSiteAndInventory.from_dict(m.to_dict())
        # prep_kgrel_input; then a JSON round trip, as the ETL writes JSON for the loader
        # (to_dict() can hold tuples that the ETL's file stores as lists)
        return {
            i: json.loads(json.dumps(DedupMineralSite.from_dedup_sites(
                lst, [id2site[r.site_id] for d in lst for r in d.ranked_sites], is_site_ranked=True
            ).dms.to_dict()))
            for i, lst in partials.items()
        }

    # Harness check. country/state (value AND refid) must match the ETL exactly.
    # Other fields may not: statickg's executor is Parallel(return_as="generator_unordered"),
    # so prep_kgrel_input sees bucket files in completion order, and ties between
    # equal-score partials / the dedup_sites[0] fallbacks depend on that order.
    base = rebuild("none")
    fields = ("country", "state_or_province")
    mismatched = [i for i, d in base.items() if any(d[k] != dms_rows[i][k] for k in fields)]
    other = collections.Counter(
        k for i, d in base.items() for k in d if k not in fields and d[k] != dms_rows[i][k]
    )
    summary["harness_check_rebuilt"] = len(base)
    summary["harness_check_country_state_mismatches"] = len(mismatched)
    summary["harness_check_order_dependent_field_mismatches"] = dict(other)
    assert not mismatched, mismatched[:5]

    for mode in ("repair", "repair+name_fallback"):
        after = {**dms_rows, **rebuild(mode)}
        outcome = collections.Counter()
        for i in before:
            d = after[i]
            if conflicted(d):
                outcome["still conflicted"] += 1
            elif not d["state_or_province"]["value"]:
                outcome["fixed: state dropped (empty)"] += 1
            else:
                outcome["fixed: state repointed"] += 1
        newly = [i for i in affected - before if conflicted(after[i])]
        changed_ok = sum(1 for i in affected - before
                         if after[i]["state_or_province"] != dms_rows[i]["state_or_province"])
        summary[f"after_{mode}"] = {
            "conflicted_before": len(before),
            "outcome_of_conflicted": dict(outcome),
            "merged_conflicted_after": sum(1 for d in after.values() if conflicted(d)),
            "newly_conflicted": len(newly),
            "non_conflicted_entities_whose_state_changed": changed_ok,
            "still_conflicted": [
                {"id": i, "country": after[i]["country"], "state_or_province": after[i]["state_or_province"],
                 "has_a_conflicted_member": i in affected}
                for i in sorted(before) if conflicted(after[i])
            ],
        }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "merged_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
