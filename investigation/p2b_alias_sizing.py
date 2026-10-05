"""Problem 2, B6: how many of the records that still drop would a few alias rows recover?

Simulates alias rows by adding each alias as an extra name of an existing state
(same id, same country) and re-running every dropped record through the rule.
Reads reports/p2b/conflicted_outcomes.jsonl (from p2b_measure.py records).

    python3 investigation/p2b_alias_sizing.py
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "investigation"))
_argv, sys.argv = sys.argv, sys.argv[:1]
from p2b_measure import by_id, states  # noqa: E402
from state_repair import StateCountryIndex  # noqa: E402

sys.argv = _argv
ALIASES = {  # alias -> existing state id (name, country)
    "Orissa": "Q3657",  # Odisha, India
    "Niedersachsen": "Q3383",  # Lower Saxony, Germany
    "Attapu": "Q4059",  # Attapeu Province, Laos
    "Buryatiya": "Q5463",  # Republic of Buryatia, Russia
    "San Blas": "Q5071",  # Guna Yala, Panama (renamed 2011)
}
EXTRA = {"Karnten": "Q2215", "Steiermark": "Q2218"}  # Carinthia, Styria (Austria)

drops = [json.loads(l) for l in open(ROOT / "reports/p2b/conflicted_outcomes.jsonl", encoding="utf-8")]
drops = [r for r in drops if r["action"] == "drop"]
for label, aliases in (("5 alias rows", ALIASES), ("7 alias rows", {**ALIASES, **EXTRA})):
    idx = StateCountryIndex.build(states + [replace(by_id[i], name=a) for a, i in aliases.items()])
    hits = [idx.repair(r["state"], r["observed_name"], r["cs"]) for r in drops]
    rec = [(r, h) for r, h in zip(drops, hits) if h[0] == "repoint"]
    assert all(h[1] in aliases.values() for _, h in rec)
    print(f"{label}: {len(rec)} of {len(drops)} remaining drops recovered "
          f"({100 * len(rec) / len(drops):.1f}%)")
