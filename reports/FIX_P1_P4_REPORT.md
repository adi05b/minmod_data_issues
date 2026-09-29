# Problems 1 and 4: `always_xy` fix, report

Aditi Bombe, USC ISI, 2026-09-28.

> **Patch:** `patches/0001-problems-1-and-4-always-xy.patch`
> **Applies to:** `usc-isi-i2/ta2-minmod-kg` @ `b6d467bae17fc66451ea2f83c363ebebbfdfa3dd` (main, 2026-09-24). Checked with `git am` on a fresh checkout.
> **Raw data used:** `DARPA-CRITICALMAAS/ta2-minmod-data` @ `3a086a5bb3507cd5ae4f8dd0d9fda0800c7eb244` (sparse, read-only)
> **Env:** Python 3.11, pyproj 3.7.0 / PROJ 9.4.1, shapely 2.0.6 (the versions in upstream `poetry.lock`)

Tags: 🟢 verified by running it · 🟡 likely (read in code, not executed end to end) · 🔴 assumed

---

## 1. Craig's question: loading time or extraction time?

**Neither.** It runs during the **merge step of the ETL**, when the relational (Postgres "kgrel") merged table is built. 🟢

| caller | stage |
|---|---|
| `minmodkg/models/kgrel/custom_types/location.py:132` `LocationView.from_location` → `reproject_geometry(centroid, crs, "EPSG:4326")` | **Merge.** It is reached from `MineralSite.from_raw_site` (`models/kgrel/mineral_site.py:226`) ← `MineralSiteAndInventory.from_raw_site` ← `MergeFn.invoke` (`etl/mineral_site.py:426`), part of the `kgrel.data.mineral_site` service in `etl.yml`. |
| same function, via `InputPublicMineralSite.to_kgrel` (`api/models/public_mineral_site.py:188`) | **API write path.** Runs when a user creates or edits a site through the API. Once deployed, new edits get the fix with no rebuild. |
| `minmodkg/misc/geo.py:54` `merge_wkts` → `reproject_wkt` | **No production caller.** `merge_wkts` is exported from `minmodkg.misc` but nothing calls it. |

It is **not** extraction (the raw JSON in `ta2-minmod-data` holds the source CRS and WKT unchanged, e.g. `POINT (337936 4506676)` / EPSG:26912). It is **not** RDF loading either: the RDF graph stores only the raw `mo:location` WKT and `mo:crs`, and reprojected lat/lon never reach the triple store. They exist only in Postgres: `mineral_site.location_view` and `dedup_mineral_site.coordinates`. 🟢 (checked by dumping `MineralSite.to_triples()` for an ardf site)

**Entry point** (README "Building TA2 knowledge graph", and `start.sh`):

```bash
python -m statickg ta2-minmod-kg/etl.yml ./kgdata ta2-minmod-data --overwrite-config --refresh 20
```

### What has to be re-run

**Only the merge and the Postgres load. No re-extraction, and nothing in `ta2-minmod-data` changes.** The RDF/Fuseki side has no reprojected values, so it doesn't need a rebuild for this fix.

**Watch out: redeploying the code is not enough on its own.** 🟡 `MergeFn.invoke` is wrapped in `@cache(backend=FileSqliteBackend.factory(filename="merge-v106.sqlite"))`. The cache key is each input file's path plus the sha256 of its contents (`statickg InputFile.get_ident`). The code isn't part of the key. The input JSON hasn't changed, so every bucket is a cache hit and the old swapped lat/lon come straight back out. `--refresh 20` is only the polling interval in seconds, not a cache bust. One of these has to happen:

- **Recommended:** the PR also bumps `merge-v106.sqlite` → `merge-v107.sqlite` in `minmodkg/etl/mineral_site.py`. That's the repo's own convention: the version number exists to invalidate this cache. I left it out of this patch because the brief said to change nothing else. It is a one-line follow-up for the PR.
- or delete the `merge-v106.sqlite` cache under the ETL workdir in `kgdata/` before restarting.

After that, the merged `kgrel/*.json` files change, and `kg.loader.postgres` reloads Postgres from them.

---

## 2. The diff

The original line numbers were 74 and 92, same as in the PyPI package, so nothing had moved. Upstream commit `b6d467b`, local branch `fix/reproject-always-xy` → `04c0ba6` (tree identical to `caea95e`, which is the SHA recorded in the measurement JSON; re-authored only). The `if from_crs == to_crs: return` early exits are untouched.

```diff
diff --git a/minmodkg/misc/geo.py b/minmodkg/misc/geo.py
index 3f8b113..49d0f3c 100644
--- a/minmodkg/misc/geo.py
+++ b/minmodkg/misc/geo.py
@@ -72,7 +72,9 @@ def reproject_wkt(wkt: str, from_crs: str, to_crs: str) -> str:
         return wkt
 
     transformer = Transformer.from_crs(
-        int(from_crs[len("EPSG:") :]), int(to_crs[len("EPSG:") :])
+        int(from_crs[len("EPSG:") :]),
+        int(to_crs[len("EPSG:") :]),
+        always_xy=True,
     )
 
     return dumps(shapely.ops.transform(transformer.transform, loads(wkt)))
@@ -90,7 +92,9 @@ def reproject_geometry(geometry, from_crs: str, to_crs: str):
         assert from_crs.startswith("EPSG:"), from_crs
         assert to_crs.startswith("EPSG:"), to_crs
         _transformation[from_crs, to_crs] = Transformer.from_crs(
-            int(from_crs[len("EPSG:") :]), int(to_crs[len("EPSG:") :])
+            int(from_crs[len("EPSG:") :]),
+            int(to_crs[len("EPSG:") :]),
+            always_xy=True,
         )
 
     return shapely.ops.transform(_transformation[from_crs, to_crs].transform, geometry)
```

---

## 3. Before / after (for the slide)

"After" depends on whether PROJ can reach the NADCON grids. By default it can't: the pyproj wheel ships without them and the upstream backend image (`python:3.12-slim`) adds neither the grids nor `PROJ_NETWORK`. 🟡 So the **"after, as deployed"** column is the realistic one.

| | before | after, as deployed (no grids) | after, with grids |
|---|---|---|---|
| P1 records with valid latitude | 0 / 24,818 | **24,817 / 24,818** | 24,817 / 24,818 |
| P1 records inside the named state | 0 / 24,817 | **24,817 / 24,817** | 24,817 / 24,817 |
| P4 records converted | 0 / 7,720 | **7,696 / 7,720** | 7,720 / 7,720 |
| P4 median error vs NADCON | 126.5 m | **5.7 m** | < 0.01 m |
| P4 p90 / max error vs NADCON | 150.5 m / 274.8 m | 22.1 m / 244.2 m | < 0.01 m / < 0.01 m |
| EPSG:4326 records changed | 0 | **0** | 0 |

Notes:
- The one P1 record left over is **Tagaung Taung** (Economic Geology, EPSG:4326). It is swapped in the source data, and the early return never touches it. **Needs a manual fix in `ta2-minmod-data`.** 🟢
- "Inside the named state" uses the state on the raw record (`location_info.state_or_province`) and a bounding box. Tagaung Taung isn't in the checked-out sources, so the denominator is 24,817.
- All numbers are 🟢. They come from `tests/measure.py` run on each commit, and the JSON is in `reports/measure_{before,after_nogrid,after_grid,before_grid}.json`.

**Proof that the join is right** 🟢: on the unpatched `b6d467b`, feeding the raw WKT through the production path (centroid → `reproject_geometry`) reproduces the spreadsheet's `stored_lat/stored_lon` for **24,817 / 24,817** records (to 1e-6°). After the patch, every output equals the old stored value with the two swapped back.

**Tests** (`tests/test_always_xy.py`, 7 tests, pytest like upstream): **7 passed** 🟢. They take about 7 minutes because `reproject_wkt` builds a new `Transformer` on every call (see §5).

**Upstream suite** 🟢: `tests/` gives **55 passed, 27 errors before, and the same 55 passed, 27 errors after**, with an identical failure set (`reports/upstream_tests_{before,after}.txt`). All 27 errors are fixtures that `docker run` a triple store or Postgres, and there's no Docker daemon on this machine. So the change breaks nothing that could run here, but the Docker-backed tests were **not** run.

---

## 4. The grid question: algorithmic or grid?

Craig was partly right. PROJ has both, and it picks the best operation it can reach **for each point**. The numbers:

| | no grids (default) | grids reachable (`PROJ_NETWORK=ON`) |
|---|---|---|
| NAD27→WGS84 operations | 31 available, 48 unavailable (missing `us_noaa_alaska.tif`, `us_noaa_conus.tif`, `ca_nrc_ntv2_0.tif`, …) | 79 available, 0 unavailable |
| Operations actually used, from `get_last_used_operation()` per point on the production transformer | NAD27→WGS84 **(7)** Helmert, acc. 12 m: 6,258 · **(13)** acc. 8 m: 1,368 · **(21)** acc. 15 m: 60 · **(22)** acc. 18 m: 5 · **(14)** acc. 10 m: 5 · **Ballpark** (no-op): **24** | NAD27→WGS84 **(85)** `us_noaa_alaska.tif`, acc. 5 m: 6,261 · **(33)** `ca_nrc_ntv2_0.tif`, acc. 2 m: 1,459 |
| Moved | 7,696 / 7,720 | 7,720 / 7,720 |
| Error vs client NADCON: median / p90 / max | 5.7 / 22.1 / 244.2 m | < 0.01 m on all |
| Within 1 m / 5 m | 185 / 3,380 | 7,720 / 7,720 |

- **The 24 that don't move without grids** are St. Lawrence Island (`sl*`) and Gareloi Island. No Helmert operation's area of use covers them, so PROJ falls back to "Ballpark", which does nothing. 🟢
- **Unpatched code with grids still converts 0 / 7,720.** 🟢 The swapped axes feed longitude in as latitude, which lands outside every grid, so PROJ falls back to Ballpark. Grids alone don't fix P4; the patch is required.
- **Verdict:** with the patch and no grids, P4 goes from 126 m to about 6 m median. That's a real improvement at zero cost. But 24 records don't move and the tail is still over 20 m. For NADCON-level accuracy the ETL needs the grids: either run `projsync --file us_noaa_alaska.tif --file ca_nrc_ntv2_0.tif` (add `us_noaa_conus.tif` for any CONUS NAD27 data) in the backend image, or set `PROJ_NETWORK=ON`. That's a container change, separate from the code patch.

---

## 5. Surprises, and where the brief was wrong

1. **Test 1 as written couldn't run.** 🟢 `coord_out_of_range.xlsx` holds the buggy **output** (WGS84 degrees, swapped), not the source-CRS input. Running `stored_lat/lon` through `reproject_wkt` "from EPSG:2994" would push degrees through a feet-based projection. Instead I joined each row (`refid` = site_id) to its raw WKT in `ta2-minmod-data` (24,817 / 24,818 matched) and ran that. The round trip above shows the join is right.
2. **The acceptance check can't be SPARQL.** 🟢 Reprojected lat/lon only live in Postgres, and the RDF holds the raw WKT, which this fix doesn't change. `acceptance/problem1_latitude_range.sql` and `problem4_nad27_spotcheck.sql` query Postgres. `problem4_nad27_spotcheck.rq` is SPARQL, but it can only confirm the *input* WKT. Both SQL files were run against a throwaway local Postgres built from upstream's own SQLAlchemy models with 8 real sites (3 Utah, 5 Alaska). Unpatched, P1 returns 3 and P4 errors are 123–275 m. Patched, P1 returns 0 and P4 errors are 0.0 m with grids or 1.3–12.6 m without (sl004 stays at 173.6 m). Outputs are in `reports/acceptance_sql_*.txt`. 🟢 Not run against production.
3. **"After a rebuild it must return 0" is wrong.** 🟢 Tagaung Taung stays out of range until it's fixed at source, so expect at least 1. And **31,109 − 24,818 = 6,291** out-of-range entities aren't in the spreadsheet. 🔴 I couldn't check the 31,109 figure or say what those 6,291 are (maybe other CRSs, or a count of `mineral_site` rather than `dedup_mineral_site`). The second query in the P1 SQL file groups the remainder by CRS, so it will show where they come from.
4. **The client's "NADCON" answers aren't independent of PROJ.** 🟢 PROJ with grids reproduces `corrected_*` to within 5e-8° on every row, which is the file's rounding precision. For the 1,459 SE Alaska points east of −141°, the match is with the **Canadian NTv2 grid** (PROJ ranks it 2 m against NADCON's 5 m), not NOAA NADCON. So the client almost certainly computed them with PROJ plus grids. That makes them a good consistency check, but not independent ground truth. If a strict NADCON answer is wanted in SE Alaska, the operation has to be pinned.
5. **The merge cache hides the fix** (§1). Without a cache bump or a cache delete, a rebuild won't change anything. 🟡 Based on reading the code; I didn't run the ETL.
6. **`reproject_wkt` is slow.** 🟢 It builds a fresh `Transformer` on every call, while `reproject_geometry` caches one. It isn't on the production path (`merge_wkts` has no callers), so I left it alone. It's the reason the test suite takes 7 minutes.
7. **Things the brief got right** 🟢: the line numbers (74, 92), the caller (`location.py`), the counts (17,073 Oregon, 7,744 Utah, 1 EPSG:4326, 7,720 NAD27), the 126.5 m median, and that current code returns NAD27 input unchanged (it goes through PROJ's "Ballpark" no-op). The `TransformerGroup[0]` trap was avoided: operations here come from `get_last_used_operation()` on the transformer the production path actually uses.

---

## Rules check

- Nothing was pushed to any `usc-isi-i2` or `DARPA-CRITICALMAAS` repo, and no PR was opened anywhere. The upstream commit exists only in the local `upstream/` clone, which is gitignored.
- No SPARQL UPDATE, no POST, nothing touched the live graph or production Postgres. The only database used was a temporary local Postgres, which was deleted afterwards.
- The client data in `data/` is gitignored and not committed.
