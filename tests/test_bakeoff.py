"""The bake-off runner: one row per model and question (SPEC, M3 model selection)."""

import pytest
from agent_helpers import FakeClient, call, toy_dirs, turn

from happy_toad.agent.bakeoff import run_bakeoff, table
from happy_toad.agent.config import Profile

PROFILES = {"one": Profile("one", "fake/one"), "two": Profile("two", "fake/two")}
QUESTIONS = {"q1": "Which budget?", "q2": "What about 12?"}


@pytest.fixture
def dirs(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    return dict(inputs_dir=inputs, runs_dir=runs, transcripts_dir=tmp_path / "t")


def test_one_row_per_model_and_question_with_the_measured_fields(dirs) -> None:
    def make_client(profile):
        script = [
            turn(call("run_scenario", input_version="test", budget=12, bogus=1)),
            turn(call("submit_report", summary="No numbers.", claims=[]), provider="HostX"),
        ]
        return FakeClient(script)

    prices = {"fake/one": {"prompt": "0.1", "completion": "0.2"}}
    rows = run_bakeoff(PROFILES, make_client, QUESTIONS, prices=prices, **dirs)
    assert [(r.profile, r.question) for r in rows] == [
        ("one", "q1"), ("one", "q2"), ("two", "q1"), ("two", "q2"),
    ]  # fmt: skip
    row = rows[0]
    assert row.model == "fake/one" and row.status == "checked" and row.turns == 2
    assert row.tools == ["run_scenario", "submit_report"]
    assert row.schema_errors == 1 and row.check_failures == []
    assert (row.prompt_tokens, row.completion_tokens) == (20, 10)
    assert row.providers == ["FakeProvider", "HostX"] and row.seconds >= 0
    assert row.price == {"prompt": "0.1", "completion": "0.2"} and rows[2].price is None


def test_a_failing_report_and_a_broken_client_are_rows_not_crashes(dirs) -> None:
    bad = dict(
        metric="spend",
        value=1.0,
        unit="cost_units",
        run_id="20260101T000000-deadbeef",
        entity="plan",
    )

    def make_client(profile):
        if profile.name == "two":
            raise RuntimeError("no key")
        return FakeClient([turn(call("submit_report", summary="x", claims=[bad]))] * 2)

    rows = run_bakeoff(PROFILES, make_client, {"q1": "q"}, **dirs)
    assert rows[0].status == "unverified" and rows[0].check_failures
    assert rows[1].status == "error" and "no key" in rows[1].error


def test_table_has_a_line_per_row() -> None:
    from happy_toad.agent.bakeoff import Row

    row = Row(profile="one", model="fake/one", question="q1", status="checked", tools=["a"],
              schema_errors=0, check_failures=[], turns=1, prompt_tokens=1, completion_tokens=1,
              cost=None, providers=["X"], seconds=1.0, price=None, error=None)  # fmt: skip
    text = table([row])
    assert "fake/one" in text and "q1" in text and "checked" in text


def make_ok(profile):
    return FakeClient([turn(call("submit_report", summary="No numbers.", claims=[]),
                            provider="Crusoe", quantization="bf16")])  # fmt: skip


def test_repeats_run_each_cell_n_times_and_number_them(dirs) -> None:
    rows = run_bakeoff({"one": PROFILES["one"]}, make_ok, QUESTIONS, repeats=3, **dirs)
    assert [(r.question, r.repeat) for r in rows] == [
        ("q1", 1), ("q1", 2), ("q1", 3), ("q2", 1), ("q2", 2), ("q2", 3),
    ]  # fmt: skip
    assert rows[0].quantizations == ["bf16"]


def test_refusals_count_rejected_reports(dirs) -> None:
    bad = dict(metric="spend", value=1.0, unit="cost_units",
               run_id="20260101T000000-deadbeef", entity="plan")  # fmt: skip
    good = turn(call("submit_report", summary="No numbers.", claims=[]))
    client = FakeClient([turn(call("submit_report", summary="x", claims=[bad])), good])
    rows = run_bakeoff({"one": PROFILES["one"]}, lambda p: client, {"q1": "q"}, **dirs)
    assert rows[0].status == "checked" and rows[0].refusals == 1


def test_stop_on_error_ends_the_run_at_the_first_error_row(dirs) -> None:
    def make_client(profile):
        raise RuntimeError("boom")

    rows = run_bakeoff(PROFILES, make_client, QUESTIONS, repeats=5, stop_on_error=True, **dirs)
    assert len(rows) == 1 and rows[0].status == "error"


def test_on_row_sees_each_row_as_it_finishes(dirs) -> None:
    seen = []
    run_bakeoff(
        {"one": PROFILES["one"]}, make_ok, {"q1": "q"}, repeats=2, on_row=seen.append, **dirs
    )
    assert [r.repeat for r in seen] == [1, 2]


def test_summary_is_one_line_per_model_and_question(dirs) -> None:
    from happy_toad.agent.bakeoff import summary

    rows = run_bakeoff({"one": PROFILES["one"]}, make_ok, {"q1": "q"}, repeats=2, **dirs)
    text = summary(rows)
    assert (
        "fake/one" in text
        and "q1" in text
        and "2/2" in text
        and "Crusoe" in text
        and "bf16" in text
    )


def test_an_api_error_is_a_row_and_does_not_stop_the_batch(dirs) -> None:
    from happy_toad.agent.client import ProviderError

    class Rejects:
        def complete(self, messages, tools):
            raise ProviderError(503, "overloaded")

    rows = run_bakeoff(
        {"one": PROFILES["one"]},
        lambda p: Rejects(),
        {"q1": "q"},
        repeats=3,
        stop_on_error=True,
        **dirs,
    )
    assert [r.status for r in rows] == ["api_error"] * 3 and rows[0].api_status == 503


def test_the_same_400_at_the_same_step_stops_the_batch(dirs) -> None:
    from happy_toad.agent.client import ProviderError

    class Rejects:
        def complete(self, messages, tools):
            raise ProviderError(400, "bad")

    rows = run_bakeoff(
        {"one": PROFILES["one"]},
        lambda p: Rejects(),
        {"q1": "q"},
        repeats=5,
        stop_on_error=True,
        **dirs,
    )
    assert len(rows) == 2


def test_summary_counts_api_errors_and_coercions_apart_from_checker_failures(dirs) -> None:
    from happy_toad.agent.bakeoff import summary
    from happy_toad.agent.client import ProviderError

    class Rejects:
        def complete(self, messages, tools):
            raise ProviderError(503, "overloaded")

    rows = run_bakeoff(
        {"one": PROFILES["one"]}, lambda p: Rejects(), {"q1": "q"}, repeats=2, **dirs
    )
    rows[0].coercions = 4
    text = summary(rows)
    assert "api_errors 2" in text and "coercions 4" in text and "failures: none" in text


def test_provenance_records_commit_prompt_hash_and_frozen_files() -> None:
    import hashlib
    import json

    from happy_toad.agent.bakeoff import provenance
    from happy_toad.agent.prompt import SYSTEM_PROMPT
    from happy_toad.agent.tools import TOOLS

    info = provenance()
    text = SYSTEM_PROMPT + json.dumps(TOOLS, sort_keys=True)  # M4: prompt plus tool definitions
    assert info["prompt_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert len(info["git_sha"]) == 40 and isinstance(info["git_dirty"], bool)
    assert set(info["frozen_files"]) == {
        "checker.py",
        "report.py",
        "tools.py",
        "prompt.py",
        "loop.py",
    }


def test_malformed_calls_are_counted_per_row_and_in_the_summary(dirs) -> None:
    from agent_helpers import FakeClient as FC

    from happy_toad.agent.bakeoff import summary
    from happy_toad.agent.client import ToolCall

    def make_client(profile):
        glued = ToolCall("c1", "run_scenario", '{"budget": 1}{"budget": 2}')
        return FC([turn(glued), turn(call("submit_report", summary="No numbers.", claims=[]))])

    rows = run_bakeoff({"one": PROFILES["one"]}, make_client, {"q1": "q"}, repeats=2, **dirs)
    assert [r.malformed_calls for r in rows] == [1, 1]
    assert "malformed 2" in summary(rows)


def test_summary_ends_with_totals_per_model(dirs) -> None:
    from happy_toad.agent.bakeoff import summary

    rows = run_bakeoff(PROFILES, make_ok, QUESTIONS, repeats=2, **dirs)
    rows[0].coercions, rows[1].malformed_calls = 3, 2
    lines = summary(rows).splitlines()
    assert lines[-2].startswith(
        "TOTAL fake/one | runs 4 | checked 4 | api_errors 0 | coercions 3 | malformed 2"
    )
    assert lines[-1].startswith(
        "TOTAL fake/two | runs 4 | checked 4 | api_errors 0 | coercions 0 | malformed 0"
    )


def test_rows_carry_defaults_reasoning_tokens_and_an_unequal_terms_note(dirs) -> None:
    from happy_toad.agent.bakeoff import summary
    from happy_toad.agent.client import Completion

    effort = Profile("glm", "fake/glm", reasoning_effort="low")
    claims = [dict(metric="n_selected", value=2, run_id="20260101T000000-deadbeef", entity="X")]

    def make_client(profile):
        sub = call("submit_report", summary="x", claims=claims)
        return FakeClient(
            [Completion(content=None, tool_calls=[sub], completion_tokens=9, reasoning_tokens=7)]
            * 2
        )

    rows = run_bakeoff({"glm": effort}, make_client, {"q1": "q"}, **dirs)
    assert rows[0].defaults == 4 and rows[0].reasoning_tokens == 14
    assert rows[0].note == "reasoning effort low; not equal terms"
    text = summary(rows)
    assert (
        "defaults 4" in text and "reasoning tokens 14.0 mean" in text and "not equal terms" in text
    )


def test_the_final_failing_report_of_an_unverified_run_is_not_a_refusal(dirs) -> None:
    """A refusal is one the model had to correct; nothing followed the last one."""
    bad = turn(call("submit_report", summary="Is 500 enough?", claims=[]))
    client = FakeClient([bad, bad])
    rows = run_bakeoff({"one": PROFILES["one"]}, lambda p: client, {"q1": "q"}, **dirs)
    assert rows[0].status == "unverified" and rows[0].refusals == 1
