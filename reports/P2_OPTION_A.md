# Option A: the dependency mapping

*2026-10-09. Proposed, then decided by Amandeep, then implemented.*
- *The four starting pairs: `patches/0005-problem-2-dependency-mapping.patch`, now on `fix/p2-state-repair` as `f01a385` (pushed by Aditi).*
- *The two approved UK pairs: `patches/0006-problem-2-uk-dependencies.patch`, on top of `f01a385`. The push to usc-isi-i2 is refused here.*

## The decision

It is a **mapping, not a correction**:
- **When:** the recorded country is the sovereign, and the state field names one of its dependencies that has its own entry in `country.csv`.
- **Then:** the record's country becomes the dependency, and the state is left empty.
- **The list is explicit:** (sovereign, the names a state field uses for the dependency) → the dependency's country. **There is no general name-matching rule.**
- **Only for drops:** it applies only to records the repair would otherwise drop, a contradiction with no match inside the recorded country. It never touches a record that resolves today.
- **The list starts with four pairs:** New Caledonia/France, Greenland/Denmark, Christmas Island/Australia, Montserrat/United Kingdom. Any other pair from the dropped list is shown for approval before it is added.
- **Approved afterwards:** British Virgin Islands/United Kingdom and Cayman Islands/United Kingdom (patch 0006).
- **Explicit exclusions:** China/Taiwan, and every homonym (Georgia, Niger, Luxembourg, Mali).
- New Caledonia's three provinces (Q4823–Q4825) will be filled from coordinates later, not now.

## The implementation (`f01a385` + patch 0006)

**`minmodkg/misc/state_repair.py`:**
- **The list:** `DEPENDENCIES`, the reviewed pairs, keyed by country `minmod_id` and matched on the **exact folded name** only:

  | sovereign | dependency | names |
  |---|---|---|
  | France `Q1075` | New Caledonia `Q1154` | "New Caledonia", "Territory of New Caledonia and Dependencies" |
  | Denmark `Q1059` | Greenland `Q1086` | "Greenland" |
  | Australia `Q1013` | Christmas Island `Q1045` | "Christmas Island", "Territory of Christmas Island" |
  | United Kingdom `Q1234` | Montserrat `Q1146` | "Montserrat" |
  | United Kingdom `Q1234` | Virgin Islands (British) `Q1243` | "British Virgin Islands", "Virgin Islands (British)" (0006) |
  | United Kingdom `Q1234` | Cayman Islands `Q1040` | "Cayman Islands" (0006) |

- **The exclusions:** `NOT_DEPENDENCIES`, which is China/Taiwan, United States/Georgia, Nigeria/Niger, Belgium/Luxembourg and Guinea/Mali (Mali Prefecture). Building an index whose list contains any of them raises an error.
- **The check:** `StateCountryIndex.dependency(state, observed_name, countries)` returns (sovereign, dependency) **only if `repair()` would drop** that candidate and its observed name is a listed name of a recorded sovereign. Otherwise it returns None. `resolve()` and `repair()` are unchanged.

**`minmodkg/models/kgrel/custom_types/location.py`:**
- **Where:** in `from_location`, a dropped candidate that `dependency()` maps replaces its sovereign with the dependency in `view.country`. The state stays dropped.
- **Order:** every candidate is decided against the recorded countries first, then the moves are applied, so the order of a record's candidates cannot matter.
- **The KG is untouched:** `location`, which goes to the KG, keeps the source's country, as with the repair.
- **Every path:** the list is code, not data, so the API save path and the GeoChem loader behave the same as the ETL merge.

**Tests:** `tests/misc/test_state_repair.py`, 23 in all, 10 of them for Option A (0006 adds a test of one sovereign with several dependencies).
- It maps only a drop: never a state that resolves, never a record without a contradiction.
- It needs the exact listed name, and the sovereign recorded.
- The excluded pairs cannot be listed.
- **On the real table** (`MINMOD_ENTITY_DIR`): each pair names two countries of `country.csv`, and no listed name resolves inside its sovereign. That keeps out places the table also models as the sovereign's own state rows: Puerto Rico, Guadeloupe and the like. No state's own name ever triggers a move.
- One end-to-end test through `LocationView.from_location`: a record with France and Colombia → New Caledonia and Colombia, state empty, `location` unchanged.
- All 23 pass on the fixture and on the fork's table. The repo's other tests are unchanged: 15 failed and 27 errors before and after, all pre-existing (a vendored file missing here, and Docker).

## Proof: zero regressions

**Records** (`investigation/p2d_option_a_measure.py` → `reports/p2d/option_a_records.json`). Every record with a location, **451,526**, is viewed through MinMod's own `LocationView.from_location`: with the list empty (the alias-pass behaviour), with the four pairs of 0005, and with all six:
- **State candidates whose repair outcome changes: 0 of 418,313.**
- **Records whose view changes: 75.** These are the 72 blocked records plus the 3 UK records approved afterwards:

  | pair | records |
  |---|--:|
  | France, "Territory Of New Caledonia And Dependencies" → New Caledonia | 49 |
  | Denmark, "Greenland" → Greenland | 15 |
  | Australia, "Territory Of Christmas Island" → Christmas Island | 5 |
  | United Kingdom, "Montserrat" → Montserrat | 3 |
  | United Kingdom, "British Virgin Islands" → Virgin Islands (British) (0006) | 2 |
  | United Kingdom, "Cayman Islands" → Cayman Islands (0006) | 1 |

- Each of the 75 changes only by one listed sovereign becoming its dependency. Its states are unchanged, and one of its candidates is a drop naming that dependency (asserted for every record).
- The other 451,451 records are identical.
- **Patch 0006 on its own:** between the four-pair and six-pair lists, **exactly 3 records change**: United Kingdom → Virgin Islands (British) 2, → Cayman Islands 1. Each is asserted to be one of the two added pairs.
- Records the repair does not drop are not touched, as decided:
  - the 67 Denmark records that name Greenland but where ProcMine matched no state;
  - the Australia record with no state chosen;
  - Puerto Rico (731), French Guiana (166), Guadeloupe (36), Martinique (6), French Polynesia (1);
  - Georgia (2,691), Kosovo, Western Sahara.

**Merged entities** (runs in [P2_PHASE5.md](P2_PHASE5.md)):
- **Patch 0005** (run C against run B): 71 entities have different inputs.
  - **70 change country:** France → New Caledonia 48, Denmark → Greenland 15, Australia → Christmas Island 4, United Kingdom → Montserrat 3.
  - **1 keeps Australia:** a Christmas Island record shares its entity with an Australia / Western Australia record that the election prefers.
- **Patch 0006** (run D against run C, `reports/p2d/merged_uk_dependencies.json`): exactly 3 entities have different inputs, and all 3 change country: United Kingdom → Virgin Islands (British) 2, → Cayman Islands 1.
  - All 3 were conflicted in the baseline (UK with US Virgin Islands or Cat Island, The Bahamas, as the state) and already emptied by the repair.
- **Together:** 73 entities change country, with **0 state changes and 0 newly conflicted.**

## The same shape in the dropped list: done

The two other dropped groups with this shape were shown for approval and approved, and are now in the list (patch 0006): British Virgin Islands (2 records) and Cayman Islands (1). Both are British Overseas Territories, with their own `country.csv` entries and no UK state row.
- **Nothing else in the dropped list has this shape.**
- "Netherlands Antilles" (Netherlands, 3) names a territory dissolved in 2010 into several, and it has no single `country.csv` entry.
- "Hong Kong Special Administrative Region" (China) now resolves to China's own Hong Kong SAR row through its approved alias.

## The acceptance note that has to change

`run_acceptance.sh` is on the PR #108 branch (`fix/reproject-always-xy`, `2b9fb49`), not on this branch, which predates #108. Its expected-results notes (lines 99–106) say:

```text
  merged_with_country          UNCHANGED     <- the fix never touches country
  merged_with_state            UNCHANGED     <- on this branch
  state_country_conflicts      UNCHANGED     <- Problem 2, a different branch
...
Only once fix/p2-state-repair is deployed as well:
  state_country_conflicts      5,856 -> 0
```

When this branch is rebased onto main after #108 merges, those notes no longer describe Problem 2's effect. On the pinned data, against the baseline (P2_PHASE5.md, merged entities):

- **`merged_with_country`: the count is still UNCHANGED (0).** The metric is `cardinality(country_val) > 0`, and Option A changes which country, never whether there is one. But "the fix never touches country" is no longer true. **80 merged entities change country value:**
  - 73 from Option A (70 from the first four pairs, 3 from the UK pairs);
  - 7 from Part B's pairing fix (`9d68111`), which already moved them.

  A compare that looks at values rather than this count would show it.
- **`merged_with_state`: −313** (−671 with the repair alone). Of the 5,856 conflicted entities, 5,543 have their state repointed and 313 are left empty.
- **`state_country_conflicts`: 5,856 → 0.**

## Earlier findings that still hold

The scan behind this (`investigation/p2d_dependency_scan.py` → `reports/p2d/dependency_scan.csv`) found 15 groups and 3,777 records where a state field names a `country.csv` country other than the recorded one:
- **The six dependency groups above:** 75 of their records are dropped and mapped, and 68 have no state chosen and are left alone.
- **Dependencies that resolve to the sovereign's own state row:** Puerto Rico, French Guiana, Guadeloupe, Martinique, French Polynesia.
- **Disputed territories:** Kosovo/Serbia, Western Sahara/Morocco.
- **A real US state:** Georgia, 2,691 records.

Mapping by a general name-matching rule would have moved the last three kinds, which is why the list is explicit.
