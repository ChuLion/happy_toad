"""Force-in/out in both stages, and the infeasibility causes (SPEC, M2A).

Toy world of known-answer tests 8-11: budget 12, no must-fund. Market X: sectors sX1, sX2 (weight
1 each), candidates X1 (cost 6), X2 (cost 5). Market Y: sector sY1 (weight 1/5), candidate Y1
(cost 6). Without limits the best plan is X1 + X2 (spend 11, relief 20).
"""

import pytest
from helpers import make_set

from happy_toad.constants import BASE_YEAR
from happy_toad.engine.markets import MarketLimits
from happy_toad.engine.model import solve
from happy_toad.reasons import ReasonCode


@pytest.fixture
def toy():
    return make_set(
        [("sX1", 10, BASE_YEAR, "X"), ("sX2", 10, BASE_YEAR, "X"), ("sY1", 10, BASE_YEAR + 4, "Y")],
        [("X1", 6), ("X2", 5), ("Y1", 6)],
        [("X1", "sX1", 10), ("X2", "sX2", 10), ("Y1", "sY1", 10)],
    )


def test_force_out_removes_a_candidate_and_lowers_relief(toy) -> None:
    result = solve(toy, budget=12, force_out=["X1"])
    assert sorted(result.selected) == ["X2", "Y1"]
    assert result.objective == pytest.approx(12)


def test_force_in_funds_a_candidate_the_optimum_would_skip(toy) -> None:
    result = solve(toy, budget=12, force_in=["Y1"])
    assert "Y1" in result.selected
    assert result.objective == pytest.approx(12) and result.spend == pytest.approx(11)


def test_force_in_holds_in_stage_2_even_when_the_candidate_adds_nothing() -> None:
    """Z adds nothing once X1 is funded; stage 2 would drop it if it were not forced."""
    data = make_set(
        [("sX1", 10), ("sX2", 10)],
        [("X1", 6), ("X2", 5), ("Z", 1)],
        [("X1", "sX1", 10), ("X2", "sX2", 10), ("Z", "sX1", 5)],
    )
    assert sorted(solve(data, budget=12).selected) == ["X1", "X2"]
    forced = solve(data, budget=12, force_in=["Z"])
    assert sorted(forced.selected) == ["X1", "X2", "Z"]
    assert forced.spend == pytest.approx(12) and forced.objective == pytest.approx(20)


def test_force_in_and_out_combine_with_market_limits(toy) -> None:
    result = solve(toy, budget=12, force_in=["X2"], limits=MarketLimits(caps={"X": 5}))
    assert sorted(result.selected) == ["X2", "Y1"]


def cause(toy, budget=12, **kwargs):
    result = solve(toy, budget, **kwargs)
    assert result.status == "Infeasible" and result.selected is None
    return result.cause.code


@pytest.fixture
def no_solver(monkeypatch):
    import pulp

    def boom(*args, **kwargs):
        raise AssertionError("pre-solve causes must not call the solver")

    monkeypatch.setattr(pulp.LpProblem, "solve", boom)


def test_cause_forced_cost_exceeds_budget(toy, no_solver) -> None:
    assert cause(toy, force_in=["X1", "X2", "Y1"]) == ReasonCode.FORCED_COST_EXCEEDS_BUDGET


def test_cause_must_fund_above_budget(no_solver) -> None:
    data = make_set([("S1", 10)], [("C1", 5)], [("C1", "S1", 5)], must_fund=[20])
    assert cause(data, budget=12) == ReasonCode.FORCED_COST_EXCEEDS_BUDGET


def test_cause_floors_exceed_budget(toy, no_solver) -> None:
    limits = MarketLimits(floors={"X": 8, "Y": 6})
    assert cause(toy, limits=limits) == ReasonCode.FLOORS_EXCEED_BUDGET


def test_cause_cap_below_floor(toy, no_solver) -> None:
    limits = MarketLimits(floors={"X": 6}, caps={"X": 4})
    assert cause(toy, limits=limits) == ReasonCode.CAP_BELOW_FLOOR


def test_cause_forced_in_exceeds_cap(toy, no_solver) -> None:
    limits = MarketLimits(caps={"X": 8})
    assert cause(toy, force_in=["X1", "X2"], limits=limits) == ReasonCode.FORCED_IN_EXCEEDS_CAP


def test_cause_floor_unreachable_after_force_out(toy, no_solver) -> None:
    limits = MarketLimits(floors={"Y": 6})
    assert cause(toy, force_out=["Y1"], limits=limits) == ReasonCode.FLOOR_UNREACHABLE


def test_unknown_cause_when_only_the_solver_finds_it_infeasible(toy) -> None:
    """Spend in X can only be 0, 5, 6 or 11, so [8, 10] is empty; no pre-solve check sees that."""
    limits = MarketLimits(floors={"X": 8}, caps={"X": 10})
    result = solve(toy, budget=12, limits=limits)
    assert result.status == "Infeasible" and result.selected is None
    assert result.cause.code == ReasonCode.CAUSE_UNKNOWN
    assert "unknown" in result.cause.message.lower()


def test_feasible_results_carry_no_cause(toy) -> None:
    assert solve(toy, budget=12).cause is None
