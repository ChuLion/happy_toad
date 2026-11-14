"""Known-answer tests 8-11 and unit tests for market floors and caps (SPEC, market floors).

Toy world: budget 12, no must-fund. Market X: sectors sX1, sX2 (weight 1 each) and candidates
X1 (cost 6), X2 (cost 5). Market Y: sector sY1 (weight 1/5) and candidate Y1 (cost 6).
"""

import pulp
import pytest
from helpers import make_set

from happy_toad.constants import BASE_YEAR
from happy_toad.data.generator import make_v1
from happy_toad.engine.markets import (
    MarketLimits,
    candidate_markets,
    fair_share_limits,
    fair_shares,
)
from happy_toad.engine.model import solve

MARKET_OF = {"X1": "X", "X2": "X", "Y1": "Y"}


@pytest.fixture
def toy():
    return make_set(
        [("sX1", 10, BASE_YEAR, "X"), ("sX2", 10, BASE_YEAR, "X"), ("sY1", 10, BASE_YEAR + 4, "Y")],
        [("X1", 6), ("X2", 5), ("Y1", 6)],
        [("X1", "sX1", 10), ("X2", "sX2", 10), ("Y1", "sY1", 10)],
    )


def market_spend(data, result, market) -> float:
    cost = {c.id: c.cost for c in data.candidates}
    return sum(cost[c] for c in result.selected if MARKET_OF[c] == market)


def test_8_baseline_without_limits(toy) -> None:
    result = solve(toy, budget=12)
    assert result.status == "Optimal"
    assert sorted(result.selected) == ["X1", "X2"]
    assert result.spend == pytest.approx(11)
    assert result.objective == pytest.approx(20)


def test_9_cap_on_x_binds(toy) -> None:
    result = solve(toy, budget=12, limits=MarketLimits(caps={"X": 8}))
    assert result.status == "Optimal"
    assert sorted(result.selected) == ["X2", "Y1"]
    assert market_spend(toy, result, "X") == pytest.approx(5)
    assert result.spend == pytest.approx(11)
    assert result.objective == pytest.approx(12)
    assert result.objective < 20  # the cap really bound


def test_10_floor_on_y_forces_y1(toy) -> None:
    result = solve(toy, budget=12, limits=MarketLimits(floors={"Y": 6}))
    assert result.status == "Optimal"
    assert "Y1" in result.selected
    assert market_spend(toy, result, "Y") == pytest.approx(6)
    assert result.spend == pytest.approx(11)
    assert result.objective == pytest.approx(12)


@pytest.fixture
def no_solver(monkeypatch):
    """Fail the test if the solver is called."""

    def boom(*args, **kwargs):
        raise AssertionError("the pre-solve check must not call the solver")

    monkeypatch.setattr(pulp.LpProblem, "solve", boom)


def test_11a_floors_above_budget_are_infeasible_without_solving(toy, no_solver) -> None:
    result = solve(toy, budget=12, limits=MarketLimits(floors={"X": 8, "Y": 6}))
    assert result.status == "Infeasible"
    assert result.selected is None
    assert result.stage_times == {}


def test_11b_cap_below_floor_is_infeasible_without_solving(toy, no_solver) -> None:
    result = solve(toy, budget=12, limits=MarketLimits(floors={"X": 6}, caps={"X": 4}))
    assert result.status == "Infeasible"
    assert result.selected is None


def test_11c_floor_is_clamped_to_the_markets_total_candidate_cost(toy) -> None:
    result = solve(toy, budget=12, limits=MarketLimits(floors={"Y": 10}))
    assert result.status == "Optimal"
    assert "Y1" in result.selected
    assert result.solver_settings["market_floors"] == {"Y": 6}


def test_limits_off_by_default_and_recorded_as_none(toy) -> None:
    settings = solve(toy, budget=12).solver_settings
    assert settings["market_floor_mult"] is None
    assert settings["market_cap_mult"] is None
    assert settings["fair_share_blend"] == 0.5
    assert settings["market_floors"] is None and settings["market_caps"] is None


def test_fair_share_is_a_blend_of_shortfall_share_and_equal_share(toy) -> None:
    assert fair_shares(toy, blend=0.5) == pytest.approx({"X": 7 / 12, "Y": 5 / 12})
    assert fair_shares(toy, blend=0.0) == pytest.approx({"X": 0.5, "Y": 0.5})
    assert fair_shares(toy, blend=1.0) == pytest.approx({"X": 2 / 3, "Y": 1 / 3})


def test_limits_are_multiples_of_fair_share_times_avail_and_scale_with_it(toy) -> None:
    small = fair_share_limits(toy, 12, floor_mult=0.5, cap_mult=1.5, blend=0.5)
    large = fair_share_limits(toy, 24, floor_mult=0.5, cap_mult=1.5, blend=0.5)
    assert small.floors["X"] == pytest.approx(0.5 * 7 / 12 * 12)
    assert small.caps["Y"] == pytest.approx(1.5 * 5 / 12 * 12)
    assert large.floors["X"] == pytest.approx(2 * small.floors["X"])
    only_cap = fair_share_limits(toy, 12, floor_mult=None, cap_mult=1.5, blend=0.5)
    assert only_cap.floors == {} and only_cap.caps == small.caps


def test_multipliers_in_solve_cap_every_market(toy) -> None:
    """cap_mult 8/7 gives X a cap of 8 and Y a cap of 40/7 = 5.71, below Y1's cost of 6."""
    result = solve(toy, budget=12, market_cap_mult=8 / 7, fair_share_blend=0.5)
    caps = result.solver_settings["market_caps"]
    assert caps["X"] == pytest.approx(8) and caps["Y"] == pytest.approx(40 / 7)
    assert result.solver_settings["market_cap_mult"] == pytest.approx(8 / 7)
    assert result.selected == ["X2"]  # Y1 cannot be funded under Y's cap
    assert result.objective == pytest.approx(10)


def test_candidate_market_is_that_of_its_largest_row_ties_by_lowest_sector_id() -> None:
    data = make_set(
        [("s1", 10, BASE_YEAR, "A"), ("s2", 10, BASE_YEAR, "B"), ("s3", 10, BASE_YEAR, "C")],
        [("big", 1), ("tie", 1)],
        [("big", "s1", 2), ("big", "s2", 7), ("tie", "s3", 4), ("tie", "s2", 4)],
    )
    assert candidate_markets(data) == {"big": "B", "tie": "B"}  # tie: s2 < s3


def test_generated_data_respects_floors_and_caps_at_the_30_percent_budget() -> None:
    data = make_v1(42)
    total = sum(c.cost for c in data.candidates)
    must_fund = sum(m.cost for m in data.must_fund)
    result = solve(data, 0.30 * total + must_fund, market_floor_mult=0.5, market_cap_mult=1.5)
    assert result.status == "Optimal"
    market = candidate_markets(data)
    cost = {c.id: c.cost for c in data.candidates}
    spend = dict.fromkeys(set(market.values()), 0.0)
    for c in result.selected:
        spend[market[c]] += cost[c]
    floors, caps = result.solver_settings["market_floors"], result.solver_settings["market_caps"]
    for m, amount in spend.items():
        assert floors[m] - 1e-6 <= amount <= caps[m] + 1e-6
    assert sum(floors.values()) == pytest.approx(0.5 * 0.30 * total, rel=0.02)  # clamping can lower
