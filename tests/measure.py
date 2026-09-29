"""Measure P1/P4 behaviour of whatever commit is checked out in upstream/.

    python tests/measure.py <label>          -> reports/measure_<label>.json

Run once on the base commit (before) and once on the patched branch (after);
set PROJ_NETWORK=ON for the with-grid run. Uses the production code path
(reproject_geometry on the centroid, as LocationView.from_location does) and
cross-checks reproject_wkt against it."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pyproj
import shapely
import shapely.wkt

sys.path.insert(0, str(Path(__file__).parent))
from conftest import ROOT, in_state, load_p1, load_p4  # noqa: E402

from minmodkg.misc import geo  # noqa: E402


def to_wgs84(wkt: str, crs: str) -> tuple[float, float, str]:
    """Returns (lat, lon, wkt_out) exactly as the merged table would store them."""
    c = geo.reproject_geometry(shapely.centroid(shapely.wkt.loads(wkt)), crs, "EPSG:4326")
    return c.y, c.x, geo.reproject_wkt(wkt, crs, "EPSG:4326")


def pctl(a, q):
    return round(float(np.percentile(a, q)), 2)


def p1_metrics():
    df = load_p1()
    res = Counter()
    for r in df.itertuples():
        if r.raw_wkt is None:  # Tagaung Taung, EPSG:4326, not in the checked-out sources
            res["no_raw_input"] += 1
            res["no_raw_input_lat_valid"] += int(-90 <= r.stored_lat <= 90)
            continue
        lat, lon, wkt_out = to_wgs84(r.raw_wkt, r.raw_crs)
        res["n"] += 1
        res["crs_matches_sheet"] += r.raw_crs == r.source_crs
        res["lat_valid"] += -90 <= lat <= 90
        res["in_named_state"] += in_state(r.raw_state, lon, lat)
        res["reproduces_sheet_stored_values"] += bool(
            np.isclose(lat, r.stored_lat, atol=1e-6) and np.isclose(lon, r.stored_lon, atol=1e-6)
        )
        p = shapely.wkt.loads(wkt_out)
        res["wkt_path_agrees"] += bool(np.isclose(p.x, lon) and np.isclose(p.y, lat))
    return dict(res)


def p4_metrics():
    df = load_p4()
    geod = pyproj.Geod(ellps="WGS84")
    moved, dist, ops = [], [], Counter()
    for r in df.itertuples():
        lat, lon, _ = to_wgs84(r.raw_coordinates_as_received, "EPSG:4267")
        # the exact transformer the production path just used
        op = geo._transformation["EPSG:4267", "EPSG:4326"].get_last_used_operation()
        ops[f"{op.description} | accuracy={op.accuracy}"] += 1
        inp = shapely.wkt.loads(r.raw_coordinates_as_received)
        moved.append(not (lon == inp.x and lat == inp.y))
        dist.append(geod.inv(lon, lat, r.corrected_lon_wgs84, r.corrected_lat_wgs84)[2])
    dist = np.array(dist)
    return {
        "n": len(df),
        "moved": int(sum(moved)),
        "unmoved": int(len(moved) - sum(moved)),
        "err_vs_nadcon_m": {
            "median": pctl(dist, 50), "p90": pctl(dist, 90),
            "max": round(float(dist.max()), 2), "within_1m": int((dist < 1).sum()),
            "within_5m": int((dist < 5).sum()),
        },
        "operations_used": dict(ops.most_common()),
    }


if __name__ == "__main__":
    label = sys.argv[1]
    out = {
        "upstream_commit": subprocess.check_output(
            ["git", "-C", str(ROOT / "upstream"), "rev-parse", "HEAD"], text=True
        ).strip(),
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
        "proj_network": pyproj.network.is_network_enabled(),
        "p1": p1_metrics(),
        "p4": p4_metrics(),
    }
    (ROOT / f"reports/measure_{label}.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
