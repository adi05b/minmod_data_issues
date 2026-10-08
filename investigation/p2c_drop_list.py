"""Problem 2, alias pass, step 1: reproduce the drop list.

Every state candidate whose state sits in a country other than the one recorded
on the same record is run through the repair, using the code on
fix/p2-state-repair (minmodkg.misc.state_repair, index built from the table by
MinMod's own reader, exactly as FileEntityService feeds the merge). The ones
that still resolve to nothing are grouped by (observed name, recorded country).

Records come from the same scan as Part A (investigation/p2_records.py:
LocationInfo.from_dict -> LocationView, MinMod's own code). The result is
checked against Part B's run (reports/p2b/conflicted_outcomes.jsonl): same
6,158 conflicted candidates, same actions, same targets.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2c_drop_list.py [entities_dir]

Writes reports/p2c/drop_list.csv (one row per group) and
reports/p2c/drop_list.json (the totals).
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
OUT = ROOT / "reports/p2c"

sys.argv = sys.argv[:1] + [str(DATA)]
sys.path.insert(0, str(ROOT / "investigation"))
from p2_records import scan  # noqa: E402

from minmodkg.etl.kgrel_entity import EntityDeserFn  # noqa: E402
from minmodkg.misc.state_repair import StateCountryIndex  # noqa: E402

countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
cid2name = {c["minmod_id"]: c["name"] for c in countries}
states = EntityDeserFn.read_state_or_province(ENT / "state_or_province.csv")
aliases = EntityDeserFn.read_state_or_province_aliases(ENT / "state_or_province.csv")
by_id = {s.id: s for s in states}
idx = StateCountryIndex.build(states, aliases)


def run() -> list[dict]:
    files = sorted(glob.glob(str(DATA / "mineral-sites/*/*/*.json")))
    with ProcessPoolExecutor() as ex:
        rows = [r for part in ex.map(scan, files, chunksize=8) for r in part]
    conf = []
    for r in rows:
        cs = list(dict.fromkeys(r["countries"]))
        if not idx.conflicts(r["state"], cs):
            continue
        r["cs"] = cs
        r["action"], r["new"] = idx.repair(r["state"], r["observed_name"], cs)
        conf.append(r)
    return rows, conf


def main() -> None:
    rows, conf = run()
    drops = [r for r in conf if r["action"] == "drop"]

    # Part B's outcomes, candidate by candidate
    prev = [json.loads(l) for l in open(ROOT / "reports/p2b/conflicted_outcomes.jsonl", encoding="utf-8")]
    key = lambda r: (r["site_id"], r["state"], r["observed_name"])  # noqa: E731
    same_as_part_b = sorted((key(r), r["action"], r["new"]) for r in conf) == sorted(
        (key(r), r["action"], r["new"]) for r in prev
    )

    groups: dict[tuple[str, str], dict] = {}
    for r in drops:
        g = groups.setdefault(
            (r["observed_name"] or "", " | ".join(cid2name[c] for c in r["cs"])),
            {"records": set(), "candidates": 0, "stored": collections.Counter()},
        )
        g["records"].add(r["site_id"])
        g["candidates"] += 1
        s = by_id[r["state"]]
        g["stored"][f"{s.id} {s.name} ({cid2name[s.country]})"] += 1

    OUT.mkdir(parents=True, exist_ok=True)
    ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]["records"]), kv[0]))
    with open(OUT / "drop_list.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["observed_name", "recorded_country", "records", "candidates", "stored_state"])
        for (obs, country), g in ordered:
            w.writerow([obs, country, len(g["records"]), g["candidates"],
                        "; ".join(k for k, _ in g["stored"].most_common())])
    totals = {
        "entities_dir": str(ENT),
        "aliases_in_table": sum(len(v) for v in aliases.values()),
        "state_candidates": len(rows),
        "conflicted_candidates": len(conf),
        "conflicted_records": len({r["site_id"] for r in conf}),
        "repointed_candidates": sum(r["action"] == "repoint" for r in conf),
        "dropped_candidates": len(drops),
        "dropped_records": len({r["site_id"] for r in drops}),
        "drop_groups": len(groups),
        "same_outcomes_as_part_b": same_as_part_b,
    }
    json.dump(totals, open(OUT / "drop_list.json", "w"), indent=2)
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
