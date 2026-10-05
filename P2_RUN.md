
# Problem 2 — investigate, then fix (state in the wrong country)

*Aditi Bombe · USC ISI. Paste this whole file into Claude Code Desktop.*

---

## Setup — do this first, before anything else

Three files are sitting in my Downloads folder. Move them into the repo:

```bash
cd ~/minmod_data_issues          # adjust if my clone is somewhere else; find it first
git pull
mkdir -p reference

cp ~/Downloads/P2_RUN.md              ./P2_RUN.md
cp ~/Downloads/state_repair.py        ./reference/state_repair.py
cp ~/Downloads/verify.py              ./reference/verify.py

ls -la reference/ && head -5 reference/state_repair.py
```

If a file is not in `~/Downloads`, search for it (`ls ~/Downloads | grep -i state`) — browsers sometimes append ` (1)` or `.txt`. Report the exact filenames you found. **Do not proceed until all three are in place.**

`reference/state_repair.py` is a tested implementation of the repair rule and `reference/verify.py` is the harness that produced the numbers quoted below. **Use them as the specification.** Do not rewrite the logic from scratch; port it, keep the behaviour identical, and if you believe something in it is wrong, say so and stop rather than silently changing it.

Commit the three files as their own commit before doing anything else, so the starting point is on the record:

```bash
git add -A && git commit -m "Problem 2: brief and reference implementation" && git push origin main
```

---

## Rules for this whole run

1. **Never push to, or open a PR against, any `usc-isi-i2` or `DARPA-CRITICALMAAS` repo.** Clone them read-only. Push only to `adi05b/minmod_data_issues`.
2. **Read-only against the live graph.** `SELECT` only. No SPARQL `UPDATE`, no `INSERT`, no POST to any endpoint, no writes to Postgres.
3. **Tag every finding** 🟢 verified by running it · 🟡 likely · 🔴 assumed. A number you did not compute yourself is not 🟢.
4. **Stop and report on failure.** Do not work around a blocked step.
5. **There is a hard stop at the end of Part A.** Do not edit a single line of pipeline code before I have read the Part A report and told you to continue.
6. Never disable TLS verification.
7. `data/` and `upstream*/` stay gitignored. Adriana's spreadsheets are client-supplied and are not committed.

---

## Background — what is already established

Verified today against source and the real reference tables 🟢:

- **MinMod does no entity normalization.** `CandidateEntity.from_dict` (`minmodkg/models/kg/candidate_entity.py`) reads `normalized_uri` straight from the source JSON; `LocationView.from_location` copies it into the view. The wrong state is passed through, not computed here.
- **The cause is upstream, in ProcMine** (`umn-ta2-database-processing`). `compile_entities` lowercases the key columns and `non2dict` keeps the *first* row per name, from a file sorted by country A→Z. `_selected_cols.pkl` gives `state_or_province: ['name']` — no country. Result: **4,967 lookup keys from 5,084 rows, so 117 state entities are unreachable.** `florida` → `Q5307` (Puerto Rico); `Q6850` (United States) is absent from that table entirely.
- **ProcMine cannot be fixed with a parameter.** At `procmine/converting/_attribute.py:152-161` the matcher iterates `unique_items`, a list of distinct observed strings with `record_id` **already dropped**. Each string is resolved once for the whole dataset. The record's country is not in scope at all.
- **But MinMod holds the full table.** `EntityDeserFn.read_state_or_province` (`minmodkg/etl/kgrel_entity.py:261`) builds one `StateOrProvince(id, name, country)` per row — all 5,084, nothing shadowed — and `EntityService.get_state_or_province_idmap()` already hands it to the merge. So the choice can be repaired at merge time with no ProcMine release and no re-extraction.
- **Country is the trustworthy half.** ProcMine's country table: 250 countries, 393 keys, **0 unreachable, 0 primary names resolving to another country.** That is why the rule repairs the state and never the country.
- **The repair rule, measured against the reference tables:** 104 of 117 shadowed entities recovered, **0 of 4,967 correct assignments altered**, inert when no country is recorded. Ten of Adriana's named cases repoint correctly (Florida → Q6850, La Paz → La Paz Department, and so on).
- **A second, separate defect.** `minmodkg/models/kgrel/dedup_mineral_site.py` elects `country` and `state_or_province` in two independent `next(...)` scans — `from_sites` lines 263-278 and `from_dedup_sites` lines 181-196. Nothing ties them to the same site, so a merged entity can pair a country from site A with a state from site B. `from_dedup_sites` is the one `prep_kgrel_input` calls.

**Confirm each of the line numbers above against the real files and say so if any has moved.** They were read at `ta2-minmod-kg@83f9b7b`.

---

# PART A — investigation. No code changes.

The repair above was measured against two reference CSVs. **No real record was ever looked at.** Part A closes that gap. Four questions, in order of how badly a wrong answer would hurt.

## A0 — Clone what you need, read-only

```bash
git clone https://github.com/usc-isi-i2/ta2-minmod-kg upstream-p2
cd upstream-p2 && git rev-parse HEAD && cd ..

git clone --depth 1 --filter=blob:none --sparse \
  https://github.com/DARPA-CRITICALMAAS/ta2-minmod-data data-p2
cd data-p2 && git sparse-checkout set data/entities && cd ..
```

Confirm `data-p2/data/entities/state_or_province.csv` has 5,084 rows and `country.csv` has 250. Then reproduce the three baseline numbers with `reference/verify.py`:

```bash
ENTITY_DIR=data-p2/data/entities python3 reference/verify.py
```

Expect **4,967** keys, **117** unreachable, **104/117** recovered, **0** altered. **If any number differs, stop and report** — the reference list has drifted and everything downstream needs rechecking.

The live SPARQL endpoint is `https://minmod.isi.edu/sparql`. If it is unreachable from this machine, say so and fall back to the raw site JSON in `ta2-minmod-data` (sparse-checkout `data/mineral-sites`, which is large — sample it rather than cloning everything).

## A1 — Is `observed_name` actually populated? **This is the gate.**

The repair re-resolves the record's own `observed_name` inside the recorded country. **If that field is empty, the rule drops the state instead of repairing it.** ProcMine sets it (`"observed_name": entity_name` in `entity2id`), but it is not the only matcher — UMN Matching System v1, SRI and the Inferlink LLM path all emit candidates. Earlier in this project a non-OPTIONAL `:observed_name` query silently dropped **7,869** nodes on the CRS field, so this field is demonstrably not universal.

Count state candidate nodes carrying a `:normalized_uri`, split by whether `:observed_name` is present, **grouped by `:source`** (the matcher name). Use `OPTIONAL` and `BOUND`, never a plain triple pattern — that is the exact mistake that produced the 7,869 undercount.

Report a table: matcher · nodes with a normalized state · how many have `observed_name` · how many do not.

**Then state plainly: on conflicted records specifically, what fraction would be dropped rather than repaired purely because `observed_name` is missing?**

This decides whether the fix is safe. A rule that quietly empties the state field on a large share of records trades a visible wrong answer for an invisible missing one, which is worse. If the missing-`observed_name` share on conflicted records is material, say so in one sentence at the top of the report and recommend falling back to the chosen state's own *name* as the lookup key, measuring that variant too.

## A2 — How many of the 5,858 does the rule actually fix?

The 104/117 is *entities in a reference table*. Adriana's 5,858 is *merged records*. Nobody has connected the two. Florida alone was roughly 1,600 rows.

1. Pull every conflicted case as distinct triples of **(observed_name, chosen state id, recorded country ids)** with a record count each. A few hundred distinct triples should cover the large majority of rows.
2. Run `reference/state_repair.py` over exactly those triples offline.
3. Report, **weighted by record count**: repointed · dropped · left alone, as counts and as a percentage of the total.

That percentage is the headline of this investigation. Write it as "the rule repoints N records, drops M, leaves K untouched" — not as a vague share.

Hand-check **15** of the repointed cases against the reference list yourself and say how many are genuinely right. Report the ones that are not.

## A3 — How big is the second defect (merge-invented pairings)?

`RefListID` carries a `refid` — the site each elected value came from (`minmodkg/models/kgrel/custom_types/ref_value.py:49-52`). So this is directly measurable on merged entities.

For conflicted merged entities, compare `country.refid` with `state_or_province.refid`:

- **different** → merge invented the pairing. No single record asserted it. This is the `dedup_mineral_site.py` defect, fixable without touching the state lookup at all.
- **same** → the conflict was already present on one record. Upstream ProcMine defect.

Report the split as counts and percentages. This number has never been measured and it decides which of the two fixes matters more.

The reprojected/normalized values live in **Postgres `kgrel`**, not in RDF. If you cannot reach Postgres, say so and derive what you can from the merged JSON in a local ETL output, or mark A3 🔴 unmeasured rather than estimating.

## A4 — How often is `country` a list?

`location_view.country` is a list — a record can carry several countries. The rule treats a match against **any** of them as agreement, which may be too lenient.

Report the distribution of how many countries conflicted records carry (1, 2, 3+), and for the multi-country ones, whether the chosen state matches any of them. If multi-country records are common, say whether "any" or "the highest-confidence one" is the better test, with the counts behind the recommendation.

## A5 — Write it up, then STOP

Write `reports/P2_INVESTIGATION.md`:

1. **The gate answer from A1, in the first three lines.** Safe to proceed, or not.
2. The A2 headline: records repointed, dropped, left alone.
3. The A3 split: upstream vs merge-invented.
4. The A4 recommendation.
5. Every query you ran, verbatim, so it can be re-run.
6. Anything in this brief that turned out wrong.

Then:

```bash
git add -A && git commit -m "Problem 2: investigation findings" && git push origin main
```

**Now stop.** Print the four headline numbers in the chat and wait. Do not start Part B. Do not edit any file under `upstream-p2/`.

---

# PART B — implementation. Only after I say go.

Do not read this as instructions to act on now. It is here so the whole plan is in one file.

## B1 — The repair module

Port `reference/state_repair.py` to `upstream-p2/minmodkg/misc/state_repair.py`. Match the repo's style — `from __future__ import annotations`, type hints, stdlib only (`re`, `unicodedata`), no new dependencies.

Behaviour must stay identical. In particular, **the two-tier match order is load-bear, not a nicety**: exact folded name first, then administrative words dropped. A single admin-word-free tier drops **135** currently-correct assignments, because Albania holds both "Berat County" and "Berat District" and 70 other countries have the same shape. And **`resolve` must never return a best-effort guess** — more than one hit returns `None`.

## B2 — Wire it in

Thread one parameter down the chain, **defaulting to `None`** so every change is additive and no existing call site breaks:

| file | line | change |
|---|---|---|
| `minmodkg/services/kgrel_entity.py` | near `get_crs_name` (:72) | cached `get_state_or_province_index()`, built from `get_state_or_province_idmap().values()` |
| `models/kgrel/custom_types/location.py` | :113 | `from_location(location, crss, state_index=None)` + apply the rule |
| `models/kgrel/mineral_site.py` | :206 | `MineralSite.from_raw_site(..., state_index=None)`; pass through at :226 |
| `models/kgrel/mineral_site.py` | :53 | `MineralSiteAndInventory.from_raw_site(..., state_index=None)`; pass through at :61 |
| `etl/mineral_site.py` | :426 | pass the index from `FileEntityService` |
| `api/models/public_mineral_site.py` | :188 | pass it |
| `etl/geochem_loader.py` | :83 | pass it |

Per state candidate: leave untouched if there is no index or no recorded country; leave untouched if the state's country is among the recorded countries; otherwise re-resolve `observed_name` within the recorded countries and repoint on a unique hit, drop otherwise.

**Repair the state, never the country** (A0 established country has no shadowing).

**Do not mutate `location`.** The raw `Location` is what `to_kg()` serialises to RDF, and the triple store must keep carrying the source's `observed_name` for curators. Only `location_view` changes. Confirm in the report that you managed this.

Apply whatever A1 concluded about the `observed_name` fallback.

## B3 — The two-pass election

Both places: `dedup_mineral_site.py` lines **263-278** (`from_sites`, over `rank_sites`) and lines **181-196** (`from_dedup_sites`, over `rank_dedup_sites`, where the fields are `site.country.value` / `site.state_or_province.value`).

Prefer the highest-ranked site carrying **both** a country and a state; fall back to the two existing independent scans only when no single site has both. **Keep the existing fallbacks byte-for-byte** — this is a preferred branch in front of them, not a rewrite.

## B4 — Tests

`tests/test_p2_repair.py`, driven off the real CSVs. Four blocks, report every number:

- **A. Recovery** — 117 shadowed entities: expect **104 repointed**, 11 kept, 2 dropped. The 11 are same-named states inside one country, where a country-based rule has nothing to discriminate on; say that rather than calling them failures.
- **B. Regression — the gate.** Every assignment ProcMine already gets right must be untouched: **4,967 untouched, 0 altered.** One alteration fails the run.
- **C. Inert** — with no recorded country, all **5,084** untouched.
- **D. The reported cases** — assert all sixteen from `reference/verify.py`, ten repointed and six dropped. Four of the six drops are correct: Spain's table is provinces so there is no Andalusia in it, Odisha replaced Orissa, Katanga was split in 2015, and Elko is a county.

`tests/test_p2_dedup_pairing.py`: two constructed sites — A with country=US and no state, B with country=Mexico and state=Sonora. Assert the old code pairs US with Sonora and the new code takes both from B. Then assert a group where one site carries both is unchanged.

Run the upstream suite and report any failure, plus whether it also failed before the change — check by stashing.

## B5 — Do not add fuzzy matching

A third tier matching inside the recorded country would catch `Michoacan → Michoacán de Ocampo` and `Valle D'Aosta → Aosta Valley`. **Do not add it.** Reproduce this table and stop:

```
Michoacan      -> Michoacán de Ocampo   0.7269   want
Katanga        -> Haut-Katanga          0.7526   one of four successors
Valle D'Aosta  -> Aosta Valley          0.5713   want
Orissa         -> Odisha                0.5425   want
Andalusia      -> Canarias              0.5032   wrong
Elko County    -> Puerto Rico           0.3711   wrong
```

Right and wrong answers interleave, and that is six data points. **Picking a threshold from a handful of examples is the exact mistake made on the commodity floor**, where 0.90 looked right on four examples and turned out to destroy 32,324 correct mappings; the corpus answer was 0.62. Say the floor is unset and why.

## B6 — The alias gap

`state_or_province.csv` columns are `minmod_id, id, name, country_id, country_code, country_name, state_code, type, latitude, longitude` — **no aliases column**, though `country.csv` has `alt names`. Adding one would fix the name-variant misses as data: `Michoacan` → Michoacán de Ocampo, `Valle d'Aosta` → Aosta Valley, `Orissa` → Odisha.

Scope it, do not build it. It lands in `ta2-minmod-data`, a different repo.

## B7 — Acceptance queries

`acceptance/problem2_state_country_conflict.sql` — counts merged entities whose state's country is in none of the entity's countries. Comment the before number: **5,858**. **SQL, not SPARQL** — normalized ids live only in Postgres and this fix deliberately leaves RDF unchanged.

It will not reach zero while the 11 same-country collisions and the alias gap remain. State the expected floor from A2 rather than claiming zero. Add a second query listing surviving conflicts grouped by `(observed_name, country)` for triage.

## B8 — Report, commit, no PR

`reports/FIX_P2_REPORT.md`: lead with where the fix lives and why ProcMine was rejected; both diffs in full with the upstream SHA; the A/B/C/D table; the B5 fuzzy table with the floor left unset; the B6 follow-up; and anything in this brief that turned out wrong.

```bash
git add -A && git commit -m "Problem 2: merge-time state repair, dedup pairing fix, tests" && git push origin main
```

Confirm nothing was pushed to any ISI or DARPA repo and no PR was opened.

---

## One thing to flag, not fix

Problems 1 and 4 need the merge cache bumped — `merge-v106.sqlite` → `merge-v107.sqlite` at `minmodkg/etl/mineral_site.py:401` — because `MergeFn.invoke` is keyed on input file paths and content hashes, and the code is not part of the key. **This fix sits inside the same cached function and needs the same bump.** The 1+4 PR is not raised yet and should carry it. Note it in the report; do not change that line here, or the two PRs will conflict on it.
