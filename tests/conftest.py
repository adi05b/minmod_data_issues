"""Shared data loading. Reads the client spreadsheets from data/ and the raw
source WKT from a read-only sparse checkout of ta2-minmod-data (upstream-data/)."""

from __future__ import annotations

import glob
import json
import os
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).parent.parent
os.environ.setdefault("CFG_FILE", str(ROOT / "upstream/tests/resources/config.yml"))

RAW_DIR = ROOT / "upstream-data/data/mineral-sites/umn"
RAW_SOURCES = [
    "utah_mineral_occurrence_system",
    "oregon_department_geology_mineral_industries",
    "ardf",
]

# lon_min, lat_min, lon_max, lat_max (state extents, rounded outward by ~0.01 deg)
STATE_BBOX = {
    "Oregon": (-124.71, 41.98, -116.45, 46.30),
    "Utah": (-114.06, 36.99, -109.03, 42.01),
}


@lru_cache(maxsize=None)
def raw_records() -> dict[str, dict]:
    """site_id -> {wkt, crs, state} from the raw JSON that the ETL reads."""
    from minmodkg.models.kg.mineral_site import MineralSiteIdent

    out = {}
    for src in RAW_SOURCES:
        for f in glob.glob(str(RAW_DIR / src / "*.json")):
            for r in json.load(open(f)):
                li = r.get("location_info") or {}
                out[MineralSiteIdent.from_dict(r).id] = {
                    "wkt": li.get("location"),
                    "crs": (li.get("crs") or {}).get("observed_name"),
                    "state": [s["observed_name"] for s in li.get("state_or_province", [])],
                }
    return out


@lru_cache(maxsize=None)
def load_p1() -> pd.DataFrame:
    df = pd.read_excel(ROOT / "data/coord_out_of_range.xlsx")
    raw = raw_records()
    df["raw_wkt"] = df.refid.map(lambda i: raw.get(i, {}).get("wkt"))
    df["raw_crs"] = df.refid.map(lambda i: raw.get(i, {}).get("crs"))
    df["raw_state"] = df.refid.map(lambda i: (raw.get(i, {}).get("state") or [None])[0])
    return df


@lru_cache(maxsize=None)
def load_p4() -> pd.DataFrame:
    return pd.read_csv(ROOT / "data/nad27_stored_as_wgs84.csv")


def in_state(state: str, lon: float, lat: float) -> bool:
    x0, y0, x1, y1 = STATE_BBOX[state]
    return x0 <= lon <= x1 and y0 <= lat <= y1


@pytest.fixture(scope="session")
def p1():
    return load_p1()


@pytest.fixture(scope="session")
def p4():
    return load_p4()
