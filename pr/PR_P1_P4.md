# Fix swapped coordinates (Problem 1) and unconverted NAD27 sites (Problem 4)

Branch: `fix/reproject-always-xy` (four commits on `83f9b7b`). `fix/p2-state-repair` (Problem 2) depends on this PR's merge-cache bump.

## What was broken

**Problem 1: swapped latitude and longitude, 24,818 sites.** Every site recorded in Oregon's projected CRS (EPSG:2994, 17,073 sites) or UTM 12N (EPSG:26912, Utah, 7,744 sites) came out of the merge with latitude and longitude exchanged. All of them had a latitude outside [−90, 90].

One more out-of-range record, Tagaung Taung (EPSG:4326, Economic Geology), is swapped in the source data itself. This PR doesn't touch it; it needs a data fix in `ta2-minmod-data`.

**Problem 4: NAD27 sites never converted, 7,720 Alaska sites (EPSG:4267).** They were stored as if already in WGS84: a median of 126.5 m off (p90 150.5 m, max 274.8 m) from the NADCON-converted position. The worst cases are in the Aleutians, west of the antimeridian.

## Where the bug was

- **`minmodkg/misc/geo.py`.** `reproject_wkt` and `reproject_geometry` built `pyproj.Transformer`s without `always_xy=True`, so pyproj used each CRS's authority axis order, but WKT is always (x = lon, y = lat). `reproject_geometry` is what the merge uses, via `LocationView.from_location`, for every record not already in EPSG:4326.
  - **EPSG:4326 output** is (lat, lon) in authority order, so every point came back swapped. That's Problem 1.
  - **EPSG:4267 input** had longitude read as latitude. That lands outside every NAD27 → WGS84 operation, so PROJ fell back to its no-op "ballpark" transform. That's Problem 4.
- **The merge cache.** `MergeFn.invoke` is cached on its input files' paths and content hashes, and the code isn't part of the key. A rebuild of unchanged data returns the old rows unless the cache name changes.
- **The backend image has no PROJ grids.** The pyproj wheel ships none and `PROJ_NETWORK` is off. So even with axes fixed, PROJ converts NAD27 with Helmert/Molodensky shifts (metres off), and 24 sites on St. Lawrence and Gareloi Islands fall outside every such operation and don't move at all.

## The fix (four commits)

1. **`always_xy=True` on both transformers** (`geo.py`, +6/−2). The `EPSG:4326 → EPSG:4326` early return is untouched.
2. **Merge cache `merge-v106` → `merge-v107`** (`etl/mineral_site.py:401`), so the next ETL run rebuilds the merged tables.
3. **The two NAD27 grids in the backend image** (`containers/backend/Dockerfile`, +7): `pyproj sync --system-directory` for `us_noaa_alaska.tif` (524,798 bytes) and `ca_nrc_ntv2_0.tif` (7,784,410 bytes). **The image grows by about 8.3 MB.**
   - These are exactly the two grids PROJ selects for the 7,720 Problem 4 sites.
   - The sync runs right after the dependency `pip install .`, *before* the code is added. The layer therefore stays cached until `pyproject.toml`, `poetry.lock` or `README.md` change, and builds don't re-download 8.3 MB on every code change or depend on `cdn.proj.org` being up.
   - **Why the 7.8 MB Canadian grid is worth it:** PROJ uses it for 1,459 south-east Alaska sites, where it ranks it more accurate than the Alaska grid. Without it, PROJ falls back to the Alaska grid for those sites, which then land a **median 1.2 m (p90 5.8 m, max 25.7 m)** away from the corrected positions. The other 6,261 sites are unaffected either way.
4. **Acceptance checks:** `run_acceptance.sh` plus `acceptance/*.sql`.
   - The script captures the same read-only counts before and after the rebuild and prints them side by side. Every connection is forced read-only, and it runs only SELECTs.
   - Counts: latitude out of range (merged and per record), state in another country, totals that must not move, the merge-cache name, and state codes.
   - The three queries add a per-CRS breakdown for Problem 1, five NAD27 spot-check sites with expected values for Problem 4, and the state/country checks for Problem 2 (`fix/p2-state-repair`). The Problem 2 checks only change once that branch is deployed too.

## How we know it works

Measured on the raw source records from `ta2-minmod-data`, through the same path the merge uses (`reproject_geometry` on each record's centroid), before and after the change:

| | before | after, no grids | after, with grids (this PR) |
|---|---:|---:|---:|
| Problem 1: sites with a valid latitude | 0 / 24,818 | 24,817 / 24,818 | 24,817 / 24,818 |
| Problem 1: sites inside their recorded state | 0 / 24,817 | 24,817 / 24,817 | 24,817 / 24,817 |
| Problem 4: NAD27 sites converted | 0 / 7,720 | 7,696 / 7,720 | **7,720 / 7,720** |
| Problem 4: median / max distance from NADCON | 126.5 m / 274.8 m | 5.7 m / 244.2 m | **< 0.01 m / < 0.01 m** |
| EPSG:4326 sites changed | 0 | 0 | 0 |

- **The cause is confirmed exactly.** Run on the raw source records, the old code reproduces the stored (swapped) values for all 24,817 Problem 1 sites. The fixed code returns the same numbers with the axes the right way round.
- **The grids are needed, and so is the code fix.** With grids, PROJ uses `us_noaa_alaska.tif` for 6,261 Problem 4 sites and `ca_nrc_ntv2_0.tif` for 1,459. With grids but *without* the code fix, 0 of the 7,720 convert: the swapped axes miss every grid.
- **EPSG:4326 → EPSG:4326 is bit-identical** (the early return), and `reproject_geometry` still builds one cached transformer per CRS pair.
- **Tests:** the 7 tests behind these numbers pass on this branch. They run on the real records and check that every Problem 1 site ends up in range and inside its state, that Problem 4 sites move to NADCON, that EPSG:4326 is untouched, and that the transformer is still cached. This repo's own suite gives 63 passed on this branch, the same as on `main`; the 27 errors are fixtures that need Docker, identical in both runs.

## Deploy

Run the acceptance script from the deployment folder, the one holding `ta2-minmod-kg/` and `kgdata/`.

1. **Before deploying, capture the current numbers:** `./ta2-minmod-kg/run_acceptance.sh before`.
2. **Rebuild the backend image.** The first build downloads the grids from `cdn.proj.org`, after which the layer is cached. The image is about 8.3 MB bigger.
3. **Run the ETL.** The `merge-v107` cache name makes it rebuild every merged table from the raw records. Nothing needs re-extracting, and nothing in `ta2-minmod-data` changes.
4. **Postgres reloads itself.** The ETL rebuilds it into a new `version-NNN` directory and swaps it in. The RDF graph doesn't need rebuilding for this PR, because reprojected coordinates live only in Postgres.
5. **Check:** run `./ta2-minmod-kg/run_acceptance.sh after`, then `… compare`.
   - The `after` environment line must show `merge-v107`. If it still shows `merge-v106`, the merge was skipped.
   - The five Problem 4 spot-check sites should be within 1 m of their expected values.
   - Of the 31,109 merged sites out of range before, the 24,818 Problem 1 sites above are fixed and Tagaung Taung remains. Any other remainder shows up in the per-CRS query.
6. Separately: fix Tagaung Taung's swapped coordinates in `ta2-minmod-data`.

`fix/p2-state-repair` (Problem 2) relies on step 3 too: merge it after, or together with, this PR.
