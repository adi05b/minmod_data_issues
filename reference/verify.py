import csv, collections
from dataclasses import dataclass
from typing import Optional
from state_repair import StateCountryIndex

import os, sys
E = os.environ.get("ENTITY_DIR", ".")
if not E.endswith("/"): E += "/"

@dataclass
class S:
    id: str; name: str; country: Optional[str]

countries = list(csv.DictReader(open(E+"country.csv")))
cname2id = {c["name"]: c["minmod_id"] for c in countries}
raw = list(csv.DictReader(open(E+"state_or_province.csv")))
states = [S(r["minmod_id"], r["name"], cname2id[r["country_name"]]) for r in raw]
by_id = {s.id: s for s in states}

idx = StateCountryIndex.build(states)

# ProcMine's table, reproduced: lowercase(name) -> first id in file order
pm = {}
for s in states:
    pm.setdefault(s.name.lower(), s.id)
shadowed = [s.id for s in states if s.id not in set(pm.values())]

def repair(state_id, observed_name, country_ids):
    """What the production rule would do. -> (action, new_state_id)"""
    if not idx.conflicts(state_id, country_ids):
        return ("keep", state_id)
    fixed = idx.resolve(observed_name, country_ids)
    return ("repoint", fixed) if fixed else ("drop", None)

print("="*78)
print("A. RECOVERY — the 117 entities ProcMine can never select")
print("="*78)
acts = collections.Counter(); right = 0
for sid in shadowed:
    s = by_id[sid]
    wrong = pm[s.name.lower()]                 # what MinMod stores today
    act, got = repair(wrong, s.name, [s.country])
    acts[act] += 1
    if got == sid: right += 1
print(f"  recovered to the correct entity : {right} / {len(shadowed)}")
print(f"  actions                         : {dict(acts)}")

print()
print("="*78)
print("B. REGRESSION — every assignment ProcMine already gets right")
print("="*78)
untouched = altered = 0
for s in states:
    if pm.get(s.name.lower()) != s.id:
        continue
    act, got = repair(s.id, s.name, [s.country])
    if act == "keep" and got == s.id: untouched += 1
    else:
        altered += 1
        if altered <= 5: print("   ALTERED:", s.name, s.country, act, got)
print(f"  untouched : {untouched}")
print(f"  altered   : {altered}")

print()
print("="*78)
print("C. NO COUNTRY ON THE RECORD — rule must be inert")
print("="*78)
inert = sum(1 for s in states if repair(s.id, s.name, []) == ("keep", s.id))
print(f"  left alone when no country recorded: {inert} / {len(states)}")

print()
print("="*78)
print("D. THE REPORTED CASES")
print("="*78)
CASES = [
 ("Florida","United States","Florida, Puerto Rico"),
 ("La Paz","Bolivia","La Pampa, Argentina"),
 ("Potosi","Bolivia","Porto, Portugal"),
 ("Oruro","Bolivia","Koror, Palau"),
 ("Santa Cruz","Bolivia","Santa Cruz, Argentina"),
 ("Camaguey","Cuba","Camuy, Puerto Rico"),
 ("Bolivar","Venezuela","Bolivar, Colombia"),
 ("Saint Andrew","Jamaica","Saint Andrew, Barbados"),
 ("Tete","Mozambique","Leyte, Philippines"),
 ("Yukon Territory*","Canada","Northern Territory, Australia"),
 ("Michoacan","Mexico","Michigan, United States"),
 ("Valle D'Aosta","Italy","Valletta, Malta"),
 ("Andalusia","Spain","Kandal, Cambodia"),
 ("Orissa","India","Garissa, Kenya"),
 ("Katanga","Democratic Republic of the Congo","Tanga, Tanzania"),
 ("Elko County","United States","Puerto Rico @0.371"),
]
print(f"  {'observed':<17}{'country':<11}{'stored today':<31}{'after the fix'}")
print("  " + "-"*74)
f = d = 0
for obs, cname, today in CASES:
    got = idx.resolve(obs, [cname2id[cname]])
    if got:
        out = f"-> {got} {by_id[got].name}"; f += 1
    else:
        out = "-> dropped (observed_name kept)"; d += 1
    print(f"  {obs:<17}{cname[:10]:<11}{today:<31}{out}")
print(f"\n  repointed: {f}    dropped: {d}")
