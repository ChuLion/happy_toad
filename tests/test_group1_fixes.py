"""M4 fix group 1 (docs/SPEC.md, M4 part D): checker fixes, one block per fix."""

import pytest
from agent_helpers import make_run, toy_dirs

from happy_toad.agent.checker import check_report
from happy_toad.agent.report import Claim, Report

COUNT = "count"


def report(summary: str, *claims: dict) -> Report:
    return Report(summary=summary, claims=list(claims))


@pytest.fixture
def two_runs(tmp_path):
    toy_dirs(tmp_path)
    a = make_run(tmp_path, budget=12.0)
    b = make_run(tmp_path, budget=17.0)
    return tmp_path, a, b


# --- (a) whole-valued counts ----------------------------------------------------------------


@pytest.mark.parametrize("metric", ["n_selected", "n_resolved", "n_sectors"])
def test_a_whole_valued_float_count_is_accepted_as_an_int(metric):
    c = Claim(metric=metric, value=2.0, unit=COUNT, run_id="r")
    assert c.value == 2 and type(c.value) is int


def test_a_signed_whole_valued_float_difference_is_accepted(two_runs):
    tmp_path, a, b = two_runs
    stored = b.result.resolved - a.result.resolved
    claim = dict(metric="diff_n_resolved", value=float(stored), run_id=a.run_id, run_id_b=b.run_id)
    assert check_report(report("", claim), tmp_path / "runs", tmp_path / "inputs").ok


@pytest.mark.parametrize("value", [2.5, -0.5])
def test_a_fractional_count_is_still_not_a_count(value):
    c = Claim(metric="n_selected", value=value, unit=COUNT, run_id="r")
    assert c.value == value  # left as it is, so it can never match a stored int


def test_money_metrics_keep_their_floats():
    assert type(Claim(metric="spend", value=11.0, unit="cost_units", run_id="r").value) is float
