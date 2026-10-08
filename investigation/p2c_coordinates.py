"""Problem 2, alias pass: do the records' own coordinates agree with the alias?

An alias is right as vocabulary if the name means the state. It is right for
the records it repairs only if they lie there. For every group with a
name-based target (proposed, or rejected here), this checks each record's
WGS84 point against Natural Earth's admin-1 polygon of that state.

  agrees         inside the polygon, or within 50 km of it (generalised
                 boundaries, coordinates rounded at source)
  uninformative  in another country, or a round placeholder (both coordinates
                 on a whole or half degree)
  disagrees      anything else

A target stands if at least half of the informative points agree, or none are
informative.

Natural Earth admin-1, 10m, v5.1 (nvkelso/natural-earth-vector @ ca96624):

    git clone --depth 1 --filter=blob:none --sparse \
      https://github.com/nvkelso/natural-earth-vector ne
    git -C ne sparse-checkout set --no-cone \
      /geojson/ne_10m_admin_1_states_provinces.geojson

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python investigation/p2c_coordinates.py ne/geojson/ne_10m_admin_1_states_provinces.geojson

Writes reports/p2c/coordinates.csv.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

NE_FILE = Path(sys.argv[1])
sys.argv = sys.argv[:1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2c_alias_candidates as ac  # noqa: E402

from shapely.geometry import Point, shape  # noqa: E402
from shapely.ops import nearest_points  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

dl = ac.dl
TOLERANCE_KM = 50

# Natural Earth (admin, name) of each target; name None = the whole admin.
NE = {
    "Q3657": ("India", "Odisha"), "Q3383": ("Germany", "Niedersachsen"),
    "Q4059": ("Laos", "Attapu"), "Q5463": ("Russia", "Buryat"),
    "Q5071": ("Panama", "Kuna Yala"), "Q3971": ("Kazakhstan", "Aqtöbe"),
    "Q3424": ("Greece", "Stereá Elláda"), "Q2215": ("Austria", "Kärnten"),
    "Q7072": ("Zambia", "North-Western"), "Q2218": ("Austria", "Steiermark"),
    "Q3211": ("Finland", "Lapland"), "Q4389": ("Malaysia", "Pulau Pinang"),
    "Q4615": ("Mongolia", "Hentiy"), "Q2906": ("Cyprus", "Nicosia"),
    "Q5467": ("Russia", "Karelia"), "Q5030": ("Pakistan", "K.P."),
    "Q5485": ("Russia", "Tuva"), "Q3122": ("Egypt", "Al Bahr al Ahmar"),
    "Q6324": ("Tunisia", "Le Kef"), "Q4855": ("Nicaragua", "Atlántico Norte"),
    "Q4912": ("North Korea", "Hamgyŏng-namdo"), "Q2757": ("Hong Kong S.A.R.", None),
    "Q5425": ("Russia", "Irkutsk"), "Q2019": ("Afghanistan", "Kunduz"),
    "Q2905": ("Cyprus", "Limassol"), "Q2216": ("Austria", "Niederösterreich"),
    "Q2220": ("Austria", "Oberösterreich"), "Q5022": ("Oman", "Dhofar"),
    "Q3961": ("Jordan", "Balqa"), "Q3103": ("Egypt", "Al Buhayrah"),
    "Q6012": ("Sudan", "Blue Nile"), "Q5496": ("Russia", "Chita"),
    "Q4052": ("Kyrgyzstan", "Chuy"), "Q5910": ("South Korea", "South Chungcheong"),
    "Q4536": ("Mexico", "Distrito Federal"), "Q5082": ("Papua New Guinea", "Eastern Highlands"),
    "Q2010": ("Afghanistan", "Ghor"), "Q3920": ("Japan", "Gunma"),
    "Q4617": ("Mongolia", "Hövsgöl"), "Q4907": ("North Korea", "Hwanghae-bukto"),
    "Q4913": ("North Korea", "Hwanghae-namdo"), "Q5431": ("Russia", "Kamchatka"),
    "Q5900": ("South Korea", "Gangwon"), "Q5468": ("Russia", "Khakass"),
    "Q3979": ("Kazakhstan", "Qostanay"), "Q4545": ("Mexico", "Michoacán"),
    "Q5448": ("Russia", "Moskovskaya"), "Q2760": ("China", "Inner Mongol"),
    "Q4773": ("Namibia", "Otjozondjupa"), "Q5476": ("Russia", "Sakhalin"),
    "Q2769": ("China", "Shandong"), "Q4622": ("Mongolia", "Sühbaatar"),
    "Q3790": ("Italy", "Aoste"), "Q5475": ("Russia", "Sakha (Yakutia)"),
    "Q6049": ("Sweden", "Östergötland"),
}


def km(p: Point, g) -> float:
    a, b = nearest_points(g, p)
    return ac.haversine(a.y, a.x, b.y, b.x)


def main() -> None:
    gj = json.load(open(NE_FILE, encoding="utf-8"))
    feats = [(shape(f["geometry"]), f["properties"]) for f in gj["features"] if f["geometry"]]
    tree = STRtree([g for g, _ in feats])

    def containing(p):
        for i in tree.query(p):
            if feats[i][0].contains(p):
                return feats[i][1]
        return None

    named = {**ac.PROPOSALS, **ac.REJECTED_ON_COORDINATES}
    _, conf = dl.run()
    points = ac.record_points(conf, set(named))
    rows = []
    for key, (target, _, _) in sorted(named.items(), key=lambda kv: kv[0]):
        admin, name = NE[target]
        polys = [g for g, pr in feats if pr["admin"] == admin and (name is None or pr["name"] == name)]
        assert polys, (target, admin, name)
        country_admins = {admin, "Hong Kong S.A.R."} if admin in ("China", "Hong Kong S.A.R.") else {admin}
        agree = disagree = uninformative = 0
        far = []
        for lat, lon in points.get(key, []):
            p = Point(lon, lat)
            pr = containing(p)
            if (lat * 2).is_integer() and (lon * 2).is_integer():
                uninformative += 1
                continue
            if pr is not None and pr["admin"] not in country_admins:
                uninformative += 1
                continue
            d = min(km(p, g) for g in polys)
            if d <= TOLERANCE_KM:
                agree += 1
            else:
                disagree += 1
                far.append(f"{pr['name'] if pr else 'no polygon'} {round(d)} km")
        informative = agree + disagree
        stands = informative == 0 or agree * 2 >= informative
        rows.append([key[0], key[1], target, dl.by_id[target].name, agree + disagree + uninformative,
                     agree, disagree, uninformative, "; ".join(sorted(set(far))),
                     "stands" if stands else "rejected"])
        expected = "stands" if key in ac.PROPOSALS else "rejected"
        assert rows[-1][-1] == expected, (key, rows[-1])

    out = ac.OUT / "coordinates.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["observed_name", "recorded_country", "target_minmod_id", "target_name", "points",
                    "agree", "disagree", "uninformative", "disagreeing_points", "verdict"])
        w.writerows(rows)
    print(f"{len(rows)} groups; " + ", ".join(
        f"{v}: {sum(r[-1] == v for r in rows)}" for v in ("stands", "rejected")))
    for r in rows:
        if r[6]:
            print(r)


if __name__ == "__main__":
    main()
