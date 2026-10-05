"""Repair state_or_province candidates whose entity sits in a different country
than the one recorded on the same record.

Problem 2. The upstream matcher (ProcMine ``identify_entity_id``) keys its
state lookup on the bare lowercased name, keeps the first row in file order,
and never sees the record's country. The file is sorted by country A->Z, so
117 of 5,084 state entities are unreachable and the observed string resolves
to whichever same-named state belongs to the alphabetically-first country.
``Florida`` resolves to Q5307 (Puerto Rico); Q6850 (United States) is absent
from that lookup table entirely.

MinMod loads the same table keyed on id, so every state *is* reachable here,
each carrying its country. That is enough to repair the choice at merge time
without re-running extraction.

The rule is deliberately narrow:

* it engages only when the chosen state's country contradicts a country
  already recorded on the record -- a correct assignment is never touched;
* it re-resolves the record's own ``observed_name`` against only the states
  of the recorded country, by exact name and then with administrative words
  dropped ("La Paz" -> "La Paz Department");
* a unique hit replaces the normalized_uri; no hit, or more than one, drops
  it and leaves ``observed_name`` in place for a curator.

It never guesses. Fuzzy matching inside the country is a separate decision
that needs its own corpus measurement -- see docs.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# Administrative words that sources drop and the reference list keeps,
# counted from the 5,084 names in state_or_province.csv.
ADMIN_WORDS = frozenset(
    {
        "district",
        "municipality",
        "province",
        "region",
        "prefecture",
        "county",
        "department",
        "oblast",
        "parish",
        "governorate",
        "state",
        "territory",
        "division",
        "council",
        "autonomous",
        "city",
        "area",
        "zone",
        "krai",
        "raion",
        "voivodeship",
        "canton",
        "emirate",
        "special",
        "metropolitan",
        "administrative",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def fold_name(name: str) -> str:
    """Lowercase, strip diacritics, reduce punctuation to single spaces."""
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_ALNUM.sub(" ", stripped.lower()).strip()


def drop_admin_words(folded: str) -> str:
    """Remove administrative words. Falls back to the input if nothing is left."""
    words = [w for w in folded.split() if w not in ADMIN_WORDS]
    return " ".join(words) if words else folded


@dataclass
class StateCountryIndex:
    """State -> country, plus per-country name indexes for re-resolution."""

    state_country: dict[str, Optional[str]] = field(default_factory=dict)
    _exact: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    _folded: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @classmethod
    def build(cls, states: Iterable) -> StateCountryIndex:
        """``states`` is any iterable of objects with .id, .name, .country."""
        self = cls()
        for s in states:
            self.state_country[s.id] = s.country
            if s.country is None:
                continue
            folded = fold_name(s.name)
            self._exact.setdefault(s.country, {}).setdefault(folded, []).append(s.id)
            self._folded.setdefault(s.country, {}).setdefault(
                drop_admin_words(folded), []
            ).append(s.id)
        return self

    def resolve(self, observed_name: str, country_ids: Sequence[str]) -> Optional[str]:
        """The one state in ``country_ids`` matching ``observed_name``, or None.

        Exact folded name first so that a real "Berat County" is not confused
        with "Berat District" in the same country; only then the admin-word-free
        form, which is what lets "La Paz" reach "La Paz Department".
        """
        if not observed_name or not country_ids:
            return None
        folded = fold_name(observed_name)
        for index, key in ((self._exact, folded), (self._folded, drop_admin_words(folded))):
            hits: list[str] = []
            for cid in country_ids:
                hits.extend(index.get(cid, {}).get(key, ()))
            hits = list(dict.fromkeys(hits))
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                return None  # ambiguous inside the country; do not guess
        return None

    def conflicts(self, state_id: str, country_ids: Sequence[str]) -> bool:
        """True when this state belongs to none of the recorded countries."""
        if not country_ids:
            return False
        owner = self.state_country.get(state_id)
        return owner is not None and owner not in country_ids
