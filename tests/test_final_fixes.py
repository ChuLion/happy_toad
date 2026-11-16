"""M4 final changes (owner, after round 3): change lists listed apart, no wording rule, 0.5x."""

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
