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
