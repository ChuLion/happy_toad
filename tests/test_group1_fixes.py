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


# --- (b) added and dropped counts -----------------------------------------------------------


def test_compare_runs_reports_the_added_and_dropped_counts(two_runs):
    from happy_toad.services.runs import compare_runs

    _, a, b = two_runs
    c = compare_runs(a, b)
    assert c.n_only_in_a == len(c.only_in_a) and c.n_only_in_b == len(c.only_in_b)
    assert c.n_only_in_b > 0  # the larger budget adds candidates


def test_added_and_dropped_are_pair_metrics():
    with pytest.raises(ValueError):
        Claim(metric="n_added", value=1, unit=COUNT, run_id="a")
    assert Claim(metric="n_added", value=1.0, unit=COUNT, run_id="a", run_id_b="b").value == 1


def test_added_and_dropped_claims_are_checked_against_the_two_selections(two_runs):
    tmp_path, a, b = two_runs
    added = len(set(b.result.selected) - set(a.result.selected))
    dropped = len(set(a.result.selected) - set(b.result.selected))
    good = [
        dict(metric="n_added", value=added, run_id=a.run_id, run_id_b=b.run_id),
        dict(metric="n_dropped", value=dropped, run_id=a.run_id, run_id_b=b.run_id),
    ]
    summary = f"{added} candidates are added and {dropped} dropped."
    assert check_report(report(summary, *good), tmp_path / "runs", tmp_path / "inputs").ok
    wrong = dict(metric="n_added", value=added + 1, run_id=a.run_id, run_id_b=b.run_id)
    assert not check_report(report("", wrong), tmp_path / "runs", tmp_path / "inputs").ok


def test_truth_has_the_added_and_dropped_counts_of_demo_a():
    import json
    from pathlib import Path

    truth = json.loads((Path(__file__).parents[1] / "evals/truth.json").read_text())
    diffs = truth["cases"]["1"]["diffs"]["0,1"]
    assert (diffs["n_added"], diffs["n_dropped"]) == (15, 2)  # 14 - 2 + 15 = 27


# --- (c) the region percent -----------------------------------------------------------------


def test_the_region_percent_is_claimable_with_percent_tolerance(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=12.0, region_total_sectors=10)
    stored = run.result.pct_of_region
    claim = dict(metric="pct_of_region", value=round(stored, 1), run_id=run.run_id)
    summary = f"That is {round(stored, 1)}% of the region."
    assert check_report(report(summary, claim), tmp_path / "runs", tmp_path / "inputs").ok
    off = dict(metric="pct_of_region", value=stored + 0.1, run_id=run.run_id)
    assert not check_report(report("", off), tmp_path / "runs", tmp_path / "inputs").ok


def test_a_run_without_a_region_has_no_region_percent(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=12.0)
    claim = dict(metric="pct_of_region", value=50.0, run_id=run.run_id)
    assert not check_report(report("", claim), tmp_path / "runs", tmp_path / "inputs").ok


# --- (d) the year skip is the planning window -----------------------------------------------


def test_only_the_planning_window_years_are_skipped():
    from happy_toad.agent.checker import find_numbers

    text = "a budget of 2000 in 2026, 2027, 2031 and 2032"
    assert [t for t, _ in find_numbers(text)] == ["2000", "2026", "2032"]


def test_a_wrong_budget_of_2000_is_now_caught(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=12.0)
    claim = dict(metric="spend", value=round(run.result.spend, 2), run_id=run.run_id)
    summary = f"At a budget of 2000 the spend is {round(run.result.spend, 2)}."
    result = check_report(report(summary, claim), tmp_path / "runs", tmp_path / "inputs")
    assert not result.ok and "2000" in " ".join(result.errors())
