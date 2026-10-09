"""Option A, investigation only: what the proposed dependency pairs would move.

Takes the record groups from p2d_dependency_scan.py and, for the proposed
(sovereign, dependency) pairs only, counts the records and the merged entities
they belong to in a local ETL output (run B: the code and table as they would
ship), with each entity's current country and state.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2d_option_a_impact.py <entities dir> <ETL workdir>

Writes reports/p2d/option_a_impact.json.
"""

from __future__ import annotations

import collections
import glob
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ENT_ARG, WORKDIR = sys.argv[1], Path(sys.argv[2])
sys.argv = sys.argv[:1] + [ENT_ARG]
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "investigation"))
import p2d_dependency_scan as scan  # noqa: E402

import serde.json  # noqa: E402

# (recorded sovereign, dependency named in the state field): the proposal
PAIRS = {
    ("France", "New Caledonia"),
    ("Denmark", "Greenland"),
    ("Australia", "Christmas Island"),
    ("United Kingdom", "Montserrat"),
    ("United Kingdom", "Cayman Islands"),
    ("United Kingdom", "Virgin Islands (British)"),
}


def main() -> None:
    files = sorted(glob.glob(str(scan.DATA / "mineral-sites/*/*/*.json")))
    with ProcessPoolExecutor() as ex:
        rows = [r for part, _ in ex.map(scan.scan, files, chunksize=8) for r in part]
    hit = [r for r in rows if (r["recorded"], r["target"]) in PAIRS]
    site2pair = {r["site_id"]: (r["recorded"], r["target"]) for r in hit}

    kg = serde.json.deser(WORKDIR / "data/mineral-sites/kgrel/dedup_sites.json.lz4")
    dms = {d["id"]: d for d in kg["DedupMineralSite"]}
    site2dedup = {}
    for d in kg["DedupMineralSite"]:
        for r in d["ranked_sites"]:
            site2dedup[r["site_id"]] = d["id"]
    missing = [s for s in site2pair if s not in site2dedup]

    per_pair = {}
    for pair in sorted(PAIRS):
        sites = {s for s, p in site2pair.items() if p == pair}
        ents = {site2dedup[s] for s in sites if s in site2dedup}
        countries = collections.Counter(
            " | ".join(scan.cid2name[c] for c in dms[e]["country"]["value"]) for e in ents)
        state_now = collections.Counter(
            "empty" if not dms[e]["state_or_province"]["value"] else
            " | ".join(scan.by_id[s].name for s in dms[e]["state_or_province"]["value"]) for e in ents)
        mixed = sum(1 for e in ents
                    if any(r["site_id"] not in sites for r in dms[e]["ranked_sites"]))
        per_pair[f"{pair[0]} -> {pair[1]}"] = {
            "records": len(sites),
            "today": dict(collections.Counter(r["today"] for r in hit if site2pair[r["site_id"]] == pair)),
            "merged_entities": len(ents),
            "merged_country_now": dict(countries.most_common()),
            "merged_state_now": dict(state_now.most_common()),
            "entities_with_other_members": mixed,
        }
    res = {
        "records": len(site2pair),
        "records_not_found_in_merged_output": len(missing),
        "merged_entities": len({site2dedup[s] for s in site2pair if s in site2dedup}),
        "per_pair": per_pair,
    }
    out = ROOT / "reports/p2d/option_a_impact.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
