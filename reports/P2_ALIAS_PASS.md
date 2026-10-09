# Problem 2, alias pass: shrinking the 671 entities left with no state

*2026-10-08. Phases 0, 2, 3 (up to the candidate list) and 4. Phase 5 waits for the approved aliases.*

> **Update 2026-10-09, after Amandeep's decisions** ([P2_PHASE5.md](P2_PHASE5.md)):
> - The code is on `fix/p2-state-repair` as `a888391`, pushed by Aditi; it has the same tree as `102da1c`, which was never pushed.
> - The Ekaterinburg row was replaced by Zacapa Department (Q7086), and Ekaterinburg is now an alt name of Sverdlovsk.
> - All 52 proposals were approved and are in the `alt names` column.
> - The data patch is now `patches/ta2-minmod-data-niamey-zacapa-alt-names.patch` (three commits); the single-commit patch named below is gone.

## Where everything is

| | repo | branch | commit |
|---|---|---|---|
| code | `usc-isi-i2/ta2-minmod-kg` | `fix/p2-state-repair` | `102da1c` on top of `9d68111`, **not pushed** (see below); as `patches/0004-problem-2-state-aliases.patch` |
| data | `adi05b/ta2-minmod-data` (fork of `usc-isi-i2/ta2-minmod-data`) | `add-niamey-ekaterinburg` | `848723d` on `3a086a5`, pushed; as `patches/ta2-minmod-data-0001-niamey-ekaterinburg.patch` |
| evidence | `adi05b/minmod_data_issues` | `main` | this commit |

**The kg push was refused.** `git push origin fix/p2-state-repair` returned HTTP 403: the Claude GitHub App has no access to `usc-isi-i2` for this account. Your earlier kg commits travel as patches, and so does this one: `git am` of `patches/0004` on `9d68111` gives tree `5132f339`, identical to `102da1c`. It needs pushing from your machine, or a push after an org admin grants the app access.

**Phase 0 numbers, all matching yours.** Data at `3a086a5` (the same commit Part A and Part B pinned). 3,769 record files, 679,778 records, 418,286 with a state, 418,313 state candidates. `state_or_province.csv` has 5,084 rows and `country.csv` 250. The clone is shallow, with no Git LFS.

## Phase 2: the code

- **Column:** `alt names` on `state_or_province.csv`, pipe-separated, each piece stripped. That is the same name and separator as `country.csv`, whose reader already splits on `|`. Read by header, so its position doesn't matter to MinMod. Append it as the **last** column anyway: the D-REPR extractors (`extractors/state_or_province*.yml`) read columns 0, 2 and 5 by position.
- **Precedence:** real names first. Aliases are a **fourth tier, after the code tier**, exact folded name only, reached only when the three existing tiers find nothing.
  - Placing it after codes, not just after tier 1, is what makes "adding aliases cannot break any match that works today" true. With aliases between tiers 1 and 2, an alias could take a name that resolves today through the admin-word-free tier ("La Paz") or the code tier ("CO").
  - An ambiguous real name stays ambiguous. Two rows of one country sharing an alias resolve to nothing.
- **No migration.** The entity step writes `aliases` into `state_or_province.json` only for rows that have them. The ETL merge reads them through `FileEntityService`. `StateOrProvince.from_dict` ignores the key, so Postgres and the KG never see it.
  - The Postgres-backed `EntityService` (API saves, GeoChem loader) has no aliases and behaves exactly as before.
  - Without the column, or with it empty, the JSON is byte-identical to before (tested).
- **Tests:** `tests/misc/test_state_repair.py`, 13 tests, no Docker.
  - An alias resolving.
  - A real name beating an alias.
  - The same alias on two rows of one country.
  - The empty and absent column.
  - On all 5,084 states, every name, admin-free name and code that resolves today given as an alias to a *different* state: 15,087 lookups, all unchanged.
  - Two data checks: no alias equals a real name in its country, and every alias resolves to its own row. Point `MINMOD_ENTITY_DIR` at a ta2-minmod-data checkout to run them on the real table.
  - **Mutations:** putting aliases in tier 1, between tiers 1 and 2, or through the tier-2 form, or removing the tier, each fails at least one test.
- **Regression:**
  - The repo's suite gives the same 15 failed / 48 passed / 27 errors with and without the change. The 15 failures are a vendored SHACL file missing from the checkout; the 27 errors are Docker fixtures.
  - The 32 Part B tests pass, including the wiring on all 418,313 candidates.

## Phase 4: two new rows

`Q7085,5685,Niamey,160,NE,Niger,8,,13.51361111,2.10888889` and `Q7086,,Ekaterinburg,182,RU,Russia,,city,,`, appended at the end.

- **The file uses CRLF line endings** (all 5,084 of them). My first commit appended with bare LF; I caught it when `git am` failed, rewrote the rows with CRLF and amended the fork branch before anything used it. The file now has 5,086 CRLF and no bare LF, and keeps its convention of no newline at end of file.
- **Diff:** byte for byte, the change is `\r\n` plus the two rows; every existing line is unchanged. Git's line count says +3/−1, not +2. The old last line had no line ending, gains one, and git counts that line as changed. Its text is identical. No append can avoid that while the file lacks a final newline.
- **Applying the patch:** use `git am --keep-cr` (plain `git am` strips the CRs and fails) or `git apply`. Both were checked on a clean `3a086a5` and reproduce the fork branch byte for byte.
- MinMod's reader parses 5,086 rows: Niamey → Niger (`Q1157`) with code `8`, and Ekaterinburg → Russia (`Q1181`) with no code.

## Phase 3: the drop list and candidate aliases

**The drop list reproduces exactly.** 6,158 conflicted candidates, 5,421 repointed, 737 dropped, candidate by candidate the same as Part B's run (`reports/p2b/conflicted_outcomes.jsonl`). The 737 are on 735 distinct records: two records each drop two states. They fall into 159 (observed name, recorded country) groups.

| | groups | records |
|---|--:|--:|
| blocked: Katanga 111 (93 + "Katanga Province" 18), New Caledonia 49, Greenland 15, Christmas Island 5, Montserrat 3, Kukes 6, Kankan 3, Boke 2, Kindia 2, Korce 2 | 11 | 198 |
| covered by the new rows: Ekaterinburg 19, Niamey 5 | 2 | 24 |
| alias pass | 146 | **515** (you estimated ~512) |
| ↳ proposed | 52 | 366 |
| ↳ no suggestion | 94 | 149 |

**Every proposal is checked mechanically** (`investigation/p2c_alias_candidates.py`):
- The target exists in the recorded country.
- No proposal is an accent-only variant.
- With all 52 in the index, every candidate of the group repoints to the target, and **0** candidates that keep or repoint today change.
- No alias equals a real name of its country, and every alias resolves to its own row.

**Then against the records' own coordinates** (`investigation/p2c_coordinates.py`, Natural Earth admin-1):
- A name can be right while the records it would repair lie elsewhere, and a centroid check proved too noisy to tell (the table puts Blue Nile in Seattle and Shandong in Oakland). So each record's point is tested against the state's polygon, with 50 km of slack.
- **Six groups (10 records) fail**, and each goes out as "no suggestion" with its name mapping and the evidence in the notes:
  - **Pulau Pinang**: all 5 records in Sabah, about 1,800 km from Penang. It was one of your examples; the name is right, these records are not.
  - **Al Buhayrah**: at Aswan; *al-Buhayrah* is also "the lake", Lake Nasser.
  - **Östergötlands Län**: in Jämtland.
  - **Hwanghae-Namdo**: in North Hamgyong.
  - **Al Balqa'**: at Aqaba.
  - **Chitinskaya Oblast'**: in Amur Oblast.
- The check also kept **Samar** (6) out before it was ever proposed: 5 of its 6 records lie in Eastern Samar, so the source means the island, not the province the table calls Western Samar.

**Projection if all 52 are approved, with the two new rows:** dropped candidates go from 737 to **347** (198 blocked, 149 no suggestion). The aliases recover 366 and the new rows 24, and all 5,421 existing repoints are unchanged. Phase 5 re-measures this with the approved set, at merged-entity level too.

### Top 30 by records

Full list: `reports/p2c/alias_candidates.csv` (146 rows). Why each row was proposed or not: `reports/p2c/alias_candidates_notes.md`.

| # | observed_name | recorded_country | records | proposed_minmod_id | proposed_name | reason |
|--:|---|---|--:|---|---|---|
| 1 | Orissa | India | 187 | Q3657 | Odisha | renamed |
| 2 | Niedersachsen | Germany | 43 | Q3383 | Lower Saxony | other language |
| 3 | Attapu | Laos | 13 | Q4059 | Attapeu Province | transliteration |
| 4 | Buryatiya | Russia | 12 | Q5463 | Republic of Buryatia | transliteration |
| 5 | San Blas* | Panama | 12 | Q5071 | Guna Yala | renamed |
| 6 | Zacapa | Guatemala | 7 |  |  | no suggestion |
| 7 | Aktyubinsk | Kazakhstan | 6 | Q3971 | Aktobe Region | renamed |
| 8 | Evvoia | Greece | 6 | Q3424 | Euboea | transliteration |
| 9 | Karnten | Austria | 6 | Q2215 | Carinthia | other language |
| 10 | North-Western | Zambia | 6 | Q7072 | Northwestern Province | transliteration |
| 11 | Samar | Philippines | 6 |  |  | no suggestion |
| 12 | Steiermark | Austria | 6 | Q2218 | Styria | other language |
| 13 | Lappi | Finland | 5 | Q3211 | Lapland | other language |
| 14 | Pulau Pinang | Malaysia | 5 |  |  | no suggestion |
| 15 | Sogn Og Fjordane | Norway | 5 |  |  | no suggestion |
| 16 | Ch'Ungch'Ong-Bukto | North Korea | 4 |  |  | no suggestion |
| 17 | Hentiy | Mongolia | 4 | Q4615 | Khentii Province | transliteration |
| 18 | Nicosia | Cyprus | 4 | Q2906 | Nicosia District (Lefkoşa) | longer official name |
| 19 | Oulu Laani | Finland | 4 |  |  | no suggestion |
| 20 | Westland | New Zealand | 4 |  |  | no suggestion |
| 21 | G�vleborg | Sweden | 3 |  |  | no suggestion |
| 22 | Kareliya | Russia | 3 | Q5467 | Republic of Karelia | transliteration |
| 23 | Netherlands Antilles | Netherlands | 3 |  |  | no suggestion |
| 24 | North-West Frontier | Pakistan | 3 | Q5030 | Khyber Pakhtunkhwa | renamed |
| 25 | Piura | Brazil | 3 |  |  | no suggestion |
| 26 | Sidamo | Ethiopia | 3 |  |  | no suggestion |
| 27 | Sofiya | Bulgaria | 3 |  |  | no suggestion |
| 28 | Tuva | Russia | 3 | Q5485 | Tuva Republic | longer official name |
| 29 | Agadir | Morocco | 2 |  |  | no suggestion |
| 30 | Al Bahr Al Ahmar | Egypt | 2 | Q3122 | Red Sea | other language |

### What the "no suggestion" rows are

- **A row the table lacks: Zacapa (Guatemala, 7 records).** Guatemala has 22 departments and the table 21. This is the same gap as Niamey and would need a new row; I didn't add one.
- **Former units split or merged into something bigger:**
  - Sogn og Fjordane, Ostfold and Troms (Norway). The Norwegian rows are the 2020 counties; Norway re-split Viken and Troms og Finnmark in 2024.
  - Oulu Province and Eastern Finland (Finland).
  - Brabant, Sidamo, Welega, Oriente, Netherlands Antilles, Limousin, Irian Jaya, Semipalatinsk.
  - These are a policy question like Katanga, not name variants.
- **Not first-level units:**
  - Counties, districts and municipalities: Westland, Buller, Caminha, Elko County and others.
  - Cities: Turku, Agadir, Oulu.
  - Islands and peninsulas: Viti Levu, Halmahera, Kola.
  - Spanish autonomous communities, where the Spanish rows are provinces: Andalusia, Castilla y León, Extremadura.
  - Historical provinces: Småland, Swedish Lapland.
- **Two rows the name could mean:** Sofiya (Sofia City / Sofia Province) and Surigao (del Norte / del Sur).
- **Wrong recorded country:** for example Ch'ungch'ong-bukto under North Korea, Piura under Brazil, Alaska under Canada.
- **Unclear:** Mexico's two-letter abbreviations (BN, BS, CO, SB, SI), which are not the table's codes; and `G�vleborg`, Gävleborg with the ä destroyed by a broken encoding upstream, which needs fixing at the source rather than as vocabulary.

### On the reason column

It uses only your five values. Four rows are spelling variants with no closer label, so I gave them `transliteration` and said so in the notes:
- North-Western and North-Western Province, where the table writes "Northwestern".
- Eastern Highland, for Eastern Highlands.
- Otjozondijupa, a misspelling of Otjozondjupa.

Two Russian rows are labelled `renamed` although the change was a merger: Kamchatka Oblast became Kamchatka Krai, merged with the autonomous okrug that lay inside it, so the territory is the same.

## Flags, not decided

1. **Two caches, one deploy order.**
   - The merge cache (`merge-v106` on this branch, `merge-v107` already built on dev) needs `merge-v108` or later.
   - `EntityDeserFn.VERSION = "v107"` names the entity-transform cache, keyed on CSV content only. This branch (`state_code`, and now `aliases`) changed its output without changing it, so a server that already transformed the current CSV keeps JSON with neither field, and the code and alias tiers never hit there.
   - **Order needed: the data repo change first, then the kg build with both versions bumped.** The merge cache does not see entity files, so data landing after a v108 build would be inert. Recorded in `FIX_P2_REPORT.md` next to the merge-cache note.
2. **"Accents need no aliases" holds only for letters Unicode decomposes.** `fold_name` drops ø, đ, ħ, ł and ə instead of folding them: 24 table names, for example Trøndelag, Møre og Romsdal, Međimurje, the Maltese Għ- councils, Łódź and Gədəbəy. An ASCII "Trondelag" would not match. None of them is in today's drop list. A mapping like the Turkish ı fix would close it, but it changes matching, so I left it.
3. `adfef76` on this repo's `main` still has a `Co-Authored-By` trailer from an earlier session. I did not rewrite `main`.

## Reproducing

```bash
# kg at 102da1c (or 9d68111 + patches/0004), data at 3a086a5 as data-p2/data
CFG_FILE=upstream-p2/tests/resources/config.yml .venv-p2/bin/python investigation/p2c_drop_list.py
CFG_FILE=... .venv-p2/bin/python investigation/p2c_coordinates.py ne/geojson/ne_10m_admin_1_states_provinces.geojson
CFG_FILE=... .venv-p2/bin/python investigation/p2c_alias_candidates.py
# kg tests: in ta2-minmod-kg
python -m pytest tests/misc/test_state_repair.py
MINMOD_ENTITY_DIR=<ta2-minmod-data>/data/entities python -m pytest tests/misc/test_state_repair.py
```

Natural Earth: `nvkelso/natural-earth-vector` at `ca96624`, sparse-checked out to `geojson/ne_10m_admin_1_states_provinces.geojson` (the command is in the script's docstring).
