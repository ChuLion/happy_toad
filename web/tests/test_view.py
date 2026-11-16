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
    assert view["schema_version"] == 3
    assert view["status"] == "CHECKED"
    assert view["checks"]["line"] == "2 claims | 2 numbers checked | 0 mismatches"
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
    assert view["checks"]["unmatched_numbers"] == ["297.57", "311.44"]
    assert view["checks"]["line"].endswith(" | 2 mismatches")


def test_one_mismatch_is_singular():
    t = _transcript(status="unverified")
    first = t.checks[0]
    t.checks = [first.model_copy(update={"numbers": [n for n in first.numbers if not n.ok][:1]})]
    assert build_view(t, [])["checks"]["line"].endswith(" | 1 mismatch")


def test_answer_without_figures_is_no_numbers_to_check():
    t = _transcript()
    t.checks = [t.checks[-1].model_copy(update={"claims": [], "numbers": []})]
    view = build_view(t, [])
    View.model_validate(view)
    assert view["status"] == "NO NUMBERS TO CHECK"
    assert view["checks"]["line"] == "No checkable figures in this answer"


def test_no_report_has_no_status_and_the_cli_status_line():
    view = build_view(_transcript(status="step_cap", report=None), [])
    View.model_validate(view)
    assert view["status"] is None
    assert view["summary"] is None
    assert view["detail"] == "Status: step_cap"


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


def test_summary_html_escapes_a_script_and_renders_bold():
    t = _transcript()
    summary = "**Spend** is 600.\n- <script>alert(1)</script>"
    t = t.model_copy(update={"report": t.report.model_copy(update={"summary": summary})})
    view = build_view(t, [_rejected_record()])
    View.model_validate(view)
    assert view["summary_html"] == (
        "<p><strong>Spend</strong> is 600.</p>"
        "<ul><li>&lt;script&gt;alert(1)&lt;/script&gt;</li></ul>"
    )
