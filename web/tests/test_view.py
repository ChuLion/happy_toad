"""build_view on a saved transcript: schema, status, correction, generic rendering, redaction."""

import json
from pathlib import Path

from happy_toad.agent.transcript import Transcript
from happy_toad.services.run import RunRecord
from web.schema import View
from web.view import build_view

FIXTURE = Path(__file__).parents[2] / "tests/fixtures/transcript_demo_c.json"
RUN_ID = "20261114T210203-96d94d4c"


def _transcript(**changes) -> Transcript:
    return Transcript.model_validate(json.loads(FIXTURE.read_text()) | changes)


def _rejected_record() -> RunRecord:
    return RunRecord(
        run_id=RUN_ID,
        created_at="2026-11-14T21:02:03Z",
        outcome="rejected",
        request={"input_version": "v1", "budget": 600, "force_in": ["C033", "C034", "C024"]},
        request_hash="h",
        input_version="v1",
        content_hash=None,
        required_minimum_budget=697.01,
        settings={},
        reasons=[],
        error=None,
        result=None,
        timing={},
        warnings=[],
    )


def test_saved_transcript_fits_the_schema():
    view = build_view(_transcript(), [_rejected_record()])
    View.model_validate(view)
    assert view["schema_version"] == 1
    assert view["status"] == "CHECKED"
    assert view["steps"][0]["tool"] == "run_scenario"
    assert "rejected" in view["steps"][0]["outcome"]
    assert view["checks"]["mismatches"] == []
    assert view["runs"][0]["values"]["budget"] == 600
    assert view["footer"]["model"] == "deepseek/deepseek-v4-flash-0731"


def test_correction_round_is_reported():
    view = build_view(_transcript(), [])
    assert view["correction"]["happened"] is True
    assert "297.57" in view["correction"]["note"]


def test_unverified_is_not_checked_with_mismatches():
    t = _transcript(status="unverified")
    t.checks = t.checks[:1]
    view = build_view(t, [])
    assert view["status"] == "NOT CHECKED"
    assert len(view["checks"]["mismatches"]) == 2


def test_unknown_tool_renders_generically():
    t = _transcript()
    t.turns[0].tool_calls.append(
        {"name": "new_tool", "arguments": '{"x": 1}', "result": {"some_metric": 3.5}}
    )
    view = build_view(t, [])
    View.model_validate(view)
    step = view["steps"][1]
    assert step == {"tool": "new_tool", "args": '{"x": 1}', "outcome": '{"some_metric": 3.5}'}


def test_keys_and_account_ids_are_redacted():
    leaked = "key sk-or-v1-" + "a" * 64 + " account user_" + "B" * 24
    view = build_view(_transcript(question=leaked), [])
    assert "sk-or" not in view["question"]
    assert "user_B" not in view["question"]
    assert view["question"].count("[redacted]") == 2
