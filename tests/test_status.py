"""Unit tests for map_status, using mocked PuLP statuses (no real solve, no real timeout)."""

import pytest
from pulp.constants import LpSolveStatus as S

from happy_toad.engine.status import map_status

OTHER = [
    S.NotSolved, S.Unbounded, S.Undefined, S.MemoryLimit, S.NodeLimit,
    S.IterationLimit, S.SolutionLimit, S.Interrupted, S.Stopped, S.NumericalError,
]  # fmt: skip


def test_optimal() -> None:
    assert map_status(S.Optimal) == "Optimal"


def test_gap_limit_is_optimal_because_gaps_are_pinned_to_zero() -> None:
    assert map_status(S.GapLimit) == "Optimal"


def test_infeasible() -> None:
    assert map_status(S.Infeasible) == "Infeasible"


def test_time_limit_is_never_optimal() -> None:
    assert map_status(S.TimeLimit) == "TimeLimit"


@pytest.mark.parametrize("status", OTHER)
def test_everything_else_is_error(status) -> None:
    assert map_status(status) == "Error"


def test_every_pulp_status_is_covered() -> None:
    covered = {S.Optimal, S.GapLimit, S.Infeasible, S.TimeLimit, *OTHER}
    assert covered == set(S)
