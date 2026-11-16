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


# --- (k) numbers from runs executed in the conversation -------------------------------------


def test_request_values_of_executed_runs_are_allowed_without_a_citing_claim(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=12.0, force_in=["Z9"])  # rejected: unknown candidate
    r = report("The run at a total budget of 12 was rejected.")
    runs, inputs = tmp_path / "runs", tmp_path / "inputs"
    assert check_report(r, runs, inputs, conversation_runs=[run.run_id]).ok
    assert not check_report(r, runs, inputs, conversation_runs=[]).ok  # not executed here


def test_numbers_in_a_rejection_message_are_allowed(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=100.0)  # above the cap 1.5 x 17 = 25.50
    message = run.reasons[0].message
    assert "25.50" in message and "1.5" in message
    r = report("A total budget of 100 is above the cap of 25.50 (1.5 times the total cost).")
    assert check_report(r, tmp_path / "runs", tmp_path / "inputs", [run.run_id]).ok


def test_a_number_only_in_the_question_stays_unallowed(tmp_path):
    toy_dirs(tmp_path)
    run = make_run(tmp_path, budget=12.0)
    spend = round(run.result.spend, 2)
    claim = dict(metric="spend", value=spend, run_id=run.run_id)
    r = report(f"The spend is {spend}, not 400.", claim)
    result = check_report(r, tmp_path / "runs", tmp_path / "inputs", [run.run_id])
    assert not result.ok and "400" in " ".join(result.errors())


def test_the_agent_loop_allows_numbers_of_its_own_rejected_runs(tmp_path):
    from agent_helpers import FakeClient, call, turn

    from happy_toad.agent.config import SMOKE
    from happy_toad.agent.loop import ask

    inputs, runs = toy_dirs(tmp_path)
    summary = "A total budget of 100 is above the cap of 25.50, so it was rejected."
    script = [
        turn(call("run_scenario", input_version="test", budget=100)),
        turn(call("submit_report", summary=summary, claims=[])),
    ]
    t = ask("q", FakeClient(script), SMOKE, inputs_dir=inputs, runs_dir=runs,
            transcripts_dir=tmp_path / "t")  # fmt: skip
    assert t.status == "checked"


# --- (e) candidate ids in the summary --------------------------------------------------------


@pytest.fixture
def c_runs(tmp_path):
    """C001 resolves sA (cost 5), C002 resolves sB (cost 5), C003 resolves sC (cost 9)."""
    from helpers import make_set

    from happy_toad.data.loader import save_input_set
    from happy_toad.services.request import SolveRequest
    from happy_toad.services.run import run_request

    inputs, runs = tmp_path / "inputs", tmp_path / "runs"
    inputs.mkdir()
    data = make_set(
        [("sA", 10), ("sB", 10), ("sC", 10)],
        [("C001", 5), ("C002", 5), ("C003", 9)],
        [("C001", "sA", 10), ("C002", "sB", 10), ("C003", "sC", 10)],
    )
    save_input_set(data, inputs / "c.json")

    def run(**kw):
        return run_request(SolveRequest(input_version="c", **kw), inputs, runs)

    return inputs, runs, run


def status_claim(record):
    return dict(metric="status", value=record.result.status if record.result else "rejected",
                run_id=record.run_id)  # fmt: skip


def test_a_selected_or_forced_candidate_may_be_named(c_runs):
    inputs, runs, run = c_runs
    record = run(budget=10.0, force_out=["C003"])
    assert record.result.selected == ["C001", "C002"]
    r = report("The plan funds C001 and C002; C003 was left out.", status_claim(record))
    assert check_report(r, runs, inputs, [record.run_id]).ok


def test_a_candidate_outside_the_cited_runs_is_refused(c_runs):
    inputs, runs, run = c_runs
    record = run(budget=10.0)
    r = report("The plan funds C001, C002 and C003.", status_claim(record))
    result = check_report(r, runs, inputs, [record.run_id])
    assert not result.ok
    assert any("C003" in e and "cited run" in e for e in result.errors())


def test_a_forced_in_unknown_candidate_of_a_cited_rejected_run_may_be_named(c_runs):
    inputs, runs, run = c_runs
    record = run(budget=10.0, force_in=["C099"])
    assert record.outcome == "rejected"
    r = report(
        "C099 is not a candidate in this data, so the run was rejected.", status_claim(record)
    )
    assert check_report(r, runs, inputs, [record.run_id]).ok


def test_a_claimless_answer_that_names_a_candidate_is_refused(c_runs):
    """As specified: no claim, so no cited run, so the id cannot be traced (affects case 9)."""
    inputs, runs, _ = c_runs
    result = check_report(report("I cannot decide whether to fund C001."), runs, inputs, [])
    assert not result.ok and "C001" in " ".join(result.errors())
