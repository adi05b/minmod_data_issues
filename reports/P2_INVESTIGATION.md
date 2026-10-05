# Problem 2, Part A: investigation findings

**Gate (A1): safe to proceed.** 🟢 Only **25 of the 6,158** conflicted state candidates (on 6,155 records; **0.4%**) lack `observed_name`, so few would be dropped for that reason alone. All 25 come from one matcher, "UMN Exact Match v1".
That's not material. I measured the fallback (re-resolve by the chosen state's own *name*) anyway: it repoints all 25, each correctly, and changes nothing else.
Aditi Bombe, USC ISI · 2026-10-04 · ta2-minmod-kg `83f9b7b` · ta2-minmod-data `3a086a5` · ProcMine `ce1ed70`

Tags: 🟢 verified by running it · 🟡 likely · 🔴 assumed / not my number.

## Headline numbers

| | |
|---|---|
| **A1** gate | 25 / 6,158 conflicted records have no `observed_name` (0.4%). With the name fallback: 0. 🟢 |
| **A2** effect on the merged entities Adriana counted | Of **5,856** conflicted merged entities (Adriana's figure is 5,858): the rule **repoints 4,995 (85.3%)**, **drops the state on 854 (14.6%)**, and **leaves 7 (0.1%)** conflicted. It creates 0 new conflicts and changes 0 non-conflicted entities. 🟢 |
| **A2** per record | Of 6,158 conflicted state candidates (on 6,155 records): **repoints 5,146 (83.6%)**, **drops 1,012 (16.4%)**, leaves 0 untouched (by construction). 🟢 |
| **A3** where the conflicts come from | **5,746 (98.1%)** have the same `refid` on country and state, so one record asserts the conflict (upstream defect). **110 (1.9%)** have different `refid`s, but in 104 of those the state's own record is itself conflicted. **Only 6 (0.1%) are pairings that no record asserts.** 🟢 |
| **A4** multi-country records | **100% of conflicted records carry exactly one country.** Only 1 of 418,286 records with a state carries two. Recommendation: keep **"any"**. 🟢 |

The state repair is by far the fix that matters: in the simulation it resolves **5,849 of the 5,856** conflicts. The two-pass election (B3) can only help the ~6 pairings that no record asserts, plus one the repair itself exposes (§A3).

---

## How this was measured, and why it differs from the brief's plan

- **No live-graph queries were run. The endpoint only answers POST, and this run is GET-only (rule 2).** 🟢 `https://minmod.isi.edu/sparql` returns `404 Service Description: /minmod/sparql` to a GET query, on both `/sparql` and `/sparql/`. The reason is `containers/nginx/nginx.conf:143,154` (`proxy_pass $kg/minmod/sparql;`): when `proxy_pass` contains a variable, nginx replaces the URI and drops the query string. A POST body would get through, but I sent no POST. So I took the brief's fallback, the raw site JSON in `ta2-minmod-data`.
- **I used the full data, not a sample** (deviation from the brief). `data/mineral-sites` is 1.3 GB and `data/same-as` 257 MB (sizes from the GitHub tree API). Conflicted records are about 1.5% of the 418,286 records with a state, so a sample would have turned every gate number into an extrapolation, and A3 needs whole dedup groups. 🟢
- **Postgres was not reachable, and I did not try to connect.** No credentials were given. For A3 and the merged-level A2, I **rebuilt the merged entities locally** by running upstream's own entity, same-as and merge ETL stages (copied verbatim from `etl.yml`, minus the loaders) on the pinned data. That produced the exact JSON the Postgres loader would load. **It reproduces Adriana's count to within 2 (5,856 vs 5,858).** 🟢 for the local count; 🟡 that the 2-record gap is data or sync drift.
- **Record-level numbers** use MinMod's own parsing (`LocationInfo.from_dict` → `LocationView.from_location`). Every repair decision comes from the unmodified `reference/state_repair.py`, with the index built exactly as `reference/verify.py` builds it. MinMod's own `EntityDeserFn.read_state_or_province` gives an **identical** state→country map for all 5,084 rows. 🟢
- **Merged-level simulation.** Each site's `location_view` is repaired in memory, then the merged rows are rebuilt with MinMod's own `DedupMineralSite.from_sites` (per bucket file, as `MergeFn` does) and `from_dedup_sites` (as `prep_kgrel_input` does). No upstream file was modified. With the repair switched off, the rebuild reproduces the ETL's `country` and `state_or_province` (value and `refid`) for **all 5,924** affected entities, with 0 mismatches. 🟢
- **SPARQL for the live graph is written but not run live.** The four queries in `investigation/sparql/` were checked with rdflib against 2.37M triples of the TTL the ETL writes for Fuseki (11 buckets, 617 conflicted candidates, 14 nodes without `observed_name`). All four agree exactly with the JSON-derived counts. 🟢 on local TTL; 🔴 on live (not run).

---

## A0: setup and baselines

Brief and reference files: `~/Downloads/P2_RUN.md`, `state_repair.py` and `verify.py` (exact names, no suffixes), copied byte-identical into `P2_RUN.md` and `reference/`. 🟢

| check | expected | got | |
|---|---|---|---|
| `state_or_province.csv` rows | 5,084 | 5,084 | 🟢 |
| `country.csv` rows | 250 | 250 | 🟢 |
| `verify.py`: ProcMine keys / unreachable | 4,967 / 117 | 4,967 / 117 | 🟢 |
| `verify.py` A: recovered | 104 / 117 | 104 / 117 (repoint 104, keep 11, drop 2) | 🟢 |
| `verify.py` B: altered | 0 | 0 (4,967 untouched) | 🟢 |
| `verify.py` C: inert, no country | 5,084 | 5,084 | 🟢 |
| `verify.py` D: reported cases | 10 repointed, 6 dropped | 10 / 6 | 🟢 |

**ProcMine itself** (its own `compile_entities`, pinned polars 1.19.0): **4,967** state keys, **117** unreachable, `florida` → Q5307, Q6850 unreachable. Country table: **393** keys, **0** unreachable, **0** primary names resolving to another country. ProcMine's real state table is **identical** to `verify.py`'s model of it. `_selected_cols.pkl` gives `state_or_province: ['name']`; I read it with `pickletools` first (no code-executing opcodes). 🟢

### Line numbers in the Background, at `83f9b7b`

The upstream HEAD *is* `83f9b7b`, so these are checked against the current code. 🟢 for every row.

| claim | where | status |
|---|---|---|
| `CandidateEntity.from_dict` reads `normalized_uri` straight from the dict | `models/kg/candidate_entity.py:32-38` | ✅ |
| `LocationView.from_location` copies it into the view | `models/kgrel/custom_types/location.py:116`, states at 145-149 | ✅ (see the B2 note below) |
| `EntityDeserFn.read_state_or_province` | `etl/kgrel_entity.py:261` | ✅ one `StateOrProvince(id, name, country)` per row |
| `get_state_or_province_idmap()` "already hands it to the merge" | `services/kgrel_entity.py:101` | ⚠️ It *exists* on the entity service the merge holds, but **nothing in the merge calls it**. Its only caller is `api/routers/lod.py:153`. |
| ProcMine matcher | `procmine/converting/_attribute.py:152-161` | ✅ `unique_items` (155) holds only distinct observed strings; each is resolved once (158-159) via `entity2id(i, dict_all_entities[mi])`, with no country in scope |
| `from_sites` election | `models/kgrel/dedup_mineral_site.py:263-278` | ✅ |
| `from_dedup_sites` election | `models/kgrel/dedup_mineral_site.py:181-196` | ✅ |
| `prep_kgrel_input` calls `from_dedup_sites` | `etl/mineral_site.py:338` | ✅ (`MergeFn` calls `from_sites` at :436) |
| `RefListID` | `models/kgrel/custom_types/ref_value.py:49-52` | ✅ |
| merge cache | `etl/mineral_site.py:401` `merge-v106.sqlite` | ✅ (flagged, not changed) |

**Part B table:** all lines match (`mineral_site.py` :53, :61, :206, :226; `etl/mineral_site.py` :426; `public_mineral_site.py` :188; `geochem_loader.py` :83; `kgrel_entity.py` `get_crs_name` :72) **except `location.py:113`**. `from_location` is at **:116** (decorator at :115); line 113 is the end of `combine`.

---

## A1: is `observed_name` populated? (the gate)

State candidate nodes carrying a `normalized_uri`, all 418,313 in the raw JSON. 🟢

| matcher (`source`) | nodes | with `observed_name` | without | conflicted | conflicted, without |
|---|---:|---:|---:|---:|---:|
| UMN Matching System-ProcMinev2 | 300,045 | 300,045 | 0 | 5,668 | 0 |
| UMN Matching System v1 | 114,857 | 114,857 | 0 | 322 | 0 |
| **UMN Exact Match v1** | **1,839** | **0** | **1,839** | **25** | **25** |
| Inferlink Extraction v3 | 1,167 | 1,167 | 0 | 99 | 0 |
| SAND | 372 | 372 | 0 | 43 | 0 |
| curators (`jhammars`, `caknoblock`, `bvu`, `glederer`) | 28 | 28 | 0 | 0 | 0 |
| Inferlink Extraction v2 | 5 | 5 | 0 | 1 | 0 |
| **total** | **418,313** | **416,474** | **1,839** | **6,158** | **25** |

**On conflicted records, 25 / 6,158 = 0.4% would be dropped purely because `observed_name` is missing.** At the merged level, the fallback changes 22 / 5,856 entities (0.4%) from "state dropped" to "repointed". 🟢

All 25 are "UMN Exact Match v1" records whose exact-name match picked the wrong same-named state: Florida (Uruguay) for US Florida, San Juan (Puerto Rico) for Argentina's, Victoria (Malta), Central/Western Province (Zambia) for Papua New Guinea's. With the name fallback all 25 repoint, and I checked each by hand: right. 🟢

**Recommendation for B2:** the rule is safe as specified. The fallback is a small gain (+25 records), all of it correct and with no other effect, so I'd include it. Your call.

---

## A2: what the rule does to real records

**6,158** conflicted state candidates on **6,155** records collapse to **362** distinct `(observed_name, chosen state, recorded countries)` triples, and **70** triples cover 90% of the records. Florida alone is **1,609** (plus 65 more resolved to Florida, Uruguay). The full list, with each triple's outcome, is in `reports/p2/conflicted_triples.csv`. 🟢

| | records | % | with name fallback |
|---|---:|---:|---:|
| repointed | **5,146** | 83.6% | 5,171 (84.0%) |
| dropped | **1,012** | 16.4% | 987 (16.0%) |
| left alone | **0** | 0% | 0 |

"Left alone" is 0 by construction: every conflicted candidate either repoints or drops. The meaningful "left alone" is at the merged level:

| of the 5,856 conflicted merged entities | entities | % | with name fallback |
|---|---:|---:|---:|
| fixed: state repointed (consistent state after the rebuild) | **4,995** | 85.3% | 5,017 |
| fixed: state dropped (merged entity ends with no state) | **854** | 14.6% | 832 |
| still conflicted | **7** | 0.1% | 7 |
| *newly conflicted entities* | *0* | | *0* |
| *non-conflicted entities whose state changed* | *0* | | *0* |

**Hand-check:** 15 random repointed triples (seed 15) checked against the reference list, **15 / 15 right**. 🟢 They were Saida → Saïda (Algeria), Potosi → Potosí Department, Shiga → Shiga Prefecture, Granma → Granma Province, Sucre → Sucre (Venezuela), Yukon Territory → Yukon, Santa Cruz → Santa Cruz Department (Bolivia), Akita → Akita Prefecture, Santa Cruz → Santa Cruz (Argentina, not Cape Verde), Setúbal District → Setúbal, Hyogo → Hyōgo Prefecture, Isabela → Isabela (Philippines), Mpumalanga Province → Mpumalanga, Cordoba Province → Córdoba (Spain), Son La Province → Sơn La.

One category to watch: **62 records with observed state "Panama" in Panama are repointed to Panamá Province.** That's a legitimate reading, but the source may simply have repeated the country name. 🟡

**Why the 1,012 are dropped** (`reports/p2/breakdown.json`): 🟢

| reason | records | examples |
|---|---:|---|
| no state of that name in the recorded country | 793 | Orissa 187 (→ Odisha), Katanga 93 + 18, "Territory of New Caledonia" 49, Niedersachsen 43, Cartago 28 (table: "Provincia de Cartago"), Ekaterinburg 19, El Beni 16 (table: "Beni Department"), Greenland 15, Elazig 12 (table: "Elazığ"; dotless ı does not fold) |
| a **state code**, not a name | **179** | CO 50, CA 46, MN 16, ME 15, SD 12, MO 11, SC 10, AR 10 |
| no `observed_name` | 25 | (fixed by the name fallback) |
| ambiguous inside the country | 15 | |

---

## A3: upstream or merge-invented?

Of the **5,856** conflicted merged entities (local rebuild): 🟢

| `country.refid` vs `state_or_province.refid` | entities | % |
|---|---:|---:|
| same site (one record asserts the conflict: upstream) | **5,746** | 98.1% |
| different sites | **110** | 1.9% |
| ↳ the state's own record is itself conflicted | 104 | |
| ↳ the state's own record is consistent with its own country: **no record asserts the pairing** | **6** | 0.1% |

The 7 that survive the repair are those **6**, plus **1 the repair exposes**. An Inferlink record (Canada) had a wrong state; once that's dropped, the election falls through to an MRDS record's "Washington" and pairs it with Inferlink's Canada.

The 6 look like **dedup groups spanning countries** rather than election quirks: Portugal + British Columbia, Uganda + Alaska (×2), Solomon Islands + Roi Et (Thailand), Pakistan + Helmand (Afghanistan), New Zealand + Queensland. 🟡

A rough check of B3 (prefer the highest-ranked site carrying both country and state, using the merged site ranking): for all 6, the top site with both is consistent, so B3 would fix them. For the 104, the top site with both is itself conflicted, so B3 alone does nothing until the record is repaired. 🟡 (approximates B3; not the real implementation)

---

## A4: is "any country" too lenient?

| countries on the record | conflicted state candidates | all state candidates (418,313) |
|---|---:|---:|
| 0 | 0 (rule inert) | 1,013 |
| 1 | **6,158 (100%)** | 417,299 |
| 2 | 0 | **1** |
| 3+ | 0 | 0 |

The one two-country record (Inferlink, `b020`): countries Namibia + South Africa, both confidence 1, state Gauteng (South Africa). "Any" keeps it, which is correct. A "highest-confidence" test would pick Namibia (first listed among equals) and **drop a correct state**. 🟢

**Recommendation: keep "any".** The stricter test changes exactly one record in the corpus, and makes it worse.

---

## What in the brief turned out wrong or incomplete

1. **The live SPARQL endpoint can't be queried by GET** (nginx drops the query string; details above). The brief's endpoint works only by POST, which rule 2 rules out. 🟢
2. **"The cause is upstream, in ProcMine": the cause is mostly the fuzzy fallback, not shadowing.** 🟢 Of 6,158 conflicted records:
   - **3,610 (58.6%)** are ProcMine's **fuzzy fallback**: no exact key, so the best-scoring state *worldwide* wins with **no confidence floor** (`identify_entity_id`; Potosi → Porto, La Paz → La Pampa, Setúbal District → "Ba, Fiji").
   - **2,058 (33.4%)** are the **shadowing** the brief describes (exact key, first country in file order).
   - **490 (8.0%)** come from other matchers (UMN Matching System v1 322, Inferlink 100, SAND 43, UMN Exact Match v1 25).

   The rule fixes all three kinds whenever `observed_name` names a state in the recorded country. But the 104/117 entity metric only measures shadowing; it says nothing about 67% of the real conflicts.
3. **"`get_state_or_province_idmap()` already hands it to the merge"**: it's available to the merge but not called there (only `api/routers/lod.py:153` uses it). 🟢
4. **`location.py:113`** in the Part B table is **:116**. 🟢
5. **A3 framing: "different refid → no single record asserted it" overstates the second defect.** 104 of the 110 different-`refid` cases have a conflicted record behind them; only 6 are pure merge pairings. 🟢
6. **"Left alone"** is always 0 at the record level. It only means something at the merged level (7). 🟢
7. **"Sample it rather than cloning everything"**: I used the full 1.3 GB (see "How this was measured"). 🟢
8. Confirmed as stated: Florida ≈ 1,600 (1,609); "a few hundred distinct triples" (362, 70 cover 90%); ProcMine 4,967 / 117 / 393 / 0. 🟢 Not re-checked: the 7,869 CRS undercount. 🔴

## Side findings (not acted on)

- **State codes:** 179 dropped records are US postal codes ("CO", "CA", …). An exact `state_code` match inside the recorded country would recover them without any fuzziness. It's a design decision for Part B, not something I'd add silently. 🟢
- **`fold_name` limits** (spec unchanged; these cause drops, not wrong answers): Turkish dotless ı (Elazığ), Spanish admin words ("Provincia de Cartago"), and articles ("El Beni"). 🟢
- **ETL order can vary from run to run.** statickg's executor is `Parallel(return_as="generator_unordered")`, so `prep_kgrel_input` reads bucket files in completion order. Ties between equal-score partials, and the `dedup_sites[0]` fallbacks, can therefore differ between runs (🟢 by reading). I didn't run the ETL twice. What I observed is that my rebuild (sorted file order) matched the ETL's country/state exactly, but differed on `mineral_form` (68), `geology_info` (5) and `deposit_types` (1) `refid`s, which is this effect. 🟢
- **Merge cache:** this fix sits inside the same cached `MergeFn.invoke` and needs the `merge-v106` → `merge-v107` bump at `etl/mineral_site.py:401`, like P1/P4. Not changed here; the 1+4 PR should carry it. 🟢 (by reading)

---

## Everything that was run, verbatim

Pinned inputs: `upstream-p2` = ta2-minmod-kg `83f9b7b2580790b2c7e197610ae905bd23c49a74`; `data-p2` = ta2-minmod-data `3a086a5bb3507cd5ae4f8dd0d9fda0800c7eb244`; `upstream-procmine` = umn-ta2-database-processing `ce1ed703df7f05d453a6c85264374656b6a0acda`. All clones are read-only and unmodified (`git status` clean).

```bash
# A0
git clone https://github.com/usc-isi-i2/ta2-minmod-kg upstream-p2
git clone --depth 1 --filter=blob:none --sparse https://github.com/DARPA-CRITICALMAAS/ta2-minmod-data data-p2
git -C data-p2 sparse-checkout set data/entities
git -C data-p2 sparse-checkout add data/mineral-sites data/same-as
git clone --filter=blob:none https://github.com/DARPA-CRITICALMAAS/umn-ta2-database-processing upstream-procmine
ENTITY_DIR=data-p2/data/entities python3 reference/verify.py          # -> reports/p2/verify_baseline.txt
PYTHONPATH=upstream-procmine uv run --no-project --python 3.11 --with polars==1.19.0 \
  --with "geopandas>=1.0.1,<2" --with "pyarrow>=18.1,<19" --with "regex>=2024.11.6,<2025" \
  --with "strsimpy>=0.2.1,<0.3" --with "bs4>=0.0.2,<0.0.3" --with "requests>=2.32.3,<3" \
  python investigation/p2_procmine_tables.py data-p2/data/entities   # -> reports/p2/procmine_tables.txt

# live endpoint probes (GET only; both returned 404 "Service Description: /minmod/sparql")
curl -sS -G --max-time 60 -H "Accept: application/sparql-results+json" --data-urlencode 'query=PREFIX mo: <https://minmod.isi.edu/ontology/> SELECT ?p (COUNT(*) AS ?n) WHERE { ?ce ?p ?o . FILTER(?p IN (mo:state_or_province, mo:country, mo:observed_name, mo:normalized_uri, mo:source)) } GROUP BY ?p' https://minmod.isi.edu/sparql
curl -sS -G --max-time 60 -H "Accept: application/sparql-results+json" --data-urlencode 'query=ASK {}' https://minmod.isi.edu/sparql/

# environment (upstream-p2's poetry.lock; pygraphviz/erdantic are doc-only and skipped)
uv venv -p 3.11 .venv-p2
(cd upstream-p2 && uvx --from poetry==1.8.5 poetry export --without-hashes --with dev -f requirements.txt | grep -vE '^(pygraphviz|erdantic)' > /tmp/req-p2.txt)
uv pip install -p .venv-p2/bin/python -r /tmp/req-p2.txt && uv pip install -p .venv-p2/bin/python --no-deps -e upstream-p2
export CFG_FILE=upstream-p2/tests/resources/config.yml

# A1, A2, A4 (record level) -> reports/p2/records_summary.json, conflicted_triples.csv, conflicted_candidates.jsonl
.venv-p2/bin/python investigation/p2_records.py data-p2/data
python3 investigation/p2_breakdown.py                                   # -> reports/p2/breakdown.json

# local merged entities (upstream's three ETL stages, verbatim, offline, no loaders) -> kgdata-p2/
.venv-p2/bin/python investigation/p2_run_etl.py investigation/p2_etl.yml kgdata-p2 data-p2
# A3 + merged-level A2 -> reports/p2/merged_summary.json
.venv-p2/bin/python investigation/p2_merged.py kgdata-p2/data
# SPARQL for the live graph, checked locally -> reports/p2/sparql_check.json
.venv-p2/bin/python investigation/p2_sparql_check.py
```

**SPARQL to re-run on the live graph** (needs a read-only POST, which this run did not send): `investigation/sparql/a1_observed_name_by_matcher.rq`, `a1_conflicted_observed_name_by_matcher.rq`, `a2_conflicted_triples.rq`, `a4_country_count.rq`. Every optional field uses `OPTIONAL` + `BOUND`. The gate query:

```sparql
PREFIX mo: <https://minmod.isi.edu/ontology/>
SELECT ?source (COUNT(*) AS ?nodes) (SUM(?has) AS ?with_observed_name)
       (COUNT(*) - SUM(?has) AS ?without_observed_name)
WHERE {
  SELECT ?ce (SAMPLE(?s) AS ?source)
         (MAX(IF(BOUND(?obs) && STRLEN(STR(?obs)) > 0, 1, 0)) AS ?has)
  WHERE {
    ?li mo:state_or_province ?ce .
    ?ce mo:normalized_uri ?uri .
    OPTIONAL { ?ce mo:source ?s }
    OPTIONAL { ?ce mo:observed_name ?obs }
  }
  GROUP BY ?ce
}
GROUP BY ?source
ORDER BY DESC(?nodes)
```

## Commits, and what is not done

- **Commits.** Both commits the brief asks for were made in order, after Aditi confirmed in chat: `Problem 2: brief and reference implementation` (only `P2_RUN.md` and `reference/`), then `Problem 2: investigation findings`. They were pushed to `adi05b/minmod_data_issues` only. Nothing was pushed to any ISI or DARPA repo, and no PR was opened.
- **Part B.** Not started. No file under `upstream-p2/` has been edited.
