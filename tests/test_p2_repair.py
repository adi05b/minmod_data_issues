"""Problem 2, B4: the merge-time state repair, against the real reference tables.

Runs on the patched upstream (upstream-p2, branch fix/p2-state-repair) and the
pinned data (data-p2 @ 3a086a5):

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python -m pytest tests/test_p2_repair.py -q
"""

from __future__ import annotations

import collections
import copy
import csv
import glob
import json
import sys
from pathlib import Path

import pytest
from minmodkg.misc import state_repair as upstream
from minmodkg.models.kg.base import NS_MR
from minmodkg.models.kg.location_info import LocationInfo
from minmodkg.models.kgrel.custom_types.location import Location, LocationView

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data-p2/data"
sys.path.insert(0, str(ROOT / "reference"))
import state_repair as reference  # noqa: E402

countries = list(csv.DictReader(open(DATA / "entities/country.csv", newline="", encoding="utf-8")))
CID = {c["name"]: c["minmod_id"] for c in countries}


class State:
    def __init__(self, r):
        self.id, self.name = r["minmod_id"], r["name"]
        self.country, self.state_code = CID[r["country_name"]], r["state_code"]


STATES = [State(r) for r in csv.DictReader(open(DATA / "entities/state_or_province.csv", newline="", encoding="utf-8"))]
BY_ID = {s.id: s for s in STATES}
IDX = upstream.StateCountryIndex.build(STATES)
# ProcMine's table: lowercased name -> first id in file order (identical to its own
# compile_entities output; see reports/p2/procmine_tables.txt)
PM: dict[str, str] = {}
for _s in STATES:
    PM.setdefault(_s.name.lower(), _s.id)
SHADOWED = [s.id for s in STATES if s.id not in set(PM.values())]


def test_tables():
    assert len(STATES) == 5084 and len(countries) == 250
    assert len(PM) == 4967 and len(SHADOWED) == 117


# ---- A. recovery: the 117 entities ProcMine can never select ----


def test_a_recovery():
    acts, right, kept = collections.Counter(), 0, []
    for sid in SHADOWED:
        s = BY_ID[sid]
        act, got = IDX.repair(PM[s.name.lower()], s.name, [s.country])
        acts[act] += 1
        right += got == sid
        if act == "keep":
            kept.append(s.name)
    assert dict(acts) == {"repoint": 104, "keep": 11, "drop": 2}
    assert right == 104
    # the 11 are same-named states inside one country: a country-based rule has
    # nothing to discriminate on, so it rightly leaves them alone
    assert sorted(kept)[:3] == ["Arecibo", "Caguas", "Carolina"]


# ---- B. regression, the gate: every assignment ProcMine already gets right ----


def test_b_regression_gate():
    correct = [s for s in STATES if PM[s.name.lower()] == s.id]
    altered = [s.id for s in correct if IDX.repair(s.id, s.name, [s.country]) != ("keep", s.id)]
    assert len(correct) == 4967
    assert altered == []


# ---- C. inert without a recorded country ----


def test_c_inert_without_country():
    assert all(IDX.repair(s.id, s.name, []) == ("keep", s.id) for s in STATES)
    assert all(IDX.repair(s.id, None, []) == ("keep", s.id) for s in STATES)


# ---- D. the reported cases (reference/verify.py) ----

CASES = [
    ("Florida", "United States", "Q6850"),
    ("La Paz", "Bolivia", "Q2453"),
    ("Potosi", "Bolivia", "Q2456"),
    ("Oruro", "Bolivia", "Q2454"),
    ("Santa Cruz", "Bolivia", "Q2457"),
    ("Camaguey", "Cuba", "Q2887"),
    ("Bolivar", "Venezuela", "Q6958"),
    ("Saint Andrew", "Jamaica", "Q3902"),
    ("Tete", "Mozambique", "Q4744"),
    ("Yukon Territory*", "Canada", "Q2665"),
    # drops; four are correct: Spain's table is provinces (no Andalusia), Odisha
    # replaced Orissa, Katanga was split in 2015, Elko is a county
    ("Michoacan", "Mexico", None),
    ("Valle D'Aosta", "Italy", None),
    ("Andalusia", "Spain", None),
    ("Orissa", "India", None),
    ("Katanga", "Democratic Republic of the Congo", None),
    ("Elko County", "United States", None),
]


@pytest.mark.parametrize("observed,country,expected", CASES)
def test_d_reported_cases(observed, country, expected):
    assert IDX.resolve(observed, [CID[country]]) == expected


# ---- the gates added for Part B ----


def test_gate_self_resolution():
    """Each state's own name, in its own country, finds itself or nothing."""
    ok, ambiguous, wrong = 0, 0, []
    for s in STATES:
        got = IDX.resolve(s.name, [s.country])
        if got == s.id:
            ok += 1
        elif got is None:
            ambiguous += 1
        else:
            wrong.append((s.name, got))
    assert (ok, ambiguous, wrong) == (5058, 26, [])


# ---- the new tiers and folding ----


def test_code_tier():
    us = CID["United States"]
    assert BY_ID[IDX.resolve("CO", [us])].name == "Colorado"
    assert BY_ID[IDX.resolve("ca", [us])].name == "California"  # case-insensitive
    assert IDX.resolve("CO", [CID["Canada"]]) is None  # only inside the recorded country


def test_name_beats_code():
    """A synthetic country where one state's code is another state's name."""
    s1, s2 = State.__new__(State), State.__new__(State)
    s1.id, s1.name, s1.country, s1.state_code = "X1", "Ica", "C", "AA"
    s2.id, s2.name, s2.country, s2.state_code = "X2", "Other", "C", "ICA"
    idx = upstream.StateCountryIndex.build([s1, s2])
    assert idx.resolve("ICA", ["C"]) == "X1"
    assert idx.resolve("AA", ["C"]) == "X1"


def test_folding():
    assert upstream.fold_name("Elazığ") == "elazig"
    assert upstream.fold_name("İzmir") == "izmir"
    assert upstream.drop_admin_words(upstream.fold_name("Provincia de Cartago")) == "cartago"
    assert upstream.drop_admin_words(upstream.fold_name("El Beni")) == "beni"
    bo, cr, tr = CID["Bolivia"], CID["Costa Rica"], CID["Turkey"]
    assert BY_ID[IDX.resolve("El Beni", [bo])].name == "Beni Department"
    assert BY_ID[IDX.resolve("Cartago", [cr])].name == "Provincia de Cartago"
    assert BY_ID[IDX.resolve("Elazig", [tr])].name == "Elazığ"


def test_name_fallback_without_observed_name():
    # "UMN Exact Match v1" records carry no observed_name: Florida (Uruguay) stored
    # on a US record is re-resolved by the stored state's own name
    q6920 = next(s for s in STATES if s.name == "Florida" and s.country == CID["Uruguay"])
    assert IDX.repair(q6920.id, None, [CID["United States"]]) == ("repoint", "Q6850")
    assert IDX.repair(q6920.id, "  ", [CID["United States"]]) == ("repoint", "Q6850")


def test_port_matches_reference_on_every_state_and_country():
    ref = reference.StateCountryIndex.build(STATES)
    cids = sorted({s.country for s in STATES})
    for s in STATES:
        for key in (s.name, s.state_code, s.name.upper() + " PROVINCE"):
            assert IDX.resolve(key, [s.country]) == ref.resolve(key, [s.country])
        assert IDX.repair(s.id, s.name, [cids[0]]) == ref.repair(s.id, s.name, [cids[0]])


# ---- the wired code path, on every raw record ----


def test_from_location_on_the_corpus():
    """LocationView.from_location with the index, on every raw record: it must equal
    the per-candidate repair, never touch the input, and give 5,421 / 737."""
    acts = collections.Counter()
    for f in sorted(glob.glob(str(DATA / "mineral-sites/*/*/*.json"))):
        for r in json.load(open(f)):
            if not r.get("location_info"):
                continue
            li = LocationInfo.from_dict(r["location_info"])
            loc = Location(country=li.country, state_or_province=li.state_or_province)
            snapshot = copy.deepcopy(loc.to_dict())
            plain = LocationView.from_location(loc, {})
            fixed = LocationView.from_location(loc, {}, IDX)
            assert loc.to_dict() == snapshot  # the raw location is never mutated
            assert fixed.country == plain.country  # the country is never repaired
            expected = []
            for c in loc.state_or_province:
                if c.normalized_uri is None:
                    continue
                act, sid = IDX.repair(NS_MR.id(c.normalized_uri), c.observed_name, plain.country)
                if act != "keep":
                    acts[act] += 1
                if sid is not None:
                    expected.append(sid)
            assert fixed.state_or_province == expected
    assert dict(acts) == {"repoint": 5421, "drop": 737}
