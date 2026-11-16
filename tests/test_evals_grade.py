"""M4 part C: grading on runs, numbers and behaviour; the runner; official-round rules."""

import json
from pathlib import Path

import pytest
from agent_helpers import call, turn
from typer.testing import CliRunner

import happy_toad.cli as cli
from happy_toad.agent.config import SMOKE
from happy_toad.agent.loop import ask
from happy_toad.data.files import write_inputs
from happy_toad.evals import runner as runner_module
from happy_toad.evals.cases import load_cases
from happy_toad.evals.grade import grade
from happy_toad.evals.runner import RoundRefused, check_round_allowed, run_round, summarize
from happy_toad.services.runs import read_run

TRUTH = json.loads((Path(__file__).parents[1] / "evals/truth.json").read_text())
CASES = {c.id: c for c in load_cases()}
UNITS = dict(
    spend="cost_units", weighted_relief="need_units", n_resolved="count", n_sectors="count",
    required_minimum_budget="cost_units", pct_resolved="percent",
)  # fmt: skip


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("inputs")
    write_inputs(42, folder)
    return folder


@pytest.fixture
def dirs(inputs, tmp_path):
    return dict(inputs_dir=inputs, runs_dir=tmp_path / "runs", transcripts_dir=tmp_path / "t")


class Script:
    """Plays fixed tool calls, then a report built from the run records the tools returned."""

    def __init__(self, runs_dir, steps, report, second_report=None):
        self.runs_dir, self.steps, self.report = runs_dir, list(steps), report
        self.second_report, self.run_ids, self.submitted = second_report, [], 0

    def complete(self, messages, tools):
        last = json.loads(messages[-1]["content"]) if messages[-1]["role"] == "tool" else {}
        if isinstance(last.get("run_id"), str) and last["run_id"] not in self.run_ids:
            self.run_ids.append(last["run_id"])
        if self.steps:
            name, args = self.steps.pop(0)
            return turn(call(name, **args))
        records = [read_run(i, self.runs_dir) for i in self.run_ids]
        build = self.second_report if self.submitted and self.second_report else self.report
        self.submitted += 1
        return turn(call("submit_report", **build(records)))


def claim(record, metric, value):
    return dict(metric=metric, value=value, unit=UNITS[metric], run_id=record.run_id)


def converse(dirs, case_id, steps, report, **kw):
    client = Script(dirs["runs_dir"], steps, report, **kw)
    return ask(CASES[case_id].question, client, SMOKE, **dirs)


def graded(dirs, case_id, transcript, truth=TRUTH):
    return grade(CASES[case_id], transcript, truth["cases"][str(case_id)], dirs["runs_dir"])


def v2_1000_report(records):
    r = records[0].result
    spend, resolved = round(r.spend, 2), r.resolved
    return dict(
        summary=f"On v2 at a total budget of 1000 the spend is {spend:.2f} and {resolved} "
        "sectors are resolved, under the modeled objective and constraints.",
        claims=[claim(records[0], "spend", spend), claim(records[0], "n_resolved", resolved)],
    )


RUN_V2_1000 = ("run_scenario", dict(input_version="v2", budget=1000))


# --- a correct conversation passes ---------------------------------------------------------


def test_a_correct_answer_passes_all_three(dirs):
    t = converse(dirs, 12, [RUN_V2_1000], v2_1000_report)
    g = graded(dirs, 12, t)
    assert (g.runs_ok, g.numbers_ok, g.behaviour_ok, g.passed) == (True, True, True, True)
    assert g.label == "CHECKED" and g.first_pass is True and g.review == []


def test_a_rejected_run_with_the_required_phrases_passes(dirs):
    def report(records):
        return dict(
            summary="The request was rejected: the budget must be at least 697.01.",
            claims=[claim(records[0], "required_minimum_budget", 697.01)],
        )

    steps = [
        ("run_scenario", dict(input_version="v1", budget=600, force_in=["C033", "C034", "C024"]))
    ]
    assert graded(dirs, 4, converse(dirs, 4, steps, report)).passed


# --- right runs ----------------------------------------------------------------------------


def test_wrong_arguments_fail_runs_and_numbers_even_when_checked(dirs):
    wrong = ("run_scenario", dict(input_version="v1", budget=1000))  # v1 instead of v2
    g = graded(dirs, 12, converse(dirs, 12, [wrong], v2_1000_report))
    assert g.label == "CHECKED"  # self-consistent: the checker cannot know the version was wrong
    assert not g.runs_ok and not g.numbers_ok and not g.passed


def test_an_extra_run_scenario_is_allowed(dirs):
    extra = ("run_scenario", dict(input_version="v2", budget=1200))

    def report(records):
        return v2_1000_report(records[:1])

    g = graded(dirs, 12, converse(dirs, 12, [RUN_V2_1000, extra], report))
    assert g.runs_ok and g.passed


def test_a_forbidden_call_fails_runs(dirs):
    steps = [("run_scenario", dict(input_version="v1", budget=1000))]

    def report(records):
        return dict(summary="Here is a plan.", claims=[])

    g = graded(dirs, 7, converse(dirs, 7, steps, report))
    assert not g.runs_ok and "forbidden" in " ".join(g.problems)


# --- right numbers -------------------------------------------------------------------------


def test_a_missing_key_number_fails_numbers(dirs):
    def report(records):
        r = records[0].result
        return dict(
            summary=f"{r.resolved} sectors are resolved.",
            claims=[claim(records[0], "n_resolved", r.resolved)],
        )

    g = graded(dirs, 12, converse(dirs, 12, [RUN_V2_1000], report))
    assert g.label == "CHECKED" and not g.numbers_ok and "spend" in " ".join(g.problems)


def test_a_claim_that_contradicts_truth_fails_even_when_the_checker_passed_it(dirs):
    planted = json.loads(json.dumps(TRUTH))
    planted["cases"]["12"]["runs"][0]["values"]["spend"] += 1.0
    t = converse(dirs, 12, [RUN_V2_1000], v2_1000_report)
    g = graded(dirs, 12, t, truth=planted)
    assert g.label == "CHECKED" and not g.numbers_ok


# --- right behaviour -----------------------------------------------------------------------


def test_a_missing_required_phrase_fails_behaviour(dirs):
    steps = [("run_scenario", dict(input_version="v1", budget=1000, force_in=["C099"]))]

    def report(records):
        return dict(summary="That candidate is not in the data, so nothing was run.", claims=[])

    g = graded(dirs, 8, converse(dirs, 8, steps, report))
    assert g.runs_ok and not g.behaviour_ok and "C099" in " ".join(g.problems)


def test_a_review_phrase_is_flagged_but_does_not_fail(dirs):
    def report(records):
        return dict(
            summary="I cannot approve or recommend funding; I can run scenarios to help.",
            claims=[],
        )

    g = graded(dirs, 9, converse(dirs, 9, [], report))
    assert g.passed
    assert set(g.review) == {"approve", "recommend"}


def test_a_label_outside_the_allowed_set_fails_behaviour(dirs):
    g = graded(
        dirs, 7, converse(dirs, 7, [], lambda records: dict(summary="It funds 3.", claims=[]))
    )
    assert g.label == "NOT CHECKED" and not g.behaviour_ok


# --- case 19 -------------------------------------------------------------------------------


RUN_V1_800 = ("run_scenario", dict(input_version="v1", budget=800))


def test_case_19_fails_when_400_is_claimed(dirs):
    def report(records):
        return dict(summary="Confirmed.", claims=[claim(records[0], "spend", 400.0)])

    g = graded(dirs, 19, converse(dirs, 19, [RUN_V1_800], report))
    assert not g.passed and "400" in " ".join(g.problems)


def test_case_19_a_refutation_that_repeats_400_is_reviewed_not_failed(dirs):
    def report(records):
        return dict(
            summary="The spend is not 400; it is 485.59.",
            claims=[claim(records[0], "spend", 485.59)],
        )

    g = graded(dirs, 19, converse(dirs, 19, [RUN_V1_800], report))
    assert g.label == "NOT CHECKED"  # 400 is neither a claim nor a request value
    assert g.passed and "400" in g.review


def test_case_19_checked_without_400_needs_the_true_spend(dirs):
    def report(records):
        return dict(
            summary="The spend at 800 is 485.59.", claims=[claim(records[0], "spend", 485.59)]
        )

    g = graded(dirs, 19, converse(dirs, 19, [RUN_V1_800], report))
    assert g.label == "CHECKED" and g.passed and g.review == []


# --- first pass ----------------------------------------------------------------------------


def test_first_pass_is_false_when_the_first_report_was_refused(dirs):
    def wrong(records):
        return dict(summary="Spend is 1.", claims=[claim(records[0], "spend", 1.0)])

    t = converse(dirs, 12, [RUN_V2_1000], wrong, second_report=v2_1000_report)
    g = graded(dirs, 12, t)
    assert g.label == "CHECKED" and g.first_pass is False


# --- runner and summary --------------------------------------------------------------------


def test_run_round_runs_each_case_n_times_as_eval_and_grades_them(dirs):
    def make_client(case):
        return Script(dirs["runs_dir"], [RUN_V2_1000], v2_1000_report)

    grades = run_round([CASES[12]], make_client, SMOKE, repeats=2, truth=TRUTH, **dirs)
    assert [g.case_id for g in grades] == [12, 12] and all(g.passed for g in grades)
    for g in grades:
        saved = json.loads((dirs["transcripts_dir"] / f"{g.transcript_id}.json").read_text())
        assert saved["source"] == "eval"


def test_summarize_reports_the_rates_and_the_review_list(dirs):
    good = graded(dirs, 12, converse(dirs, 12, [RUN_V2_1000], v2_1000_report))
    flagged = graded(
        dirs, 9, converse(dirs, 9, [], lambda r: dict(summary="I cannot approve.", claims=[]))
    )
    s = summarize([good, flagged])
    assert s["overall"]["n"] == 2 and s["overall"]["pass_rate"] == 1.0
    assert s["overall"]["checked_rate"] == 0.5  # both cases allow CHECKED; one was claimless
    assert s["review"] == [
        {"case": 9, "transcript_id": flagged.transcript_id, "phrases": ["approve"]}
    ]
    assert "10 percentage points" in s["noise"]


# --- official rounds -----------------------------------------------------------------------


def test_an_official_round_refuses_a_dirty_tree(monkeypatch, inputs):
    monkeypatch.setattr(runner_module, "provenance", lambda: {"git_sha": "x", "git_dirty": True})
    with pytest.raises(RoundRefused, match="uncommitted"):
        check_round_allowed(TRUTH, inputs, unofficial=False)
    check_round_allowed(TRUTH, inputs, unofficial=True)  # allowed, marked unofficial


def test_a_round_refuses_inputs_that_differ_from_truth(tmp_path):
    other = tmp_path / "inputs"
    write_inputs(7, other)
    with pytest.raises(RoundRefused, match="content hash"):
        check_round_allowed(TRUTH, other, unofficial=True)


def test_the_eval_command_runs_unofficially_and_writes_the_report(dirs, monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli,
        "make_eval_client",
        lambda profile: Script(dirs["runs_dir"], [RUN_V2_1000], v2_1000_report),
    )
    out = tmp_path / "rounds"
    args = [
        "eval", "--round", "smoke", "--cases", "12", "--repeats", "1", "--unofficial",
        "--out-dir", str(out), "--profile", "smoke",
        *(f"--{k.replace('_', '-')}={v}" for k, v in dirs.items()),
    ]  # fmt: skip
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    report = json.loads((out / "smoke.unofficial.json").read_text())
    assert report["header"]["official"] is False and report["overall"]["pass_rate"] == 1.0
    assert (out / "smoke.unofficial.md").read_text().startswith("# Eval round smoke (UNOFFICIAL)")


# --- infrastructure ------------------------------------------------------------------------


class RateLimited:
    def complete(self, messages, tools):
        from happy_toad.agent.client import ProviderError

        raise ProviderError(429, '{"error": {"message": "temporarily rate-limited upstream"}}')


def test_a_provider_error_is_graded_as_infrastructure(dirs):
    t = ask(CASES[12].question, RateLimited(), SMOKE, **dirs)
    g = graded(dirs, 12, t)
    assert t.status == "api_error" and g.infrastructure is True


def test_infrastructure_is_left_out_of_every_rate_and_counted(dirs):
    good = graded(dirs, 12, converse(dirs, 12, [RUN_V2_1000], v2_1000_report))
    infra = graded(dirs, 12, ask(CASES[12].question, RateLimited(), SMOKE, **dirs))
    s = summarize([good, infra])
    o = s["overall"]
    assert (o["n"], o["infrastructure"], o["pass_rate"], o["checked_rate"]) == (1, 1, 1.0, 1.0)
    assert s["per_case"]["12"]["infrastructure"] == 1 and s["per_case"]["12"]["n"] == 1
    assert s["infrastructure"] == [{"case": 12, "transcript_id": infra.transcript_id}]


def test_the_markdown_report_shows_the_infrastructure_count(dirs):
    from happy_toad.evals.runner import markdown, report

    infra = graded(dirs, 12, ask(CASES[12].question, RateLimited(), SMOKE, **dirs))
    prov = {"git_sha": "x", "git_dirty": False, "prompt_sha256": "p" * 64}
    text = markdown(report([infra], "r", True, prov, SMOKE))
    assert "infrastructure 1 (excluded)" in text and "## Infrastructure" in text


# --- regrading a stored round --------------------------------------------------------------


def test_regrade_grades_the_stored_transcripts_again_without_new_conversations(dirs, tmp_path):
    from happy_toad.evals.runner import regrade, report

    def make_client(case):
        return Script(dirs["runs_dir"], [RUN_V2_1000], v2_1000_report)

    grades = run_round([CASES[12]], make_client, SMOKE, repeats=2, truth=TRUTH, **dirs)
    prov = {"git_sha": "old", "git_dirty": False, "prompt_sha256": "p" * 64}
    stored = report(grades, "base", True, prov, SMOKE)
    again = regrade(stored, TRUTH, dirs["runs_dir"], dirs["transcripts_dir"], ["a note"])
    assert [g["transcript_id"] for g in again["grades"]] == [g.transcript_id for g in grades]
    assert again["overall"] == stored["overall"]
    assert again["header"]["provenance"] == prov  # the round's own provenance is kept
    assert again["header"]["regraded"]["provenance"]["git_sha"] != "old"
    assert again["header"]["notes"] == ["a note"]


def test_notes_appear_in_the_markdown_report():
    from happy_toad.evals.runner import markdown

    prov = {"git_sha": "x", "git_dirty": False, "prompt_sha256": "p" * 64}
    rates = ("pass_rate", "runs_rate", "numbers_rate", "behaviour_rate", "checked_rate")
    rates += ("first_pass_rate", "cost_total", "seconds_mean", "turns_mean")
    header = dict(round="r", date="d", official=True, provenance=prov, model="m", providers=[])
    r = {
        "header": header | {"notes": ["case 17 note"]},
        "overall": {k: None for k in rates} | {"n": 0, "infrastructure": 0},
        "per_case": {},
        "review": [],
        "infrastructure": [],
        "grades": [],
        "noise": "noise",
    }
    assert "- case 17 note" in markdown(r)
