"""The compact `ask` renderer, on the saved live transcript of demo question (c)."""

from pathlib import Path

from rich.console import Console

from happy_toad.agent.checker import CheckResult, ClaimCheck
from happy_toad.agent.report import Report
from happy_toad.agent.transcript import Transcript
from happy_toad.cli import compact_outcome, compact_tool_call, exit_code, verdict

FIXTURE = Path(__file__).parent / "fixtures" / "transcript_demo_c.json"


def render(t: Transcript) -> str:
    console = Console(record=True, width=120, color_system=None)
    for turn in t.turns:
        for call in turn.tool_calls:
            compact_tool_call(call, console)
    compact_outcome(t, console)
    return console.export_text()


def demo_c() -> Transcript:
    return Transcript.model_validate_json(FIXTURE.read_text())


def test_each_tool_call_is_one_line_without_json() -> None:
    out = render(demo_c())
    assert "{" not in out and "}" not in out
    run_lines = [line for line in out.splitlines() if line.startswith("run_scenario")]
    assert run_lines == [
        "run_scenario v1, budget 600, force in C033, C034, C024 -> rejected "
        "FORCED_COST_EXCEEDS_BUDGET, minimum budget 697.01 [20261114T210203-96d94d4c]"
    ]
    submits = [line for line in out.splitlines() if line.startswith("submit_report")]
    assert submits == [
        "submit_report 2 claims -> refused (2 problems)",
        "submit_report 2 claims -> accepted",
    ]


def test_accepted_report_is_a_checked_panel_with_counts_and_correction() -> None:
    out = render(demo_c())
    assert "CHECKED" in out and "NOT CHECKED" not in out
    assert "at least 697.01" in out
    assert "First report refused, then corrected: unmatched numbers 297.57, 311.44" in out
    assert "2 claims, 2 numbers matched against stored runs, 0 mismatches" in out


def test_footer_has_model_provider_turns_cost_and_seconds() -> None:
    last = render(demo_c()).strip().splitlines()[-1]
    assert last == "deepseek/deepseek-v4-flash-0731 | BaseTen | 3 turns | $0.0010 | 3.8 s"


def test_unverified_report_is_not_checked_and_lists_mismatches() -> None:
    t = demo_c()
    first = t.checks[0]
    t = t.model_copy(update={"status": "unverified", "checks": [first, first]})
    out = render(t)
    assert "NOT CHECKED" in out
    assert "2 claims, 3 numbers matched against stored runs, 2 mismatches" in out
    assert "number 297.57 in the summary: does not match" in out
    assert "First report refused" not in out


def test_a_run_without_a_report_prints_its_status() -> None:
    t = demo_c().model_copy(update={"status": "step_cap", "report": None})
    out = render(t)
    assert "Status: step_cap" in out and "CHECKED" not in out


def no_figures(t: Transcript) -> Transcript:
    """Demo (c) as if the final report had asked a clarifying question: no claims, no numbers."""
    report = Report(summary="Which input version do you mean?", claims=[])
    return t.model_copy(
        update={"report": report, "checks": [t.checks[0], CheckResult(claims=[], numbers=[])]}
    )


def test_a_report_with_no_claims_and_no_numbers_is_not_shown_as_checked() -> None:
    out = render(no_figures(demo_c()))
    assert "NO NUMBERS TO CHECK" in out and "No checkable figures in this answer" in out
    assert "CHECKED" not in out
    assert "numbers matched" not in out


def test_one_verified_claim_keeps_the_checked_badge() -> None:
    t = demo_c()
    claim = t.report.claims[0]
    one = t.model_copy(
        update={
            "report": Report(summary="The run was rejected.", claims=[claim]),
            "checks": [
                t.checks[0],
                CheckResult(
                    claims=[ClaimCheck(claim=claim, ok=True, message="matches")], numbers=[]
                ),
            ],
        }
    )
    out = render(one)
    assert "CHECKED" in out and "NO NUMBERS TO CHECK" not in out
    assert "1 claims, 0 numbers matched against stored runs, 0 mismatches" in out


def test_one_verdict_per_transcript_and_its_exit_code() -> None:
    t = demo_c()
    cases = {
        "checked": (t, "CHECKED", 0),
        "no figures": (no_figures(t), "NO NUMBERS TO CHECK", 3),
        "unverified": (t.model_copy(update={"status": "unverified"}), "NOT CHECKED", 1),
        "step cap": (t.model_copy(update={"status": "step_cap"}), None, 1),
        "api error": (t.model_copy(update={"status": "api_error", "report": None}), None, 1),
    }
    for name, (case, label, code) in cases.items():
        assert (verdict(case), exit_code(case)) == (label, code), name


def test_one_mismatch_is_singular() -> None:
    t = demo_c()
    first = t.checks[0]
    one_bad = [n for n in first.numbers if not n.ok][:1]
    one = first.model_copy(update={"numbers": one_bad})
    out = render(t.model_copy(update={"status": "unverified", "checks": [one, one]}))
    assert "0 numbers matched against stored runs, 1 mismatch\n" in out
