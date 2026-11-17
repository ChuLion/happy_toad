"""M5 5.4: the explain_revision tool and what the model sees (docs/SPEC.md, M5)."""

import json

from revision_helpers import BUDGET, toy_dirs

from happy_toad.agent.tools import TOOLS, ToolRunner
from happy_toad.reasons import ReasonCode
from happy_toad.services.runs import read_run


def tool(name):
    return next(t for t in TOOLS if t["function"]["name"] == name)


def explain(tmp_path, **args):
    inputs, runs = toy_dirs(tmp_path)
    return ToolRunner(inputs, runs).call("explain_revision", json.dumps(args)), runs


def test_the_tool_is_listed_and_states_the_order_and_the_rules():
    description = tool("explain_revision")["function"]["description"]
    assert "costs -> offloads -> triggers -> sectors" in description
    assert "entity" in description and "percent" in description and "budget" in description
    properties = tool("explain_revision")["function"]["parameters"]["properties"]
    assert set(properties) == {"budget", "plan_of_record", "refreshed_forecast"}


def test_the_view_shows_inputs_decisions_and_ordered_steps(tmp_path):
    view, _ = explain(tmp_path, budget=BUDGET, plan_of_record="a", refreshed_forecast="b")
    assert view["outcome"] == "completed"
    rev = view["revision"]
    assert rev["order_text"] == "costs -> offloads -> triggers -> sectors"
    assert rev["inputs"]["sectors_added"] == ["s3"] and rev["inputs"]["costs_changed"] == ["A"]
    assert rev["decisions"]["only_in_a"] == ["A"] and rev["decisions"]["only_in_b"] == ["B"]
    assert [s["name"] for s in rev["steps"]] == [
        "plan_of_record", "costs", "offloads", "triggers", "sectors",
    ]  # fmt: skip
    assert all("content_hash" not in s and "applied" not in s for s in rev["steps"])
    assert rev["complete"] is True and rev["total_relief"] == -1
    assert (rev["n_sectors_new"], rev["n_resolved_new"]) == (1, 1)


def test_a_missing_budget_is_a_schema_rejection_with_a_record(tmp_path):
    view, runs = explain(tmp_path, plan_of_record="a", refreshed_forecast="b")
    assert view["outcome"] == "rejected"
    assert [r["code"] for r in view["reasons"]] == [ReasonCode.SCHEMA_INVALID]
    assert "budget" in view["reasons"][0]["message"]
    assert read_run(view["run_id"], runs).kind == "revision"


def test_unknown_arguments_are_rejected(tmp_path):
    view, _ = explain(tmp_path, budget=BUDGET, force_in=["A"])
    assert [r["code"] for r in view["reasons"]] == [ReasonCode.SCHEMA_INVALID]


def test_the_order_is_returned_as_data(tmp_path):
    view, _ = explain(tmp_path, budget=BUDGET, plan_of_record="a", refreshed_forecast="b")
    assert view["revision"]["order"] == ["costs", "offloads", "triggers", "sectors"]
