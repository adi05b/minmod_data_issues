# Problem 2, Phase 5: the approved aliases and new rows, measured

*2026-10-09. After Amandeep's decisions. Option A (the dependency mapping) has its own report, [P2_OPTION_A.md](P2_OPTION_A.md); its merged-entity effect is measured here too (runs C and D).*

## What is measured

| | where | what |
|---|---|---|
| code | `usc-isi-i2/ta2-minmod-kg` `fix/p2-state-repair` @ `a888391` | the repair plus the alias tier: the same tree as `patches/0004`, pushed by Aditi |
| data | `adi05b/ta2-minmod-data` `add-niamey-ekaterinburg` @ `250abc7` (4 commits on `3a086a5`) | **Q7085 Niamey** (Niger); **Q7086 Zacapa Department** (Guatemala); the **`alt names`** column |
| patch | `patches/ta2-minmod-data-niamey-zacapa-alt-names.patch` | the 4 commits; `git am --keep-cr` on `3a086a5` gives the fork's tree exactly (`399763a7`) |

**What the decisions changed since the alias pass:**
- **The Ekaterinburg row is gone.** "Ekaterinburg" is now an alt name on Q5481 Sverdlovsk.
- **Zacapa takes Q7086,** so the new IDs stay gap-free.
- **Zacapa row** (`Q7086,5239,Zacapa Department,90,GT,Guatemala,ZA,,14.97072190,-89.52974110`):
  - id 5239 and the coordinates are dr5hn's.
  - The name follows Guatemala's other 21 rows ("X Department"); type is blank like theirs.
  - The state_code is **`ZA`**, the letter-code style of the other 21 rows (AV, BV, …), as Amandeep decided. Zacapa's current ISO 3166-2 code, which dr5hn now uses, is the numeric **GT-19**.
  - Codes are unique within Guatemala. Matching is unaffected: "Zacapa" reaches the row through its name.
- **`alt names` column:**
  - It is the last column. It holds 53 names on 50 rows: the 52 approved in `reports/p2c/alias_candidates.csv`, plus Ekaterinburg.
  - Values are pipe-separated where there is more than one (Buryatia, Northwestern Province, North Caribbean Coast).
  - Line endings stay CRLF, with no newline at the end of the file.
  - Every line is its old bytes plus `,` and the value. Git shows all 5,087 lines changed, which no added column can avoid.
- **Checks:**
  - **The two data checks pass on the real table:** no alias equals a real name in its country, and all 53 resolve to their own row. These are `tests/misc/test_state_repair.py` with `MINMOD_ENTITY_DIR` set to the fork; all 22 tests pass, including Option A's.
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

Four local runs of the same ETL stages Part B used (`investigation/p2_etl.yml`), each in a fresh workdir:

| run | code | table |
|---|---|---|
| base | `83f9b7b`, no repair (Part B's baseline) | pristine `3a086a5` |
| A | `a888391`, the repair and the alias code | pristine, so no aliases and the alias code is inert |
| B | `a888391` | the fork branch: new rows and `alt names` |
| C | `f01a385` (patch 0005): plus Option A, four pairs | the fork branch |
| D | patch 0006 on `f01a385`: plus the two UK pairs | the fork branch |

**How it was measured here, and why it is still exact:**
- **The memory limit:** the pipeline's last step builds all 419,098 merged entities in one process, and the kernel killed it at 13.9 GB (this container's limit). So the runs stop after the merge (`investigation/p2d_run_merge.py`).
- **Diffing:** `investigation/p2d_merged.py` diffs the merged files between consecutive runs. An entity's final merged form depends only on those files and the election code.
- **Rebuilding:** every entity whose inputs differ anywhere, plus every entity that could be conflicted in any run (5,936 in all), is rebuilt with MinMod's own `from_dedup_sites`, exactly as the last step does, under each run's own code.
- **Any other entity:**
  - **A, B and C:** these share the election code, so an entity whose inputs are identical comes out identical.
  - **base vs A:** the election code differs (Part B's `9d68111`). Part B's full-pipeline comparison showed it changes no values outside the conflicted entities, only refids (`reports/p2b/compare_base_vs_pipeline_full.json`).
- **Noise:** inventories differ between runs only in list order, from Python's per-process string hashing; 0 differ once sorted.
- **Checks on the harness:** the run has **419,098** merged entities and the rebuilt baseline has **5,856** conflicted, both exactly Part B's. A reproduces Part B's result exactly.

| of the 5,856 conflicted merged entities | A: repair only | **B: + aliases and new rows** | C: + Option A |
|---|--:|--:|--:|
| state repointed | 5,185 (88.5%) | **5,543 (94.7%)** | 5,543 |
| state emptied | 671 (11.5%) | **313 (5.3%)** | 313 |
| still conflicted | 0 | **0** | 0 |
| conflicted anywhere, all entities | 0 | 0 | 0 |

**A → B: 360 merged entities have different inputs (397 member records, the 397 recovered candidates).**
- **358 empty states filled.** Odisha 152, Lower Saxony 43, Sverdlovsk (Ekaterinburg) 19, Attapeu 13, Buryatia 12, Guna Yala 12, Zacapa 7, Northwestern Province 6, and so on.
- **0 countries changed and 0 newly conflicted.**
- **Two entities changed some other way.** Both come from MinMod's election, not from any record that resolved before:
  - **A state added, none removed.** A Papua New Guinea record carries two state candidates: Chimbu, kept, and "Eastern Highland", which used to drop and now resolves. The entity's state goes from [Chimbu] to [Chimbu, Eastern Highlands].
  - **"Ozernoe": Bashkortostan → Buryatia.** The entity merges two VMS records of equal source score that are **different deposits about 3,400 km apart**:
    - VMS 1537 at 59.35°E, 54.20°N, in Bashkortostan;
    - VMS 1570 at 111.70°E, 52.93°N, whose "Buryatia" now resolves through the Buryatiya alias.
  - The election takes country and state from the highest-ranked record carrying both, and 1570 now qualifies and ranks first. Neither value is right for an entity that merges two places. The same-as merge upstream is the real defect.

**B → C (Option A): 71 merged entities have different inputs (the 72 moved records).**
- **70 change country:** France → New Caledonia 48, Denmark → Greenland 15, Australia → Christmas Island 4, United Kingdom → Montserrat 3. No state changes.
- **1 keeps Australia.** A moved Christmas Island record shares its entity with a record carrying Australia / Western Australia, and the election prefers the record that carries both.
- **0 newly conflicted.**
- **C → D (patch 0006, the two UK pairs; `reports/p2d/merged_uk_dependencies.json`):** exactly 3 entities have different inputs, and all 3 change country only: United Kingdom → Virgin Islands (British) 2, → Cayman Islands 1. No state changes, nothing newly conflicted.
- **Where the 313 emptied states are now (D):** 73 are in their dependency's country, with the state empty by design (New Caledonia's provinces will be filled from coordinates later), and 4 were already recorded as Greenland. The rest are led by DR Congo, 109: the blocked Katanga records.

**The acceptance counts move like this against the baseline:**

| | A | B | C | D |
|---|--:|--:|--:|--:|
| `merged_with_state` | −671 | **−313** | −313 | −313 |
| `merged_with_country` (entities with any country) | 0 | 0 | 0 | **0** |
| entities whose country value changed | 7 | 7 | 77 | **80** |
| `state_country_conflicts` | 5,856 → 0 | 5,856 → 0 | 5,856 → 0 | 5,856 → 0 |

The 7 country changes in A and B are Part B's pairing fix (`9d68111`): all 7 are among the 5,856 conflicted entities. Option A adds 73 (70 with patch 0005, 3 more with 0006). **`merged_with_country` stays the same as a count**, because Option A changes which country, never whether there is one. See [P2_OPTION_A.md](P2_OPTION_A.md) for what that means for `run_acceptance.sh`.

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
# merged entities: four runs up to the merge, each with its own code on the path
.venv-p2/bin/python investigation/p2d_run_merge.py investigation/p2_etl.yml kg-base data-p2  # code 83f9b7b
.venv-p2/bin/python investigation/p2d_run_merge.py investigation/p2_etl.yml kg-A data-p2     # code a888391
.venv-p2/bin/python investigation/p2d_run_merge.py investigation/p2_etl.yml kg-B <fork>      # code a888391
.venv-p2/bin/python investigation/p2d_run_merge.py investigation/p2_etl.yml kg-C <fork>      # code f01a385 (patch 0005)
.venv-p2/bin/python investigation/p2d_run_merge.py investigation/p2_etl.yml kg-D <fork>      # code f01a385 + patch 0006
p2d_merged.py candidates <run> <fork>/data/entities cand_<run>.json          # for each run
p2d_merged.py diff kg-base kg-A diff_base_A.json   # and A B, B C
# union of the candidates and diffs -> union.json, then for each run, with that run's code:
p2d_merged.py rebuild <run> union.json rebuilt_<run>.json
p2d_merged.py report <fork>/data/entities <work dir> reports/p2d/merged.json
# patch 0006: diff kg-C kg-D, rebuild both for those ids, then
p2d_merged.py pair <fork>/data/entities rebuilt_C.json rebuilt_D.json diff_C_D.json reports/p2d/merged_uk_dependencies.json
# kg tests on the real table
MINMOD_ENTITY_DIR=<fork>/data/entities python -m pytest tests/misc/test_state_repair.py   # in ta2-minmod-kg
```
