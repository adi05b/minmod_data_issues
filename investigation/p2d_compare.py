"""Phase 5, merged entities: compare the merged tables of local ETL runs.

Three runs of investigation/p2_etl.yml (p2_run_etl.py), each in a fresh workdir:

  base  ta2-minmod-kg 83f9b7b (no repair), data 3a086a5      (Part B's baseline)
  A     ta2-minmod-kg a888391 (repair + aliases code), data 3a086a5
  B     ta2-minmod-kg a888391, data = fork branch add-niamey-ekaterinburg
        (Niamey, Zacapa, 53 alt names)

base vs A must reproduce Part B (5,856 conflicted -> 5,185 repointed, 671
emptied): without the column the alias code is inert. A vs B is the effect of
the approved aliases and new rows: only entities whose emptied state comes
back may change, and no country may change.

A merged entity is conflicted when one of its states belongs to none of its
countries (the acceptance-query definition). Conflicts are judged with the
index of the code under test over the new table, which only adds rows.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2d_compare.py <entities dir> <base> <A> <B>

Writes reports/p2d/merged.json.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import serde.json
from minmodkg.etl.kgrel_entity import EntityDeserFn
from minmodkg.misc.state_repair import StateCountryIndex

ROOT = Path(__file__).resolve().parent.parent
ENT, BASE, RUN_A, RUN_B = map(Path, sys.argv[1:5])

states = EntityDeserFn.read_state_or_province(ENT / "state_or_province.csv")
idx = StateCountryIndex.build(states)
names = {s.id: s.name for s in states}


def load(workdir: Path) -> dict[str, dict]:
    kg = serde.json.deser(workdir / "data/mineral-sites/kgrel/dedup_sites.json.lz4")
    return {d["id"]: d for d in kg["DedupMineralSite"]}


def bad(d) -> bool:
    return any(idx.conflicts(s, d["country"]["value"]) for s in d["state_or_province"]["value"])


def outcome(d) -> str:
    if bad(d):
        return "still conflicted"
    return "state emptied" if not d["state_or_province"]["value"] else "state repointed"


def main() -> None:
    base, a, b = load(BASE), load(RUN_A), load(RUN_B)
    assert base.keys() == a.keys() == b.keys(), "different merged entity sets"
    conflicted = {i for i, d in base.items() if bad(d)}

    res = {
        "merged_entities": len(base),
        "conflicted_in_base": len(conflicted),
        "base_to_A": dict(collections.Counter(outcome(a[i]) for i in conflicted).most_common()),
        "base_to_B": dict(collections.Counter(outcome(b[i]) for i in conflicted).most_common()),
        "conflicted_anywhere": {"A": sum(map(bad, a.values())), "B": sum(map(bad, b.values()))},
    }

    # A -> B, every merged entity
    changes = collections.Counter()
    gained = collections.Counter()
    unexpected = []
    for i in base:
        sa, sb = a[i]["state_or_province"], b[i]["state_or_province"]
        ca, cb = a[i]["country"], b[i]["country"]
        if ca["value"] != cb["value"]:
            changes["country value changed"] += 1
            unexpected.append({"id": i, "why": "country", "A": ca["value"], "B": cb["value"]})
        if sa["value"] != sb["value"]:
            if not sa["value"] and sb["value"]:
                changes["state filled (was empty)"] += 1
                for s in sb["value"]:
                    gained[names.get(s, s)] += 1
            else:
                changes["state value changed otherwise"] += 1
                unexpected.append({"id": i, "why": "state", "A": sa["value"], "B": sb["value"]})
        elif sa["refid"] != sb["refid"] or ca["refid"] != cb["refid"]:
            changes["refid only changed"] += 1
        if bad(b[i]) and not bad(a[i]):
            changes["newly conflicted"] += 1
            unexpected.append({"id": i, "why": "conflict", "B": sb["value"]})
    res["A_to_B"] = dict(changes.most_common())
    res["A_to_B_states_gained"] = dict(gained.most_common())
    res["A_to_B_unexpected"] = unexpected[:20]
    res["emptied_of_the_conflicted"] = {
        "A": sum(1 for i in conflicted if outcome(a[i]) == "state emptied"),
        "B": sum(1 for i in conflicted if outcome(b[i]) == "state emptied"),
    }
    out = ROOT / "reports/p2d/merged.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
