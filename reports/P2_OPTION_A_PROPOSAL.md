# Option A: dependency mapping. Investigation and proposal only

*2026-10-09. Nothing here is implemented. Approval comes before any code.*

Amandeep's decision, as a **mapping, not a correction**: when the recorded country is the sovereign state and the state field names one of its dependencies that has its own entry in `country.csv`, the record's country becomes that dependency, and the state is left empty. New Caledonia's three provinces (Q4823–Q4825) will be filled from coordinates later, not now.

## What the scan found

`investigation/p2d_dependency_scan.py` checks every state candidate of every record with a recorded country, 418,313 candidates and whether or not ProcMine chose a state for it, against `country.csv`.
- **What it matches:** country names and `alt names`, folded. ISO codes are left out: "CO" is a Mexican abbreviation, not Colombia.
- **Match levels**, strictest first:
  - exact;
  - after dropping administrative words ("Territory Of Christmas Island");
  - the same set of words ("British Virgin Islands" against "Virgin Islands (British)");
  - a two-or-more-word country name inside the observed name ("Territory Of New Caledonia **And Dependencies**").
- **What it ignores:** matches to a recorded country of the same record.
- **"Today"** is what the code and table as they would ship (fix/p2-state-repair, fork branch) do with each candidate.

**15 groups, 3,777 records** (`reports/p2d/dependency_scan.csv`). They fall into four kinds:

| kind | recorded | observed state | names the country | match | records | today |
|---|---|---|---|---|--:|---|
| **A. dependency, no state row under the sovereign** | France | Territory Of New Caledonia And Dependencies | New Caledonia | contains | 49 | dropped 49 |
| | Denmark | Greenland | Greenland | exact | 82 | dropped 15, no state chosen 67 |
| | Australia | Territory Of Christmas Island | Christmas Island | admin words | 5 + 1 | dropped 5, no state chosen 1 |
| | United Kingdom | Montserrat | Montserrat | exact | 3 | dropped 3 |
| | United Kingdom | British Virgin Islands | Virgin Islands (British) | word set | 2 | dropped 2 |
| | United Kingdom | Cayman Islands | Cayman Islands | exact | 1 | dropped 1 |
| **B. dependency, but the sovereign has a state row of that name** | United States | Puerto Rico | Puerto Rico | exact | 731 | kept: Q6889 Puerto Rico (US) |
| | France | Department Of Guiana [French Guiana] | French Guiana | word set | 166 | kept: Q3262 French Guiana (France) |
| | France | Department Of Guadeloupe | Guadeloupe | admin words | 36 | kept: Q3269 Guadeloupe (France) |
| | France | Department Of Martinique | Martinique | admin words | 6 | kept: Q3301 Martinique (France) |
| | France | Territory Of French Polynesia | French Polynesia | admin words | 1 | kept: Q3263 French Polynesia (France) |
| **C. disputed, not a dependency** | Serbia | Kosovo | Kosovo | exact | 2 | no state chosen |
| | Morocco | Western Sahara | Western Sahara | exact | 1 | no state chosen |
| **D. a real state that shares a country's name** | United States | Georgia | Georgia | exact | 2,691 | kept: Q6851 Georgia (US) |

**Wrong recorded country: none in this scan.** The cases Amandeep named are not country names, so a mapping keyed on country names cannot reach them: Alaska under Canada, Piura under Brazil, Ch'ungch'ong-bukto/-namdo under North Korea or DR Congo. That is true by construction, not by luck, as long as the mapping is the explicit list below. They stay dropped (`reports/p2c/alias_candidates.csv`, "no suggestion").

**Kind A is what Option A is for: 143 records.**
- They cover all 72 blocked records: New Caledonia 49, Greenland 15, Christmas Island 5, Montserrat 3.
- They also take the 3 UK records that were "no suggestion": British Virgin Islands 2, Cayman Islands 1.
- **And 68 records that have no state today:** Greenland 67 and Christmas Island 1, where ProcMine matched no state at all. Their country is Denmark or Australia today, and Option A as worded moves it too. Only one Greenland group is blocked; the other 67 Greenland records were never in a drop list, so they need an explicit yes or no.

**Kind B is why the wording needs one more condition.**
- **The problem:** "the state field names one of its dependencies that has its own entry in country.csv" is also true of 940 records that resolve correctly today. Puerto Rico is both a US state row (Q6889) and a country (Q1177), and the same holds for French Guiana, Guadeloupe and Martinique (France's overseas departments are integral parts of France). The table models these places both ways. Moving them changes how MinMod models them, which is a choice of its own, not a repair.
- **The same shape elsewhere:** the table has 16 such rows in all; the scan found records only for these five. Others are China → Taiwan, Finland → Åland, the UK's Saint Helena and the US's Guam.
- **Recommendation:** Option A applies only where the sovereign has **no** state row for the dependency. That holds for all six kind-A pairs and none of kind B.

**Kinds C and D are why it must not be a rule.**
- **Rule 1, "a state name equal to another country's name":** moves 2,691 Georgia (US) records to the country of Georgia, plus Puerto Rico, the French departments, Kosovo and Western Sahara.
- **Rule 2, "only when the state resolves to nothing":** still moves Kosovo and Western Sahara, which are disputed, not dependencies.

## How to define it: an explicit list (recommended)

```text
(sovereign, dependency)            country ids     state row under sovereign?
(France, New Caledonia)            Q1075 -> Q1154  no
(Denmark, Greenland)               Q1059 -> Q1086  no
(Australia, Christmas Island)      Q1013 -> Q1045  no
(United Kingdom, Montserrat)       Q1234 -> Q1146  no
(United Kingdom, Cayman Islands)   Q1234 -> Q1040  no
(United Kingdom, Virgin Islands (British))  Q1234 -> Q1243  no
```

Why a list and not a rule:
- **Bounded:** it can't reach kinds B, C or D, and each pair has records behind it.
- **Reviewable and testable:** a test can check that every pair exists in `country.csv` and that the sovereign has no state row for the dependency. That keeps kind B from creeping in later.
- **Pairs grow by review**, the same way aliases do.

**Matching the state field to the dependency:**
- Use the dependency's `country.csv` name and alt names, with the state repair's own exact and admin-word-dropped tiers, and nothing looser.
- Two of the six only matched loosely in the scan. Rather than putting word-set or substring matching in code, add two country alt names in `country.csv`: "Territory of New Caledonia and Dependencies" on New Caledonia, and "British Virgin Islands" on Virgin Islands (British).
- Side effect of those alt names: ProcMine reads `country.csv` alt names for its own country matching, and `/api/v1/countries` serves them. Both effects look correct, but they're visible.
- The alternative is to keep those two strings next to the pairs in code.

**Where the list would live (recommended):** a constant next to the state repair (`minmodkg/misc/state_repair.py`, or a small sibling module), keyed by country `minmod_id` with names in comments. The alternative is a "sovereign" column in `country.csv`. That would make every one of the ~50 territories eligible, including kind B (Puerto Rico, the French departments, Taiwan), unless exclusions were added. It's a bigger data change for the same six pairs.

**Where it would run:** `LocationView.from_location` (`minmodkg/models/kgrel/custom_types/location.py`), where `view.country` is built and the state repair already runs.
- **When:** before the repair, for each state candidate whose observed name names a listed dependency of a recorded country.
- **What it does:** replace that sovereign with the dependency in `view.country`, and leave that candidate out of `view.state_or_province`.
- **Candidates without a state:** it must look at every candidate with an observed name, including those where ProcMine set no `normalized_uri` (the 68 above), which the repair loop skips today.
- **Then:** the existing repair runs against the updated countries.
- **`location` (what goes to the KG) is untouched,** as with the repair.
- **Across paths:** country names and alt names are in Postgres as well (`Country.aliases`, which also holds ISO codes; match only entries longer than three characters). So unlike state aliases, this behaves the same on the API, ETL and GeoChem paths.
- **Merged entities:** the merged entity's country then comes from the election in `dedup_mineral_site.py` (9d68111). It prefers a record carrying both a country and a state; mapped records carry no state, so mixed entities fall back to the separate scans. Counts are below.

## What it changes downstream

- **It is the first change to the country field.** Part B and Phase 5 both measured zero "country value changed" on merged entities (`p2b_compare.py`, `p2d_compare.py`). Option A makes those counts non-zero by design, so every note that says the merged country is unchanged has to change. I could not find the literal "merged_with_country UNCHANGED" in either repo; the closest are `acceptance/problem2_state_country_conflict.sql` ("this fix deliberately leaves the RDF unchanged") and the compare reports' zero country changes. Can you point me to the note you mean?
- **Merged country counts move.** France, Denmark, Australia and the United Kingdom lose merged entities to New Caledonia, Greenland, Christmas Island, Montserrat, Cayman Islands and Virgin Islands (British). The counts come from run B and are in the next section.
- **KG and Postgres diverge on country for these records.** The KG keeps the source's country (France) and Postgres and the API say New Caledonia. That's the same design as the state repair, but country is a more visible field: API filters (`?country=France`) and any per-country totals move with Postgres, while SPARQL does not.
- **New Caledonia entities have no state** until the coordinate fill.
- **Acceptance query 1** (a state in none of the entity's countries) is unaffected: mapped records carry no state.
- **Cache:** it sits inside the cached merge, so it needs the same merge-cache bump (v108 or later) and the same deploy order. The two country alt names, if added, change `country.csv` and re-run its transform. Its output shape is unchanged.

## Merged-entity impact (run B)

*Pending: counted from run B's merged output when the ETL runs above finish.*
