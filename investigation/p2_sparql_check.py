"""Check the investigation/sparql/*.rq queries before anyone runs them on the live graph.

The live endpoint only answers POST, so the queries were not run there. Instead
they run here, with rdflib, over TTL that the local ETL wrote for Fuseki
(kgdata-p2/data/mineral-sites/kg/<source>/<bucket>.ttl, the files the loader
would load) plus the state entity TTL. Each answer is compared with the same
count computed straight from the matching merged JSON (the records the TTL was
written from). The check uses the buckets holding the most conflicted records,
the bucket with the most state nodes lacking observed_name (the case a plain
triple pattern would silently drop), plus a few random ones.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2_sparql_check.py
"""

from __future__ import annotations

import collections
import csv
import glob
import json
import random
import sys
from pathlib import Path

import serde.json
from rdflib import Graph

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reference"))
sys.argv = sys.argv[:1] + ["kgdata-p2/data"]
sys.path.insert(0, str(ROOT / "investigation"))
from p2_merged import bad_states, idx  # noqa: E402  (same index as verify.py)

KG = ROOT / "kgdata-p2/data"
Q = ROOT / "investigation/sparql"
N_TOP, N_RANDOM = 6, 4


def candidates(ms: dict):
    loc = ms.get("location") or {}
    cs = [c["normalized_uri"].rsplit("/", 1)[1] for c in loc.get("country", []) if c.get("normalized_uri")]
    for c in loc.get("state_or_province", []):
        if c.get("normalized_uri"):
            yield c, c["normalized_uri"].rsplit("/", 1)[1], cs


merged = sorted(glob.glob(str(KG / "mineral-sites/merged/*/*.json.lz4")))
n_conf, n_noobs = {}, {}
for f in merged:
    cands = [c for x in serde.json.deser(f)["MineralSiteAndInventory"] for c in candidates(x["ms"])]
    n_conf[f] = sum(1 for _, st, cs in cands if bad_states([st], list(dict.fromkeys(cs))))
    n_noobs[f] = sum(1 for c, _, _ in cands if not (c.get("observed_name") or "").strip())
top = sorted(merged, key=lambda f: -n_conf[f])[:N_TOP]
top += [f for f in sorted(merged, key=lambda f: -n_noobs[f])[:1] if f not in top]
random.seed(2)
pick = top + random.sample([f for f in merged if f not in top], N_RANDOM)

g = Graph()
g.parse(KG / "entities/state_or_province.ttl", format="turtle")
exp = {"a1": collections.defaultdict(collections.Counter), "a1c": collections.defaultdict(collections.Counter),
       "a2": collections.Counter(), "a4": collections.Counter()}
for f in pick:
    ttl = f.replace("/merged/", "/kg/").replace(".json.lz4", ".ttl")
    g.parse(ttl, format="turtle")
    for x in serde.json.deser(f)["MineralSiteAndInventory"]:
        cands = list(candidates(x["ms"]))
        if cands:
            exp["a4"][len(set(cands[0][2]))] += 1
        for c, st, cs in cands:
            src, has = c.get("source"), int(bool((c.get("observed_name") or "").strip()))
            exp["a1"][src]["nodes"] += 1
            exp["a1"][src]["with"] += has
            if bad_states([st], list(dict.fromkeys(cs))):
                exp["a1c"][src]["nodes"] += 1
                exp["a1c"][src]["with"] += has
                exp["a2"][(c.get("observed_name"), st, " ".join(sorted(set(cs))))] += 1
print(f"graph: {len(g):,} triples from {len(pick)} buckets "
      f"({sum(n_conf[f] for f in pick)} conflicted candidates, "
      f"{sum(n_noobs[f] for f in pick)} state nodes without observed_name)")


def run(name):
    return list(g.query((Q / name).read_text()))


ok = True


def check(label, got, want):
    global ok
    same = got == want
    ok &= same
    print(f"  {'OK ' if same else 'MISMATCH'} {label}")
    if not same:
        print("     sparql:", got, "\n     json:  ", want)


got = {str(r.source): {"nodes": int(r.nodes), "with": int(r.with_observed_name)} for r in run("a1_observed_name_by_matcher.rq")}
check("a1_observed_name_by_matcher.rq", got, {k: dict(v) for k, v in exp["a1"].items()})
got = {str(r.source): {"nodes": int(r.conflicted_nodes), "with": int(r.with_observed_name)}
       for r in run("a1_conflicted_observed_name_by_matcher.rq")}
check("a1_conflicted_observed_name_by_matcher.rq", got, {k: dict(v) for k, v in exp["a1c"].items()})
got = collections.Counter()
for r in run("a2_conflicted_triples.rq"):
    obs = str(r.observed_name) if r.observed_name is not None else None
    got[(obs, str(r.state), " ".join(sorted(str(r.countries).split())))] += int(r.records)
check("a2_conflicted_triples.rq", dict(got), dict(exp["a2"]))
got = {int(r.n_countries): int(r.records) for r in run("a4_country_count.rq")}
check("a4_country_count.rq", got, dict(exp["a4"]))
print("ALL QUERIES AGREE WITH THE JSON" if ok else "SOME QUERIES DISAGREE")
json.dump({"buckets": [f.split("merged/")[1] for f in pick], "triples": len(g), "all_agree": ok},
          open(ROOT / "reports/p2/sparql_check.json", "w"), indent=2)
