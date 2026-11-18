"""A4 scripted equivalence: the same model script through the direct and the MCP path (SPEC, M6)."""

import json
import re

import pytest
from agent_helpers import call, toy_dirs, turn

from happy_toad.agent.client import ToolCall
from happy_toad.agent.config import SMOKE
from happy_toad.agent.label import verdict
from happy_toad.agent.loop import ask

RUN_ID = re.compile(r"\d{8}T\d{6}-[0-9a-f]{8}")
SOLVE_TIME = re.compile(r'"solve_time": [0-9.e-]+')  # wall clock, differs between any two solves
FAILING = dict(summary="The spend is 400.", claims=[])


def first_turn():
    return turn(
        call("list_input_versions"),
        call("run_scenario", input_version="test", budget=12),
        call("run_scenario", input_version="test", budget=15),
        call("run_scenario", input_version="test", budget=100),
        call("run_scenario", input_version="test", budget=12, market_floor_mult=3.0),
        call("run_scenario", input_version="test", budget="abc"),
        ToolCall(id="raw", name="run_scenario", arguments='{"budget": 8'),
        ToolCall(id="list", name="get_run", arguments="[1, 2]"),
        call("no_such_tool"),
        call("get_run", run_id="20990101T000000-00000000"),
        call("find_target_budget", input_version="test", target_pct_resolved=50),
        call("explain_revision", budget=12),
    )


class Script:
    """A fake model whose later turns use the run ids the first turn produced."""

    def __init__(self, ending):
        self.ending, self.step = ending, 0

    def complete(self, messages, tools):
        self.step += 1
        if self.step == 1:
            return first_turn()
        if self.step == 2:
            results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
            a, b = results[1]["run_id"], results[2]["run_id"]
            return turn(call("compare_runs", run_id_a=a, run_id_b=b), call("get_run", run_id=a))
        return self.ending(self.step - 3, messages)


def fail_twice(i, messages):
    return turn(call("submit_report", **FAILING))


def fail_then_pass(i, messages):
    if i == 0:
        return turn(call("submit_report", **FAILING))
    run = json.loads([m for m in messages if m["role"] == "tool"][1]["content"])  # budget 12
    claim = dict(metric="status", value="Optimal", run_id=run["run_id"])
    return turn(call("submit_report", summary="The plan solved.", claims=[claim]))


def claimless(i, messages):
    return turn(call("submit_report", summary="No numbers here.", claims=[]))


def renumber(value) -> str:
    """JSON text with run ids numbered by first appearance and solve times blanked."""
    text, seen = SOLVE_TIME.sub('"solve_time": "t"', json.dumps(value, sort_keys=True)), {}
    return RUN_ID.sub(lambda m: f"run-{seen.setdefault(m.group(), len(seen))}", text)


def comparable(t) -> dict:
    calls = [[dict(c) for c in x.tool_calls] for x in t.turns]
    for c in (c for turn_calls in calls for c in turn_calls):
        c["result"] = {k: v for k, v in c["result"].items() if k not in ("label", "summary")}
    return {
        "tool_calls": renumber(calls),
        "checks": renumber([c.model_dump(mode="json") for c in t.checks]),
        "report": renumber(t.report.model_dump(mode="json") if t.report else None),
        "status": t.status,
        "report_accepted": t.report_accepted,
        "coercions": renumber(t.coercions),
        "defaults": renumber(t.defaults),
        "label": verdict(t),
    }


def run_both(tmp_path, ending):
    out = {}
    for via in ("direct", "mcp"):
        (tmp_path / via).mkdir()
        inputs, runs = toy_dirs(tmp_path / via)
        t = ask(
            "q", Script(ending), SMOKE, inputs_dir=inputs, runs_dir=runs,
            transcripts_dir=tmp_path / via / "transcripts", via=via,
        )  # fmt: skip
        out[via] = t
    return out["direct"], out["mcp"]


@pytest.mark.parametrize(
    ("ending", "label"),
    [(fail_twice, "NOT CHECKED"), (fail_then_pass, "CHECKED"), (claimless, "NO NUMBERS TO CHECK")],
)
def test_both_paths_give_identical_results_checks_and_labels(tmp_path, ending, label) -> None:
    direct, mcp = run_both(tmp_path, ending)
    assert verdict(direct) == label
    assert comparable(mcp) == comparable(direct)


def test_the_mcp_path_records_its_route(tmp_path) -> None:
    direct, mcp = run_both(tmp_path, claimless)
    assert direct.provenance["via"] == "direct" and mcp.provenance["via"] == "mcp"
    assert direct.provenance["prompt_sha256"] == mcp.provenance["prompt_sha256"]


def test_runs_made_through_the_server_carry_the_client_transcript_id(tmp_path) -> None:
    _, mcp = run_both(tmp_path, claimless)
    records = [json.loads(p.read_text()) for p in (tmp_path / "mcp" / "runs").glob("*.json")]
    assert records and {r["transcript_id"] for r in records} == {mcp.transcript_id}


def test_only_check_record_fields_are_copied_from_the_server() -> None:
    from happy_toad.agent.mcp_client import McpTools
    from happy_toad.agent.transcript import Transcript

    record = Transcript(transcript_id="mine", question="q", profile="p", model="m")
    tools = McpTools(None, None, record)
    tools._copy_record({"status": "checked", "report_accepted": True, "transcript_id": "theirs"})
    assert record.transcript_id == "mine" and record.status == "checked"
    tools._copy_record({"status": "error", "report_accepted": False})
    assert record.status == "checked" and record.report_accepted is False
