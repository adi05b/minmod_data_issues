"""How many of the 111 Katanga records carry a usable WGS84 coordinate?

The records are the dropped ones observing "Katanga" or "Katanga Province" with
DR Congo recorded (reports/p2c/drop_list.csv: 93 + 18). A coordinate is usable
when all of these hold:
  - the record's CRS is EPSG:4326 (Q701) or unset, which MinMod reads as 4326;
  - the location is a WKT POINT, or a MULTIPOINT holding one point;
  - it is not 0,0 and not a round placeholder (both coordinates on a whole or
    half degree);
  - it lies inside DR Congo (Natural Earth admin-1, all DR Congo polygons).

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2d_katanga.py <natural earth admin-1 geojson>

Writes reports/p2d/katanga_coordinates.json.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

NE_FILE = Path(sys.argv[1])
sys.argv = sys.argv[:1]
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "investigation"))
import p2c_drop_list as dl  # noqa: E402

from minmodkg.models.kg.mineral_site import MineralSiteIdent  # noqa: E402
from shapely import wkt  # noqa: E402
from shapely.geometry import MultiPoint, Point, shape  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

GROUPS = {("Katanga", "Democratic Republic of the Congo"), ("Katanga Province", "Democratic Republic of the Congo")}


def single_point(loc: str):
    try:
        g = wkt.loads(loc)
    except Exception:
        return None
    if isinstance(g, Point):
        return g
    if isinstance(g, MultiPoint) and len(g.geoms) == 1:
        return g.geoms[0]
    return None


def main() -> None:
    gj = json.load(open(NE_FILE, encoding="utf-8"))
    drc = unary_union([shape(f["geometry"]) for f in gj["features"]
                       if f["geometry"] and f["properties"]["admin"] == "Democratic Republic of the Congo"])

    _, conf = dl.run()
    wanted = collections.defaultdict(set)
    for r in conf:
        key = (r["observed_name"] or "", " | ".join(dl.cid2name[c] for c in r["cs"]))
        if key in GROUPS and r["action"] == "drop":
            wanted[r["file"]].add(r["site_id"])
    sites = {s for v in wanted.values() for s in v}

    outcome = collections.Counter()
    seen = set()
    for file, ids in wanted.items():
        for rec in json.load(open(dl.DATA / "mineral-sites" / file, encoding="utf-8")):
            sid = MineralSiteIdent.from_dict(rec).id
            if sid not in ids or sid in seen:
                continue
            seen.add(sid)
            li = rec.get("location_info") or {}
            loc = (li.get("location") or "").strip()
            crs = ((li.get("crs") or {}).get("normalized_uri") or "").rsplit("/", 1)[-1]
            pt = single_point(loc) if loc else None
            if not loc:
                outcome["no location"] += 1
            elif crs not in ("", "Q701"):
                outcome[f"not WGS84 ({crs})"] += 1
            elif pt is None:
                outcome["not a single point"] += 1
            else:
                lon, lat = pt.x, pt.y
                if lat == 0 and lon == 0:
                    outcome["0,0"] += 1
                elif (lat * 2).is_integer() and (lon * 2).is_integer():
                    outcome["round placeholder"] += 1
                elif not drc.contains(Point(lon, lat)):
                    outcome["outside DR Congo"] += 1
                else:
                    outcome["usable"] += 1
    assert seen == sites, len(sites - seen)
    res = {"records": len(sites), "usable": outcome["usable"], "breakdown": dict(outcome.most_common())}
    out = ROOT / "reports/p2d/katanga_coordinates.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
