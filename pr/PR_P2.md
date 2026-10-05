# Repair states recorded in the wrong country at merge time

Branch: `fix/p2-state-repair` (2 commits on `83f9b7b`). **Depends on `fix/reproject-always-xy` for its merge-cache bump** (see Deploy).

## What was broken

**5,856 merged mineral sites have a state that belongs to a different country than the site's own country.** That's 6,158 state assignments on 6,155 source records. Examples:

- **Florida → Florida, Puerto Rico** on 1,609 US records.
- **La Paz → La Pampa, Argentina** on 586 Bolivian records.
- **Potosi → Porto, Portugal** on 552 Bolivian records.
- **Bolivar → Bolívar, Colombia** on 475 Venezuelan records.

These are counts from the current `ta2-minmod-data` (`3a086a5`), merged locally with this repo's own ETL stages.

## Where the bug was

- **Upstream of MinMod, in the state matcher** (UMN ProcMine), which produces most of the `normalized_uri`s. It looks up states by name only, keeps the first row per name, and never sees the record's country:
  - 117 of the 5,084 states can never be selected. Florida, United States is one; the name always resolves to Puerto Rico's.
  - When a name has no exact match, it falls back to the best fuzzy score over every state in the world, with no floor.
  - Of the 6,158 bad assignments, 59% come from that fuzzy fallback, 33% from name shadowing, and 8% from other matchers.
- **In MinMod, nothing checks the state against the record's country.** `LocationView.from_location` copies the `normalized_uri` into the merged view as-is.
- **The merge can also invent a pairing.** `DedupMineralSite.from_sites` / `from_dedup_sites` elect country and state in two independent scans, so a merged site can take its country from one record and its state from another.

**Why fix it here and not in the matcher:** the matcher resolves each distinct string once for the whole dataset, with no record context. MinMod already holds every state with its country at merge time, so the state can be repaired without re-extracting any source. The country side is clean and is never changed.

## The fix

**1. `5318bdf` Repair states that contradict the recorded country at merge time.**
- New `minmodkg/misc/state_repair.py`. It's wired through `EntityService.get_state_or_province_index()` into `LocationView.from_location`, and from there into `MineralSite.from_raw_site` and `MineralSiteAndInventory.from_raw_site`. Their three callers (`etl/mineral_site.py`, `api/models/public_mineral_site.py`, `etl/geochem_loader.py`) pass the index.
- A state whose country is none of the record's countries is re-resolved *inside* those countries, stopping at the first tier that matches:
  1. the exact folded name;
  2. the name with administrative words and stopwords dropped ("La Paz" → La Paz Department);
  3. the exact `state_code` ("CO" → Colorado).
- A record with no `observed_name` is re-resolved by the stored state's own name.
- One match repoints the state. No match, or more than one, drops it. It never guesses, and there's no fuzzy tier.
- Only `location_view` changes. The raw `location`, which is what goes to the KG, is untouched.
- Adds `state_or_province.state_code` (nullable), filled by the entity loader, plus **`migrations/005_state_or_province_state_code.{up,down}.sql`**.

**2. `9d68111` Take a merged entity's country and state from one record.** Both elections now prefer the highest-ranked record carrying both. The existing scans are unchanged and remain the fallback.

## How we know it works

Measured by running this repo's entity, same-as and merge stages locally on the full `ta2-minmod-data`, before and after:

| | before | after |
|---|---:|---:|
| merged sites whose state is in another country | **5,856** | **0** |
| ↳ state repointed to the right one | | 5,185 (88.5%) |
| ↳ state removed (no unique match in the recorded country) | | 671 (11.5%) |
| conflicted state assignments, per record | 6,158 | repointed 5,421 (88.0%), dropped 737 (12.0%) |

- **No collateral changes:**
  - 0 of the 4,967 assignments the matcher already gets right are altered.
  - Each of the 5,084 states, given its own name and its own country, resolves to itself (5,058) or to nothing (26 same-named pairs). It never resolves to another state.
  - 0 merged sites become conflicted, and 0 non-conflicted sites change state or country value.
- **The election change affects values on 7 merged sites.** All 7 are merge groups spanning two countries, and in each the country now follows the record carrying the state. On 1,031 other sites only the provenance changes (`*_refid`), now one record for both values; the values themselves stay the same.
- **The KG export is unchanged:** all 2,446 mineral-site TTL files (41.2M lines) are identical before and after, compared as triples with node ids normalized. The `state_or_province` TTL is byte-identical.
- **The acceptance query** (count of merged sites whose state is in none of their countries) returns 5,856 before and 0 after, on a local Postgres loaded through `PostgresLoaderService.restore`.
- **Tests:** 32 tests (repair rule, wiring on all 418,313 state candidates, election) pass. This repo's suite gives 63 passed before and after; the 27 errors are fixtures that need Docker, identical in both runs.

**For confirmation:** 72 records give the country's own name as their state ("Panama" 62, "Mexico" 10, from USGS MRDS and VMS). They're repointed to Panamá Province and Estado de México. That's a valid reading, but the source may simply repeat the country name.

## Deploy

1. **Merge after, or together with, `fix/reproject-always-xy`.** Its merge-cache bump (`merge-v106` → `merge-v107`) is what makes the next ETL run rebuild the merged tables. Without it, existing data never passes through this code.
2. **Apply `migrations/005_state_or_province_state_code.up.sql` before starting the new API.** The API reads `state_or_province`, and doesn't add columns to existing tables. The migration is idempotent; `005_*.down.sql` reverts it.
3. **Run the ETL and reload.** The entity load fills `state_code`, and the merge rebuilds `location_view` and `dedup_mineral_site`. Until that load, existing rows have `NULL` codes, so API edits simply skip the code tier.
4. Run the acceptance query. Expect 0 on current data; anything that remains is listed by its triage query.
