"""Option A, record level: the dependency mapping changes only what it should.

Run with the Option A code on the path. Every record with a location is
viewed twice through MinMod's own LocationView.from_location (coordinates
left out): with the dependency list empty, which is the alias-pass behaviour,
and with the reviewed list. Must hold:

  - every state candidate's repair outcome is identical (the list never
    touches resolve or repair);
  - a record's view changes only by a recorded sovereign becoming a listed
    dependency, its states unchanged, and only when one of its candidates is
    dropped and names that dependency.

Also compares the list before its last additions (PREVIOUS) with the list as
it is: only records naming an added dependency may change between the two.

    CFG_FILE=<option-a code>/tests/resources/config.yml PYTHONPATH=<option-a code> \\
      .venv-p2/bin/python investigation/p2d_option_a_measure.py <entities dir>

Writes reports/p2d/option_a_records.json.
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data-p2/data"
ENT = Path(sys.argv[1])

from minmodkg.etl.kgrel_entity import EntityDeserFn  # noqa: E402
from minmodkg.misc.state_repair import DEPENDENCIES, NOT_DEPENDENCIES, StateCountryIndex  # noqa: E402

countries = list(csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8")))
cname = {c["minmod_id"]: c["name"] for c in countries}
states = EntityDeserFn.read_state_or_province(ENT / "state_or_province.csv")
aliases = EntityDeserFn.read_state_or_province_aliases(ENT / "state_or_province.csv")
plain = StateCountryIndex.build(states, aliases, dependencies=())
listed = StateCountryIndex.build(states, aliases)
# the pairs added last (approved after review): United Kingdom -> Virgin
# Islands (British) and United Kingdom -> Cayman Islands
ADDED = {("Q1234", "Q1243"), ("Q1234", "Q1040")}
assert ADDED <= {(s, d) for s, d, _ in DEPENDENCIES}
previous = StateCountryIndex.build(
    states, aliases, dependencies=[x for x in DEPENDENCIES if (x[0], x[1]) not in ADDED])


def scan(path: str) -> dict:
    from minmodkg.models.kg.base import NS_MR
    from minmodkg.models.kg.location_info import LocationInfo
    from minmodkg.models.kg.mineral_site import MineralSiteIdent
    from minmodkg.models.kgrel.custom_types.location import Location, LocationView

    out = collections.Counter()
    moves, since_previous, candidate_changes = collections.Counter(), collections.Counter(), []
    for r in json.load(open(path, encoding="utf-8")):
        if not r.get("location_info"):
            continue
        li = LocationInfo.from_dict(r["location_info"])
        loc = Location(country=li.country, state_or_province=li.state_or_province)
        a = LocationView.from_location(loc, {}, plain)
        b = LocationView.from_location(loc, {}, listed)
        out["records"] += 1
        countries_ = [NS_MR.id(c.normalized_uri) for c in li.country if c.normalized_uri is not None]
        cs = list(dict.fromkeys(countries_))
        for c in li.state_or_province:
            if c.normalized_uri is None:
                continue
            sid = NS_MR.id(c.normalized_uri)
            out["state candidates"] += 1
            if plain.repair(sid, c.observed_name, cs) != listed.repair(sid, c.observed_name, cs):
                candidate_changes.append(MineralSiteIdent.from_dict(r).id)
        p = LocationView.from_location(loc, {}, previous)
        if (p.country, p.state_or_province) != (b.country, b.state_or_province):
            assert p.state_or_province == b.state_or_province, (p, b)
            swap = [(x, y) for x, y in zip(p.country, b.country) if x != y]
            assert len(swap) == 1 and swap[0] in ADDED, (p.country, b.country)
            since_previous[(cname[swap[0][0]], cname[swap[0][1]])] += 1
        if (a.country, a.state_or_province) == (b.country, b.state_or_province):
            out["view unchanged"] += 1
            continue
        out["view changed"] += 1
        assert a.state_or_province == b.state_or_province, (a, b)
        swap = [(x, y) for x, y in zip(a.country, b.country) if x != y]
        assert len(a.country) == len(b.country) and len(swap) == 1, (a.country, b.country)
        assert swap[0] in {(s, d) for s, d, _ in DEPENDENCIES}, swap
        assert swap[0] not in NOT_DEPENDENCIES
        names = [c.observed_name for c in li.state_or_province
                 if c.normalized_uri is not None
                 and listed.dependency(NS_MR.id(c.normalized_uri), c.observed_name, cs) == swap[0]]
        assert names, swap
        moves[(cname[swap[0][0]], names[0], cname[swap[0][1]])] += 1
    return {"counts": out, "moves": moves, "since_previous": since_previous, "candidate_changes": candidate_changes}


def main() -> None:
    files = sorted(glob.glob(str(DATA / "mineral-sites/*/*/*.json")))
    with ProcessPoolExecutor() as ex:
        parts = list(ex.map(scan, files, chunksize=8))
    counts, moves, since = collections.Counter(), collections.Counter(), collections.Counter()
    changed_candidates = []
    for p in parts:
        counts += p["counts"]
        moves += p["moves"]
        since += p["since_previous"]
        changed_candidates += p["candidate_changes"]
    res = {
        "entities_dir": str(ENT),
        "list": [f"{cname[s]} -> {cname[d]}: {', '.join(n)}" for s, d, n in DEPENDENCIES],
        "excluded": [f"{cname[s]} / {cname[d]}" for s, d in sorted(NOT_DEPENDENCIES)],
        **dict(counts),
        "state_candidates_with_a_different_repair_outcome": len(changed_candidates),
        "records_moved": {f"{s} | {o} -> {d}": n for (s, o, d), n in moves.most_common()},
        "records_changed_since_previous_list": {f"{s} -> {d}": n for (s, d), n in since.most_common()},
    }
    out = ROOT / "reports/p2d/option_a_records.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
