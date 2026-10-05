"""Problem 2, B3: the merge must not pair one record's country with another's state.

    CFG_FILE=upstream-p2/tests/resources/config.yml \
      .venv-p2/bin/python -m pytest tests/test_p2_dedup_pairing.py -q
"""

from __future__ import annotations

import csv
from pathlib import Path

from minmodkg.models.kgrel.custom_types.ref_value import RefListID
from minmodkg.models.kgrel.custom_types.site_and_score import SiteScore
from minmodkg.models.kgrel.dedup_mineral_site import DedupMineralSite
from minmodkg.models.kgrel.mineral_site import MineralSiteAndInventory

ENT = Path(__file__).parent.parent / "data-p2/data/entities"
CID = {c["name"]: c["minmod_id"] for c in csv.DictReader(open(ENT / "country.csv", newline="", encoding="utf-8"))}
SID = {
    (r["name"], r["country_name"]): r["minmod_id"]
    for r in csv.DictReader(open(ENT / "state_or_province.csv", newline="", encoding="utf-8"))
}
US, MX = CID["United States"], CID["Mexico"]
SONORA, ARIZONA = SID[("Sonora", "Mexico")], SID[("Arizona", "United States")]
URI = "https://minmod.isi.edu/resource/"


def site(record_id: str, score: float, country: str | None, state: str | None) -> MineralSiteAndInventory:
    def cand(ent):
        return [{"source": "test", "confidence": 1.0, "observed_name": ent, "normalized_uri": URI + ent}] if ent else []

    source_id = f"https://example.org/{record_id}"
    raw = {
        "source_id": source_id,
        "record_id": record_id,
        "created_by": "https://minmod.isi.edu/users/s/test",
        "modified_at": "2024-01-01T00:00:00Z",
        "location_info": {"country": cand(country), "state_or_province": cand(state)},
    }
    msi = MineralSiteAndInventory.from_raw_site(raw, {}, {}, {source_id: score})
    msi.ms.dedup_site_id = "dedup_site__test"
    return msi


def independent_scans(sites):
    """The pre-B3 election, copied verbatim from dedup_mineral_site.py:263-278 @ 83f9b7b."""
    rank_sites = [s.ms for s in sorted(sites, key=lambda s: SiteScore.get_score(s.ms), reverse=True)]
    country = next(
        (
            RefListID(site.location_view.country, site.site_id)
            for site in rank_sites
            if len(site.location_view.country) > 0
        ),
        RefListID([], rank_sites[0].site_id),
    )
    state_or_province = next(
        (
            RefListID(site.location_view.state_or_province, site.site_id)
            for site in rank_sites
            if len(site.location_view.state_or_province) > 0
        ),
        RefListID([], rank_sites[0].site_id),
    )
    return country, state_or_province


def test_old_code_pairs_us_with_sonora_new_code_takes_both_from_b():
    a = site("a", 0.9, US, None)  # higher ranked: country, no state
    b = site("b", 0.5, MX, SONORA)  # carries both
    old_c, old_s = independent_scans([a, b])
    assert (old_c.value, old_s.value) == ([US], [SONORA])  # a pairing no record made
    assert (old_c.refid, old_s.refid) == (a.ms.site_id, b.ms.site_id)
    new = DedupMineralSite.from_sites([a, b]).dms
    assert (new.country.value, new.state_or_province.value) == ([MX], [SONORA])
    assert new.country.refid == new.state_or_province.refid == b.ms.site_id


def test_unchanged_when_the_top_site_carries_both():
    a = site("a", 0.9, US, ARIZONA)
    b = site("b", 0.5, MX, SONORA)
    old_c, old_s = independent_scans([a, b])
    new = DedupMineralSite.from_sites([a, b]).dms
    assert (new.country, new.state_or_province) == (old_c, old_s)
    assert (new.country.value, new.state_or_province.value) == ([US], [ARIZONA])


def test_fallback_when_no_site_carries_both():
    a = site("a", 0.9, US, None)
    b = site("b", 0.5, None, SONORA)
    old_c, old_s = independent_scans([a, b])
    new = DedupMineralSite.from_sites([a, b]).dms
    assert (new.country, new.state_or_province) == (old_c, old_s)


def test_merge_level_takes_both_from_one_record():
    """from_dedup_sites: partial merges from two buckets."""
    a = site("a", 0.9, US, None)
    b = site("b", 0.5, MX, SONORA)
    pa = DedupMineralSite.from_sites([a]).dms
    pb = DedupMineralSite.from_sites([b]).dms
    new = DedupMineralSite.from_dedup_sites([pa, pb], [a, b], is_site_ranked=True).dms
    assert (new.country.value, new.state_or_province.value) == ([MX], [SONORA])
    assert new.country.refid == new.state_or_province.refid == b.ms.site_id


def test_merge_level_needs_one_record_behind_both_values():
    """A partial whose country and state come from different records is not "a site
    carrying both": the lower-ranked partial whose pair comes from one record wins."""
    a1 = site("a1", 0.9, US, None)
    a2 = site("a2", 0.8, None, ARIZONA)
    b = site("b", 0.5, MX, SONORA)
    p1 = DedupMineralSite.from_sites([a1, a2]).dms
    assert p1.country.refid != p1.state_or_province.refid
    pb = DedupMineralSite.from_sites([b]).dms
    new = DedupMineralSite.from_dedup_sites([p1, pb], [a1, a2, b], is_site_ranked=True).dms
    assert (new.country.value, new.state_or_province.value) == ([MX], [SONORA])
