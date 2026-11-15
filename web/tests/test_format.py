"""web/format.py says exactly what the CLI says (only "1 mismatch" differs), and the view
module no longer imports the CLI."""

import json
import subprocess
import sys
from pathlib import Path

from happy_toad import cli
from happy_toad.agent.transcript import Transcript
from web import format as fmt

FIXTURE = Path(__file__).parents[2] / "tests/fixtures/transcript_demo_c.json"


def _transcript(**changes) -> Transcript:
    return Transcript.model_validate(json.loads(FIXTURE.read_text()) | changes)


CALLS = [
    ("run_scenario", '{"input_version": "v1", "budget": 600, "force_in": ["C033"]}', {}),
    ("submit_report", '{"claims": [{}, {}]}', {"accepted": False, "errors": ["a", "b"]}),
    ("submit_report", "not json", {"accepted": True}),
    ("list_input_versions", "{}", {"versions": ["v1", "v2"]}),
    ("compare_runs", '{"run_id_a": "x", "run_id_b": "y"}', {"fields": {}}),
    ("get_run", '{"run_id": "x"}', {"error": "no such run"}),
    ("new_tool", '{"x": 1}', {"y": 2}),
]


def test_tool_call_wording_matches_the_cli():
    t = _transcript()
    saved = [(c["name"], c["arguments"], c["result"]) for turn in t.turns for c in turn.tool_calls]
    for name, raw, result in CALLS + saved:
        assert fmt.call_args(name, raw) == cli._call_args(name, raw)
        assert fmt.call_outcome(name, result) == cli._call_outcome(name, result)


def test_verdict_correction_and_status_lines_match_the_cli():
    for t in (_transcript(), _transcript(status="unverified"), _transcript(status="step_cap")):
        assert fmt.verdict(t) == cli.verdict(t)
        assert fmt.correction(t) == cli._correction(t)
    assert fmt.NO_FIGURES == cli.NO_FIGURES


def test_check_line_matches_the_cli_except_one_mismatch():
    check = _transcript().checks[0]
    assert fmt.check_line(check) == cli._counts(check)[0]
    one_bad = [n for n in check.numbers if not n.ok][:1]
    one = check.model_copy(update={"numbers": one_bad})
    assert fmt.check_line(one).endswith(", 1 mismatch")
    assert cli._counts(one)[0].endswith(", 1 mismatches")


def test_view_module_does_not_import_the_cli():
    code = "import sys, web.view; print('happy_toad.cli' in sys.modules)"
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr
