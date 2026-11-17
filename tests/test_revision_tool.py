"""M5 5.4: the explain_revision tool and what the model sees (docs/SPEC.md, M5)."""

import json

from agent_helpers import call, turn
from helpers import make_set
from revision_helpers import BUDGET, toy_dirs

from happy_toad.agent.config import SMOKE
from happy_toad.agent.loop import ask
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


class RevisionThenReport:
    """Calls explain_revision, then submits the report that `build` makes from its result."""

    def __init__(self, build):
        self.build, self.called = build, False

    def complete(self, messages, tools):
        if not self.called:
            self.called = True
            return turn(call("explain_revision", budget=BUDGET, plan_of_record="a",
                             refreshed_forecast="b"))  # fmt: skip
        return turn(call("submit_report", **self.build(json.loads(messages[-1]["content"]))))


def ask_toy(tmp_path, build, a=None, b=None):
    inputs, runs = toy_dirs(tmp_path, a, b)
    client = RevisionThenReport(build)
    return ask("Why?", client, SMOKE, inputs_dir=inputs, runs_dir=runs,
               transcripts_dir=tmp_path / "t")  # fmt: skip


def test_claims_on_the_two_end_runs_are_known_without_get_run(tmp_path):
    def build(view):
        rev = view["revision"]
        a, b = rev["run_id_a"], rev["run_id_b"]
        return dict(
            summary="Weighted relief fell by 1.00, under the modeled objective and constraints.",
            claims=[dict(metric="diff_weighted_relief", value=-1.0, run_id=a, run_id_b=b)],
        )

    t = ask_toy(tmp_path, build)
    assert t.status == "checked", t.turns[-1].tool_calls[-1]["result"]


def test_candidates_listed_as_changed_inputs_are_traced(tmp_path):
    """The toy candidates are A and B; a C### id needs a pair with generator-style ids."""
    a = make_set([("s1", 10)], [("C001", 6), ("C002", 6)], [("C001", "s1", 10), ("C002", "s1", 8)])
    b = make_set([("s1", 10)], [("C001", 6), ("C002", 5)], [("C001", "s1", 10), ("C002", "s1", 8)])

    def build(view):
        claims = [dict(metric="n_costs_changed", value=1, run_id=view["run_id"])]
        return dict(summary="1 cost changed: C002.", claims=claims)

    t = ask_toy(
        tmp_path,
        build,
        a.model_copy(update={"version_id": "a"}),
        b.model_copy(update={"version_id": "b"}),
    )
    assert t.status == "checked", t.turns[-1].tool_calls[-1]["result"]
