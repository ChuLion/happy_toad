"""M5 evaluations: the revision cases, their truth and the separate group (docs/SPEC.md, M5)."""

import json
from pathlib import Path
from typing import get_args

import pytest
from test_evals_grade import Script
from test_evals_truth import load_truth_module
from typer.testing import CliRunner

import happy_toad.cli as cli
from happy_toad.agent.config import SMOKE
from happy_toad.agent.loop import ask
from happy_toad.agent.report import Metric
from happy_toad.agent.tools import TOOLS
from happy_toad.data.files import write_inputs
from happy_toad.evals.cases import load_cases, load_revision_cases
from happy_toad.evals.grade import Grade, grade
from happy_toad.evals.runner import summarize
from happy_toad.services.revision import ORDER, RevisionRequest, run_revision

ROOT = Path(__file__).parents[1]
REVISION_TRUTH = ROOT / "evals/revision_truth.json"
TOLERANCE = 1e-6


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("inputs")
    write_inputs(42, folder)
    return folder


def test_there_are_four_revision_cases_101_to_104_and_the_19_are_unchanged():
    assert [c.id for c in load_revision_cases()] == [101, 102, 103, 104]
    assert [c.id for c in load_cases()] == list(range(1, 20))


def test_revision_cases_name_known_tools_metrics_and_kinds():
    tools = {t["function"]["name"] for t in TOOLS}
    metrics = set(get_args(Metric))
    for case in load_revision_cases():
        assert {c.tool for c in case.required_calls} <= tools, case.id
        assert set(case.forbidden_calls) <= tools, case.id
        assert {k.metric for k in case.key_numbers} <= metrics, case.id
        assert {k.entity for k in case.key_numbers} <= {"plan", *ORDER}, case.id


def test_the_missing_budget_case_has_no_budget_and_forbids_solving():
    case = next(c for c in load_revision_cases() if c.id == 101)
    assert case.runs == [] and "explain_revision" in case.forbidden_calls
    assert case.allowed_labels == ["NO NUMBERS TO CHECK"] and "budget" in case.required_phrases


def test_revision_truth_is_reproduced_by_the_truth_module(inputs):
    truth = load_truth_module().compute_revision(inputs)
    assert truth == json.loads(REVISION_TRUTH.read_text())


def test_the_engine_agrees_with_revision_truth(inputs, tmp_path):
    truth = json.loads(REVISION_TRUTH.read_text())
    specs = {
        (r.plan_of_record, r.input_version, r.budget) for c in load_revision_cases() for r in c.runs
    }
    for a, b, budget in specs:
        request = RevisionRequest(budget=budget, plan_of_record=a, refreshed_forecast=b)
        record = run_revision(request, inputs, tmp_path / "runs")
        expected = truth["budgets"][f"{a}|{b}|{budget:g}"]
        rev = record.revision
        assert rev.complete == expected["complete"]
        assert [s.selected for s in rev.steps] == expected["selected"]
        for step, value in zip(rev.steps[1:], expected["effect_relief"], strict=True):
            assert step.effect_relief == pytest.approx(value, abs=TOLERANCE)
        assert rev.total_relief == pytest.approx(expected["total_relief"], abs=TOLERANCE)
        assert rev.inputs.sectors_removed == [] and len(rev.inputs.sectors_added) == 3


def test_summarize_reports_revision_cases_as_a_separate_group():
    def grade(case_id, passed):
        return Grade(
            case_id=case_id, transcript_id=f"t{case_id}", label="CHECKED", runs_ok=passed,
            numbers_ok=passed, behaviour_ok=passed, first_pass=passed, allows_checked=True,
            review=[], problems=[], cost=0.0, seconds=1.0, turns=1, providers=["p"],
        )  # fmt: skip

    s = summarize([grade(1, True), grade(2, True), grade(101, False), grade(102, True)])
    assert s["overall"]["n"] == 2 and s["overall"]["pass_rate"] == 1.0
    assert s["revision"]["n"] == 2 and s["revision"]["pass_rate"] == 0.5


def test_case_102_requires_the_order_as_a_graded_phrase():
    case = next(c for c in load_revision_cases() if c.id == 102)
    assert "costs -> offloads -> triggers -> sectors" in case.required_phrases


# --- grading a revision conversation ------------------------------------------------------------


def _case_102_report(with_order: bool):
    def build(records):
        rev = records[0].revision
        claims = [
            dict(
                metric="effect_relief",
                value=round(s.effect_relief, 2),
                run_id=records[0].run_id,
                entity=s.name,
            )
            for s in rev.steps[1:]
        ] + [
            dict(metric="total_relief", value=round(rev.total_relief, 2), run_id=records[0].run_id)
        ]
        effects = ", ".join(f"{s.name} {s.effect_relief:.2f}" for s in rev.steps[1:])
        order = f"Applied in the order {rev.order_text}: " if with_order else "Effects: "
        summary = f"{order}{effects}; total {rev.total_relief:.2f} weighted relief."
        return dict(summary=summary, claims=claims)

    return build  # fmt: skip


@pytest.mark.parametrize("with_order", [True, False])
def test_case_102_is_graded_on_numbers_and_the_order_phrase(inputs, tmp_path, with_order):
    dirs = dict(inputs_dir=inputs, runs_dir=tmp_path / "runs", transcripts_dir=tmp_path / "t")
    case = next(c for c in load_revision_cases() if c.id == 102)
    steps = [("explain_revision", dict(budget=1000))]
    client = Script(dirs["runs_dir"], steps, _case_102_report(with_order))
    t = ask(case.question, client, SMOKE, **dirs)
    truth = json.loads(REVISION_TRUTH.read_text())["cases"]["102"]
    g = grade(case, t, truth, dirs["runs_dir"])
    assert g.label == "CHECKED" and g.runs_ok and g.numbers_ok, g.problems
    assert g.behaviour_ok is with_order


def test_the_eval_command_runs_the_revision_group(inputs, tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    steps = [("explain_revision", dict(budget=1000))]
    monkeypatch.setattr(
        cli, "make_eval_client", lambda profile: Script(runs, list(steps), _case_102_report(True))
    )
    out = tmp_path / "rounds"
    args = [
        "eval", "--revision", "--round", "m5", "--cases", "102", "--repeats", "1", "--unofficial",
        "--out-dir", str(out), "--profile", "smoke", f"--inputs-dir={inputs}",
        f"--runs-dir={runs}", f"--transcripts-dir={tmp_path / 't'}",
    ]  # fmt: skip
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    report = json.loads((out / "m5.unofficial.json").read_text())
    assert report["revision"]["n"] == 1 and report["revision"]["pass_rate"] == 1.0
    assert report["overall"]["n"] == 0
    assert "Revision group" in (out / "m5.unofficial.md").read_text()


def test_the_eval_command_refuses_cases_missing_from_the_truth_file(inputs, tmp_path):
    args = [
        "eval", "--revision", "--truth", str(ROOT / "evals/truth.json"), "--round", "x",
        "--unofficial", f"--inputs-dir={inputs}", f"--runs-dir={tmp_path / 'runs'}",
    ]  # fmt: skip
    result = CliRunner().invoke(cli.app, args)
    assert result.exit_code == 2 and "[101, 102, 103, 104]" in result.output
