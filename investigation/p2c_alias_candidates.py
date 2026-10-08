"""Problem 2, alias pass, step 2: candidate aliases for the drop list.

Reads reports/p2c/drop_list.csv (step 1), leaves out the groups that are
blocked on a decision and the two that the new Niamey and Ekaterinburg rows
cover, and gives each remaining group a proposed existing row, or none.

The proposals below are judgement, made one group at a time against the
table's own rows for that country. A target is proposed only when the observed
name is the same place as an existing row of the recorded country under
another name. Anything else (a city, a district, an island, a former unit that
was split or merged, a wrong recorded country, a row the table lacks) gets
"no suggestion" and a note saying why.

Then every proposal is checked, mechanically:
  - the target exists and is in the recorded country;
  - the observed name does not already fold to the target's name (accents
    need no alias);
  - with all proposed aliases in the index, every dropped candidate of the
    group repoints to the target, and no candidate anywhere that repoints or
    keeps without aliases changes;
  - no alias equals a real name of its country, and every alias resolves to
    its own state (the two data tests in ta2-minmod-kg).

A name can be right while the records it would repair lie elsewhere.
investigation/p2c_coordinates.py checks every name-based target against the
records' own points; the targets it rejects are in REJECTED_ON_COORDINATES
and go out as "no suggestion", with the evidence in the notes.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2c_drop_list.py
    CFG_FILE=... .venv-p2/bin/python investigation/p2c_coordinates.py <natural earth admin-1 geojson>
    CFG_FILE=... .venv-p2/bin/python investigation/p2c_alias_candidates.py

Writes reports/p2c/alias_candidates.csv (the six columns to review),
reports/p2c/alias_candidates_notes.md and reports/p2c/alias_candidates.json.
"""

from __future__ import annotations

import collections
import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "investigation"))
import p2c_drop_list as dl  # noqa: E402

from minmodkg.misc.state_repair import StateCountryIndex, fold_name  # noqa: E402

OUT = ROOT / "reports/p2c"
POINT = re.compile(r"POINT\s*\(\s*(-?[0-9.]+)\s+(-?[0-9.]+)\s*\)", re.I)

# Waiting on a decision; not touched, no rows for them.
BLOCKED = {
    ("Katanga", "Democratic Republic of the Congo"),
    ("Katanga Province", "Democratic Republic of the Congo"),
    ("Territory Of New Caledonia And Dependencies", "France"),
    ("Greenland", "Denmark"),
    ("Territory Of Christmas Island", "Australia"),
    ("Montserrat", "United Kingdom"),
    ("Kukes", "Albania"),
    ("Kankan", "Guinea"),
    ("Boke", "Guinea"),
    ("Kindia", "Guinea"),
    ("Korce", "Albania"),
}
# Covered by the two new rows (ta2-minmod-data branch add-niamey-ekaterinburg).
NEW_ROWS = {("Niamey", "Niger"): "Q7085", ("Ekaterinburg", "Russia"): "Q7086"}

RENAMED, LANG, TRANSLIT, LONGER = (
    "renamed",
    "other language",
    "transliteration",
    "longer official name",
)
# (observed name, recorded country) -> (target minmod_id, reason, note)
PROPOSALS = {
    ("Orissa", "India"): ("Q3657", RENAMED, "renamed Odisha in 2011"),
    ("Niedersachsen", "Germany"): ("Q3383", LANG, "German"),
    ("Attapu", "Laos"): ("Q4059", TRANSLIT, ""),
    ("Buryatiya", "Russia"): ("Q5463", TRANSLIT, ""),
    ("San Blas*", "Panama"): ("Q5071", RENAMED, "Comarca de San Blas, renamed Kuna Yala (1998), Guna Yala (2011)"),
    ("Aktyubinsk", "Kazakhstan"): ("Q3971", RENAMED, "renamed Aktobe in 1999"),
    ("Evvoia", "Greece"): ("Q3424", TRANSLIT, ""),
    ("Karnten", "Austria"): ("Q2215", LANG, "German (Kärnten)"),
    ("North-Western", "Zambia"): ("Q7072", TRANSLIT, "spelling: the table writes Northwestern; Zambia writes North-Western"),
    ("Steiermark", "Austria"): ("Q2218", LANG, "German"),
    ("Lappi", "Finland"): ("Q3211", LANG, "Finnish"),
    ("Hentiy", "Mongolia"): ("Q4615", TRANSLIT, ""),
    ("Nicosia", "Cyprus"): ("Q2906", LONGER, "row is Nicosia District (Lefkoşa)"),
    ("Kareliya", "Russia"): ("Q5467", TRANSLIT, ""),
    ("North-West Frontier", "Pakistan"): ("Q5030", RENAMED, "North-West Frontier Province, renamed Khyber Pakhtunkhwa in 2010"),
    ("Tuva", "Russia"): ("Q5485", LONGER, ""),
    ("Al Bahr Al Ahmar", "Egypt"): ("Q3122", LANG, "Arabic for Red Sea"),
    ("Al Kaf", "Tunisia"): ("Q6324", TRANSLIT, ""),
    ("Atlantico Nort", "Nicaragua"): ("Q4855", RENAMED, "Región Autónoma del Atlántico Norte, renamed Costa Caribe Norte in 2014; the source truncates Norte"),
    ("Hamgyong-Namdo", "North Korea"): ("Q4912", LANG, "Korean (namdo = South province)"),
    ("Hong Kong Special Administrative Region", "China"): ("Q2757", LONGER, "row is Hong Kong SAR"),
    ("Irkutskaya Oblast'", "Russia"): ("Q5425", TRANSLIT, "Russian adjectival form"),
    ("Kondoz [Kunduz]", "Afghanistan"): ("Q2019", TRANSLIT, ""),
    ("Limassol", "Cyprus"): ("Q2905", LONGER, "row is Limassol District (Leymasun)"),
    ("Niederosterreich", "Austria"): ("Q2216", LANG, "German"),
    ("Oberosterreich", "Austria"): ("Q2220", LANG, "German"),
    ("Zufar", "Oman"): ("Q5022", TRANSLIT, ""),
    ("An Nil Al Azra", "Sudan"): ("Q6012", LANG, "Arabic for Blue Nile (An Nil al Azraq); the source truncates the final q"),
    ("Buryatia", "Russia"): ("Q5463", LONGER, ""),
    ("Chui", "Kyrgyzstan"): ("Q4052", TRANSLIT, ""),
    ("Chungcheongnam-do", "South Korea"): ("Q5910", LANG, "Korean"),
    ("Distrito Federal*", "Mexico"): ("Q4536", RENAMED, "renamed Ciudad de México in 2016"),
    ("Eastern Highland", "Papua New Guinea"): ("Q5082", TRANSLIT, "spelling: singular of Eastern Highlands"),
    ("Ghowr [Ghor]", "Afghanistan"): ("Q2010", TRANSLIT, ""),
    ("Gumma", "Japan"): ("Q3920", TRANSLIT, "older Hepburn spelling of Gunma"),
    ("Hovsgol", "Mongolia"): ("Q4617", TRANSLIT, ""),
    ("Hwanghae-Bukto", "North Korea"): ("Q4907", LANG, "Korean (bukto = North province)"),
    ("Kamchatskaya Oblast'", "Russia"): ("Q5431", RENAMED, "Kamchatka Oblast became Kamchatka Krai in 2007, merged with the Koryak okrug that lay inside it: same territory"),
    ("Kangwon-Do", "South Korea"): ("Q5900", TRANSLIT, "McCune-Reischauer spelling of Gangwon; recorded country is South Korea"),
    ("Khakassia", "Russia"): ("Q5468", LONGER, ""),
    ("Kostenay Oblast", "Kazakhstan"): ("Q3979", TRANSLIT, ""),
    ("Michoacan", "Mexico"): ("Q4545", LONGER, "row is Michoacán de Ocampo"),
    ("Moskovskaya Oblast'", "Russia"): ("Q5448", TRANSLIT, "Russian adjectival form"),
    ("Nei Mongol", "China"): ("Q2760", LANG, "Chinese (pinyin) for Inner Mongolia"),
    ("North-Western Province", "Zambia"): ("Q7072", TRANSLIT, "spelling: the table writes Northwestern; Zambia writes North-Western"),
    ("Otjozondijupa", "Namibia"): ("Q4773", TRANSLIT, "misspelling of Otjozondjupa"),
    ("REGIÓN AUTÓNOMA DE LA COSTA CARIBE NORTE", "Nicaragua"): ("Q4855", LANG, "Spanish"),
    ("Sakhalinskaya Oblast'", "Russia"): ("Q5476", TRANSLIT, "Russian adjectival form"),
    ("Shandong [Shantung]", "China"): ("Q2769", TRANSLIT, "Wade-Giles in brackets"),
    ("Suhbaatar", "Mongolia"): ("Q4622", TRANSLIT, ""),
    ("Valle D'Aosta", "Italy"): ("Q3790", LANG, "Italian"),
    ("Yakutia", "Russia"): ("Q5475", LANG, "Russian name of the Sakha Republic"),
}

# The name means this row, but the records it would repair lie elsewhere
# (reports/p2c/coordinates.csv). Out as "no suggestion".
REJECTED_ON_COORDINATES = {
    ("Pulau Pinang", "Malaysia"): ("Q4389", LANG, "Malay for Penang, but all 5 records lie in Sabah, about 1,800 km away"),
    ("Al Buhayrah", "Egypt"): ("Q3103", TRANSLIT, "Beheira, but the record lies at Aswan, 690 km away; al-Buhayrah is also 'the lake' (Lake Nasser)"),
    ("Al Balqa'", "Jordan"): ("Q3961", TRANSLIT, "Balqa, but the record lies at Aqaba, 240 km away"),
    ("Chitinskaya Oblast'", "Russia"): ("Q5496", RENAMED, "Chita Oblast is now Zabaykalsky Krai, but the record lies in Amur Oblast, 130 km away"),
    ("Hwanghae-Namdo", "North Korea"): ("Q4913", LANG, "South Hwanghae, but the record lies in North Hamgyong, 365 km away"),
    ("Östergötlands Län", "Sweden"): ("Q6049", LANG, "Östergötland County, but the record lies in Jämtland, 600 km away"),
}

WRONG_COUNTRY = "the name belongs to another country than the one recorded"
NO_SUGGESTION = {
    ("Zacapa", "Guatemala"): "a real department missing from the table (Guatemala has 22, the table 21); needs a row, like Niamey",
    ("Samar", "Philippines"): "the island, not the province: 5 of the 6 records lie in Eastern Samar",
    ("Sogn Og Fjordane", "Norway"): "merged into Vestland in 2020: a part of it, not another name for it",
    ("Ch'Ungch'Ong-Bukto", "North Korea"): WRONG_COUNTRY + " (South Korea)",
    ("Oulu Laani", "Finland"): "former province, abolished 2009; now Northern Ostrobothnia and Kainuu",
    ("Westland", "New Zealand"): "a district inside West Coast Region",
    ("G�vleborg", "Sweden"): "Gävleborg with the ä destroyed by a broken encoding upstream; fix the source, not the vocabulary",
    ("Netherlands Antilles", "Netherlands"): "dissolved 2010 into several territories",
    ("Piura", "Brazil"): WRONG_COUNTRY + " (Peru)",
    ("Sidamo", "Ethiopia"): "former province, split in 1995",
    ("Sofiya", "Bulgaria"): "Sofia City Province or Sofia Province: two rows",
    ("Agadir", "Morocco"): "a city (seat of Agadir-Ida-Ou-Tanane prefecture), not the prefecture's name",
    ("Banska Bystricka Region", "Central African Republic"): WRONG_COUNTRY + " (Slovakia)",
    ("Brabant", "Belgium"): "former province, split in 1995",
    ("British Virgin Islands", "United Kingdom"): "no such row under the United Kingdom",
    ("Buller", "New Zealand"): "a district inside West Coast Region",
    ("Caminha", "Portugal"): "a municipality (Viana do Castelo district)",
    ("Eastern Finland", "Finland"): "former province spanning several regions",
    ("Khalkidhiki", "Greece"): "the Chalkidiki regional unit has no row (the Greek rows mix regions and units)",
    ("Oriente", "Cuba"): "former province, split in 1976",
    ("Rapu-Rapu Island", "Philippines"): "an island municipality in Albay",
    ("Semipalatinsk", "Kazakhstan"): "former oblast; merged 1997, most of it now Abai Region (2022), which the table lacks",
    ("Surigao*", "Philippines"): "Surigao del Norte or Surigao del Sur: two rows",
    ("Surigao", "Philippines"): "Surigao del Norte or Surigao del Sur: two rows",
    ("Turku", "Finland"): "a city",
    ("Vila Nova De Cerveira", "Portugal"): "a municipality (Viana do Castelo district)",
    ("Viti Levu Island", "Fiji Islands"): "an island spanning several provinces",
    ("Welega [Walaga]", "Ethiopia"): "former province, now zones of Oromia",
    ("York County", "Canada"): "a county",
    ("Alaska", "Canada"): WRONG_COUNTRY + " (United States)",
    ("Alto Alentejo", "Portugal"): "historical province spanning districts",
    ("Andalucía", "Spain"): "an autonomous community; the Spanish rows are provinces",
    ("Andalusia", "Spain"): "an autonomous community; the Spanish rows are provinces",
    ("BN", "Mexico"): "a two-letter abbreviation that is not a code in the table",
    ("BS", "Mexico"): "a two-letter abbreviation that is not a code in the table",
    ("Bad Bleiberg", "Austria"): "a municipality in Carinthia",
    ("Bayern [Bavaria, Germany]", "Czech Republic"): WRONG_COUNTRY + " (Germany)",
    ("British Columbia", "Finland"): WRONG_COUNTRY + " (Canada)",
    ("CO", "Mexico"): "a two-letter abbreviation that is not a code in the table",
    ("Castilla y León", "Spain"): "an autonomous community; the Spanish rows are provinces",
    ("Cayman Islands", "United Kingdom"): "no such row under the United Kingdom",
    ("Ch'Ungch'Ong-Bukto", "Democratic Republic of the Congo"): WRONG_COUNTRY + " (South Korea)",
    ("Ch'Ungch'Ong-Namdo", "Democratic Republic of the Congo"): WRONG_COUNTRY + " (South Korea)",
    ("Ch'Ungch'Ong-Namdo", "North Korea"): WRONG_COUNTRY + " (South Korea)",
    ("Chicha", "Peru"): "not a Peruvian region; unclear what it names",
    ("Cleveland", "United Kingdom"): "former county, abolished 1996 and split",
    ("Copiapó", "Chile"): "a province and city inside Atacama",
    ("Côte d’Ivoire", "Cote D'Ivoire (Ivory Coast)"): "the country's own name",
    ("Eastern Guinea", "Guinea"): "not an administrative unit",
    ("Eastern Slovakia", "Slovakia"): "a macro-region spanning two regions",
    ("Elko County", "United States"): "a county (Nevada)",
    ("Esmeralda County", "United States"): "a county (Nevada)",
    ("Extremadura", "Spain"): "an autonomous community; the Spanish rows are provinces",
    ("Guarayos", "Bolivia"): "a province inside Santa Cruz",
    ("Halmahera Island", "Indonesia"): "an island",
    ("Humboldt County", "United States"): "a county",
    ("Irian Jaya", "Indonesia"): "former name of all of western New Guinea, now several provinces",
    ("Kainantu", "Papua New Guinea"): "a town in Eastern Highlands",
    ("Karibib District", "Namibia"): "a constituency in Erongo",
    ("Kola Peninsula", "Russia"): "a peninsula",
    ("Kommune Kujalleq", "Greenland"): "the table has no Greenland rows",
    ("Kujalleq", "Greenland"): "the table has no Greenland rows",
    ("Qaasuitsup", "Greenland"): "the table has no Greenland rows",
    ("Qaqortoq District", "Greenland"): "the table has no Greenland rows",
    ("Kuril Islands", "Russia"): "an island chain",
    ("Labrador", "Canada"): "a part of Newfoundland and Labrador",
    ("Lapland", "Sweden"): "historical province spanning two counties",
    ("Liard Mining Division", "Canada"): "a mining division",
    ("Limousin", "France"): "former region, merged into Nouvelle-Aquitaine in 2016: a part of it",
    ("Melsiripura", "Sri Lanka"): "a town",
    ("Mirab Gojam", "Ethiopia"): "a zone of Amhara",
    ("Mirab Harerge", "Ethiopia"): "a zone of Oromia",
    ("Moramanga", "Madagascar"): "a district",
    ("Muhanga", "Rwanda"): "a district",
    ("Nevada", "Canada"): WRONG_COUNTRY + " (United States)",
    ("Northwest Region", "Yemen"): "not a Yemeni governorate",
    ("Nye", "United States"): "a county (Nevada)",
    ("Ostfold", "Norway"): "merged into Viken in 2020 (split out again in 2024): a part of it",
    ("Oulu", "Finland"): "a city, or the former province",
    ("SB", "Mexico"): "a two-letter abbreviation that is not a code in the table",
    ("SI", "Mexico"): "a two-letter abbreviation that is not a code in the table",
    ("Smaland", "Sweden"): "historical province spanning three counties",
    ("Southeast Alaska", "United States"): "a region of Alaska",
    ("Stevens County", "United States"): "a county",
    ("Timor Island", "Indonesia"): "an island",
    ("Troms", "Norway"): "merged into Troms og Finnmark in 2020 (split out again in 2024): a part of it",
    ("Western Churchill Province", "Canada"): "a geological province",
    ("Zhitigara District", "Kazakhstan"): "a district",
}


def haversine(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def record_points(conf: list[dict], keys: set) -> dict[tuple[str, str], list[tuple[float, float]]]:
    """WGS84 points of the records in the given groups (other CRSs are skipped)."""
    from minmodkg.models.kg.mineral_site import MineralSiteIdent

    wanted = collections.defaultdict(set)
    for r in conf:
        key = (r["observed_name"] or "", " | ".join(dl.cid2name[c] for c in r["cs"]))
        if key in keys:
            wanted[r["file"]].add((r["site_id"], key))
    points = collections.defaultdict(list)
    for file, ids in wanted.items():
        by_site = dict(ids)
        for rec in json.load(open(dl.DATA / "mineral-sites" / file, encoding="utf-8")):
            key = by_site.get(MineralSiteIdent.from_dict(rec).id)
            li = rec.get("location_info") or {}
            crs = ((li.get("crs") or {}).get("normalized_uri") or "").rsplit("/", 1)[-1]
            m = POINT.fullmatch((li.get("location") or "").strip())
            if key and m and crs in ("", "Q701"):
                points[key].append((float(m.group(2)), float(m.group(1))))
    return points


def coords_cell(c) -> str:
    if c is None:
        return ""
    informative = int(c["agree"]) + int(c["disagree"])
    return f"{c['agree']}/{informative}" if informative else "none"


def main() -> None:
    groups = list(csv.DictReader(open(OUT / "drop_list.csv", newline="", encoding="utf-8")))
    keys = [(g["observed_name"], g["recorded_country"]) for g in groups]
    assert len(set(keys)) == len(keys)
    for k in list(BLOCKED) + list(NEW_ROWS) + list(PROPOSALS) + list(REJECTED_ON_COORDINATES) + list(NO_SUGGESTION):
        assert k in keys, f"not a drop group: {k}"
    decided = set(PROPOSALS) | set(REJECTED_ON_COORDINATES) | set(NO_SUGGESTION)
    assert len(decided) == len(PROPOSALS) + len(REJECTED_ON_COORDINATES) + len(NO_SUGGESTION)
    assert not decided & (BLOCKED | set(NEW_ROWS))
    todo = [k for k in keys if k not in BLOCKED and k not in NEW_ROWS]
    assert set(todo) == decided, sorted(set(todo) ^ decided)

    rows = list(csv.DictReader(open(dl.ENT / "state_or_province.csv", newline="", encoding="utf-8")))
    raw = {r["minmod_id"]: r for r in rows}
    cname2id = {v: k for k, v in dl.cid2name.items()}
    records = {k: int(g["records"]) for k, g in zip(keys, groups)}

    # target exists, in the recorded country; not an accent-only variant
    for (obs, country), (target, _, _) in {**PROPOSALS, **REJECTED_ON_COORDINATES}.items():
        assert target in dl.by_id, target
        assert dl.cid2name[dl.by_id[target].country] == country, (obs, target)
        assert fold_name(obs) != fold_name(dl.by_id[target].name), (obs, target)

    # all proposals as aliases, on top of whatever the table already has
    aliases = {k: list(v) for k, v in dl.aliases.items()}
    for (obs, _), (target, _, _) in PROPOSALS.items():
        aliases.setdefault(target, []).append(obs)
    plain, with_aliases = dl.idx, StateCountryIndex.build(dl.states, aliases)

    all_rows, conf = dl.run()
    changed, recovered = [], collections.Counter()
    for r in conf:
        before = plain.repair(r["state"], r["observed_name"], r["cs"])
        after = with_aliases.repair(r["state"], r["observed_name"], r["cs"])
        key = (r["observed_name"] or "", " | ".join(dl.cid2name[c] for c in r["cs"]))
        if before[0] != "drop":
            if after != before:
                changed.append((r["site_id"], before, after))
            continue
        if key in PROPOSALS:
            assert after == ("repoint", PROPOSALS[key][0]), (key, after)
            recovered[key] += 1
        else:
            assert after == before, (key, after)
    assert changed == [], changed[:5]
    # the same kept / repointed outcome for every non-conflicted candidate too
    for r in all_rows:
        cs = list(dict.fromkeys(r["countries"]))
        if not plain.conflicts(r["state"], cs):
            assert with_aliases.repair(r["state"], r["observed_name"], cs) == ("keep", r["state"])

    # projection: the two new rows (fork branch add-niamey-ekaterinburg) plus
    # every proposal; only the new-row and proposed groups may change
    from minmodkg.models.kgrel.entities.state_or_province import StateOrProvince

    cname = {v: k for k, v in dl.cid2name.items()}
    new_states = dl.states + [
        StateOrProvince(id="Q7085", name="Niamey", country=cname["Niger"], state_code="8"),
        StateOrProvince(id="Q7086", name="Ekaterinburg", country=cname["Russia"], state_code=None),
    ]
    projected = StateCountryIndex.build(new_states, aliases)
    projection = collections.Counter()
    for r in conf:
        before = plain.repair(r["state"], r["observed_name"], r["cs"])
        after = projected.repair(r["state"], r["observed_name"], r["cs"])
        key = (r["observed_name"] or "", " | ".join(dl.cid2name[c] for c in r["cs"]))
        if key in NEW_ROWS:
            assert before[0] == "drop" and after == ("repoint", NEW_ROWS[key]), (key, after)
            projection["new_rows"] += 1
        elif key in PROPOSALS:
            assert after == ("repoint", PROPOSALS[key][0]), (key, after)
            projection["aliases"] += 1
        else:
            assert after == before, (key, before, after)
            projection["drop" if after[0] == "drop" else "unchanged_" + after[0]] += 1

    # the two data tests of ta2-minmod-kg
    real = {(s.country, fold_name(s.name)) for s in dl.states}
    clashes = [(sid, a) for sid, names in aliases.items() for a in names
               if (dl.by_id[sid].country, fold_name(a)) in real]
    dead = [(sid, a) for sid, names in aliases.items() for a in names
            if with_aliases.resolve(a, [dl.by_id[sid].country]) != sid]
    assert clashes == [] and dead == [], (clashes, dead)

    # coordinates: verdicts from p2c_coordinates.py, when it has been run
    coord = {}
    if (OUT / "coordinates.csv").exists():
        for c in csv.DictReader(open(OUT / "coordinates.csv", newline="", encoding="utf-8")):
            coord[(c["observed_name"], c["recorded_country"])] = c
        named = set(PROPOSALS) | set(REJECTED_ON_COORDINATES)
        assert set(coord) == named, sorted(set(coord) ^ named)
        for key, c in coord.items():
            assert (c["verdict"] == "stands") == (key in PROPOSALS), (key, c["verdict"])

    out_rows = []
    for key in sorted(todo, key=lambda k: (-records[k], k)):
        obs, country = key
        if key in PROPOSALS:
            target, reason, _ = PROPOSALS[key]
            out_rows.append([obs, country, records[key], target, dl.by_id[target].name, reason])
        else:
            out_rows.append([obs, country, records[key], "", "", "no suggestion"])
    with open(OUT / "alias_candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["observed_name", "recorded_country", "records", "proposed_minmod_id",
                    "proposed_name", "reason"])
        w.writerows(out_rows)

    with open(OUT / "alias_candidates_notes.md", "w", encoding="utf-8") as f:
        f.write("# Alias candidates: notes\n\n"
                "Generated by `investigation/p2c_alias_candidates.py` next to "
                "`alias_candidates.csv`. *Coordinates* is agree / informative points from "
                "`coordinates.csv`: a record agrees if its own point lies inside the row's "
                "Natural Earth polygon or within 50 km of it; points in another country "
                "or on a round placeholder do not count.\n\n"
                "## Proposed\n\n| observed name | country | records | proposed | reason | coordinates | note |\n"
                "|---|---|--:|---|---|--:|---|\n")
        for row in out_rows:
            key = (row[0], row[1])
            if key in PROPOSALS:
                f.write(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} {row[4]} | {row[5]} | "
                        f"{coords_cell(coord.get(key))} | {PROPOSALS[key][2]} |\n")
        f.write("\n## No suggestion: the name fits a row, the records do not\n\n"
                "| observed name | country | records | the name means | coordinates | evidence |\n"
                "|---|---|--:|---|--:|---|\n")
        for row in out_rows:
            key = (row[0], row[1])
            if key in REJECTED_ON_COORDINATES:
                t, reason, note = REJECTED_ON_COORDINATES[key]
                f.write(f"| {row[0]} | {row[1]} | {row[2]} | {t} {dl.by_id[t].name} ({reason}) | "
                        f"{coords_cell(coord.get(key))} | {note} |\n")
        f.write("\n## No suggestion: no row is the same place\n\n| observed name | country | records | why |\n|---|---|--:|---|\n")
        for row in out_rows:
            key = (row[0], row[1])
            if key in NO_SUGGESTION:
                f.write(f"| {row[0]} | {row[1]} | {row[2]} | {NO_SUGGESTION[key]} |\n")

    summary = {
        "drop_groups": len(keys),
        "drop_records": sum(records.values()),
        "blocked": {"groups": len(BLOCKED), "records": sum(records[k] for k in BLOCKED)},
        "new_rows": {"groups": len(NEW_ROWS), "records": sum(records[k] for k in NEW_ROWS)},
        "alias_pass": {"groups": len(todo), "records": sum(records[k] for k in todo)},
        "proposed": {"groups": len(PROPOSALS), "records": sum(records[k] for k in PROPOSALS),
                     "distinct_target_rows": len({t for t, _, _ in PROPOSALS.values()}),
                     "by_reason": dict(collections.Counter(r for _, r, _ in PROPOSALS.values()))},
        "no_suggestion": {"groups": len(NO_SUGGESTION) + len(REJECTED_ON_COORDINATES),
                          "records": sum(records[k] for k in list(NO_SUGGESTION) + list(REJECTED_ON_COORDINATES)),
                          "of_which_rejected_on_coordinates": {
                              "groups": len(REJECTED_ON_COORDINATES),
                              "records": sum(records[k] for k in REJECTED_ON_COORDINATES)}},
        "checks": {
            "candidates_recovered_if_all_approved": sum(recovered.values()),
            "candidates_changed_that_resolved_before": len(changed),
            "alias_equals_real_name": len(clashes),
            "alias_not_resolving_to_its_row": len(dead),
            "coordinates_checked": bool(coord),
        },
        "projection_with_new_rows_and_every_proposal": {
            "conflicted_candidates": len(conf),
            "repointed_without_change": projection["unchanged_repoint"],
            "recovered_by_new_rows": projection["new_rows"],
            "recovered_by_aliases": projection["aliases"],
            "still_dropped": projection["drop"],
            "still_dropped_blocked": sum(records[k] for k in BLOCKED),
            "still_dropped_no_suggestion": projection["drop"] - sum(records[k] for k in BLOCKED),
        },
    }
    json.dump(summary, open(OUT / "alias_candidates.json", "w"), indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
