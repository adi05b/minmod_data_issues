"""Problem 2, B7: run acceptance/problem2_state_country_conflict.sql on a throwaway
local Postgres, loaded with a local ETL output through MinMod's own loader
(PostgresLoaderService.restore), and compare with the count computed in Python.

    initdb -D $PG -U postgres -E UTF8 --locale=C
    pg_ctl -D $PG -o "-p 54329 -k /tmp" start; createdb -h /tmp -p 54329 -U postgres acc
    CFG_FILE=upstream-p2/tests/resources/config.yml .venv-p2/bin/python \
      investigation/p2b_sql_check.py kgdata-p2-after "postgresql+psycopg://postgres@/acc?host=/tmp&port=54329" after
"""

from __future__ import annotations

import glob
import subprocess
import sys
from pathlib import Path

import serde.json
from minmodkg.etl.postgres import PostgresLoaderService
from minmodkg.models.kgrel.base import Base
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "investigation"))
_argv, sys.argv = sys.argv, sys.argv[:1]
from p2b_compare import bad  # noqa: E402

sys.argv = _argv

workdir, dsn, label = sys.argv[1], sys.argv[2], sys.argv[3]
engine = create_engine(dsn)
Base.metadata.create_all(engine)
tables: dict[str, list] = {}
for f in glob.glob(str(ROOT / workdir / "data/entities/*.json")):
    for cls, records in serde.json.deser(f).items():
        if cls in ("Country", "StateOrProvince"):
            tables[cls] = records
kg = serde.json.deser(ROOT / workdir / "data/mineral-sites/kgrel/dedup_sites.json.lz4")
tables["DedupMineralSite"] = kg["DedupMineralSite"]
tables["MineralSite"] = kg["MineralSite"]
expected = sum(1 for d in kg["DedupMineralSite"] if bad(d))
del kg
PostgresLoaderService.restore(None, engine, tables)  # restore() does not use self

url = make_url(dsn)
sql = subprocess.run(
    ["psql", "-h", url.query["host"], "-p", str(url.query["port"]), "-U", url.username,
     "-d", url.database, "-v", "ON_ERROR_STOP=1",
     "-f", str(ROOT / "acceptance/problem2_state_country_conflict.sql")],
    capture_output=True, text=True, check=True,
).stdout
out = f"# {label}: {workdir}; Python count of conflicted merged entities = {expected}\n{sql}"
(ROOT / f"reports/p2b/sql_check_{label}.txt").write_text(out)
print(out)
