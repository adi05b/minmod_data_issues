"""Problem 2, Part B: compare the merged entities of two local ETL outputs.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2b_compare.py kgdata-p2 kgdata-p2-after [label]

Used twice: baseline vs a second baseline run (run-to-run noise from statickg's
unordered executor), and baseline vs the patched pipeline (gate 3). A merged
entity is conflicted when one of its states belongs to none of its countries
(the acceptance-query definition). Entities are also split by whether any
member record is itself conflicted: the state repair can only reach those, so a
change anywhere else comes from the election (B3) or from noise.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import serde.json

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "investigation"))
_argv, sys.argv = sys.argv, sys.argv[:1]
from p2b_measure import cid2name, idx, pct  # noqa: E402

sys.argv = _argv


def load(workdir: str):
    kg = serde.json.deser(ROOT / workdir / "data/mineral-sites/kgrel/dedup_sites.json.lz4")
    dms = {d["id"]: d for d in kg["DedupMineralSite"]}
    views = {s["site_id"]: s.get("location_view") or {} for s in kg["MineralSite"]}
    return dms, views


def bad(d) -> bool:
    return any(idx.conflicts(s, d["country"]["value"]) for s in d["state_or_province"]["value"])


def main(a: str, b: str, label: str) -> dict:
    A, va = load(a)
    B, vb = load(b)
    assert A.keys() == B.keys(), "different merged entity sets"
    # members that are conflicted at record level, in the BEFORE output
    has_bad_member = {
        i for i, d in A.items()
        if any(any(idx.conflicts(s, va.get(r["site_id"], {}).get("country", []))
                   for s in va.get(r["site_id"], {}).get("state_or_province", []))
               for r in d["ranked_sites"])
    }
    before = {i for i, d in A.items() if bad(d)}
    out = collections.Counter()
    for i in before:
        d = B[i]
        out["still conflicted" if bad(d) else
            "fixed: state dropped (empty)" if not d["state_or_province"]["value"] else
            "fixed: state repointed"] += 1
    ch = collections.Counter()
    examples = collections.defaultdict(list)
    for i in A.keys() - before:
        reach = "repair-reachable" if i in has_bad_member else "election-only"
        sv = A[i]["state_or_province"]["value"] != B[i]["state_or_province"]["value"]
        cv = A[i]["country"]["value"] != B[i]["country"]["value"]
        sr = A[i]["state_or_province"]["refid"] != B[i]["state_or_province"]["refid"]
        cr = A[i]["country"]["refid"] != B[i]["country"]["refid"]
        if bad(B[i]):
            ch[f"newly conflicted ({reach})"] += 1
        if sv:
            ch[f"state value changed ({reach})"] += 1
            if len(examples[reach]) < 8:
                examples[reach].append({
                    "id": i,
                    "country": [A[i]["country"]["value"], B[i]["country"]["value"]],
                    "state": [A[i]["state_or_province"]["value"], B[i]["state_or_province"]["value"]],
                    "country_names_after": [cid2name.get(c, c) for c in B[i]["country"]["value"]],
                })
        if cv:
            ch[f"country value changed ({reach})"] += 1
        if (sr or cr) and not (sv or cv):
            ch[f"refid only changed ({reach})"] += 1
    n = len(before)
    res = {
        "label": label, "before": a, "after": b,
        "merged_entities": len(A),
        "conflicted_before": n,
        "conflicted_after": sum(1 for d in B.values() if bad(d)),
        "outcome_of_conflicted": {k: f"{v} ({pct(v, n)})" for k, v in out.most_common()},
        "non_conflicted_entities": len(A) - n,
        "changes_on_non_conflicted": dict(ch.most_common()),
        "examples_state_value_changed": dict(examples),
        "still_conflicted": [{"id": i, "country": [cid2name.get(c, c) for c in B[i]["country"]["value"]],
                              "state": B[i]["state_or_province"]["value"],
                              "country_refid": B[i]["country"]["refid"], "state_refid": B[i]["state_or_province"]["refid"]}
                             for i in sorted(before) if bad(B[i])],
    }
    out_dir = ROOT / "reports/p2b"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"compare_{label}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return res


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:3], sys.argv[3] if len(sys.argv) > 3 else "compare"), indent=2, ensure_ascii=False))
