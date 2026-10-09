# Problem 2, Phase 5: the approved aliases and new rows, measured

*2026-10-09. After Amandeep's decisions. Option A is a separate, proposal-only report: [P2_OPTION_A_PROPOSAL.md](P2_OPTION_A_PROPOSAL.md).*

## What is measured

| | where | what |
|---|---|---|
| code | `usc-isi-i2/ta2-minmod-kg` `fix/p2-state-repair` @ `a888391` | the repair plus the alias tier: the same tree as `patches/0004`, pushed by Aditi |
| data | `adi05b/ta2-minmod-data` `add-niamey-ekaterinburg` @ `d6e5a5a` (3 commits on `3a086a5`) | **Q7085 Niamey** (Niger); **Q7086 Zacapa Department** (Guatemala); the **`alt names`** column |
| patch | `patches/ta2-minmod-data-niamey-zacapa-alt-names.patch` | the 3 commits; `git am --keep-cr` on `3a086a5` gives the fork's tree exactly |

**What the decisions changed since the alias pass:**
- **The Ekaterinburg row is gone.** "Ekaterinburg" is now an alt name on Q5481 Sverdlovsk.
- **Zacapa takes Q7086,** so the new IDs stay gap-free.
- **Zacapa row** (`Q7086,5239,Zacapa Department,90,GT,Guatemala,19,,14.97072190,-89.52974110`):
  - id 5239, state_code `19` and the coordinates are dr5hn's.
  - The name follows Guatemala's other 21 rows ("X Department"); type is blank like theirs.
  - **Flag:** those 21 rows carry the older ISO **letter** codes (AV, BV, …), so Zacapa's matching code would be `ZA`. dr5hn has moved to numeric codes. Changing it is one cell; matching is unaffected, because "Zacapa" reaches the row through the admin-word tier.
- **`alt names` column:**
  - It is the last column. It holds 53 names on 50 rows: the 52 approved in `reports/p2c/alias_candidates.csv`, plus Ekaterinburg.
  - Values are pipe-separated where there is more than one (Buryatia, Northwestern Province, North Caribbean Coast).
  - Line endings stay CRLF, with no newline at the end of the file.
  - Every line is its old bytes plus `,` and the value. Git shows all 5,087 lines changed, which no added column can avoid.
- **Checks:**
  - **The two data checks pass on the real table:** no alias equals a real name in its country, and all 53 resolve to their own row. These are `tests/misc/test_state_repair.py` with `MINMOD_ENTITY_DIR` set to the fork; all 13 tests pass.
  - MinMod's reader parses 5,086 states and 53 aliases.
  - The positional D-REPR extractor (`extractors/state_or_province.yml`, used by the validator) still reads the country name from column 5 for all 5,086 rows.

## Records: every state candidate (`reports/p2d/records.json`)

`investigation/p2d_measure.py` runs the repair over all **418,313** state candidates on 418,286 records, with the table before (pristine, no aliases: Part B's state) and after (the fork branch).

| | candidates | records |
|---|--:|--:|
| **resolve to nothing, before** | **737** | **735** |
| **resolve to nothing, after** | **340** | **338** |
| ↳ blocked, waiting on a decision | 198 | |
| ↳ no suggestion (`alias_candidates_notes.md`) | 142 | |
| recovered by the 52 approved aliases | 366 | |
| recovered by the Ekaterinburg alias on Sverdlovsk | 19 | |
| recovered by the new row Zacapa | 7 | |
| recovered by the new row Niamey | 5 | |

**Zero regressions.** All 412,155 candidates kept before are kept after, and all 5,421 repointed before go to the same state after. **0 candidates change other than drop → repoint.** Every recovered candidate goes to the approved target, or to Niamey or Zacapa (asserted in the script).

## Self-resolution: every state, its own name, its own country (`reports/p2d/self.json`)

| | states | finds itself | resolves to nothing | **resolves to another entity** |
|---|--:|--:|--:|--:|
| before (Part B's gate 2) | 5,084 | 5,058 | 26 | **0** |
| after | 5,086 | 5,060 | 26 | **0** |
| after, the 53 aliases (each in its row's country) | 53 | 53 | 0 | **0** |

The 26 that resolve to nothing are the same 13 duplicate-name pairs as before: 10 in Puerto Rico, plus Zagreb (Croatia), and Chiayi and Hsinchu (Taiwan). Two rows share a name in one country, and the rule refuses to guess between them. **No state that found itself before stops finding itself.**

## Merged entities (`reports/p2d/merged.json`)

*Pending: three local ETL runs (baseline 83f9b7b, and a888391 on the old and the new table) are in progress; this section is filled in when they finish.*

## Katanga: usable WGS84 coordinates (Amandeep's request)

**97 of the 111 Katanga records** (93 "Katanga" + 18 "Katanga Province", DR Congo recorded) have a usable WGS84 coordinate.
- **Usable** means: CRS EPSG:4326 or unset; a POINT, or a MULTIPOINT holding one point; not 0,0; not a round placeholder (both coordinates on a whole or half degree); and inside DR Congo (Natural Earth admin-1).
- **The other 14:** no location 8, outside DR Congo 5, round placeholder 1.
- `investigation/p2d_katanga.py` → `reports/p2d/katanga_coordinates.json`.

## Reproducing

```bash
export CFG_FILE=upstream-p2/tests/resources/config.yml     # ta2-minmod-kg @ a888391
# data-p2: ta2-minmod-data @ 3a086a5; <fork>: adi05b/ta2-minmod-data @ add-niamey-ekaterinburg
.venv-p2/bin/python investigation/p2d_measure.py <fork>/data/entities records
.venv-p2/bin/python investigation/p2d_measure.py <fork>/data/entities self
.venv-p2/bin/python investigation/p2d_katanga.py ne/geojson/ne_10m_admin_1_states_provinces.geojson
# merged entities: three fresh ETL runs of investigation/p2_etl.yml, then
.venv-p2/bin/python investigation/p2_run_etl.py investigation/p2_etl.yml kg-base data-p2     # code 83f9b7b
.venv-p2/bin/python investigation/p2_run_etl.py investigation/p2_etl.yml kg-A data-p2        # code a888391
.venv-p2/bin/python investigation/p2_run_etl.py investigation/p2_etl.yml kg-B <fork>         # code a888391
.venv-p2/bin/python investigation/p2d_compare.py <fork>/data/entities kg-base kg-A kg-B
# kg tests on the real table
MINMOD_ENTITY_DIR=<fork>/data/entities python -m pytest tests/misc/test_state_repair.py   # in ta2-minmod-kg
```
