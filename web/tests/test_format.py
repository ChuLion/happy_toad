"""web/format.py says exactly what the CLI says, and the view
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
    ("submit_report", '{"claims": []}', {"accepted": False, "errors": ["a"]}),
    ("submit_report", "not json", {"accepted": True}),
    ("list_input_versions", "{}", {"versions": ["v1", "v2"]}),
    ("compare_runs", '{"run_id_a": "x", "run_id_b": "y"}', {"fields": {}}),
    ("get_run", '{"run_id": "x"}', {"error": "no such run"}),
    ("new_tool", '{"x": 1}', {"y": 2}),
]
TARGET_ARGS = '{"input_version": "v1", "target_pct_resolved": 50, "force_in": ["C033"]}'
FOUND = {
    "run_id": "r1", "outcome": "completed", "follow_up_run_id": "r2",
    "result": {"status": "Optimal", "target_budget": 1145.21, "total_sectors": 80},
    "follow_up": {"run_id": "r2", "result": {"resolved": 33, "total_sectors": 80}},
}  # fmt: skip
UNREACHABLE = {
    "run_id": "r1", "outcome": "completed", "follow_up_run_id": None,
    "result": {"status": "Infeasible", "target_budget": None, "max_resolvable": 76,
               "max_pct_resolvable": 95.0, "total_sectors": 80},
}  # fmt: skip
REFUSED = {"run_id": "r1", "outcome": "rejected", "result": None,
           "reasons": [{"code": "VERSION_NOT_FOUND", "message": "x"}]}  # fmt: skip
FOLLOW_UP_REJECTED = {
    "run_id": "r1", "outcome": "completed", "follow_up_run_id": "r2",
    "result": {"status": "Optimal", "target_budget": 0.0, "total_sectors": 4},
    "follow_up": {"run_id": "r2", "outcome": "rejected", "result": None,
                  "reasons": [{"code": "BUDGET_NOT_POSITIVE", "message": "x"}]},
}  # fmt: skip
CALLS += [
    ("find_target_budget", TARGET_ARGS, r)
    for r in (FOUND, UNREACHABLE, REFUSED, FOLLOW_UP_REJECTED)
]


def test_target_budget_wording():
    assert fmt.call_args("find_target_budget", TARGET_ARGS) == "v1, target 50%, force in C033"
    assert fmt.call_outcome("find_target_budget", FOUND) == (
        "target budget 1145.21 [r1]; optimizer at 1145.21 resolves 33 of 80 [r2]"
    )
    assert fmt.call_outcome("find_target_budget", UNREACHABLE) == (
        "unreachable: at most 76 of 80 sectors (95.0%) [r1]"
    )
    assert fmt.call_outcome("find_target_budget", REFUSED) == "rejected VERSION_NOT_FOUND [r1]"
    assert fmt.call_outcome("find_target_budget", FOLLOW_UP_REJECTED) == (
        "target budget 0.00 [r1]; optimizer at 0.00: rejected BUDGET_NOT_POSITIVE [r2]"
    )


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


def test_check_line_matches_the_cli():
    check = _transcript().checks[0]
    assert fmt.check_line(check) == cli._counts(check)[0]
    one_bad = [n for n in check.numbers if not n.ok][:1]
    one = check.model_copy(update={"numbers": one_bad})
    assert fmt.check_line(one) == cli._counts(one)[0]
    assert fmt.check_line(one).endswith(" | 1 mismatch")


def test_view_module_does_not_import_the_cli():
    code = "import sys, web.view; print('happy_toad.cli' in sys.modules)"
    root = Path(__file__).parents[2]
    out = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr


def test_one_problem_is_singular():
    result = {"accepted": False, "errors": ["a"]}
    assert fmt.call_outcome("submit_report", result) == "refused (1 problem)"


def test_the_trace_shows_the_change_lists():
    result = {"versions": ["v1", "v2"], "change_lists": ["changes_v1_to_v2"]}
    expected = "v1, v2; change lists: changes_v1_to_v2"
    assert fmt.call_outcome("list_input_versions", result) == expected
    assert cli._call_outcome("list_input_versions", result) == expected


def test_one_claim_is_singular_in_both():
    check = _transcript().checks[0]
    one = check.model_copy(update={"claims": check.claims[:1]})
    assert fmt.check_line(one) == cli._counts(one)[0]
    assert fmt.check_line(one).startswith("1 claim | ")


def test_correction_matches_the_cli_with_schema_refusals():
    refused = {"accepted": False, "error": "report does not fit the schema: x"}
    schema = {"name": "submit_report", "arguments": "{}", "result": refused}
    t = _transcript()
    both = [turn.model_copy(deep=True) for turn in t.turns]
    both[0].tool_calls.append(schema)
    alone = [turn.model_copy(deep=True) for turn in t.turns]
    alone[1].tool_calls = [schema]
    cases = [
        t.model_copy(update={"turns": both}),
        t.model_copy(update={"turns": alone, "checks": t.checks[1:]}),
    ]
    for case in cases:
        assert fmt.correction(case) == cli._correction(case)
        assert "(no correction used)" in fmt.correction(case)
