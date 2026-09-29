"""Proof for Problems 1 and 4 against the real client spreadsheets.

Must be run with upstream/ on branch fix/reproject-always-xy."""

from __future__ import annotations

import numpy as np
import pyproj
import shapely
import shapely.wkt
from conftest import in_state
from minmodkg.misc import geo
from minmodkg.misc.geo import reproject_geometry, reproject_wkt
from shapely.geometry import Point


def xy(wkt: str) -> tuple[float, float]:
    p = shapely.wkt.loads(wkt)
    return p.x, p.y


# --- Test 1: Problem 1, swapped Oregon/Utah records --------------------------


def test_p1_all_records_have_raw_input(p1):
    missing = p1[p1.raw_wkt.isna()]
    assert list(missing.name_val) == ["Tagaung Taung"]
    assert (p1.dropna(subset=["raw_wkt"]).raw_crs == p1.dropna(subset=["raw_wkt"]).source_crs).all()
    assert p1.source_crs.value_counts().to_dict() == {
        "EPSG:2994": 17073, "EPSG:26912": 7744, "EPSG:4326": 1,
    }


def test_p1_fixed_latitude_in_range_and_inside_named_state(p1):
    rows = p1.dropna(subset=["raw_wkt"])
    bad_lat, outside = [], []
    for r in rows.itertuples():
        lon, lat = xy(reproject_wkt(r.raw_wkt, r.raw_crs, "EPSG:4326"))
        if not -90 <= lat <= 90:
            bad_lat.append(r.refid)
        if not in_state(r.raw_state, lon, lat):
            outside.append((r.refid, r.raw_state, lon, lat))
    assert len(rows) == 24817
    assert bad_lat == []
    assert outside == []


def test_p1_fixed_output_is_old_stored_value_unswapped(p1):
    """The old stored (lat, lon) were the right numbers in the wrong slots."""
    rows = p1.dropna(subset=["raw_wkt"])
    for r in rows.itertuples():
        lon, lat = xy(reproject_wkt(r.raw_wkt, r.raw_crs, "EPSG:4326"))
        assert np.isclose(lon, r.stored_lat, atol=1e-6), r.refid
        assert np.isclose(lat, r.stored_lon, atol=1e-6), r.refid


def test_p1_tagaung_taung_swapped_at_source_is_not_fixed(p1):
    """KNOWN MANUAL FIX: EPSG:4326 record, swapped in the source data itself.
    The early return means this change never touches it."""
    r = p1[p1.name_val == "Tagaung Taung"].iloc[0]
    assert r.source_crs == "EPSG:4326"
    wkt = f"POINT ({r.stored_lon} {r.stored_lat})"  # as stored: x=lat, y=lon
    assert reproject_wkt(wkt, "EPSG:4326", "EPSG:4326") == wkt
    assert not -90 <= r.stored_lat <= 90


# --- Test 2: Problem 4, NAD27 Alaska records ---------------------------------


def test_p4_fixed_records_move_toward_nadcon(p4):
    geod = pyproj.Geod(ellps="WGS84")
    before, after = [], []
    for r in p4.itertuples():
        x0, y0 = xy(r.raw_coordinates_as_received)
        x1, y1 = xy(reproject_wkt(r.raw_coordinates_as_received, "EPSG:4267", "EPSG:4326"))
        before.append(geod.inv(x0, y0, r.corrected_lon_wgs84, r.corrected_lat_wgs84)[2])
        after.append(geod.inv(x1, y1, r.corrected_lon_wgs84, r.corrected_lat_wgs84)[2])
    before, after = np.array(before), np.array(after)
    assert len(p4) == 7720
    assert round(float(np.median(before)), 1) == 126.5  # matches the client's shift_m
    # without grids PROJ uses Helmert/Molodensky ops; with grids it uses NADCON.
    # Both must be far better than doing nothing.
    assert np.median(after) < 10
    assert (after < before).mean() > 0.99


# --- Test 3: regression ------------------------------------------------------


def test_epsg4326_passthrough_is_bit_identical(p1):
    r = p1[p1.source_crs == "EPSG:4326"].iloc[0]
    wkt = f"POINT ({r.stored_lon!r} {r.stored_lat!r})"
    assert reproject_wkt(wkt, "EPSG:4326", "EPSG:4326") is wkt
    g = Point(r.stored_lon, r.stored_lat)
    assert reproject_geometry(g, "EPSG:4326", "EPSG:4326") is g


def test_reproject_geometry_caches_one_transformer(monkeypatch):
    built = []
    real = pyproj.Transformer.from_crs

    def counting(*a, **kw):
        built.append((a, kw))
        return real(*a, **kw)

    monkeypatch.setattr(geo.Transformer, "from_crs", counting)
    monkeypatch.setattr(geo, "_transformation", {})
    reproject_geometry(Point(337936, 4506676), "EPSG:26912", "EPSG:4326")
    reproject_geometry(Point(337000, 4506000), "EPSG:26912", "EPSG:4326")
    assert len(built) == 1
    assert built[0][1] == {"always_xy": True}
