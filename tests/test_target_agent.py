"""M2B through the agent: the find_target_budget tool, rule 12, provenance and the CLI command."""

import json

import pytest
from agent_helpers import call, turn
from test_target_budget import toy
from typer.testing import CliRunner

from happy_toad.agent.checker import check_report
from happy_toad.agent.config import SMOKE
from happy_toad.agent.loop import ask
from happy_toad.agent.prompt import SYSTEM_PROMPT
from happy_toad.agent.report import Report
from happy_toad.agent.tools import TOOLS
from happy_toad.cli import app
from happy_toad.data.loader import save_input_set
from happy_toad.reasons import ReasonCode
from happy_toad.services.runs import read_run
from happy_toad.services.target import TargetBudgetRequest, run_target

QUESTION = "On test, what total budget resolves at least 25% of sectors?"
NOT_IN_CONVERSATION = "run was not executed or read in this conversation"


@pytest.fixture
def dirs(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    save_input_set(toy(), inputs / "test.json")
    return dict(inputs_dir=inputs, runs_dir=tmp_path / "runs", transcripts_dir=tmp_path / "t")


class Searcher:
    """Calls find_target_budget, then reports claims from the search and its follow-up run."""

    def __init__(self, args: dict) -> None:
        self.args, self.result, self.seen = args, None, []

    def complete(self, messages, tools):
        self.seen.append(messages[-1])
        if self.result is None and messages[-1]["role"] == "tool":
            self.result = json.loads(messages[-1]["content"])
        if self.result is None:
            return turn(call("find_target_budget", **self.args))
        if not self.result.get("follow_up_run_id"):
            return turn(call("submit_report", summary="The search was refused.", claims=[]))
        return turn(call("submit_report", **self.report()))

    def report(self) -> dict:
        search, follow = self.result["run_id"], self.result["follow_up_run_id"]
        budget = self.result["result"]["target_budget"]
        claims = [
            dict(metric="target_sectors", value=1, unit="count", run_id=search),
            dict(metric="n_sectors", value=4, unit="count", run_id=search),
            dict(metric="target_budget", value=budget, unit="cost_units", run_id=search),
            dict(metric="n_resolved", value=0, unit="count", run_id=follow),
        ]
        summary = (
            f"The cheapest plan that resolves at least 1 of 4 sectors needs a total budget of "
            f"{budget:.2f}. At that budget the optimizer's usual plan, which maximizes weighted "
            "relief, resolves 0 sectors. A higher budget does not guarantee more resolved sectors."
        )
        return dict(summary=summary, claims=claims)


def test_six_tools_include_find_target_budget():
    names = [t["function"]["name"] for t in TOOLS]
    assert names == [
        "list_input_versions", "run_scenario", "find_target_budget", "get_run", "compare_runs",
        "submit_report",
    ]  # fmt: skip
    spec = next(t["function"] for t in TOOLS if t["function"]["name"] == "find_target_budget")
    assert "total budget" in spec["description"] and "cheapest plan" in spec["description"]
    assert set(spec["parameters"]["properties"]) == {
        "input_version", "target_pct_resolved", "force_in", "force_out", "label",
    }  # fmt: skip


def test_rule_12_states_the_target_as_sectors_and_the_caveat():
    assert "12. " in SYSTEM_PROMPT and "find_target_budget" in SYSTEM_PROMPT
    assert '"at least k of N sectors"' in SYSTEM_PROMPT
    assert "including must-fund projects" in SYSTEM_PROMPT
    assert "A higher budget does not guarantee more resolved sectors" in SYSTEM_PROMPT
    assert "max_pct_resolvable" in SYSTEM_PROMPT


def test_the_tool_returns_the_search_and_its_follow_up_run(dirs):
    client = Searcher(dict(input_version="test", target_pct_resolved=25))
    ask(QUESTION, client, SMOKE, **dirs)
    result = client.result
    assert result["result"]["target_budget"] == 5.0
    assert result["result"]["target_sectors"] == 1
    assert result["follow_up"]["run_id"] == result["follow_up_run_id"]
    assert result["follow_up"]["result"]["resolved"] == 0


def test_a_question_about_a_target_ends_checked_with_claims_from_both_runs(dirs):
    client = Searcher(dict(input_version="test", target_pct_resolved=25))
    t = ask(QUESTION, client, SMOKE, **dirs)
    assert t.status == "checked", t.checks[-1].errors()
    cited = {c.run_id for c in t.report.claims}
    assert cited == {client.result["run_id"], client.result["follow_up_run_id"]}


def test_a_claim_on_the_follow_up_run_fails_when_it_was_not_in_the_conversation(dirs):
    search = run_target(
        TargetBudgetRequest(input_version="test", target_pct_resolved=25),
        dirs["inputs_dir"],
        dirs["runs_dir"],
    )
    claim = dict(metric="n_resolved", value=0, unit="count", run_id=search.follow_up_run_id)
    report = Report(summary="", claims=[claim])
    only_search = check_report(
        report, dirs["runs_dir"], dirs["inputs_dir"], conversation_runs=[search.run_id]
    )
    assert not only_search.ok
    assert NOT_IN_CONVERSATION in only_search.errors()[0]
    both = [search.run_id, search.follow_up_run_id]
    assert check_report(report, dirs["runs_dir"], dirs["inputs_dir"], conversation_runs=both).ok


def test_multipliers_through_the_tool_become_a_schema_invalid_record(dirs):
    args = dict(input_version="test", target_pct_resolved=25, market_floor_mult=1.0)
    client = Searcher(args)
    ask(QUESTION, client, SMOKE, **dirs)
    result = client.result
    assert result["outcome"] == "rejected"
    reason = result["reasons"][0]
    assert reason["code"] == ReasonCode.SCHEMA_INVALID
    assert "market_floor_mult is not supported in the target-budget search" in reason["message"]
    assert read_run(result["run_id"], dirs["runs_dir"]).kind == "target_budget"


# --- CLI ---------------------------------------------------------------------------------------

runner = CliRunner(env={"COLUMNS": "200"})


def test_cli_target_budget_prints_the_search_and_the_follow_up(dirs):
    args = ["target-budget", str(dirs["inputs_dir"] / "test.json"), "--target", "25",
            "--runs-dir", str(dirs["runs_dir"])]  # fmt: skip
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "target 25% = at least 1 of 4 sectors" in result.output
    assert "target budget 5.00 (total, including must-fund)" in result.output
    assert "optimizer at 5.00 resolves 0 of 4" in result.output
    assert "a higher budget does not guarantee more resolved sectors" in result.output


def test_cli_target_budget_reports_an_unreachable_target(dirs):
    args = ["target-budget", str(dirs["inputs_dir"] / "test.json"), "--target", "75",
            "--runs-dir", str(dirs["runs_dir"])]  # fmt: skip
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "unreachable: at most 2 of 4 sectors (50.0%) can be resolved" in result.output


def _invoke(dirs, *extra):
    base = ["target-budget", str(dirs["inputs_dir"] / "test.json"), "--runs-dir"]
    return runner.invoke(app, [*base, str(dirs["runs_dir"]), *extra])


def test_cli_exit_codes_found_and_unreachable_are_zero(dirs):
    assert _invoke(dirs, "--target", "25").exit_code == 0
    assert _invoke(dirs, "--target", "75").exit_code == 0


def test_cli_exit_code_for_a_gate_rejection_is_1(dirs):
    result = _invoke(dirs, "--target", "25", "--force-in", "Z9")
    assert result.exit_code == 1
    assert "UNKNOWN_CANDIDATE" in result.output


def test_cli_exit_code_for_an_invalid_request_is_2(dirs):
    assert _invoke(dirs, "--target", "101").exit_code == 2


def test_cli_exit_code_for_a_time_limit_is_3(dirs, monkeypatch):
    from happy_toad.engine.target import CheapestPlan
    from happy_toad.services import target as service

    stopped = CheapestPlan("TimeLimit", None, None, {"stage1": 30.0})
    monkeypatch.setattr(service, "cheapest_plan", lambda *args, **kwargs: stopped)
    result = _invoke(dirs, "--target", "25")
    assert result.exit_code == 3
    assert "TimeLimit: no proven cheapest plan" in result.output
