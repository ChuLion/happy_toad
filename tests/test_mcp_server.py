"""The MCP server: the seven tools translated to a ToolSession (SPEC, M6 Q3, Q4, Q7, A1, A2)."""

import json

import pytest
from agent_helpers import toy_dirs

from happy_toad.agent.tools import TOOLS
from happy_toad.mcp_server import RAW, McpSession, arguments_text, tool_list

PASSING = {"summary": "No numbers here.", "claims": []}
FAILING = {"summary": "The spend is 400.", "claims": []}


@pytest.fixture
def dirs(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    return inputs, runs, tmp_path / "transcripts"


def as_openai(tool) -> dict:
    spec = {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}
    return {"type": "function", "function": spec}


def test_the_tool_list_is_the_seven_tools_unchanged() -> None:
    assert [as_openai(t) for t in tool_list()] == TOOLS


def test_arguments_are_sent_on_as_json_text() -> None:
    assert json.loads(arguments_text({"run_id": "x"})) == {"run_id": "x"}
    assert arguments_text(None) == "{}"


def test_unparseable_arguments_reach_the_runner_as_written() -> None:
    assert arguments_text({RAW: '{"budget": 8'}) == '{"budget": 8'


def test_a_final_report_carries_label_and_summary(dirs) -> None:
    s = McpSession(*dirs)
    result = s.handle("submit_report", PASSING)
    assert result == {
        "accepted": True,
        "label": "NO NUMBERS TO CHECK",
        "summary": PASSING["summary"],
    }


def test_a_pending_correction_has_no_label(dirs) -> None:
    s = McpSession(*dirs)
    result = s.handle("submit_report", FAILING)
    assert result["instruction"] == "fix and resubmit once" and "label" not in result
    final = s.handle("submit_report", FAILING)
    assert final["label"] == "NOT CHECKED" and final["summary"] == FAILING["summary"]


def test_a_desktop_session_logs_every_call(dirs) -> None:
    s = McpSession(*dirs)
    s.handle("list_input_versions", {})
    s.handle("submit_report", PASSING)
    log = json.loads((dirs[2] / "mcp" / f"{s.record.transcript_id}.json").read_text())
    assert log["source"] == "mcp"
    assert [c["name"] for c in log["tool_calls"]] == ["list_input_versions", "submit_report"]
    assert log["tool_calls"][1]["result"]["label"] == "NO NUMBERS TO CHECK"


def test_an_eval_session_uses_the_given_transcript_id_and_writes_no_log(dirs) -> None:
    s = McpSession(*dirs, transcript_id="20261117T000000-abcdef12")
    result = s.handle("run_scenario", {"input_version": "test", "budget": 12})
    record = json.loads((dirs[1] / f"{result['run_id']}.json").read_text())
    assert record["transcript_id"] == "20261117T000000-abcdef12"
    assert not (dirs[2] / "mcp").exists()


def test_submit_results_carry_the_check_record_for_the_client(dirs) -> None:
    s = McpSession(*dirs)
    meta = s.record_meta()
    assert set(meta) == {"checks", "report", "status", "report_accepted", "coercions", "defaults"}


# A1: one process, many chats.


def test_limit_1_a_pending_correction_carries_into_the_next_chat(dirs) -> None:
    s = McpSession(*dirs)
    s.handle("submit_report", FAILING)  # chat 1 is abandoned here
    result = s.handle("submit_report", FAILING)  # chat 2's first report
    assert result["label"] == "NOT CHECKED" and "instruction" not in result


def test_after_a_final_verdict_the_next_report_gets_a_correction_again(dirs) -> None:
    s = McpSession(*dirs)
    s.handle("submit_report", PASSING)
    assert s.handle("submit_report", FAILING)["instruction"] == "fix and resubmit once"


def test_limit_2_a_run_from_an_earlier_chat_is_known(dirs) -> None:
    s = McpSession(*dirs)
    run = s.handle("run_scenario", {"input_version": "test", "budget": 12})  # chat 1
    claim = {"metric": "status", "value": run["result"]["status"], "unit": "none",
             "run_id": run["run_id"], "entity": "plan"}  # fmt: skip
    report = {"summary": "The plan solved.", "claims": [claim]}
    assert s.handle("submit_report", report)["label"] == "CHECKED"  # chat 2


def test_provenance_is_fixed_when_the_session_starts(dirs) -> None:
    s = McpSession(*dirs)
    before = dict(s.record.provenance)
    s.handle("list_input_versions", {})
    assert s.record.provenance == before and set(before) >= {"git_sha", "prompt_sha256"}
