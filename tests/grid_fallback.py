"""Problem 4: what if the image shipped only the Alaska grid?

    PROJ_NETWORK=ON  .venv-p2/bin/python tests/grid_fallback.py both       <out.json>
    PROJ_NETWORK=OFF .venv-p2/bin/python tests/grid_fallback.py alaska <dir> <out.json>
    .venv-p2/bin/python tests/grid_fallback.py compare <both.json> <alaska.json>

"both": every grid reachable (what the image does with us_noaa_alaska.tif and
ca_nrc_ntv2_0.tif). "alaska": network off and a data directory holding only
us_noaa_alaska.tif (fetched with `pyproj sync --file us_noaa_alaska.tif
--target-directory <dir>`), so PROJ picks whatever it can without the Canadian
grid. Each point records its result and the operation PROJ actually applied
(get_last_used_operation, not TransformerGroup[0]).
"""

import csv
import json
import statistics
import sys
from pathlib import Path

import pyproj
import shapely.wkt
from pyproj import Transformer

ROOT = Path(__file__).parent.parent
mode = sys.argv[1]

if mode in ("both", "alaska"):
    if mode == "alaska":
        assert not pyproj.network.is_network_enabled()
        pyproj.datadir.append_data_dir(sys.argv[2])
    out = sys.argv[-1]
    t = Transformer.from_crs(4267, 4326, always_xy=True)
    res = {}
    for r in csv.DictReader(open(ROOT / "data/nad27_stored_as_wgs84.csv", newline="", encoding="utf-8")):
        p = shapely.wkt.loads(r["raw_coordinates_as_received"])
        x, y = t.transform(p.x, p.y)
        res[r["site_id"]] = {"lon": x, "lat": y, "op": t.get_last_used_operation().description,
                             "ref": [float(r["corrected_lon_wgs84"]), float(r["corrected_lat_wgs84"])]}
    json.dump(res, open(out, "w"))
    print(mode, "| network:", pyproj.network.is_network_enabled(), "| points:", len(res))
else:
    both, alaska = (json.load(open(f)) for f in sys.argv[2:4])
    geod = pyproj.Geod(ellps="WGS84")

    def dist(a, b):
        return geod.inv(a["lon"], a["lat"], b["lon"], b["lat"])[2]

    canada = [k for k, v in both.items() if "(33)" in v["op"]]
    rest = [k for k in both if k not in canada]
    moved = [dist(both[k], alaska[k]) for k in canada]
    vs_ref = [geod.inv(alaska[k]["lon"], alaska[k]["lat"], *alaska[k]["ref"])[2] for k in canada]
    ops = {}
    for k in canada:
        ops[alaska[k]["op"]] = ops.get(alaska[k]["op"], 0) + 1
    q = statistics.quantiles(moved, n=10)
    print(f"points PROJ puts on ca_nrc_ntv2_0.tif when every grid is available: {len(canada)}")
    print(f"  with only us_noaa_alaska.tif, operations used: {ops}")
    print(f"  distance from the both-grids result: median {statistics.median(moved):.2f} m, "
          f"p90 {q[8]:.2f} m, max {max(moved):.2f} m, min {min(moved):.2f} m")
    print(f"  distance from the corrected values in the client file: median {statistics.median(vs_ref):.2f} m, "
          f"max {max(vs_ref):.2f} m")
    print(f"the other {len(rest)} points: max distance between the two setups "
          f"{max(dist(both[k], alaska[k]) for k in rest):.6f} m")
