"""The agent loop with a scripted fake client (SPEC, M3 decisions 3, 7, 8, 11)."""

import json

import pytest
from agent_helpers import FakeClient, call, toy_dirs, turn

from happy_toad.agent.config import DEMO, MAX_STEPS, SMOKE
from happy_toad.agent.loop import ask
from happy_toad.agent.tools import TOOLS
from happy_toad.reasons import ReasonCode


@pytest.fixture
def dirs(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    return dict(inputs_dir=inputs, runs_dir=runs, transcripts_dir=tmp_path / "transcripts")


def run_ids(dirs):
    return sorted(p.stem for p in dirs["runs_dir"].glob("*.json"))


def claims_for(run_id, **values):
    units = dict(spend="cost_units", weighted_relief="need_units", n_selected="count")
    return [
        dict(metric=m, value=v, unit=units[m], run_id=run_id, entity="plan")
        for m, v in values.items()
    ]


def tool_result(client, index=-1):
    """The content of the last tool message the model saw before turn `index`."""
    return json.loads([m for m in client.seen[index] if m["role"] == "tool"][-1]["content"])


def test_five_tools_are_offered_with_descriptions() -> None:
    names = [t["function"]["name"] for t in TOOLS]
    assert names == [
        "list_input_versions", "run_scenario", "get_run", "compare_runs", "submit_report",
    ]  # fmt: skip
    assert all(t["function"]["description"] for t in TOOLS)


def test_profiles_pin_models_and_routing() -> None:
    assert MAX_STEPS == 10
    assert SMOKE.model.endswith(":free") and SMOKE.allow_fallbacks
    assert DEMO.provider_order and not DEMO.allow_fallbacks


def test_question_to_checked_report_and_transcript(dirs) -> None:
    client = FakeClient(
        [
            turn(call("list_input_versions")),
            turn(call("run_scenario", input_version="test", budget=12, label="q")),
            turn(call("submit_report", summary="placeholder", claims=[])),  # replaced below
        ]
    )
    # the report needs the real run id, so build the last turn lazily from the first run
    first = client.script.pop()
    real = {}

    def complete(messages, tools):
        client.seen.append([dict(m) for m in messages])
        nxt = client.script.pop(0) if client.script else first
        if nxt is first:
            run_id = tool_result(client)["run_id"]
            real["id"] = run_id
            args = dict(
                summary="At a budget of 12 the plan funds 2 candidates with spend 11.00.",
                claims=claims_for(run_id, spend=11.0, n_selected=2),
            )
            return turn(call("submit_report", **args))
        return nxt

    client.complete = complete
    t = ask("Plan on the test version at budget 12?", client, SMOKE, **dirs)
    assert t.status == "checked" and t.checks[-1].ok
    assert [c["name"] for turn_ in t.turns for c in turn_.tool_calls] == [
        "list_input_versions", "run_scenario", "submit_report",
    ]  # fmt: skip
    assert run_ids(dirs) == [real["id"]]
    saved = json.loads(next(dirs["transcripts_dir"].glob("*.json")).read_text())
    assert saved["question"].startswith("Plan on") and saved["model"] == SMOKE.model
    assert saved["total_tokens"] == {"prompt": 30, "completion": 15}
    assert saved["cost"] == pytest.approx(0.003) and saved["status"] == "checked"
    assert saved["turns"][0]["provider"] == "FakeProvider" and saved["elapsed_seconds"] >= 0


def scripted_report(dirs, claims_fn, summary):
    """A client: run once, then submit what claims_fn(run_id) says (resubmitting if asked)."""
    state = {}

    class Client:
        seen: list = []

        def complete(self, messages, tools):
            self.seen.append([dict(m) for m in messages])
            if not state:
                state["n"] = 0
                return turn(call("run_scenario", input_version="test", budget=12))
            run_id = tool_result(self)["run_id"] if "id" not in state else state["id"]
            state["id"] = run_id
            state["n"] += 1
            return turn(
                call(
                    "submit_report",
                    summary=summary(state["n"]),
                    claims=claims_fn(run_id, state["n"]),
                )
            )

    return Client()


def test_a_wrong_claim_is_sent_back_once_and_a_corrected_report_passes(dirs) -> None:
    client = scripted_report(
        dirs,
        lambda rid, n: claims_for(rid, spend=99.0 if n == 1 else 11.0),
        lambda n: "Spend 99.00" if n == 1 else "Spend 11.00",
    )
    t = ask("q", client, SMOKE, **dirs)
    assert t.status == "checked" and [c.ok for c in t.checks] == [False, True]
    assert "spend" in json.dumps(tool_result(client))  # the error text reached the model


def test_a_second_failing_report_is_flagged_unverified(dirs) -> None:
    client = scripted_report(
        dirs, lambda rid, n: claims_for(rid, spend=99.0), lambda n: "Spend 99.00"
    )
    t = ask("q", client, SMOKE, **dirs)
    assert t.status == "unverified" and [c.ok for c in t.checks] == [False, False]
    assert len(t.turns) == 3


def test_a_schema_invalid_report_is_returned_and_does_not_use_the_correction(dirs) -> None:
    client = FakeClient(
        [
            turn(call("submit_report", summary="x", claims=[{"metric": "profit"}])),
            turn(call("submit_report", summary="I can only report on runs.", claims=[])),
        ]
    )
    t = ask("q", client, SMOKE, **dirs)
    assert t.status == "checked" and len(t.turns) == 2 and len(t.checks) == 1
    assert "metric" in json.dumps(tool_result(client, 1))


def test_step_cap_is_a_flagged_failure(dirs) -> None:
    client = FakeClient([turn(call("list_input_versions")) for _ in range(MAX_STEPS)])
    t = ask("q", client, SMOKE, **dirs)
    assert t.status == "step_cap" and len(t.turns) == MAX_STEPS and client.script == []
    assert (
        json.loads(next(dirs["transcripts_dir"].glob("*.json")).read_text())["status"] == "step_cap"
    )


def test_unknown_tool_is_an_error_result_and_nothing_executes(dirs) -> None:
    client = FakeClient(
        [
            turn(call("run_python", code="import os")),
            turn(call("submit_report", summary="No numbers.", claims=[])),
        ]
    )
    t = ask("q", client, SMOKE, **dirs)
    assert "unknown tool" in json.dumps(tool_result(client, 1)) and t.status == "checked"
    assert run_ids(dirs) == []


def test_a_plain_text_reply_is_nudged_to_submit_a_report(dirs) -> None:
    client = FakeClient(
        [
            turn(content="Which budget?"),
            turn(call("submit_report", summary="Which budget do you want?", claims=[])),
        ]
    )
    t = ask("q", client, SMOKE, **dirs)
    assert t.status == "checked"
    assert "submit_report" in client.seen[1][-1]["content"]


def test_schema_invalid_run_scenario_becomes_a_rejected_run_record(dirs) -> None:
    client = FakeClient(
        [
            turn(call("run_scenario", input_version="test", budget=12, bogus=1)),
            turn(call("submit_report", summary="No numbers.", claims=[])),
        ]
    )
    ask("q", client, SMOKE, **dirs)
    (run_id,) = run_ids(dirs)
    record = json.loads((dirs["runs_dir"] / f"{run_id}.json").read_text())
    assert record["outcome"] == "rejected" and record["result"] is None
    assert record["reasons"][0]["code"] == ReasonCode.SCHEMA_INVALID
    assert "bogus" in record["reasons"][0]["message"]
    assert record["request"]["bogus"] == 1 and len(record["request_hash"]) == 64
    assert tool_result(client, 1)["run_id"] == run_id


def test_get_run_and_compare_runs_work_through_the_tools(dirs) -> None:
    state = {}

    class Client:
        seen: list = []

        def complete(self, messages, tools):
            self.seen.append([dict(m) for m in messages])
            n = len(self.seen)
            if n == 1:
                return turn(call("run_scenario", input_version="test", budget=12))
            if n == 2:
                state["a"] = tool_result(self)["run_id"]
                return turn(call("run_scenario", input_version="test", budget=12, force_in=["Y1"]))
            if n == 3:
                state["b"] = tool_result(self)["run_id"]
                return turn(call("get_run", run_id=state["a"]))
            if n == 4:
                return turn(call("compare_runs", run_id_a=state["a"], run_id_b=state["b"]))
            return turn(call("submit_report", summary="No numbers.", claims=[]))

    client = Client()
    t = ask("q", client, SMOKE, **dirs)
    assert t.status == "checked"
    comparison = json.loads([m for m in client.seen[4] if m["role"] == "tool"][-1]["content"])
    assert (
        comparison["only_in_b"] == ["Y1"] or comparison["only_in_a"] == ["X1", "X2"] or comparison
    )
    got = json.loads([m for m in client.seen[3] if m["role"] == "tool"][-1]["content"])
    assert got["run_id"] == state["a"] and got["result"]["status"] == "Optimal"


def test_gate_rejection_tells_the_model_the_minimum_budget(dirs) -> None:
    client = FakeClient(
        [
            turn(
                call("run_scenario", input_version="test", budget=12, force_in=["X1", "X2", "Y1"])
            ),
            turn(call("submit_report", summary="No numbers.", claims=[])),
        ]
    )
    ask("q", client, SMOKE, **dirs)
    seen = tool_result(client, 1)
    assert seen["outcome"] == "rejected" and seen["required_minimum_budget"] == pytest.approx(17)
    assert seen["reasons"][0]["code"] == "FORCED_COST_EXCEEDS_BUDGET"
    assert "at least 17.00" not in json.dumps(seen)  # the model states it; the number is in data


def test_solver_infeasible_result_carries_the_minimum_budget_in_the_record(dirs) -> None:
    from happy_toad.services.request import SolveRequest
    from happy_toad.services.run import run_request

    request = SolveRequest(input_version="test", budget=12, market_floor_mult=3.0)
    record = run_request(request, dirs["inputs_dir"], dirs["runs_dir"])
    assert record.result.status == "Infeasible" and record.result.cause is not None
    assert record.required_minimum_budget == record.result.required_minimum_budget
    assert record.required_minimum_budget > 12


def test_the_api_key_and_system_prompt_rules(dirs, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-123")
    client = FakeClient([turn(call("submit_report", summary="Which budget?", claims=[]))])
    ask("q", client, SMOKE, **dirs)
    assert "sk-secret-123" not in next(dirs["transcripts_dir"].glob("*.json")).read_text()
    system = client.seen[0][0]
    assert (
        system["role"] == "system"
        and "under the modeled objective and constraints" in system["content"]
    )
    assert "displayed precision" in system["content"]


def test_a_client_failure_is_recorded_as_an_error_transcript(dirs) -> None:
    class Broken:
        def complete(self, messages, tools):
            raise RuntimeError("network down")

    t = ask("q", Broken(), SMOKE, **dirs)
    assert t.status == "error" and "network down" in t.error
    assert next(dirs["transcripts_dir"].glob("*.json")).exists()
