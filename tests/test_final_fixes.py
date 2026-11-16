"""M4 final changes (owner, after round 3): change lists listed apart, no wording rule, 0.5x."""

import pytest
from agent_helpers import toy_dirs

from happy_toad.agent.checker import check_report, find_numbers
from happy_toad.agent.report import Report
from happy_toad.agent.tools import TOOLS, ToolRunner

# --- (1) change lists are listed apart from the versions -------------------------------------


def test_list_input_versions_returns_change_lists_separately(tmp_path):
    from happy_toad.data.files import write_inputs

    write_inputs(42, tmp_path)
    result = ToolRunner(tmp_path, tmp_path / "runs").call("list_input_versions", "{}")
    assert result == {"versions": ["v1", "v2"], "change_lists": ["changes_v1_to_v2"]}


def test_the_tool_says_a_change_list_is_not_a_version():
    spec = next(t["function"] for t in TOOLS if t["function"]["name"] == "list_input_versions")
    assert "change_lists" in spec["description"] and "not a version" in spec["description"]


# --- (3) a number glued to a letter is skipped whole -----------------------------------------


@pytest.mark.parametrize(
    "text, numbers",
    [
        ("a market floor of 0.5x fair share", []),
        ("about 1,284x more", []),
        ("spend 485.59.", ["485.59"]),
        ("spend 1,284.34, relief 12.5%; then 3.", ["1,284.34", "12.5%", "3"]),
        ("values 1,2,3", ["1", "2", "3"]),  # punctuation chains stay checked
        ("spend 485.59.12", ["485.59"]),
        ("a rate of 12.5%x", []),
    ],
)
def test_a_number_touching_a_letter_is_skipped_not_cut_short(text, numbers):
    assert [t for t, _ in find_numbers(text)] == numbers


def test_case_13s_summary_no_longer_reads_a_zero(tmp_path):
    from happy_toad.services.request import SolveRequest
    from happy_toad.services.run import run_request

    inputs, runs = toy_dirs(tmp_path)
    run = run_request(
        SolveRequest(input_version="test", budget=12.0, market_floor_mult=0.5), inputs, runs
    )
    claim = dict(metric="status", value=run.result.status, run_id=run.run_id)
    r = Report(summary="I applied a market floor of 0.5x fair share.", claims=[claim])
    assert check_report(r, runs, inputs, [run.run_id]).ok
