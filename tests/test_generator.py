"""Tests for the seeded v1 generator."""

from collections import Counter

import pytest

from happy_toad.data.checks import check_input_set
from happy_toad.data.config import GeneratorConfig
from happy_toad.data.generator import make_v1

CFG = GeneratorConfig()


@pytest.fixture(scope="module")
def v1():
    return make_v1(seed=1, cfg=CFG)


def test_sizes(v1) -> None:
    assert len(v1.sectors) == 60
    assert len(v1.candidates) == 120
    assert len(v1.must_fund) == 5


def test_passes_load_checks(v1) -> None:
    check_input_set(v1, CFG.base_year)


def test_ranges(v1) -> None:
    assert all(2026 <= s.trigger_year <= 2035 for s in v1.sectors)
    assert all(10 <= s.shortfall <= 100 for s in v1.sectors)
    assert len({s.market for s in v1.sectors}) <= 4
    assert len({c.type for c in v1.candidates}) <= 3


def test_triggers_skew_near(v1) -> None:
    years = [s.trigger_year for s in v1.sectors]
    assert sum(y <= 2030 for y in years) > len(years) / 2


def test_each_candidate_relieves_one_to_four_sectors(v1) -> None:
    rows = Counter(o.candidate_id for o in v1.offloads)
    assert set(rows) == {c.id for c in v1.candidates}
    assert all(1 <= n <= 4 for n in rows.values())


def test_offload_is_20_to_80_percent_of_sector_shortfall(v1) -> None:
    shortfall = {s.id: s.shortfall for s in v1.sectors}
    for o in v1.offloads:
        share = o.amount / shortfall[o.sector_id]
        assert 0.19 <= share <= 0.81  # tolerance for 2-decimal rounding


def test_some_sectors_are_under_served(v1) -> None:
    supply = Counter()
    for o in v1.offloads:
        supply[o.sector_id] += o.amount
    under = [s for s in v1.sectors if supply[s.id] < s.shortfall]
    assert len(under) >= round(CFG.under_served_share * 60)


def test_cost_tracks_candidate_total_offload(v1) -> None:
    total = Counter()
    for o in v1.offloads:
        total[o.candidate_id] += o.amount
    for c in v1.candidates:
        assert 0.69 <= c.cost / total[c.id] <= 1.31


def test_must_fund_total_is_about_10_percent_of_candidate_cost(v1) -> None:
    candidate_total = sum(c.cost for c in v1.candidates)
    assert sum(m.cost for m in v1.must_fund) == pytest.approx(0.1 * candidate_total, rel=0.01)


def test_same_seed_gives_same_data_and_other_seed_differs() -> None:
    assert make_v1(1, CFG) == make_v1(1, CFG)
    assert make_v1(1, CFG).content_hash != make_v1(2, CFG).content_hash
