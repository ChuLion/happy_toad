"""ToolSession: tool calls and report checks shared by the loop and the MCP server (SPEC, M6)."""

import json

import pytest
from agent_helpers import toy_dirs

from happy_toad.agent.session import ToolSession
from happy_toad.agent.transcript import Transcript

PASSING = json.dumps({"summary": "No numbers here.", "claims": []})
FAILING = json.dumps({"summary": "The spend is 400.", "claims": []})
NOT_A_REPORT = json.dumps({"summary": "x", "claims": [{"metric": "profit"}]})


@pytest.fixture
def session(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    record = Transcript(transcript_id="t1", question="q", profile="p", model="m")
    return ToolSession(inputs, runs, record)


def test_a_passing_report_is_accepted_and_checked(session) -> None:
    assert session.call("submit_report", PASSING) == {"accepted": True}
    assert session.record.status == "checked"
    assert session.record.report_accepted


def test_a_failing_report_asks_for_one_correction(session) -> None:
    result = session.call("submit_report", FAILING)
    assert result["accepted"] is False
    assert result["instruction"] == "fix and resubmit once"
    assert session.correction_pending


def test_a_second_failure_is_final_and_unverified(session) -> None:
    session.call("submit_report", FAILING)
    result = session.call("submit_report", FAILING)
    assert result["accepted"] is False and "instruction" not in result
    assert session.record.status == "unverified"
    assert not session.correction_pending


def test_a_correction_that_passes_is_accepted(session) -> None:
    session.call("submit_report", FAILING)
    assert session.call("submit_report", PASSING) == {"accepted": True}
    assert session.record.status == "checked"
    assert not session.correction_pending


def test_a_schema_failure_does_not_move_the_state(session) -> None:
    result = session.call("submit_report", NOT_A_REPORT)
    assert result["accepted"] is False and "schema" in result["error"]
    assert not session.correction_pending and session.record.checks == []
    session.call("submit_report", FAILING)
    session.call("submit_report", NOT_A_REPORT)
    assert session.correction_pending


def test_runs_returned_by_tools_become_known(session) -> None:
    result = session.call("run_scenario", json.dumps({"input_version": "test", "budget": 12}))
    assert session.runs == [result["run_id"]]
    session.call("get_run", json.dumps({"run_id": result["run_id"]}))
    assert session.runs == [result["run_id"]]


def test_other_tools_go_to_the_runner(session) -> None:
    assert "versions" in session.call("list_input_versions", "{}")
    assert session.call("no_such_tool", "{}") == {"error": "unknown tool 'no_such_tool'"}
