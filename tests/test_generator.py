"""Tests for the seeded v1 generator: structure, measured properties, determinism."""

from collections import Counter, defaultdict

import pytest

from happy_toad.data.checks import check_input_set
from happy_toad.data.config import GeneratorConfig
from happy_toad.data.generator import make_v1, market_counts

CFG = GeneratorConfig()
SEEDS = [1, 2, 3, 42]


@pytest.fixture(scope="module", params=SEEDS)
def v1(request):
    return make_v1(seed=request.param, cfg=CFG)


def spend_by_type(data) -> dict[str, float]:
    spend: dict[str, float] = defaultdict(float)
    for c in data.candidates:
        spend[c.type] += c.cost
    return spend


def sectors_per_candidate(data) -> Counter:
    return Counter(o.candidate_id for o in data.offloads)


def candidates_per_sector(data) -> Counter:
    return Counter(o.sector_id for o in data.offloads)


def test_sizes_and_derived_candidate_count(v1) -> None:
    assert len(v1.sectors) == 60
    assert len(v1.must_fund) == 5
    assert 30 <= len(v1.candidates) <= 50
    assert set(sectors_per_candidate(v1)) == {c.id for c in v1.candidates}


def test_passes_load_checks(v1) -> None:
    check_input_set(v1, CFG.base_year)


def test_trigger_years_and_shortfalls(v1) -> None:
    assert all(2026 <= s.trigger_year <= 2035 for s in v1.sectors)
    assert all(10 <= s.shortfall <= 100 for s in v1.sectors)
    years = [s.trigger_year for s in v1.sectors]
    assert sum(y <= 2030 for y in years) > len(years) / 2


def test_market_counts_follow_need_rates(v1) -> None:
    assert market_counts(CFG) == [8, 13, 17, 22]
    counts = Counter(s.market for s in v1.sectors)
    assert [counts[m] for m in CFG.markets] == [8, 13, 17, 22]


def test_spend_shares_by_type_are_85_10_5(v1) -> None:
    spend = spend_by_type(v1)
    total = sum(spend.values())
    shares = [spend[t] / total for t in CFG.types]
    assert shares == pytest.approx([0.85, 0.10, 0.05], abs=0.04)


def test_cost_ratios_between_types(v1) -> None:
    by_type = defaultdict(list)
    for c in v1.candidates:
        by_type[c.type].append(c.cost)
    mean = {t: sum(v) / len(v) for t, v in by_type.items()}
    assert mean["type_b"] / mean["type_a"] == pytest.approx(0.33, rel=0.2)
    assert mean["type_c"] / mean["type_a"] == pytest.approx(0.10, rel=0.2)


def test_reach_by_type(v1) -> None:
    reach = sectors_per_candidate(v1)
    for c in v1.candidates:
        low, high = (2, 4) if c.type == "type_a" else (1, 1)
        assert low <= reach[c.id] <= high


def test_one_fifth_of_sectors_have_several_candidates(v1) -> None:
    per_sector = candidates_per_sector(v1)
    assert set(per_sector) == {s.id for s in v1.sectors}
    multi = sum(n >= 2 for n in per_sector.values())
    assert multi / len(v1.sectors) == pytest.approx(0.20, abs=0.02)


def test_total_supply_is_one_to_one_point_three_times_need(v1) -> None:
    supply = sum(o.amount for o in v1.offloads)
    need = sum(s.shortfall for s in v1.sectors)
    assert 1.0 <= supply / need <= 1.3


def test_offload_share_of_sector_shortfall(v1) -> None:
    shortfall = {s.id: s.shortfall for s in v1.sectors}
    lo, hi = CFG.offload_share_range
    for o in v1.offloads:
        share = o.amount / shortfall[o.sector_id]
        assert lo - 0.01 <= share <= hi + 0.01  # tolerance for 2-decimal rounding


def test_must_fund_total_is_about_10_percent_of_candidate_cost(v1) -> None:
    candidate_total = sum(c.cost for c in v1.candidates)
    assert sum(m.cost for m in v1.must_fund) == pytest.approx(0.1 * candidate_total, rel=0.01)


def test_same_seed_gives_same_data_and_other_seed_differs() -> None:
    assert make_v1(1, CFG) == make_v1(1, CFG)
    assert make_v1(1, CFG).content_hash != make_v1(2, CFG).content_hash
