"""Problem 2, B5: what a fuzzy tier inside the recorded country would pick.

Not part of the fix. Uses ProcMine's own scorer (identify_entity_id: the mean of
six string similarities, exact key first), restricted to the states of the record's
country. Two columns: names folded first (state_repair.fold_name), which reproduces
the brief's table exactly, and ProcMine's own keys (lowercased, diacritics kept).

    PYTHONPATH=upstream-procmine uv run --no-project --python 3.11 \
      --with polars==1.19.0 --with "geopandas>=1.0.1,<2" --with "pyarrow>=18.1,<19" \
      --with "regex>=2024.11.6,<2025" --with "strsimpy>=0.2.1,<0.3" \
      --with "bs4>=0.0.2,<0.0.3" --with "requests>=2.32.3,<3" \
      python investigation/p2b_fuzzy_table.py data-p2/data/entities
"""

import csv
import sys
from pathlib import Path

from procmine.converting._entity import identify_entity_id

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reference"))
from state_repair import fold_name  # noqa: E402

ENT = Path(sys.argv[1])
rows = list(csv.DictReader(open(ENT / "state_or_province.csv", newline="", encoding="utf-8")))
name = {r["minmod_id"]: r["name"] for r in rows}

CASES = [
    ("Michoacan", "Mexico", "want"),
    ("Katanga", "Democratic Republic of the Congo", "one of four successors"),
    ("Valle D'Aosta", "Italy", "want"),
    ("Orissa", "India", "want"),
    ("Andalusia", "Spain", "wrong"),
    ("Elko County", "United States", "wrong"),
]
print(f"{'observed':<14}    {'best state in the recorded country':<21}  folded  raw     verdict")
for observed, country, verdict in CASES:
    out = []
    for key in (fold_name, str.lower):
        table: dict[str, str] = {}
        for r in rows:
            if r["country_name"] == country:
                table.setdefault(key(r["name"]), r["minmod_id"])
        out.append(identify_entity_id(observed_entity_name=key(observed), dict_entities=table))
    (sid, folded), (sid_raw, raw) = out
    assert sid == sid_raw
    print(f"{observed:<14} -> {name[sid]:<21}  {folded:.4f}  {raw:.4f}  {verdict}")
