# Option A: the dependency mapping

*2026-10-09. Proposed, then decided by Amandeep, then implemented as `cbac0a9` on `fix/p2-state-repair`: `patches/0005-problem-2-dependency-mapping.patch` (the push to usc-isi-i2 is refused here).*

## The decision

It is a **mapping, not a correction**:
- **When:** the recorded country is the sovereign, and the state field names one of its dependencies that has its own entry in `country.csv`.
- **Then:** the record's country becomes the dependency, and the state is left empty.
- **The list is explicit:** (sovereign, the names a state field uses for the dependency) → the dependency's country. **There is no general name-matching rule.**
- **Only for drops:** it applies only to records the repair would otherwise drop, a contradiction with no match inside the recorded country. It never touches a record that resolves today.
- **The list starts with four pairs:** New Caledonia/France, Greenland/Denmark, Christmas Island/Australia, Montserrat/United Kingdom. Any other pair from the dropped list is shown for approval before it is added.
- **Explicit exclusions:** China/Taiwan, and every homonym (Georgia, Niger, Luxembourg, Mali).
- New Caledonia's three provinces (Q4823–Q4825) will be filled from coordinates later, not now.

## The implementation (`cbac0a9`)

**`minmodkg/misc/state_repair.py`:**
- **The list:** `DEPENDENCIES`, the reviewed pairs, keyed by country `minmod_id` and matched on the **exact folded name** only:

  | sovereign | dependency | names |
  |---|---|---|
  | France `Q1075` | New Caledonia `Q1154` | "New Caledonia", "Territory of New Caledonia and Dependencies" |
  | Denmark `Q1059` | Greenland `Q1086` | "Greenland" |
  | Australia `Q1013` | Christmas Island `Q1045` | "Christmas Island", "Territory of Christmas Island" |
  | United Kingdom `Q1234` | Montserrat `Q1146` | "Montserrat" |

- **The exclusions:** `NOT_DEPENDENCIES`, which is China/Taiwan, United States/Georgia, Nigeria/Niger, Belgium/Luxembourg and Guinea/Mali (Mali Prefecture). Building an index whose list contains any of them raises an error.
- **The check:** `StateCountryIndex.dependency(state, observed_name, countries)` returns (sovereign, dependency) **only if `repair()` would drop** that candidate and its observed name is a listed name of a recorded sovereign. Otherwise it returns None. `resolve()` and `repair()` are unchanged.

**`minmodkg/models/kgrel/custom_types/location.py`:**
- **Where:** in `from_location`, a dropped candidate that `dependency()` maps replaces its sovereign with the dependency in `view.country`. The state stays dropped.
- **Order:** every candidate is decided against the recorded countries first, then the moves are applied, so the order of a record's candidates cannot matter.
- **The KG is untouched:** `location`, which goes to the KG, keeps the source's country, as with the repair.
- **Every path:** the list is code, not data, so the API save path and the GeoChem loader behave the same as the ETL merge.

**Tests:** `tests/misc/test_state_repair.py`, 22 in all, 9 of them for Option A.
- It maps only a drop: never a state that resolves, never a record without a contradiction.
- It needs the exact listed name, and the sovereign recorded.
- The excluded pairs cannot be listed.
- **On the real table** (`MINMOD_ENTITY_DIR`): each pair names two countries of `country.csv`, and no listed name resolves inside its sovereign. That keeps out places the table also models as the sovereign's own state rows: Puerto Rico, Guadeloupe and the like. No state's own name ever triggers a move.
- One end-to-end test through `LocationView.from_location`: a record with France and Colombia → New Caledonia and Colombia, state empty, `location` unchanged.
- All 22 pass on the fixture and on the fork's table. The repo's other tests are unchanged: 15 failed and 27 errors before and after, all pre-existing (a vendored file missing here, and Docker).

## Proof: zero regressions

**Records** (`investigation/p2d_option_a_measure.py` → `reports/p2d/option_a_records.json`). Every record with a location, **451,526**, is viewed through MinMod's own `LocationView.from_location`, once with the list empty (the alias-pass behaviour) and once with the four pairs:
- **State candidates whose repair outcome changes: 0 of 418,313.**
- **Records whose view changes: 72**, exactly the 72 blocked records:

  | pair | records |
  |---|--:|
  | France, "Territory Of New Caledonia And Dependencies" → New Caledonia | 49 |
  | Denmark, "Greenland" → Greenland | 15 |
  | Australia, "Territory Of Christmas Island" → Christmas Island | 5 |
  | United Kingdom, "Montserrat" → Montserrat | 3 |

- Each of the 72 changes only by one listed sovereign becoming its dependency. Its states are unchanged, and one of its candidates is a drop naming that dependency (asserted for every record).
- The other 451,454 records are identical.
- Records the repair does not drop are not touched, as decided:
  - the 67 Denmark records that name Greenland but where ProcMine matched no state;
  - the Australia record with no state chosen;
  - Puerto Rico (731), French Guiana (166), Guadeloupe (36), Martinique (6), French Polynesia (1);
  - Georgia (2,691), Kosovo, Western Sahara.

**Merged entities** (run C against run B in [P2_PHASE5.md](P2_PHASE5.md)):
- 71 entities have different inputs.
- **70 change country:** France → New Caledonia 48, Denmark → Greenland 15, Australia → Christmas Island 4, United Kingdom → Montserrat 3.
- **1 keeps Australia:** a Christmas Island record shares its entity with an Australia / Western Australia record that the election prefers.
- **0 state changes, and 0 newly conflicted.**

## For approval: the same shape in the dropped list

Two more dropped groups have exactly this shape. They are **not added**:

| sovereign | observed state | dependency (`country.csv`) | records | today |
|---|---|---|--:|---|
| United Kingdom `Q1234` | British Virgin Islands | Virgin Islands (British) `Q1243` | 2 | dropped |
| United Kingdom `Q1234` | Cayman Islands | Cayman Islands `Q1040` | 1 | dropped |

Both are British Overseas Territories, with their own `country.csv` entries and no UK state row. If approved, each is one line in `DEPENDENCIES` with its names as above.
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

- **`merged_with_country`: the count is still UNCHANGED (0).** The metric is `cardinality(country_val) > 0`, and Option A changes which country, never whether there is one. But "the fix never touches country" is no longer true. **77 merged entities change country value:**
  - 70 from Option A;
  - 7 from Part B's pairing fix (`9d68111`), which already moved them.

  A compare that looks at values rather than this count would show it.
- **`merged_with_state`: −313** (−671 with the repair alone). Of the 5,856 conflicted entities, 5,543 have their state repointed and 313 are left empty.
- **`state_country_conflicts`: 5,856 → 0.**

## Earlier findings that still hold

The scan behind this (`investigation/p2d_dependency_scan.py` → `reports/p2d/dependency_scan.csv`) found 15 groups and 3,777 records where a state field names a `country.csv` country other than the recorded one:
- **The six dependency groups above:** 72 of their records are dropped and mapped, 3 are pending approval, and 68 have no state chosen and are left alone.
- **Dependencies that resolve to the sovereign's own state row:** Puerto Rico, French Guiana, Guadeloupe, Martinique, French Polynesia.
- **Disputed territories:** Kosovo/Serbia, Western Sahara/Morocco.
- **A real US state:** Georgia, 2,691 records.

Mapping by a general name-matching rule would have moved the last three kinds, which is why the list is explicit.
