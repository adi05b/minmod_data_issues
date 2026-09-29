# minmod_data_issues

Evidence package for MinMod coordinate problems 1 and 4 (USC ISI, Aditi Bombe).

- **Problem 1**: 24,818 Oregon (EPSG:2994) and Utah (EPSG:26912) sites have latitude and longitude swapped in the merged table.
- **Problem 4**: 7,720 Alaska sites in NAD27 (EPSG:4267) are stored unconverted, about 126 m off.

Both come from the same root cause. `minmodkg/misc/geo.py` in
[`ta2-minmod-kg`](https://github.com/usc-isi-i2/ta2-minmod-kg) builds its pyproj
`Transformer`s without `always_xy=True`, so WKT `(x=lon, y=lat)` gets read in EPSG
authority axis order `(lat, lon)`. The fix adds that one argument in two places.

**Start with [reports/FIX_P1_P4_REPORT.md](reports/FIX_P1_P4_REPORT.md).**

## Layout

```
patches/      0001-problems-1-and-4-always-xy.patch  (git am-able against upstream b6d467b)
tests/        conftest.py        data loading and joins
              test_always_xy.py  pytest proof (Tests 1–3)
              measure.py         before/after numbers -> reports/measure_<label>.json
              grid_check.py      which NAD27->WGS84 operations PROJ can use
acceptance/   queries to run after the merged table is rebuilt (not run against prod)
reports/      the write-up, measurement JSON, and upstream test logs
upstream/     (gitignored) clone of usc-isi-i2/ta2-minmod-kg
upstream-data/(gitignored) sparse read-only clone of DARPA-CRITICALMAAS/ta2-minmod-data
data/         (gitignored) client spreadsheets
```

## Setup

```bash
git clone https://github.com/usc-isi-i2/ta2-minmod-kg upstream
git -C upstream checkout b6d467bae17fc66451ea2f83c363ebebbfdfa3dd
git -C upstream checkout -b fix/reproject-always-xy
git -C upstream am ../patches/0001-problems-1-and-4-always-xy.patch

git clone --filter=blob:none --no-checkout https://github.com/DARPA-CRITICALMAAS/ta2-minmod-data upstream-data
git -C upstream-data sparse-checkout set --no-cone data/entities/crs.csv \
  data/mineral-sites/umn/utah_mineral_occurrence_system/ \
  data/mineral-sites/umn/oregon_department_geology_mineral_industries/ \
  data/mineral-sites/umn/ardf/
git -C upstream-data checkout 3a086a5bb3507cd5ae4f8dd0d9fda0800c7eb244

uv venv -p 3.11 .venv
(cd upstream && uvx --from poetry==1.8.5 poetry export --without-hashes --with dev -f requirements.txt \
  | grep -vE '^(pygraphviz|erdantic)' > /tmp/req.txt)
uv pip install -p .venv/bin/python -r /tmp/req.txt openpyxl
uv pip install -p .venv/bin/python --no-deps -e upstream
```

## Running

```bash
.venv/bin/python -m pytest tests -q                                  # proof, patched upstream
PROJ_NETWORK=OFF .venv/bin/python tests/measure.py after_nogrid     # numbers
PROJ_NETWORK=ON  .venv/bin/python tests/measure.py after_grid       # with NADCON grids (slow, fetches tiles)
```

## Data files (not committed)

`data/` holds two spreadsheets that Adriana (Inferlink) sent by email under the
DARPA CriticalMAAS project. They are client-supplied, so they stay out of git
until Craig says it's fine to commit them. Get them from that email thread and
save them as:

```
data/coord_out_of_range.xlsx           (24,818 rows: stored_lat, stored_lon, source_crs, ...)
data/nad27_stored_as_wgs84.csv         (7,720 rows; Google Sheets exports it as
                                        "nad27_stored_as_wgs84 - nad27_stored_as_wgs84.csv")
```

The raw source coordinates come from the public `ta2-minmod-data` repo (see Setup).
