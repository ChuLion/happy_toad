"""Tests for the seeded v1 generator: structure, measured properties, determinism."""

from collections import Counter, defaultdict

import pytest

from happy_toad.constants import BASE_YEAR
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
    assert len(v1.sectors) == 80
    assert len(v1.must_fund) == 5
    assert 35 <= len(v1.candidates) <= 55
    assert set(sectors_per_candidate(v1)) == {c.id for c in v1.candidates}


def test_passes_load_checks(v1) -> None:
    check_input_set(v1, BASE_YEAR)


def test_trigger_years_and_shortfalls(v1) -> None:
    assert all(BASE_YEAR <= s.trigger_year <= BASE_YEAR + 4 for s in v1.sectors)
    assert all(10 <= s.shortfall <= 100 for s in v1.sectors)


def mean_year(data, markets) -> float:
    years = [s.trigger_year for s in data.sectors if s.market in markets]
    return sum(years) / len(years)


def test_mean_trigger_year_urgent_before_mixed_before_relaxed(v1) -> None:
    urgent = mean_year(v1, {"market_g", "market_h"})
    mixed = mean_year(v1, {"market_b", "market_c", "market_d", "market_e", "market_f"})
    relaxed = mean_year(v1, {"market_a"})
    assert urgent < mixed < relaxed


def test_market_counts_follow_need_rates(v1) -> None:
    expected = [6, 7, 8, 9, 11, 11, 13, 15]
    assert market_counts(CFG) == expected
    counts = Counter(s.market for s in v1.sectors)
    assert [counts[m] for m in CFG.markets] == expected
    assert len(CFG.markets) == 8 and sum(expected) == 80


def test_multi_sector_candidates_draw_85_percent_from_their_own_market(v1) -> None:
    market = {s.id: s.market for s in v1.sectors}
    rows = defaultdict(list)
    for o in v1.offloads:
        rows[o.candidate_id].append(market[o.sector_id])
    multi = [m for m in rows.values() if len(m) > 1]
    same = sum(Counter(m).most_common(1)[0][1] for m in multi)
    assert same / sum(len(m) for m in multi) == pytest.approx(0.85, abs=0.10)


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


def supply_by_sector(data) -> dict[str, float]:
    supply = {s.id: 0.0 for s in data.sectors}
    for o in data.offloads:
        supply[o.sector_id] += o.amount
    return supply


def test_95_percent_of_sectors_are_resolvable_with_every_candidate_funded(v1) -> None:
    supply = supply_by_sector(v1)
    resolvable = [s for s in v1.sectors if supply[s.id] >= s.shortfall - 1e-6]
    assert len(resolvable) / len(v1.sectors) == pytest.approx(0.95, abs=0.04)


def test_unresolvable_sectors_never_reach_their_shortfall_and_none_is_marginal(v1) -> None:
    supply = supply_by_sector(v1)
    short = [s for s in v1.sectors if supply[s.id] < s.shortfall - 1e-6]
    assert len(short) == round(CFG.unresolvable_share * len(v1.sectors))
    assert all(supply[s.id] <= 0.95 * s.shortfall + 0.01 for s in short)


def test_every_resolvable_sector_has_a_row_with_offload_share_between_1_and_1_3(v1) -> None:
    supply = supply_by_sector(v1)
    best = defaultdict(float)
    shortfall = {s.id: s.shortfall for s in v1.sectors}
    for o in v1.offloads:
        best[o.sector_id] = max(best[o.sector_id], o.amount / shortfall[o.sector_id])
    for s in v1.sectors:
        if supply[s.id] >= s.shortfall - 1e-6:
            assert 1.0 - 1e-9 <= best[s.id] <= 1.3 + 0.005


def test_supply_ratio_is_logged_not_gated(v1, record_property) -> None:
    ratio = sum(o.amount for o in v1.offloads) / sum(s.shortfall for s in v1.sectors)
    record_property("supply_ratio", round(ratio, 3))
    assert ratio > 0


def test_offload_shares_stay_within_the_configured_ranges(v1) -> None:
    shortfall = {s.id: s.shortfall for s in v1.sectors}
    supply = supply_by_sector(v1)
    low = CFG.offload_share_range[0]
    for o in v1.offloads:
        share = o.amount / shortfall[o.sector_id]
        assert share <= CFG.resolving_share_range[1] + 0.005  # 2-decimal rounding
        if supply[o.sector_id] >= shortfall[o.sector_id] - 1e-6:
            assert share >= low - 0.005


def test_must_fund_total_is_about_10_percent_of_candidate_cost(v1) -> None:
    candidate_total = sum(c.cost for c in v1.candidates)
    assert sum(m.cost for m in v1.must_fund) == pytest.approx(0.1 * candidate_total, rel=0.01)


def test_same_seed_gives_same_data_and_other_seed_differs() -> None:
    assert make_v1(1, CFG) == make_v1(1, CFG)
    assert make_v1(1, CFG).content_hash != make_v1(2, CFG).content_hash
