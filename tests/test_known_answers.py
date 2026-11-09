"""Known-answer tests for the optimizer (SPEC tests 1-7, plus weights, metadata, no-plan)."""

import dataclasses

import pulp
import pytest
from helpers import make_set
from pulp.constants import LpSolveStatus

from happy_toad.engine.model import solve


def test_1_zero_budget_selects_nothing() -> None:
    data = make_set([("S1", 10)], [("C1", 5)], [("C1", "S1", 3)])
    result = solve(data, budget=0)
    assert result.status == "Optimal"
    assert result.selected == []
    assert result.objective == 0
    assert result.spend == 0


def test_2_ample_budget_covers_all_possible_relief() -> None:
    sectors = [("S1", 10), ("S2", 10), ("S3", 10)]
    candidates = [("C1", 4), ("C2", 6), ("C3", 5)]
    offloads = [
        ("C1", "S1", 7),
        ("C2", "S1", 7),  # S1: offload 14 > shortfall 10 -> capped at 10
        ("C2", "S2", 4),
        ("C3", "S2", 3),  # S2: offload 7 < shortfall 10 -> 7
    ]  # fmt: skip  (S3: no candidate -> relief 0)
    data = make_set(sectors, candidates, offloads, must_fund=[3])
    result = solve(data, budget=sum(c[1] for c in candidates) + 3)
    assert result.status == "Optimal"
    assert result.relief == pytest.approx({"S1": 10, "S2": 7, "S3": 0})


def test_3_shared_candidate_beats_two_singles_when_cheaper() -> None:
    # Budget funds all three; relief is identical either way, so only the tie-break decides.
    sectors = [("S1", 5), ("S2", 5)]
    candidates = [("SHARED", 4), ("SINGLE1", 3), ("SINGLE2", 3)]
    offloads = [
        ("SHARED", "S1", 5), ("SHARED", "S2", 5),
        ("SINGLE1", "S1", 5), ("SINGLE2", "S2", 5),
    ]  # fmt: skip
    result = solve(make_set(sectors, candidates, offloads), budget=10)
    assert result.selected == ["SHARED"]
    assert result.spend == 4


def test_4_must_fund_above_budget_is_infeasible() -> None:
    data = make_set([("S1", 10)], [("C1", 5)], [("C1", "S1", 3)], must_fund=[8])
    result = solve(data, budget=5)
    assert result.status == "Infeasible"
    assert result.selected is None
    assert result.objective is None


def test_5a_candidate_with_zero_offload_is_not_funded() -> None:
    data = make_set([("S1", 5)], [("C1", 3), ("DUD", 1)], [("C1", "S1", 5), ("DUD", "S1", 0)])
    assert solve(data, budget=10).selected == ["C1"]


def test_5b_candidate_on_sector_with_no_shortfall_is_not_funded() -> None:
    data = make_set(
        [("S1", 5), ("S2", 0)], [("C1", 3), ("C2", 2)], [("C1", "S1", 5), ("C2", "S2", 4)]
    )
    assert solve(data, budget=10).selected == ["C1"]


def test_5c_redundant_candidate_is_not_funded() -> None:
    data = make_set(
        [("S1", 5)], [("CHEAP", 2), ("DEAR", 3)], [("CHEAP", "S1", 5), ("DEAR", "S1", 5)]
    )
    assert solve(data, budget=10).selected == ["CHEAP"]


def test_6_greedy_trap_picks_two_small_over_one_big() -> None:
    sectors = [("SA", 20), ("SB", 20), ("SC", 20)]
    candidates = [("A", 6), ("B", 5), ("C", 5)]
    offloads = [("A", "SA", 6), ("B", "SB", 4.5), ("C", "SC", 4.5)]
    result = solve(make_set(sectors, candidates, offloads), budget=10)
    assert sorted(result.selected) == ["B", "C"]
    assert result.objective == pytest.approx(9.0, abs=1e-9)  # weighted relief only, no cost term


def test_7_tie_break_never_beats_real_relief() -> None:
    # One candidate costs the whole available budget; its weighted relief is just above delta.
    data = make_set([("S1", 10)], [("C1", 7)], [("C1", "S1", 1.5e-4)])
    result = solve(data, budget=7)
    assert result.selected == ["C1"]
    assert result.objective == pytest.approx(1.5e-4, abs=1e-12)


def test_earlier_trigger_gets_higher_weight() -> None:
    sectors = [("NOW", 10, 2026), ("LATER", 10, 2027)]  # weights 1 and 1/2
    offloads = [("C1", "NOW", 5), ("C2", "LATER", 5)]
    result = solve(make_set(sectors, [("C1", 5), ("C2", 5)], offloads), budget=5)
    assert result.selected == ["C1"]
    assert result.objective == pytest.approx(5.0)


def test_result_records_inputs_and_solver_settings() -> None:
    data = make_set([("S1", 10)], [("C1", 5)], [("C1", "S1", 3)], must_fund=[2])
    result = solve(data, budget=12, base_year=2026)
    assert (result.budget, result.must_fund_total, result.base_year) == (12, 2, 2026)
    assert (result.version_id, result.content_hash) == (data.version_id, data.content_hash)
    settings = result.solver_settings
    assert (settings["threads"], settings["timeLimit"]) == (1, 30)
    assert (settings["gapRel"], settings["gapAbs"], settings["delta"]) == (0, 0, 1e-4)
    assert settings["epsilon"] == pytest.approx(1e-4 / (10 * 10))  # avail = 12 - 2
    assert result.solve_time >= 0


def test_time_limit_without_plan_has_none_not_empty(monkeypatch) -> None:
    no_plan = pulp.core.lp_stats.LpSolveStats(status=LpSolveStatus.TimeLimit, has_solution=False)
    monkeypatch.setattr(pulp.LpProblem, "solve", lambda self, solver=None, **kw: no_plan)
    data = make_set([("S1", 10)], [("C1", 5)], [("C1", "S1", 3)])
    result = solve(data, budget=10)
    assert (result.status, result.selected, result.objective) == ("TimeLimit", None, None)


def test_time_limit_with_incumbent_reports_best_found_plan(monkeypatch) -> None:
    real_solve = pulp.LpProblem.solve

    def stopped_on_time(self, solver=None, **kw):
        stats = real_solve(self, solver, **kw)
        return dataclasses.replace(stats, status=LpSolveStatus.TimeLimit)

    monkeypatch.setattr(pulp.LpProblem, "solve", stopped_on_time)
    data = make_set([("S1", 10)], [("C1", 5)], [("C1", "S1", 3)])
    result = solve(data, budget=10)
    assert result.status == "TimeLimit"  # never "Optimal"
    assert result.selected == ["C1"]
