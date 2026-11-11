"""Regression: at realistic scale every funded candidate must add real relief.

Found by the budget sweep on generated v1, not by the small known-answer tests. The first design
(an epsilon cost term in one solve) lost the cost term below CBC's tolerances at large budgets and
funded candidates that added nothing. The two-stage solve fixes it (docs/DECISIONS.md D2).
"""

import pytest

from happy_toad.data.generator import make_v1
from happy_toad.engine.model import BASE_YEAR, solve
from happy_toad.engine.relief import weighted_relief
from happy_toad.engine.result import DEFAULT_SETTINGS
from happy_toad.engine.stages import build_stage1, make_solver
from happy_toad.engine.sweep import default_budgets

DATA = make_v1(seed=42)
BUDGETS = default_budgets(sum(c.cost for c in DATA.candidates), sum(m.cost for m in DATA.must_fund))


@pytest.mark.parametrize("budget", [BUDGETS[1], BUDGETS[5], BUDGETS[8], BUDGETS[9], BUDGETS[11]])
def test_every_selected_candidate_adds_more_than_delta(budget) -> None:
    result = solve(DATA, budget)
    assert result.status == "Optimal"
    chosen = set(result.selected)
    total = weighted_relief(DATA, chosen, BASE_YEAR)
    useless = [
        c
        for c in sorted(chosen)
        if total - weighted_relief(DATA, chosen - {c}, BASE_YEAR) <= DEFAULT_SETTINGS.delta
    ]
    assert useless == []


def test_plateau_spend_is_the_same_once_the_budget_stops_binding() -> None:
    """Minimum spend at maximum relief cannot depend on how much extra budget there is."""
    spends = [solve(DATA, b).spend for b in BUDGETS[9:]]
    assert spends == pytest.approx([spends[0]] * len(spends), abs=1e-6)
    # Pinned value for v1 seed 42: before the two-stage fix macOS gave 4090.14 and Linux 4064.59.
    assert spends[0] == pytest.approx(3743.94, abs=0.01)


@pytest.mark.parametrize("budget", [BUDGETS[0], BUDGETS[4], BUDGETS[8], BUDGETS[11]])
def test_relief_is_within_slack_of_the_stage1_optimum(budget) -> None:
    must_fund = sum(m.cost for m in DATA.must_fund)
    prob, _ = build_stage1(DATA, budget - must_fund, BASE_YEAR)
    prob.solve(make_solver(DEFAULT_SETTINGS, 30))
    best = prob.objective.value()
    result = solve(DATA, budget)
    assert result.status == "Optimal"
    assert best - DEFAULT_SETTINGS.relief_slack <= result.objective <= best + 1e-6
