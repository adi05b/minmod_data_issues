"""Problem 2, alias pass, Phase 5: measure the approved aliases and new rows.

before  the pristine table (data-p2 @ 3a086a5), no aliases: Part B's state.
after   the table on adi05b/ta2-minmod-data branch add-niamey-ekaterinburg
        (Niamey Q7085, Zacapa Q7086, 53 alt names), read with MinMod's own
        readers exactly as FileEntityService feeds the merge.

Both run the code on fix/p2-state-repair (minmodkg.misc.state_repair).

  records  every state candidate of every record (418,313): drops before and
           after, and any candidate whose outcome changes other than a drop
           turning into a repoint (must be 0)
  self     every state's own name in its own country, and every alias in its
           row's country: resolves to itself, to nothing, or to another
           entity (must be 0)

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2d_measure.py <after entities dir> records|self

Writes reports/p2d/<what>.json.
"""

from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AFTER = Path(sys.argv[1])
WHAT = sys.argv[2]
sys.argv = sys.argv[:1]
sys.path.insert(0, str(ROOT / "investigation"))
import p2c_alias_candidates as ac  # noqa: E402
import p2c_drop_list as dl  # noqa: E402

from minmodkg.etl.kgrel_entity import EntityDeserFn  # noqa: E402
from minmodkg.misc.state_repair import StateCountryIndex, drop_admin_words, fold_name  # noqa: E402

OUT = ROOT / "reports/p2d"

before_states, before_idx = dl.states, dl.idx
assert dl.aliases == {}, "the before table must have no aliases"
after_states = EntityDeserFn.read_state_or_province(AFTER / "state_or_province.csv")
after_aliases = EntityDeserFn.read_state_or_province_aliases(AFTER / "state_or_province.csv")
after_idx = StateCountryIndex.build(after_states, after_aliases)
after_by_id = {s.id: s for s in after_states}
cid2name = dl.cid2name


def key_of(r) -> tuple[str, str]:
    return (r["observed_name"] or "", " | ".join(cid2name[c] for c in r["cs"]))


def records() -> dict:
    rows, _ = dl.run()
    # the new table only adds rows: every old row is unchanged
    assert all(after_by_id[s.id].to_dict() == s.to_dict() for s in before_states)
    new_ids = set(after_by_id) - {s.id for s in before_states}

    changed, transitions = [], collections.Counter()
    drops_before, drops_after = [], []
    how = collections.Counter()
    for r in rows:
        cs = list(dict.fromkeys(r["countries"]))
        r["cs"] = cs
        b = before_idx.repair(r["state"], r["observed_name"], cs)
        a = after_idx.repair(r["state"], r["observed_name"], cs)
        transitions[(b[0], a[0])] += 1
        if b[0] == "drop":
            drops_before.append(r)
        if a[0] == "drop":
            drops_after.append(r)
        if b != a:
            if b[0] == "drop" and a[0] == "repoint":
                key = key_of(r)
                if a[1] in new_ids:
                    how[f"new row {a[1]} {after_by_id[a[1]].name}"] += 1
                elif a[1] in after_aliases:
                    how["alias"] += 1
                    assert any(fold_name(x) == fold_name(r["observed_name"] or "")
                               for x in after_aliases[a[1]]), (key, a)
                else:
                    raise AssertionError(("repointed by neither", key, a))
            else:
                changed.append({"site_id": r["site_id"], "before": b, "after": a})

    groups_after = collections.Counter(key_of(r) for r in drops_after)
    proposed = {k for k in ac.PROPOSALS}
    left = collections.Counter()
    for k, n in groups_after.items():
        if k in ac.BLOCKED:
            left["blocked"] += n
        elif k in ac.NO_SUGGESTION or k in ac.REJECTED_ON_COORDINATES:
            left["no suggestion"] += n
        else:
            left[f"unexpected: {k}"] += n
    assert not any(k in proposed for k in groups_after), "a proposed group still drops"
    return {
        "after_entities": str(AFTER),
        "after_table": {"rows": len(after_states), "new_rows": sorted(new_ids),
                        "rows_with_aliases": len(after_aliases),
                        "alias_values": sum(len(v) for v in after_aliases.values())},
        "state_candidates": len(rows),
        "records_with_a_state": len({r["site_id"] for r in rows}),
        "conflicted_candidates": sum(1 for r in rows if before_idx.conflicts(r["state"], r["cs"])),
        "dropped": {
            "before": {"candidates": len(drops_before), "records": len({r["site_id"] for r in drops_before})},
            "after": {"candidates": len(drops_after), "records": len({r["site_id"] for r in drops_after})},
        },
        "recovered": dict(how.most_common()),
        "after_drops_by_kind": dict(left.most_common()),
        "transitions_before_to_after": {f"{b} -> {a}": n for (b, a), n in sorted(transitions.items())},
        "changed_other_than_drop_to_repoint": len(changed),
        "changed_examples": changed[:10],
    }


def self_check() -> dict:
    res = {}
    for label, states, idx, aliases in (
        ("before", before_states, before_idx, {}),
        ("after", after_states, after_idx, after_aliases),
    ):
        by_id = {s.id: s for s in states}
        out = collections.Counter()
        wrong = []
        none_names = []
        for s in states:
            got = idx.resolve(s.name, [s.country])
            if got == s.id:
                out["itself"] += 1
            elif got is None:
                out["nothing"] += 1
                none_names.append(f"{s.name} ({cid2name[s.country]})")
            else:
                out["another entity"] += 1
                wrong.append((s.id, s.name, got, by_id[got].name))
        alias_out = collections.Counter()
        for sid, names in aliases.items():
            for n in names:
                got = idx.resolve(n, [by_id[sid].country])
                alias_out["itself" if got == sid else "nothing" if got is None else "another entity"] += 1
        res[label] = {
            "states": len(states),
            "own_name": dict(out),
            "own_name_to_another_entity": wrong,
            "own_name_to_nothing": sorted(none_names),
            "aliases": dict(alias_out),
        }
    # nothing that found itself before may stop finding itself
    lost = [s.id for s in before_states
            if before_idx.resolve(s.name, [s.country]) == s.id
            and after_idx.resolve(s.name, [s.country]) != s.id]
    res["found_itself_before_but_not_after"] = lost
    return res


if __name__ == "__main__":
    res = {"records": records, "self": self_check}[WHAT]()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{WHAT}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False)[:4000])
