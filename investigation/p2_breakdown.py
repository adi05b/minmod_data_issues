"""Problem 2, Part A: why records conflict, and why the rule drops some.

Reads reports/p2/conflicted_candidates.jsonl (from p2_records.py). Same index as
reference/verify.py; the ProcMine table is verify.py's model of it, which matches
ProcMine's own compile_entities (4,967 keys, same unreachable set).

    python3 investigation/p2_breakdown.py
"""

from __future__ import annotations

import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))
from state_repair import StateCountryIndex, drop_admin_words, fold_name  # noqa: E402

ENT = ROOT / "data-p2/data/entities"
countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
cname2id = {c["name"]: c["minmod_id"] for c in countries}
cid2name = {c["minmod_id"]: c["name"] for c in countries}
raw = list(csv.DictReader(open(ENT / "state_or_province.csv", newline="", encoding="utf-8")))


class S:
    def __init__(self, r):
        self.id, self.name, self.country = r["minmod_id"], r["name"], cname2id[r["country_name"]]
        self.code = r["state_code"]


states = [S(r) for r in raw]
by_id = {s.id: s for s in states}
idx = StateCountryIndex.build(states)
pm: dict[str, str] = {}
for s in states:  # verify.py's ProcMine table
    pm.setdefault(s.name.lower(), s.id)

rows = [json.loads(l) for l in open(ROOT / "reports/p2/conflicted_candidates.jsonl", encoding="utf-8")]


def mechanism(r) -> str:
    obs, sid = r["observed_name"] or "", r["state"]
    if r["source"] == "UMN Matching System-ProcMinev2":
        key = re.sub(r"[0-9]\s", "", obs.lower())  # identify_entity_id's normalisation
        if pm.get(key) == sid:
            return "ProcMine exact key, shadowed (same name, first country in file order)"
        return "ProcMine fuzzy fallback (no exact key; best score worldwide, no floor)"
    if fold_name(obs) == fold_name(by_id[sid].name):
        return f"{r['source']}: same name, other country"
    return f"{r['source']}: different name"


def tier_hits(obs: str | None, cids: list[str]) -> tuple[int, int]:
    if not obs:
        return (0, 0)
    f = fold_name(obs)
    exact = {h for c in cids for h in idx._exact.get(c, {}).get(f, ())}
    folded = {h for c in cids for h in idx._folded.get(c, {}).get(drop_admin_words(f), ())}
    return len(exact), len(folded)


def drop_reason(r) -> str:
    if not r["observed_name"]:
        return "no observed_name"
    e, f = tier_hits(r["observed_name"], r["countries"])
    if e > 1 or (e == 0 and f > 1):
        return "ambiguous inside the country"
    code = r["observed_name"].strip().upper()
    if any(s.code.upper() == code and s.country in r["countries"] for s in states):
        return "state code (e.g. 'CO'), not a name"
    return "no state of that name in the country"


out = {"conflicted_candidates": len(rows)}
out["mechanism"] = dict(collections.Counter(mechanism(r) for r in rows).most_common())
drops = [r for r in rows if r["action"] == "drop"]
out["drops"] = len(drops)
out["drop_reason"] = dict(collections.Counter(drop_reason(r) for r in drops).most_common())
tops = collections.Counter(
    (r["observed_name"], "|".join(cid2name[c] for c in dict.fromkeys(r["countries"])), drop_reason(r))
    for r in drops
)
out["top_drops"] = [{"records": n, "observed_name": o, "country": c, "reason": why}
                    for (o, c, why), n in tops.most_common(25)]
(ROOT / "reports/p2/breakdown.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
print(json.dumps(out, indent=2, ensure_ascii=False))
