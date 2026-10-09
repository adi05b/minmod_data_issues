# Problem 2, Part B: merge-time state repair and dedup pairing fix

Aditi Bombe, USC ISI · 2026-10-05

> **Patches:** `patches/0002-problem-2-merge-time-state-repair.patch` (B1+B2) and `patches/0003-problem-2-dedup-pairing.patch` (B3).
> **Applies to:** `usc-isi-i2/ta2-minmod-kg` @ `83f9b7b2580790b2c7e197610ae905bd23c49a74`. Branch `fix/p2-state-repair`: `5318bdf`, then `9d68111`. These are the measured commits with only their messages rewritten (co-author trailer removed); the trees are identical. Checked with `git am` on a fresh checkout; the resulting tree is identical. **Pushed to `usc-isi-i2/ta2-minmod-kg` as a branch for review; no PR opened.**
> **Data:** ta2-minmod-data `3a086a5` · **Env:** Python 3.11, upstream-p2's `poetry.lock`

Tags: 🟢 verified by running it · 🟡 likely · 🔴 assumed / not my number.

## Where the fix lives, and why not in ProcMine

**In MinMod, at merge time.** `LocationView.from_location` (`models/kgrel/custom_types/location.py:116`) runs once per record while the merged (Postgres) tables are built. It now re-resolves any state that sits in none of the record's countries, using a `StateCountryIndex` (`minmodkg/misc/state_repair.py`) that the entity service builds from its own full state table.

**Not in ProcMine.** Its matcher resolves each *distinct observed string once for the whole dataset*, with `record_id` already dropped (`procmine/converting/_attribute.py:155-159`), so the record's country is not in scope and there's no parameter to pass it through. Fixing it there would mean a ProcMine release and re-extracting every source.

MinMod already holds all 5,084 states with their countries, nothing shadowed, and the country side is clean (393 keys, 0 unreachable). So the state can be repaired from data MinMod already has, with no re-extraction. The country is never touched.

## The three gates: all pass

| gate | expected | got | |
|---|---|---|---|
| 1. regression: currently-correct assignments altered | 0 of 4,967 | **0 of 4,967** | 🟢 |
| 2. self-resolution: every state's own name, in its own country | 5,058 self · 26 ambiguous · 0 wrong | **5,058 · 26 · 0** (and 0 with no hit) | 🟢 |
| 3. merged entities: newly conflicted / non-conflicted with a changed state | 0 / 0 | **0 / 0, with the repair alone and with B3** | 🟢 |

The 26 ambiguous drops are 13 same-named pairs inside one country: Zagreb city and county, Puerto Rico's duplicated municipalities (Arecibo, Bayamón, Caguas, Carolina, Guaynabo, Mayagüez, Ponce, San Juan, Toa Baja, Trujillo Alto), and Taiwan's Chiayi and Hsinchu (city and county).

## Results

### Per record: matches your expectation exactly

Of **6,158** conflicted state candidates (on 6,155 records, out of 418,313 with a state), the rule **repoints 5,421 (88.0%)** and **drops 737 (12.0%)**. 🟢 Expected 5,421 / 737, so the run continued.

| how the 5,421 were resolved | records |
|---|---:|
| tier 1, exact folded name | 2,436 |
| tier 2, admin words and stopwords dropped | 2,781 |
| tier 3, `state_code` | **179** |
| no `observed_name`; re-resolved by the stored state's own name (24 at tier 1, 1 at tier 2) | 25 |

| why the 737 drop | records |
|---|---:|
| no state of that name or code in the recorded country | 722 |
| ambiguous inside the country (two matches; never guessed) | 15 |

Compared with Part A (5,146 / 1,012), the change is purely additive. **All 5,146 Part A repoints are unchanged: none is redirected or lost.** 275 records that Part A dropped now repoint: 179 by state code, 59 through the new tier-2 words (Cartago → Provincia de Cartago, El Beni → Beni Department, Mexico → Estado de México, …), 25 by the name fallback, and 12 through the dotless-i folding (Elazig → Elazığ). 🟢

### Merged entities (the 5,856 that correspond to Adriana's 5,858)

All from the real ETL (upstream's own entity, same-as and merge stages run locally on the pinned data), comparing the unpatched baseline with the patched output. 🟢

| of 5,856 conflicted merged entities | repair only (B1+B2) | repair + B3 (the patch set) |
|---|---:|---:|
| fixed: state repointed | 5,178 (88.4%) | **5,185 (88.5%)** |
| fixed: state dropped (entity left with no state) | 671 (11.5%) | **671 (11.5%)** |
| still conflicted | 7 (0.1%) | **0** |
| *newly conflicted entities* | *0* | *0* |
| *non-conflicted entities whose state value changed* | *0* | *0* |
| *non-conflicted entities whose country value changed* | *0* | *0* |

The repair-only column matches the Part A-style simulation exactly (5,178 / 671 / 7). That confirms the wiring end to end through the production path.

**Run-to-run noise.** Two runs of the *unpatched* ETL agree on every country and state *value*, but **168** merged entities differ in `refid` alone. statickg's executor is `Parallel(return_as="generator_unordered")`, so ties between equal-score partial merges break differently each run. Value comparisons are therefore exact; `refid`-only differences are noise (repair-only run: 140, all in entities the repair can't reach). 🟢

### B3, described accurately

B3 leaves the existing scans in place. When a record carries both a country and a state, it takes both from the highest-ranked such record. In `from_dedup_sites`, that means a partial merge whose country and state share a `refid`.

**It changes values on exactly 7 entities.** Those are the 6 cross-country merge pairings from Part A, plus the 1 the repair exposes: an Inferlink record (Canada) whose wrong state is dropped, so the election fell through to an MRDS record's Washington. In all 7 it's the **country** that changes, to the country of the record that carries the state: 🟢

| merged entity | repair only | with B3 |
|---|---|---|
| `dedup_site__api-cdr-land-v1-docs-documents__02c4dfe31bb57da226b14ffc1205519e8a56a6d087922f8346736f552d4cbdbf25__inferlink` | Canada + Washington | United States + Washington |
| `dedup_site__api-cdr-land-v1-docs-documents__0283468d8e32eb2151b91e8f29b005238f1438c1258edddbc4f40471ae044bb892__inferlink` | Portugal + British Columbia | Canada + British Columbia |
| `dedup_site__doi-org-10-1016-j-oregeorev-2016-08-010__reef-ridge-837__usc` | Uganda + Alaska | United States + Alaska |
| `dedup_site__doi-org-10-1016-j-oregeorev-2016-08-010__su-lik-843__usc` | Uganda + Alaska | United States + Alaska |
| `dedup_site__mrdata-usgs-gov-phosphate__1134__sri` | Solomon Islands + Roi Et | Thailand + Roi Et |
| `dedup_site__mrdata-usgs-gov-phosphate__1__sri` | Pakistan + Helmand | Afghanistan + Helmand |
| `dedup_site__mrdata-usgs-gov-phosphate__954__sri` | New Zealand + Queensland | Australia + Queensland |

Six of the seven are merge groups spanning two countries: a Ugandan record merged with an Alaskan one, a Portuguese one with British Columbia. B3 makes each pair consistent, but it can't tell which record the entity should follow. That's a same-as linking question for whoever owns the groups. 🟡

Everywhere else, B3 changes **provenance only**. On **1,031** entities (959 that were never conflicted, plus 72 the repair had already fixed), the country and state values stay the same but now come from one record instead of two, so their `refid`s change. After B3, all 372,520 merged entities with both a country and a state take them from one record. No other value changes anywhere: 0 newly conflicted entities, and 0 non-conflicted entities with a changed state or country value. 🟢

So B3 is a small fix: 7 entities on this data, not half the problem.

### The RDF is unchanged, and `location` is never mutated

- `location` (the raw record, what `to_kg()` writes to the triple store) is only read. The corpus test runs `from_location` on every raw record and asserts the input is identical afterwards, and that the country is never changed. 🟢
- **Every** mineral-site TTL file the ETL writes for Fuseki (2,446 files, 41,155,464 lines) is identical before and after as a sorted multiset of triples, with the random node ids normalized. Two runs of unchanged code already differ byte for byte because of those ids, so I compared multisets instead. The entity TTL (`state_or_province.ttl`) is byte-identical. 🟢

---

## The diffs

### 1. B1 + B2: `5318bdf` "Repair states that contradict the recorded country at merge time"

```diff
diff --git a/migrations/005_state_or_province_state_code.down.sql b/migrations/005_state_or_province_state_code.down.sql
new file mode 100644
index 0000000..b932b9f
--- /dev/null
+++ b/migrations/005_state_or_province_state_code.down.sql
@@ -0,0 +1,6 @@
+-- Reverts 005_state_or_province_state_code.up.sql.
+BEGIN;
+
+ALTER TABLE state_or_province DROP COLUMN IF EXISTS state_code;
+
+COMMIT;
diff --git a/migrations/005_state_or_province_state_code.up.sql b/migrations/005_state_or_province_state_code.up.sql
new file mode 100644
index 0000000..1909316
--- /dev/null
+++ b/migrations/005_state_or_province_state_code.up.sql
@@ -0,0 +1,8 @@
+-- State codes for the merge-time state repair. Idempotent; run before the new
+-- API starts. Existing rows stay NULL (the code tier never hits) until the next
+-- data load fills them from ta2-minmod-data's state_or_province.csv.
+BEGIN;
+
+ALTER TABLE state_or_province ADD COLUMN IF NOT EXISTS state_code VARCHAR;
+
+COMMIT;
diff --git a/minmodkg/api/models/public_mineral_site.py b/minmodkg/api/models/public_mineral_site.py
index 997da27..4ac1f07 100644
--- a/minmodkg/api/models/public_mineral_site.py
+++ b/minmodkg/api/models/public_mineral_site.py
@@ -195,6 +195,7 @@ class InputPublicMineralSite(InputMineralSite):
                 if self.dedup_site_uri is not None
                 else None
             ),
+            state_index=entser.get_state_or_province_index(),
         )
         site.ms.modified_at = time.time_ns()
         site.ms.created_by = owner_uri
diff --git a/minmodkg/etl/geochem_loader.py b/minmodkg/etl/geochem_loader.py
index 4ac937d..1de1c4c 100644
--- a/minmodkg/etl/geochem_loader.py
+++ b/minmodkg/etl/geochem_loader.py
@@ -85,6 +85,7 @@ def to_msi(site: KGMineralSite, entser: EntityService) -> MineralSiteAndInventor
         commodity_form_conversion=entser.get_commodity_form_conversion(),
         crs_names=entser.get_crs_name(),
         source_score=entser.get_data_source_score(),
+        state_index=entser.get_state_or_province_index(),
     )
     msi.ms.modified_at = time.time_ns()
     return msi
diff --git a/minmodkg/etl/kgrel_entity.py b/minmodkg/etl/kgrel_entity.py
index 25b6890..910e18e 100644
--- a/minmodkg/etl/kgrel_entity.py
+++ b/minmodkg/etl/kgrel_entity.py
@@ -273,6 +273,7 @@ class EntityDeserFn:
                     id=raw_record["minmod_id"],
                     name=raw_record["name"],
                     country=name2country[raw_record["country_name"]].id,
+                    state_code=raw_record.get("state_code") or None,
                 )
             )
         return records
diff --git a/minmodkg/etl/mineral_site.py b/minmodkg/etl/mineral_site.py
index ad738fc..d6d38c6 100644
--- a/minmodkg/etl/mineral_site.py
+++ b/minmodkg/etl/mineral_site.py
@@ -428,6 +428,7 @@ class MergeFn:
                     commodity_form_conversion=self.entity_service.get_commodity_form_conversion(),
                     crs_names=self.entity_service.get_crs_name(),
                     source_score=self.entity_service.get_data_source_score(),
+                    state_index=self.entity_service.get_state_or_province_index(),
                 )
                 norm_site.ms.dedup_site_id = dedup_map[norm_site.ms.site_id]
                 lst_msi.append(norm_site)
diff --git a/minmodkg/misc/state_repair.py b/minmodkg/misc/state_repair.py
new file mode 100644
index 0000000..3487866
--- /dev/null
+++ b/minmodkg/misc/state_repair.py
@@ -0,0 +1,199 @@
+"""Repair state_or_province candidates whose entity sits in a different country
+than the one recorded on the same record.
+
+The upstream matcher (ProcMine ``identify_entity_id``) keys its state lookup on
+the bare lowercased name, keeps the first row in file order, falls back to the
+best fuzzy score over every state in the world, and never sees the record's
+country. So ``Florida`` resolves to Q5307 (Puerto Rico), and ``Potosi`` to Porto
+(Portugal).
+
+MinMod loads the same table keyed on id, so every state *is* reachable here,
+each carrying its country. That is enough to repair the choice at merge time
+without re-running extraction.
+
+The rule is deliberately narrow:
+
+* it engages only when the chosen state's country contradicts a country
+  already recorded on the record -- a correct assignment is never touched;
+* it re-resolves the record's own ``observed_name`` against only the states
+  of the recorded country, in three tiers, stopping at the first that hits:
+  the exact folded name, then the name with administrative words and
+  stopwords dropped ("La Paz" -> "La Paz Department"), then the exact
+  ``state_code`` ("CO" -> Colorado). Codes come last so a real name always
+  beats a coincidental code;
+* a record with no ``observed_name`` is re-resolved by the chosen state's own
+  name instead (Florida, Uruguay -> Florida, United States);
+* a unique hit replaces the normalized_uri; no hit, or more than one, drops
+  it and leaves ``observed_name`` in place for a curator.
+
+It never guesses: there is no fuzzy matching.
+"""
+
+from __future__ import annotations
+
+import re
+import unicodedata
+from dataclasses import dataclass, field
+from typing import Iterable, Optional, Sequence
+
+from minmodkg.typing import InternalID
+
+# Administrative words that sources drop and the reference list keeps,
+# counted from the 5,084 names in state_or_province.csv.
+ADMIN_WORDS = frozenset(
+    {
+        "district",
+        "municipality",
+        "province",
+        "region",
+        "prefecture",
+        "county",
+        "department",
+        "oblast",
+        "parish",
+        "governorate",
+        "state",
+        "territory",
+        "division",
+        "council",
+        "autonomous",
+        "city",
+        "area",
+        "zone",
+        "krai",
+        "raion",
+        "voivodeship",
+        "canton",
+        "emirate",
+        "special",
+        "metropolitan",
+        "administrative",
+        # the same words in the languages the reference list uses
+        # ("Provincia de Cartago", "Estado de México", "Região Norte")
+        "provincia",
+        "departamento",
+        "departement",
+        "estado",
+        "regiao",
+        "regione",
+        "provincie",
+        "bundesland",
+    }
+)
+
+# Function words dropped with them, so "El Beni" meets "Beni Department".
+STOPWORDS = frozenset(
+    {"of", "de", "del", "la", "el", "los", "las", "the", "du", "da", "dos", "das", "do"}
+)
+
+_NON_ALNUM = re.compile(r"[^a-z0-9]+")
+# NFKD does not decompose the Turkish dotless i, so "Elazığ" would fold to
+# "elaz g"; map it (and the dotted capital) before normalising.
+_TURKISH_I = str.maketrans({"ı": "i", "İ": "i"})
+
+
+def fold_name(name: str) -> str:
+    """Lowercase, strip diacritics, reduce punctuation to single spaces."""
+    decomposed = unicodedata.normalize("NFKD", name.translate(_TURKISH_I))
+    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
+    return _NON_ALNUM.sub(" ", stripped.lower()).strip()
+
+
+def drop_admin_words(folded: str) -> str:
+    """Remove administrative words and stopwords. Falls back to the input if
+    nothing is left."""
+    words = [w for w in folded.split() if w not in ADMIN_WORDS and w not in STOPWORDS]
+    return " ".join(words) if words else folded
+
+
+@dataclass
+class StateCountryIndex:
+    """State -> country, plus per-country name and code indexes for re-resolution."""
+
+    state_country: dict[InternalID, Optional[InternalID]] = field(default_factory=dict)
+    state_name: dict[InternalID, str] = field(default_factory=dict)
+    _exact: dict[InternalID, dict[str, list[InternalID]]] = field(default_factory=dict)
+    _folded: dict[InternalID, dict[str, list[InternalID]]] = field(default_factory=dict)
+    _code: dict[InternalID, dict[str, list[InternalID]]] = field(default_factory=dict)
+
+    @classmethod
+    def build(cls, states: Iterable) -> StateCountryIndex:
+        """``states`` is any iterable of objects with .id, .name, .country and,
+        optionally, .state_code (without it, the code tier never hits)."""
+        self = cls()
+        for s in states:
+            self.state_country[s.id] = s.country
+            self.state_name[s.id] = s.name
+            if s.country is None:
+                continue
+            folded = fold_name(s.name)
+            self._exact.setdefault(s.country, {}).setdefault(folded, []).append(s.id)
+            self._folded.setdefault(s.country, {}).setdefault(
+                drop_admin_words(folded), []
+            ).append(s.id)
+            code = getattr(s, "state_code", None)
+            if code and code.strip():
+                self._code.setdefault(s.country, {}).setdefault(
+                    code.strip().upper(), []
+                ).append(s.id)
+        return self
+
+    def resolve(
+        self, observed_name: Optional[str], country_ids: Sequence[InternalID]
+    ) -> Optional[InternalID]:
+        """The one state in ``country_ids`` matching ``observed_name``, or None.
+
+        Exact folded name first so that a real "Berat County" is not confused
+        with "Berat District" in the same country; only then the admin-word-free
+        form, which is what lets "La Paz" reach "La Paz Department"; and only
+        then the state code, case-insensitive, so a real name always beats a
+        coincidental code.
+        """
+        if not observed_name or not country_ids:
+            return None
+        folded = fold_name(observed_name)
+        for index, key in (
+            (self._exact, folded),
+            (self._folded, drop_admin_words(folded)),
+            (self._code, observed_name.strip().upper()),
+        ):
+            hits: list[InternalID] = []
+            for cid in country_ids:
+                hits.extend(index.get(cid, {}).get(key, ()))
+            hits = list(dict.fromkeys(hits))
+            if len(hits) == 1:
+                return hits[0]
+            if len(hits) > 1:
+                return None  # ambiguous inside the country; do not guess
+        return None
+
+    def conflicts(
+        self, state_id: InternalID, country_ids: Sequence[InternalID]
+    ) -> bool:
+        """True when this state belongs to none of the recorded countries."""
+        if not country_ids:
+            return False
+        owner = self.state_country.get(state_id)
+        return owner is not None and owner not in country_ids
+
+    def repair(
+        self,
+        state_id: InternalID,
+        observed_name: Optional[str],
+        country_ids: Sequence[InternalID],
+    ) -> tuple[str, Optional[InternalID]]:
+        """What to do with one state candidate: ("keep", id), ("repoint", new id)
+        or ("drop", None).
+
+        Untouched unless the state contradicts the recorded countries. A record
+        without an ``observed_name`` is re-resolved by the chosen state's own
+        name, which is what lets Florida (Uruguay) reach Florida (United States).
+        """
+        if not self.conflicts(state_id, country_ids):
+            return ("keep", state_id)
+        if observed_name and observed_name.strip():
+            key = observed_name
+        else:
+            key = self.state_name.get(state_id)
+        fixed = self.resolve(key, country_ids)
+        return ("repoint", fixed) if fixed else ("drop", None)
diff --git a/minmodkg/models/kgrel/custom_types/location.py b/minmodkg/models/kgrel/custom_types/location.py
index b420081..6054e1b 100644
--- a/minmodkg/models/kgrel/custom_types/location.py
+++ b/minmodkg/models/kgrel/custom_types/location.py
@@ -5,6 +5,7 @@ from typing import Annotated, Optional
 
 import shapely.wkt
 from minmodkg.misc.geo import reproject_geometry
+from minmodkg.misc.state_repair import StateCountryIndex
 from minmodkg.misc.utils import extend_unique, makedict
 from minmodkg.models.kg.base import NS_MR
 from minmodkg.models.kg.candidate_entity import CandidateEntity
@@ -113,7 +114,11 @@ class LocationView(GeoCoordinate):
         return self
 
     @staticmethod
-    def from_location(location: Location, crss: dict[str, str]) -> LocationView:
+    def from_location(
+        location: Location,
+        crss: dict[str, str],
+        state_index: Optional[StateCountryIndex] = None,
+    ) -> LocationView:
         view = LocationView()
         if location.coordinates is not None:
             if location.crs is None or location.crs.normalized_uri is None:
@@ -147,4 +152,18 @@ class LocationView(GeoCoordinate):
             for ent in location.state_or_province
             if ent.normalized_uri is not None
         ]
+        if state_index is not None and len(view.country) > 0:
+            # A state that sits in none of the recorded countries is re-resolved
+            # inside them, or dropped. Only the view changes: `location` is what
+            # goes to the KG, and keeps the source's observed_name for curators.
+            states = []
+            for ent in location.state_or_province:
+                if ent.normalized_uri is None:
+                    continue
+                _, state = state_index.repair(
+                    NS_MR.id(ent.normalized_uri), ent.observed_name, view.country
+                )
+                if state is not None:
+                    states.append(state)
+            view.state_or_province = states
         return view
diff --git a/minmodkg/models/kgrel/entities/state_or_province.py b/minmodkg/models/kgrel/entities/state_or_province.py
index 8dd4f40..1f43ed7 100644
--- a/minmodkg/models/kgrel/entities/state_or_province.py
+++ b/minmodkg/models/kgrel/entities/state_or_province.py
@@ -19,6 +19,9 @@ class StateOrProvince(MappedAsDataclass, Base):
     country: Mapped[Optional[InternalID]] = mapped_column(
         ForeignKey("country.id", ondelete="CASCADE")
     )
+    # ISO 3166-2 subdivision code, unique within a country ("CO" -> Colorado);
+    # only used to repair state assignments, not exported to the KG.
+    state_code: Mapped[Optional[str]] = mapped_column(default=None)
 
     @property
     def uri(self):
@@ -29,6 +32,7 @@ class StateOrProvince(MappedAsDataclass, Base):
             "id": self.id,
             "name": self.name,
             "country": self.country,
+            "state_code": self.state_code,
         }
 
     @classmethod
@@ -37,6 +41,7 @@ class StateOrProvince(MappedAsDataclass, Base):
             id=data["id"],
             name=data["name"],
             country=data["country"],
+            state_code=data.get("state_code"),
         )
 
     def to_kg(self) -> KGStateOrProvince:
diff --git a/minmodkg/models/kgrel/mineral_site.py b/minmodkg/models/kgrel/mineral_site.py
index 2b0e5fd..76658c2 100644
--- a/minmodkg/models/kgrel/mineral_site.py
+++ b/minmodkg/models/kgrel/mineral_site.py
@@ -6,6 +6,7 @@ from datetime import datetime
 from typing import TYPE_CHECKING, Annotated, Iterable, Optional
 
 from minmodkg.grade_tonnage_model import GradeTonnageModel
+from minmodkg.misc.state_repair import StateCountryIndex
 from minmodkg.misc.utils import datetime_to_nanoseconds, format_nanoseconds, makedict
 from minmodkg.models.kg.base import NS_MR
 from minmodkg.models.kg.candidate_entity import CandidateEntity
@@ -57,8 +58,9 @@ class MineralSiteAndInventory:
         crs_names: dict[str, str],
         source_score: dict[IRI, float | None],
         dedup_site_id: Optional[str] = None,
+        state_index: Optional[StateCountryIndex] = None,
     ) -> MineralSiteAndInventory:
-        ms = MineralSite.from_raw_site(raw_site, crs_names, source_score)
+        ms = MineralSite.from_raw_site(raw_site, crs_names, source_score, state_index)
         if dedup_site_id is not None:
             ms.dedup_site_id = dedup_site_id
 
@@ -207,6 +209,7 @@ class MineralSite(MappedAsDataclass, Base):
         raw_site: dict | KGMineralSite,
         crs_names: dict[str, str],
         source_score: dict[IRI, float | None],
+        state_index: Optional[StateCountryIndex] = None,
     ) -> MineralSite:
         site = (
             KGMineralSite.from_dict(raw_site)
@@ -223,7 +226,7 @@ class MineralSite(MappedAsDataclass, Base):
                 crs=site.location_info.crs,
                 coordinates=site.location_info.location,
             )
-            location_view = LocationView.from_location(location, crs_names)
+            location_view = LocationView.from_location(location, crs_names, state_index)
 
         out_site = MineralSite(
             site_id=site.id,
diff --git a/minmodkg/services/kgrel_entity.py b/minmodkg/services/kgrel_entity.py
index 3ae57e2..14f3ccc 100644
--- a/minmodkg/services/kgrel_entity.py
+++ b/minmodkg/services/kgrel_entity.py
@@ -6,6 +6,7 @@ from urllib.parse import urljoin
 
 import httpx
 import serde.json
+from minmodkg.misc.state_repair import StateCountryIndex
 from minmodkg.models.kg.base import NS_MR
 from minmodkg.models.kg.entities.commodity_form import CommodityForm as KGCommodityForm
 from minmodkg.models.kg.entities.crs import CRS as KGCRS
@@ -74,6 +75,17 @@ class EntityService:
             self.crs_name = {crs.uri: crs.name for crs in self.get_crs()}
         return self.crs_name
 
+    def get_state_or_province_index(self) -> StateCountryIndex:
+        """Every state with its country, name and code, for the merge-time repair."""
+        if (
+            not hasattr(self, "state_or_province_index")
+            or self.state_or_province_index is None
+        ):
+            self.state_or_province_index = StateCountryIndex.build(
+                self.get_state_or_province_idmap().values()
+            )
+        return self.state_or_province_index
+
     def get_deposit_type_idmap(self) -> dict[InternalID, DepositType]:
         if self.deposit_type_idmap is None:
             self.deposit_type_idmap = {dt.id: dt for dt in self.get_deposit_types()}
```

### 2. B3: `9d68111` "Take a merged entity's country and state from one record"

```diff
diff --git a/minmodkg/models/kgrel/dedup_mineral_site.py b/minmodkg/models/kgrel/dedup_mineral_site.py
index 7a7c08e..fb11295 100644
--- a/minmodkg/models/kgrel/dedup_mineral_site.py
+++ b/minmodkg/models/kgrel/dedup_mineral_site.py
@@ -218,6 +218,21 @@ class DedupMineralSite(MappedAsDataclass, Base):
             ),
             modified_at=max(dedup_site.modified_at for dedup_site in dedup_sites),
         )
+        # As in from_sites: prefer the highest-ranked partial merge whose country and
+        # state come from one record; the two scans above stay as the fallback.
+        both = next(
+            (
+                site
+                for site, _ in rank_dedup_sites
+                if len(site.country.value) > 0
+                and len(site.state_or_province.value) > 0
+                and site.country.refid == site.state_or_province.refid
+            ),
+            None,
+        )
+        if both is not None:
+            merged_dedup_site.country = both.country
+            merged_dedup_site.state_or_province = both.state_or_province
         merged_dedup_invs = merged_dedup_site.select_inventories(
             {msi.ms.site_id: msi.invs for msi in sites}
         )
@@ -276,6 +291,23 @@ class DedupMineralSite(MappedAsDataclass, Base):
             ),
             RefListID([], rank_sites[0].site_id),
         )
+        # Prefer the highest-ranked site carrying both a country and a state, so the
+        # merged pair is one a record actually asserts; the two independent scans
+        # above stay as the fallback when no site carries both.
+        both = next(
+            (
+                site
+                for site in rank_sites
+                if len(site.location_view.country) > 0
+                and len(site.location_view.state_or_province) > 0
+            ),
+            None,
+        )
+        if both is not None:
+            country = RefListID(both.location_view.country, both.site_id)
+            state_or_province = RefListID(
+                both.location_view.state_or_province, both.site_id
+            )
 
         ranked_deposit_types = top_5_deposit_types(_rank_ss)
         if len(ranked_deposit_types) > 0:
```

### What the wiring needed beyond the brief's B2 table

- **`state_code` had to become data MinMod carries.** `StateOrProvince` (the Postgres table *and* the entity JSON the ETL reads) held only `(id, name, country)`, and the API reads states straight from Postgres. So the patch adds a nullable `state_or_province.state_code` column, filled by `EntityDeserFn.read_state_or_province` from the CSV, plus **`migrations/005_state_or_province_state_code.{up,down}.sql`**. That follows the repo's rule that the API "never adds columns to existing ones", and the migration passes the repo's sqlfluff lint.
  - The RDF model (`models/kg/entities/state_or_province.py`, used by `to_kg()`) is untouched, so the KG is unchanged.
  - Until the next data load refills the table, rows already in Postgres have `NULL` codes. For user edits made through the API in that window, tier 3 simply never hits.
- **`location.py:116`**, as you corrected; the brief had `:113`.
- **The merge cache bump (`merge-v106` → `merge-v107`, `etl/mineral_site.py:401`) is deliberately not in this patch.** The P1+P4 PR carries it. This fix sits inside the same cached `MergeFn.invoke`, so it also needs that bump to take effect.
  - **Update (alias pass, 2026-10-08):** `merge-v107` has since been built on the dev server by the P1+P4 PR, so this branch needs `merge-v108` or later. Not changed on the branch: the version is decided once the merge order is known. The merge cache key is the site files and the same-as file only, **not the entity files**, so a change to `state_or_province.csv` (the new rows, aliases) does not re-run a merge that is already cached.
- **A second cache has the same problem, and this branch already depends on it (flagged, not changed).** `EntityDeserFn.VERSION = "v107"` (`etl/kgrel_entity.py:80`) names the entity-transform cache, `transform-v107.sqlite`, keyed on the CSV's path and content hash only. This branch changed what `read_state_or_province` writes (`state_code`, and now `aliases`) without changing that version. On a server that has already transformed the current `state_or_province.csv` (v107 dates from March 2025), the cached `state_or_province.json` has neither field, so at merge time the code tier and the alias tier never hit, and migration 005's column stays `NULL`. A changed CSV forces a re-transform, but only with the new code already deployed. Read from the cache code (`libactor` keys on the serialised arguments; `FileSqliteBackend` reuses the output files), not reproduced on a server.
- Two other callers of `MineralSiteAndInventory.from_raw_site` were left on the default `state_index=None`: `tests/conftest.py:190` and `tests/utils.py:32`. Both are test helpers.

### Deploying it

Updated 2026-10-08 for the alias pass; both cache versions are still to be decided:

1. **Data repo change first.** Merge the `ta2-minmod-data` change (the Niamey and Zacapa rows, and the approved `alt names`) before the kg build that should use it. The merge cache does not see entity files, so data landing after a v108 build would be inert there.
2. **Then the kg build, with both versions bumped:** `MergeFn`'s `merge-v106` to `merge-v108` or later (`etl/mineral_site.py:401`), and `EntityDeserFn.VERSION` past `v107` (`etl/kgrel_entity.py:80`), so the entity JSON is rebuilt with `state_code` and `aliases` even where a build with old code already cached the new CSV.
3. Apply `migrations/005_state_or_province_state_code.up.sql` before starting the new API (as the README asks for every migration).
4. Reload. The entity load fills `state_code`, and the merge rebuilds `location_view` and `dedup_mineral_site`.

---

## B4: tests

`tests/test_p2_repair.py` (27 tests) and `tests/test_p2_dedup_pairing.py` (5 tests) run against the patched upstream and the real CSVs. **32 passed.** 🟢

| block | expected (brief) | got | |
|---|---|---|---|
| A. recovery of the 117 shadowed entities | 104 repointed, 11 kept, 2 dropped | **104 repointed (all correct), 11 kept, 2 dropped** | 🟢 |
| B. regression: ProcMine's correct assignments | 4,967 untouched, 0 altered | **4,967 untouched, 0 altered** | 🟢 |
| C. inert with no recorded country | 5,084 untouched | **5,084 untouched** (with and without `observed_name`) | 🟢 |
| D. the sixteen reported cases | 10 repointed, 6 dropped | **10 repointed, 6 dropped** (same cases) | 🟢 |

- **The 11 kept** are same-named states inside one country (Zagreb, nine Puerto Rico municipalities, Chiayi, Hsinchu). A country-based rule has nothing to tell them apart with, so leaving them alone is correct, not a failure.
- **The 2 dropped** are Puerto Rico's two "San Juan" entries, which are ambiguous by name.
- **Four of D's six drops are correct:** Spain's table is provinces (no Andalusia), Odisha replaced Orissa, Katanga was split in 2015, and Elko is a county. The other two (Michoacan, Valle D'Aosta) are the alias gap (B6).

Also covered:
- gate 2;
- the code tier: "CO" → Colorado, case-insensitive, and only inside the recorded country;
- a real name beating a coincidental code, on a synthetic table, since the real table has no such case;
- the dotless i (Elazığ, İzmir) and the new words (Provincia de Cartago, El Beni);
- the name fallback;
- the port matching `reference/state_repair.py` on every state;
- **the wired `from_location` on all 418,313 candidates**: it equals the per-candidate rule, never mutates its input, and gives 5,421 / 737.

**B3 test:** A (US, no state) ranked above B (Mexico + Sonora). The pre-B3 scans, copied verbatim from 83f9b7b, pair US with Sonora; the new code takes both from B. A group where the top site carries both is unchanged, and so is one where no site carries both (fallback). The merge-level cases are covered too. Run against the code without B3, the three tests that assert the new pairing **fail**, and the two "unchanged" tests pass. 🟢

**Upstream suite** (`tests/`): **63 passed, 27 errors, both before (clean 83f9b7b) and after.** The failure set is identical, and all 27 errors are fixtures that start Docker, which isn't running here. To get a fair baseline I first initialized the `vendor/ta2-table-understanding` submodule. Without it, 15 `test_sample.py` tests fail on a missing SHACL file, in both states. 🟢

## B5: no fuzzy tier

Reproduced with ProcMine's own scorer (`identify_entity_id`: the mean of six string similarities), restricted to the states of the recorded country: 🟢

```
observed          best state in the recorded country  folded  raw     verdict
Michoacan      -> Michoacán de Ocampo    0.7269  0.6570  want
Katanga        -> Haut-Katanga           0.7526  0.7526  one of four successors
Valle D'Aosta  -> Aosta Valley           0.5713  0.5704  want
Orissa         -> Odisha                 0.5425  0.5425  want
Andalusia      -> Canarias               0.5032  0.5032  wrong
Elko County    -> Puerto Rico            0.3711  0.3711  wrong
```

**The "folded" column reproduces your table exactly.** Scoring on ProcMine's own keys (lowercase, diacritics kept) gives the same picks but lower scores for Michoacan (0.6570) and Valle D'Aosta (0.5704). So your numbers were computed on folded names.

**The floor is left unset.** Right and wrong answers interleave: Katanga, a wrong pick (one of four successors), scores *higher* than Michoacan, a right one. No threshold separates them, and six points can't tell you where one should go. Picking a floor from a handful of examples is the mistake that put the commodity floor at 0.90 and destroyed 32,324 correct mappings; the corpus answer turned out to be 0.62. A state floor would need the same corpus-scale measurement first. 🔴 (the commodity figures are from your brief, not re-measured)

## B6: the alias gap, sized

The top 10 of the 737 records that still drop:

| records | observed | recorded country | an alias row would fix it? |
|---:|---|---|---|
| 187 | Orissa | India | **yes**: Odisha (Q3657) |
| 93 | Katanga | DR Congo | no: split into four provinces in 2015; no single target |
| 49 | Territory of New Caledonia and Dependencies | France | no: New Caledonia is a *country* in the table; the recorded country is the problem |
| 43 | Niedersachsen | Germany | **yes**: Lower Saxony (Q3383) |
| 19 | Ekaterinburg | Russia | no: a city (in Sverdlovsk Oblast), not a state name |
| 18 | Katanga Province | DR Congo | no: as Katanga |
| 15 | Greenland | Denmark | no: Greenland is a *country* in the table |
| 13 | Attapu | Laos | **yes**: Attapeu Province (Q4059) |
| 12 | Buryatiya | Russia | **yes**: Republic of Buryatia (Q5463) |
| 12 | San Blas* | Panama | **yes**: Guna Yala (Q5071), renamed in 2011 |

**Five alias rows recover 267 of the 737 records (36.2%).** Adding Karnten → Carinthia and Steiermark → Styria makes seven rows and 279 records (37.9%). I measured this, not just judged it: each alias was added as an extra name of the existing state, and every dropped record was re-run through the rule (`investigation/p2b_alias_sizing.py`). 🟢

**Scope** (not built; it lands in ta2-minmod-data): add an `aliases` column to `state_or_province.csv`, `|`-separated like `country.csv`'s `alt names`. MinMod would then read it into `StateOrProvince` alongside `state_code`, and the index would add each alias as another name at tiers 1 and 2. Michoacan → Michoacán de Ocampo and Valle d'Aosta → Aosta Valley are the same kind of row.

> **Superseded by the alias pass ([P2_ALIAS_PASS.md](P2_ALIAS_PASS.md)).** The column is `alt names`, matching `country.csv`. Aliases are not on the `StateOrProvince` model or in Postgres, and they form a fourth, exact-only tier after the code tier, so they can never change a match made without them.

## The 72 country-name-repeat records: for Adriana to confirm

These records give the country's own name as the state: "Panama" on a Panama record, "Mexico" on a Mexico record. ProcMine stored Naama (Algeria) and New Mexico (United States). The rule now **repoints** them, as you decided: Panama → **Panamá Province** (62) and Mexico → **Estado de México** (10).

That's a legitimate reading, but the source may simply have repeated the country name in its state field, in which case the true state is unknown. **Adriana, please confirm these against the sources** (USGS MRDS for 70, VMS for 2). Also in `reports/p2b/country_name_repeats.csv`.

| # | site_id | source file | observed | stored by ProcMine | repointed to |
|---:|---|---|---|---|---|
| 1 | `site__mrdata-usgs-gov-mrds__10106734__umn` | `umn/mrdata_mrds/b061.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 2 | `site__mrdata-usgs-gov-mrds__10182436__umn` | `umn/mrdata_mrds/b002.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 3 | `site__mrdata-usgs-gov-mrds__10182442__umn` | `umn/mrdata_mrds/b041.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 4 | `site__mrdata-usgs-gov-mrds__10230586__umn` | `umn/mrdata_mrds/b057.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 5 | `site__mrdata-usgs-gov-mrds__10255198__umn` | `umn/mrdata_mrds/b023.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 6 | `site__mrdata-usgs-gov-mrds__10256515__umn` | `umn/mrdata_mrds/b010.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 7 | `site__mrdata-usgs-gov-mrds__10302935__umn` | `umn/mrdata_mrds/b020.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 8 | `site__mrdata-usgs-gov-mrds__60001685__umn` | `umn/mrdata_mrds/b031.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 9 | `site__mrdata-usgs-gov-vms__1161__umn` | `umn/mrdata_vms/b008.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 10 | `site__mrdata-usgs-gov-vms__1162__umn` | `umn/mrdata_vms/b017.json` | Mexico | Q6879 New Mexico (United States) | Q4540 Estado de México |
| 11 | `site__mrdata-usgs-gov-mrds__10057089__umn` | `umn/mrdata_mrds/b034.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 12 | `site__mrdata-usgs-gov-mrds__10057091__umn` | `umn/mrdata_mrds/b006.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 13 | `site__mrdata-usgs-gov-mrds__10057092__umn` | `umn/mrdata_mrds/b026.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 14 | `site__mrdata-usgs-gov-mrds__10057093__umn` | `umn/mrdata_mrds/b041.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 15 | `site__mrdata-usgs-gov-mrds__10057094__umn` | `umn/mrdata_mrds/b041.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 16 | `site__mrdata-usgs-gov-mrds__10057096__umn` | `umn/mrdata_mrds/b027.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 17 | `site__mrdata-usgs-gov-mrds__10057098__umn` | `umn/mrdata_mrds/b044.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 18 | `site__mrdata-usgs-gov-mrds__10057099__umn` | `umn/mrdata_mrds/b007.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 19 | `site__mrdata-usgs-gov-mrds__10057100__umn` | `umn/mrdata_mrds/b040.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 20 | `site__mrdata-usgs-gov-mrds__10057102__umn` | `umn/mrdata_mrds/b004.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 21 | `site__mrdata-usgs-gov-mrds__10057103__umn` | `umn/mrdata_mrds/b026.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 22 | `site__mrdata-usgs-gov-mrds__10057104__umn` | `umn/mrdata_mrds/b011.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 23 | `site__mrdata-usgs-gov-mrds__10057106__umn` | `umn/mrdata_mrds/b033.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 24 | `site__mrdata-usgs-gov-mrds__10057107__umn` | `umn/mrdata_mrds/b060.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 25 | `site__mrdata-usgs-gov-mrds__10057110__umn` | `umn/mrdata_mrds/b003.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 26 | `site__mrdata-usgs-gov-mrds__10057111__umn` | `umn/mrdata_mrds/b017.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 27 | `site__mrdata-usgs-gov-mrds__10057112__umn` | `umn/mrdata_mrds/b046.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 28 | `site__mrdata-usgs-gov-mrds__10057114__umn` | `umn/mrdata_mrds/b025.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 29 | `site__mrdata-usgs-gov-mrds__10057117__umn` | `umn/mrdata_mrds/b049.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 30 | `site__mrdata-usgs-gov-mrds__10057118__umn` | `umn/mrdata_mrds/b039.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 31 | `site__mrdata-usgs-gov-mrds__10057119__umn` | `umn/mrdata_mrds/b028.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 32 | `site__mrdata-usgs-gov-mrds__10057120__umn` | `umn/mrdata_mrds/b025.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 33 | `site__mrdata-usgs-gov-mrds__10057121__umn` | `umn/mrdata_mrds/b046.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 34 | `site__mrdata-usgs-gov-mrds__10057122__umn` | `umn/mrdata_mrds/b024.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 35 | `site__mrdata-usgs-gov-mrds__10057125__umn` | `umn/mrdata_mrds/b050.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 36 | `site__mrdata-usgs-gov-mrds__10057127__umn` | `umn/mrdata_mrds/b058.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 37 | `site__mrdata-usgs-gov-mrds__10057128__umn` | `umn/mrdata_mrds/b002.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 38 | `site__mrdata-usgs-gov-mrds__10057130__umn` | `umn/mrdata_mrds/b021.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 39 | `site__mrdata-usgs-gov-mrds__10057132__umn` | `umn/mrdata_mrds/b032.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 40 | `site__mrdata-usgs-gov-mrds__10057134__umn` | `umn/mrdata_mrds/b008.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 41 | `site__mrdata-usgs-gov-mrds__10057135__umn` | `umn/mrdata_mrds/b027.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 42 | `site__mrdata-usgs-gov-mrds__10057137__umn` | `umn/mrdata_mrds/b061.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 43 | `site__mrdata-usgs-gov-mrds__10057142__umn` | `umn/mrdata_mrds/b043.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 44 | `site__mrdata-usgs-gov-mrds__10057155__umn` | `umn/mrdata_mrds/b010.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 45 | `site__mrdata-usgs-gov-mrds__10057156__umn` | `umn/mrdata_mrds/b019.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 46 | `site__mrdata-usgs-gov-mrds__10057158__umn` | `umn/mrdata_mrds/b013.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 47 | `site__mrdata-usgs-gov-mrds__10057342__umn` | `umn/mrdata_mrds/b000.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 48 | `site__mrdata-usgs-gov-mrds__10057346__umn` | `umn/mrdata_mrds/b032.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 49 | `site__mrdata-usgs-gov-mrds__10057347__umn` | `umn/mrdata_mrds/b061.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 50 | `site__mrdata-usgs-gov-mrds__10057416__umn` | `umn/mrdata_mrds/b010.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 51 | `site__mrdata-usgs-gov-mrds__10057418__umn` | `umn/mrdata_mrds/b007.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 52 | `site__mrdata-usgs-gov-mrds__10057419__umn` | `umn/mrdata_mrds/b047.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 53 | `site__mrdata-usgs-gov-mrds__10057420__umn` | `umn/mrdata_mrds/b027.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 54 | `site__mrdata-usgs-gov-mrds__10057421__umn` | `umn/mrdata_mrds/b016.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 55 | `site__mrdata-usgs-gov-mrds__10057422__umn` | `umn/mrdata_mrds/b054.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 56 | `site__mrdata-usgs-gov-mrds__10057426__umn` | `umn/mrdata_mrds/b004.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 57 | `site__mrdata-usgs-gov-mrds__10057428__umn` | `umn/mrdata_mrds/b026.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 58 | `site__mrdata-usgs-gov-mrds__10057429__umn` | `umn/mrdata_mrds/b001.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 59 | `site__mrdata-usgs-gov-mrds__10057431__umn` | `umn/mrdata_mrds/b003.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 60 | `site__mrdata-usgs-gov-mrds__10057432__umn` | `umn/mrdata_mrds/b001.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 61 | `site__mrdata-usgs-gov-mrds__10057433__umn` | `umn/mrdata_mrds/b058.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 62 | `site__mrdata-usgs-gov-mrds__10057434__umn` | `umn/mrdata_mrds/b039.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 63 | `site__mrdata-usgs-gov-mrds__10057435__umn` | `umn/mrdata_mrds/b036.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 64 | `site__mrdata-usgs-gov-mrds__10057436__umn` | `umn/mrdata_mrds/b060.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 65 | `site__mrdata-usgs-gov-mrds__10057437__umn` | `umn/mrdata_mrds/b047.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 66 | `site__mrdata-usgs-gov-mrds__10057438__umn` | `umn/mrdata_mrds/b027.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 67 | `site__mrdata-usgs-gov-mrds__10061670__umn` | `umn/mrdata_mrds/b012.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 68 | `site__mrdata-usgs-gov-mrds__10064753__umn` | `umn/mrdata_mrds/b033.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 69 | `site__mrdata-usgs-gov-mrds__10100787__umn` | `umn/mrdata_mrds/b022.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 70 | `site__mrdata-usgs-gov-mrds__10100790__umn` | `umn/mrdata_mrds/b059.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 71 | `site__mrdata-usgs-gov-mrds__10100791__umn` | `umn/mrdata_mrds/b031.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |
| 72 | `site__mrdata-usgs-gov-mrds__10100792__umn` | `umn/mrdata_mrds/b008.json` | Panama | Q2118 Naama (Algeria) | Q5076 Panamá Province |

## B7: acceptance query

`acceptance/problem2_state_country_conflict.sql`: (1) the count of merged entities whose state belongs to none of their countries; (2) the survivors grouped by `(observed_name, countries)` for triage. It's SQL against Postgres, because the normalized ids live only there and this fix leaves the RDF unchanged.

**Expected after the rebuild: 0 on this data.** The brief expected the 11 same-country collisions and the alias gap to keep a floor above zero, but neither leaves a conflict. Same-country collisions aren't conflicts, and alias-gap records are *dropped*, which leaves them with no state at all. On this data the count goes from 5,856 to **0** with both patches, or 7 with the repair alone. What the rule can't repair, it *drops*: 671 merged entities end up with no state rather than a wrong one, and those don't count as conflicts. On live data the number can differ (Adriana's count is 2 higher than this snapshot, and new records keep arriving), which is what query 2 is for.

**Validated on a throwaway local Postgres**, loaded through upstream's own Postgres loader (`PostgresLoaderService.restore`) with the full local ETL output: before the fix it returns **5,856** (equal to the Python count), and the triage query lists 347 `(observed_name, countries)` groups, led by Florida / United States (1,649). After the fix it returns **0**, and the triage query returns no rows. I also ran migration 005 there: down, up, then up again, which is idempotent. Existing rows get `NULL` codes until a data load fills them. 🟢 Not run against production.

## What in the brief turned out wrong

1. **The B2 table assumed `state_code` was available to MinMod.** It wasn't, in either the Postgres table or the entity JSON. The code tier needs a new nullable column and migration `005` (above). 🟢
2. **"It will not reach zero while the 11 same-country collisions and the alias gap remain"**: neither leaves a conflict. The floor is entirely merge pairings: 7 with the repair alone, 0 with B3. 🟢
3. **B5's scores** were computed on folded names. ProcMine's own keys give 0.6570 and 0.5704 for two of the rows. The picks are the same. 🟢
4. **`location.py:113` → `:116`**, and **the merge-cache bump stays out of this patch**: both as you corrected.
5. **The ETL isn't deterministic in `refid`s** (168 entities between two identical runs). That doesn't change any value, but anyone diffing two loads will see it. 🟢
6. From Part A: most conflicts come from ProcMine's no-floor fuzzy fallback, not shadowing. The rule fixes both kinds, as these numbers show.

## Everything that was run

```bash
export CFG_FILE=upstream-p2/tests/resources/config.yml
git -C upstream-p2 submodule update --init                        # vendored schema, for a fair test baseline
# gates 1-2, record level, the 72 repeats, the remaining drops (before any upstream change)
.venv-p2/bin/python investigation/p2b_measure.py gates            # -> reports/p2b/gates.json
.venv-p2/bin/python investigation/p2b_measure.py records          # -> reports/p2b/records.json, country_name_repeats.csv
.venv-p2/bin/python investigation/p2b_measure.py merged           # repair-only simulation -> reports/p2b/merged.json
python3 investigation/p2b_alias_sizing.py                         # -> reports/p2b/alias_sizing.txt
# the real pipeline: baseline, baseline again (noise), repair only (5318bdf), repair + B3 (9d68111)
.venv-p2/bin/python investigation/p2_run_etl.py investigation/p2_etl.yml <workdir> data-p2
.venv-p2/bin/python investigation/p2b_compare.py kgdata-p2 kgdata-p2-base2 noise_base_vs_base2
.venv-p2/bin/python investigation/p2b_compare.py kgdata-p2 kgdata-p2-repair base_vs_pipeline_repair_only
.venv-p2/bin/python investigation/p2b_compare.py kgdata-p2 kgdata-p2-after base_vs_pipeline_full
python3 investigation/p2b_rdf_check.py kgdata-p2 kgdata-p2-after  # KG export unchanged
# B4
.venv-p2/bin/python -m pytest tests/test_p2_repair.py tests/test_p2_dedup_pairing.py -q
(cd upstream-p2 && ../.venv-p2/bin/python -m pytest tests -q --no-cov)   # before (83f9b7b) and after (9d68111)
# B5 (ProcMine's scorer; same uv environment as Part A's p2_procmine_tables.py)
PYTHONPATH=upstream-procmine uv run --no-project --python 3.11 --with polars==1.19.0 ... python investigation/p2b_fuzzy_table.py data-p2/data/entities
# B7, on a throwaway local Postgres (initdb / pg_ctl in a temp folder)
.venv-p2/bin/python investigation/p2b_sql_check.py kgdata-p2 "postgresql+psycopg://postgres@/before?host=...&port=..." before
.venv-p2/bin/python investigation/p2b_sql_check.py kgdata-p2-after "postgresql+psycopg://postgres@/after?host=...&port=..." after
```

## Rules check

- No PR was opened for this branch. `fix/p2-state-repair` was later pushed to `usc-isi-i2/ta2-minmod-kg`, as a branch only, for review. Nothing was pushed to `main` or to any `DARPA-CRITICALMAAS` repo.
- No query, POST or write went to the live graph or production Postgres. The only databases used were throwaway local Postgres clusters.
- `data/`, `upstream*/`, `data-p2/`, `kgdata-p2*/` and `.venv*/` stay gitignored. No client spreadsheets are involved in Problem 2.
