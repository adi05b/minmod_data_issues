"""Phase 5 and Option A, merged entities, without building all 419,098 at once.

The pipeline's last step (prep_kgrel_input) builds every merged entity in one
process and does not fit in 14 GB here. It only reads the merged files, so:

  candidates <run>          entities that could be conflicted in that run: one
                            of its members' states lies outside some member's
                            countries (necessary for a conflict, whichever
                            member the election takes the country from)
  diff <run1> <run2>        entities whose merged inputs differ between two
                            runs (member views, partial merged entities;
                            inventories compared as sets, their order is
                            per-process hash noise)
  rebuild <run> <ids> <out> the final merged entity for each id, built exactly
                            as prep_kgrel_input builds it (from_dedup_sites
                            over every partial and member), with the code on
                            the path: run it with that run's own code
  report <entities> <out dir>   reads the files above, writes merged.json

Any entity outside a diff has identical inputs in both runs, so its final
merged entity is identical too: the diffs make the comparison complete.

    run=<ETL workdir>; CFG_FILE=<that code's config> [PYTHONPATH=<that code>] \\
      .venv-p2/bin/python investigation/p2d_merged.py ...
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import sys
from pathlib import Path

import serde.json


def merged_files(run: Path) -> dict[str, Path]:
    base = run / "data/mineral-sites/merged"
    return {str(p.relative_to(base)): p for p in sorted(base.glob("*/*"))}


def state_country(entities: Path) -> dict[str, str]:
    cname = {c["name"]: c["minmod_id"] for c in csv.DictReader(open(entities / "country.csv", encoding="utf-8"))}
    return {s["minmod_id"]: cname[s["country_name"]]
            for s in csv.DictReader(open(entities / "state_or_province.csv", encoding="utf-8"))}


def candidates(run: Path, entities: Path, out: Path) -> None:
    owner = state_country(entities)
    members = collections.defaultdict(list)
    for p in merged_files(run).values():
        for m in serde.json.deser(p)["MineralSiteAndInventory"]:
            v = m["ms"].get("location_view") or {}
            members[m["ms"]["dedup_site_id"]].append((v.get("country", []), v.get("state_or_province", [])))
    ids = []
    for e, ms in members.items():
        states = {s for _, ss in ms for s in ss}
        if any(cs and owner.get(s) and owner[s] not in cs for s in states for cs, _ in ms):
            ids.append(e)
    out.write_text(json.dumps(sorted(ids)))
    print(f"{run.name}: {len(members)} merged entities, {len(ids)} could be conflicted")


def diff(run1: Path, run2: Path, out: Path) -> None:
    f1, f2 = merged_files(run1), merged_files(run2)
    assert f1.keys() == f2.keys()
    ids, what = set(), collections.Counter()

    def norm(m):
        return {**m["ms"], "_invs": sorted(json.dumps(i, sort_keys=True) for i in m.get("invs", []))}

    for k in f1:
        a, b = serde.json.deser(f1[k]), serde.json.deser(f2[k])
        ma = {m["ms"]["site_id"]: m for m in a["MineralSiteAndInventory"]}
        mb = {m["ms"]["site_id"]: m for m in b["MineralSiteAndInventory"]}
        assert ma.keys() == mb.keys(), k
        for s in ma:
            x, y = norm(ma[s]), norm(mb[s])
            if x != y:
                ids.add(x["dedup_site_id"])
                for kk in set(x) | set(y):
                    if x.get(kk) != y.get(kk):
                        what[f"member {kk}"] += 1
        da = {d["id"]: d for d in a["DedupMineralSite"]}
        db = {d["id"]: d for d in b["DedupMineralSite"]}
        assert da.keys() == db.keys(), k
        for e in da:
            if da[e] != db[e]:
                ids.add(e)
                for kk in set(da[e]) | set(db[e]):
                    if da[e].get(kk) != db[e].get(kk):
                        what[f"partial {kk}"] += 1
    out.write_text(json.dumps({"ids": sorted(ids), "fields": dict(what.most_common())}))
    print(f"{run1.name} vs {run2.name}: {len(ids)} entities differ; {dict(what.most_common())}")


def rebuild(run: Path, ids_file: Path, out: Path) -> None:
    from minmodkg.models.kgrel.dedup_mineral_site import DedupMineralSite
    from minmodkg.models.kgrel.mineral_site import MineralSiteAndInventory

    ids = set(json.loads(ids_file.read_text()))
    partials, member_ids = collections.defaultdict(list), set()
    files = merged_files(run)
    for p in files.values():
        for x in serde.json.deser(p)["DedupMineralSite"]:
            if x["id"] in ids:
                partials[x["id"]].append(x)
                member_ids.update(r["site_id"] for r in x["ranked_sites"])
    sites = {}
    for p in files.values():
        for x in serde.json.deser(p)["MineralSiteAndInventory"]:
            if x["ms"]["site_id"] in member_ids:
                sites[x["ms"]["site_id"]] = MineralSiteAndInventory.from_dict(x)
    res = {}
    for e, lst in partials.items():
        dms_lst = [DedupMineralSite.from_dict(x) for x in lst]
        d = DedupMineralSite.from_dedup_sites(
            dms_lst, [sites[r.site_id] for dms in dms_lst for r in dms.ranked_sites], is_site_ranked=True
        ).dms.to_dict()
        res[e] = {"country": d["country"], "state_or_province": d["state_or_province"]}
    assert set(res) == ids, len(ids - set(res))
    out.write_text(json.dumps(res))
    import minmodkg
    print(f"{run.name}: rebuilt {len(res)} merged entities with {minmodkg.__file__}")


def report(entities: Path, work: Path, out: Path) -> None:
    owner = state_country(entities)
    names = {s["minmod_id"]: s["name"] for s in csv.DictReader(open(entities / "state_or_province.csv", encoding="utf-8"))}
    cname = {c["minmod_id"]: c["name"] for c in csv.DictReader(open(entities / "country.csv", encoding="utf-8"))}
    R = {r: json.loads((work / f"rebuilt_{r}.json").read_text()) for r in ("base", "A", "B", "C")}
    D = {k: json.loads((work / f"diff_{k}.json").read_text()) for k in ("base_A", "A_B", "B_C")}
    # every entity whose inputs differ between any two runs is rebuilt in all
    # four; any other entity is identical in all four, so deltas over the
    # rebuilt set are the deltas over all merged entities
    rebuilt = set(R["base"])
    assert all(set(R[r]) == rebuilt for r in R)
    assert all(set(D[k]["ids"]) <= rebuilt for k in D)

    def bad(d):
        return any(owner.get(s) and owner[s] not in d["country"]["value"] for s in d["state_or_province"]["value"])

    def outcome(d):
        return "still conflicted" if bad(d) else "state emptied" if not d["state_or_province"]["value"] else "state repointed"

    conflicted = {e for e, d in R["base"].items() if bad(d)}
    res = {
        "conflicted_in_base": len(conflicted),
        "outcome": {r: dict(collections.Counter(outcome(R[r][e]) for e in conflicted).most_common()) for r in ("A", "B", "C")},
        "conflicted_anywhere": {r: sum(map(bad, R[r].values())) for r in R},
        "rebuilt_entities": len(rebuilt),
        "merged_with_state_delta_vs_base": {
            r: sum(bool(R[r][e]["state_or_province"]["value"]) for e in rebuilt)
            - sum(bool(R["base"][e]["state_or_province"]["value"]) for e in rebuilt) for r in ("A", "B", "C")},
        "merged_with_country_delta_vs_base": {
            r: sum(bool(R[r][e]["country"]["value"]) for e in rebuilt)
            - sum(bool(R["base"][e]["country"]["value"]) for e in rebuilt) for r in ("A", "B", "C")},
        "country_value_changed_vs_base": {
            r: sum(R[r][e]["country"]["value"] != R["base"][e]["country"]["value"] for e in rebuilt)
            for r in ("A", "B", "C")},
    }
    for pair, (x, y) in (("base_A", ("base", "A")), ("A_B", ("A", "B")), ("B_C", ("B", "C"))):
        ch, moved, filled, unexpected = collections.Counter(), collections.Counter(), collections.Counter(), []
        for e in D[pair]["ids"]:
            a, b = R[x][e], R[y][e]
            cv = a["country"]["value"] != b["country"]["value"]
            sv = a["state_or_province"]["value"] != b["state_or_province"]["value"]
            if cv:
                ch["country value changed"] += 1
                moved[" | ".join(cname.get(c, c) for c in a["country"]["value"]) + " -> "
                      + " | ".join(cname.get(c, c) for c in b["country"]["value"])] += 1
            if sv:
                if not a["state_or_province"]["value"]:
                    ch["state filled (was empty)"] += 1
                    for s in b["state_or_province"]["value"]:
                        filled[names.get(s, s)] += 1
                else:
                    ch["state value changed otherwise"] += 1
                    unexpected.append({"id": e, "state": [a["state_or_province"]["value"], b["state_or_province"]["value"]]})
            if not cv and not sv:
                ch["inputs differ, country and state the same"] += 1
            if bad(b) and not bad(a):
                ch["newly conflicted"] += 1
                unexpected.append({"id": e, "newly conflicted": b})
        res[pair] = {"entities_with_different_inputs": len(D[pair]["ids"]), "input_fields": D[pair]["fields"],
                     "changes": dict(ch.most_common()), "country_moves": dict(moved.most_common()),
                     "states_filled": dict(filled.most_common()), "unexpected": unexpected[:20]}
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    cmd, args = sys.argv[1], [Path(a) for a in sys.argv[2:]]
    {"candidates": candidates, "diff": diff, "rebuild": rebuild, "report": report}[cmd](*args)
