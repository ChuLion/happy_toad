"""The `ask` command (SPEC, M3 decision 10)."""

import pytest
from agent_helpers import FakeClient, call, toy_dirs, turn
from typer.testing import CliRunner

import happy_toad.cli as cli


@pytest.fixture
def invoke(tmp_path, monkeypatch):
    inputs, runs = toy_dirs(tmp_path)
    monkeypatch.setenv("COLUMNS", "200")

    def go(script, question="What does budget 12 give?", verbose=True):
        monkeypatch.setattr(cli, "make_client", lambda profile: FakeClient(script))
        args = [
            "ask", question, "--inputs-dir", str(inputs), "--runs-dir", str(runs),
            "--transcripts-dir", str(tmp_path / "transcripts"),
        ] + (["--verbose"] if verbose else [])  # fmt: skip
        return CliRunner().invoke(cli.app, args), runs

    return go


def test_ask_prints_tool_calls_report_and_checks_and_exits_0(invoke) -> None:
    first = turn(call("run_scenario", input_version="test", budget=12))

    class Script(list):
        """Build the report from the real run id once the run exists."""

    result, runs = invoke([first, turn(call("submit_report", summary="Which budget?", claims=[]))])
    assert result.exit_code == 0, result.output
    assert "run_scenario" in result.output and "submit_report" in result.output
    assert "checked" in result.output and "Which budget?" in result.output
    assert "cost:" in result.output and "tokens" in result.output
    assert list(runs.glob("*.json"))


def test_ask_exits_1_when_the_step_cap_is_hit(invoke) -> None:
    result, _ = invoke([turn(call("list_input_versions")) for _ in range(10)])
    assert result.exit_code == 1 and "step_cap" in result.output


def test_cost_not_configured_is_printed_when_the_response_has_none(invoke) -> None:
    result, _ = invoke([turn(call("submit_report", summary="Hello.", claims=[]), cost=None)])
    assert "cost: not configured" in result.output


def test_a_rejected_draft_is_not_shown_as_the_report_when_the_run_did_not_finish(invoke) -> None:
    draft = turn(call("submit_report", summary="Is 500 enough?", claims=[]))
    result, _ = invoke([draft] + [turn(call("list_input_versions")) for _ in range(9)])
    assert result.exit_code == 1 and "step_cap" in result.output
    assert "Report:" not in result.output


def test_an_unknown_profile_lists_the_valid_names(invoke, monkeypatch) -> None:
    from happy_toad.agent.config import PROFILES

    monkeypatch.setattr(cli, "make_client", lambda profile: None)
    result = CliRunner().invoke(cli.app, ["ask", "q", "--profile", "nope"])
    assert result.exit_code == 2
    assert all(name in result.output for name in PROFILES)


def test_default_output_is_compact(invoke) -> None:
    first = turn(call("run_scenario", input_version="test", budget=12))
    done = turn(call("submit_report", summary="Which budget?", claims=[]))
    result, _ = invoke([first, done], verbose=False)
    assert result.exit_code == 0, result.output
    assert "run_scenario test, budget 12 -> Optimal" in result.output
    assert "CHECKED" in result.output and "Which budget?" in result.output
    assert "tokens" not in result.output and '"result"' not in result.output
