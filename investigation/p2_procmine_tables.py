"""Problem 2, A0: ProcMine's own lookup tables, built by ProcMine's own code.

Runs procmine._utils.compile_entities (umn-ta2-database-processing @ ce1ed70) on the
MinMod state and country tables, then checks reference/verify.py's model of it.
ProcMine expects its own entity file names, so only the two relevant CSVs are copied
into a temporary folder. _selected_cols.pkl was first checked with pickletools: it has
no code-executing opcodes, so loading it only builds plain dicts and lists.

    PYTHONPATH=upstream-procmine uv run --no-project --python 3.11 \
      --with polars==1.19.0 --with "geopandas>=1.0.1,<2" --with "pyarrow>=18.1,<19" \
      --with "regex>=2024.11.6,<2025" --with "strsimpy>=0.2.1,<0.3" \
      --with "bs4>=0.0.2,<0.0.3" --with "requests>=2.32.3,<3" \
      python investigation/p2_procmine_tables.py data-p2/data/entities
"""

import csv
import pickle
import pickletools
import shutil
import sys
import tempfile
from pathlib import Path

from procmine._utils import compile_entities

ENT = Path(sys.argv[1])
PKL = Path("upstream-procmine/procmine/_entities/_selected_cols.pkl").read_bytes()
UNSAFE = {"GLOBAL", "STACK_GLOBAL", "REDUCE", "INST", "OBJ", "NEWOBJ", "NEWOBJ_EX", "BUILD",
          "EXT1", "EXT2", "EXT4"}
assert not {op.name for op, _, _ in pickletools.genops(PKL)} & UNSAFE
cols = pickle.loads(PKL)
print("_selected_cols.pkl:", cols)

with tempfile.TemporaryDirectory() as tmp:
    for f in ("state_or_province.csv", "country.csv"):
        shutil.copy(ENT / f, tmp)
    d = compile_entities(tmp, cols)

states = list(csv.DictReader(open(ENT / "state_or_province.csv", newline="", encoding="utf-8")))
countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
sp, co = d["state_or_province"], d["country"]
print("state_or_province: keys", len(sp), "| rows", len(states),
      "| unreachable ids", len({s["minmod_id"] for s in states} - set(sp.values())))
print("  florida ->", sp.get("florida"), "| Q6850 reachable:", "Q6850" in set(sp.values()))
print("country: keys", len(co), "| rows", len(countries),
      "| unreachable ids", len({c["minmod_id"] for c in countries} - set(co.values())))
wrong = [c["name"] for c in countries if co.get(c["name"].lower()) != c["minmod_id"]]
print("  primary names resolving to another country:", len(wrong), wrong[:10])

pm = {}
for s in states:  # reference/verify.py's model of ProcMine's table
    pm.setdefault(s["name"].lower(), s["minmod_id"])
print("ProcMine's real state table == verify.py's model:", sp == pm)
