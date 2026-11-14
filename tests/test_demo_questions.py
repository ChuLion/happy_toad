"""The three demo questions end to end with a scripted fake client on generated v1, seed 42.

The live run of each question is the acceptance check (needs OPENROUTER_API_KEY); these tests pin
the tool path, the numbers and that every claim passes the checker.
"""

import json

import pytest
from agent_helpers import call, turn

from happy_toad.agent.config import DEMO
from happy_toad.agent.demo import QUESTIONS
from happy_toad.agent.loop import ask
from happy_toad.data.generator import make_v1
from happy_toad.data.loader import save_input_set
from happy_toad.services.runs import read_run


@pytest.fixture(scope="module")
def dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo")
    (root / "inputs").mkdir()
    save_input_set(make_v1(seed=42), root / "inputs" / "v1.json")
    return dict(
        inputs_dir=root / "inputs", runs_dir=root / "runs", transcripts_dir=root / "transcripts"
    )


class Demo:
    """Plays a fixed tool path, then a report built from the stored runs it created."""

    def __init__(self, runs_dir, steps, report) -> None:
        self.runs_dir, self.steps, self.report = runs_dir, steps, report
        self.run_ids: list[str] = []

    def complete(self, messages, tools):
        last = json.loads(messages[-1]["content"]) if messages[-1]["role"] == "tool" else {}
        if "run_id" in last and last["run_id"] not in self.run_ids:
            self.run_ids.append(last["run_id"])
        if self.steps:
            name, args = self.steps.pop(0)
            if name == "compare_runs":
                args = dict(run_id_a=self.run_ids[0], run_id_b=self.run_ids[1])
            return turn(call(name, **args))
        records = [read_run(i, self.runs_dir) for i in self.run_ids]
        return turn(call("submit_report", **self.report(records)))


def claims(record, **metrics):
    units = dict(
        spend="cost_units", weighted_relief="need_units", n_selected="count",
        n_resolved="count", required_minimum_budget="cost_units",
    )  # fmt: skip
    return [
        dict(metric=m, value=v, unit=units[m], run_id=record.run_id, entity="plan")
        for m, v in metrics.items()
    ]


def run_step(budget, **extra):
    return ("run_scenario", dict(input_version="v1", budget=budget, **extra))


def test_demo_a_budget_comparison(dirs) -> None:
    def report(records):
        lo, hi = records
        parts, listed = [], []
        for record in (lo, hi):
            r = record.result
            values = dict(spend=round(r.spend, 2), weighted_relief=round(r.objective, 2))
            values["n_resolved"] = r.resolved
            listed += claims(record, **values)
            parts.append(
                f"At a budget of {record.request['budget']:.0f}, under the modeled objective and "
                f"constraints: spend {values['spend']:.2f}, weighted relief "
                f"{values['weighted_relief']:.2f}, {r.resolved} sectors resolved."
            )
        return dict(summary=" ".join(parts), claims=listed)

    steps = [
        run_step(800),
        run_step(1500),
        ("compare_runs", {}),
    ]
    client = Demo(dirs["runs_dir"], steps, report)
    t = ask(QUESTIONS["a"], client, DEMO, **dirs)
    assert t.status == "checked"
    lo, hi = (read_run(i, dirs["runs_dir"]) for i in client.run_ids)
    assert (round(lo.result.spend, 2), round(lo.result.objective, 2)) == (485.59, 1284.34)
    assert (round(hi.result.spend, 2), round(hi.result.objective, 2)) == (1186.32, 1979.11)
    assert (len(lo.result.selected), len(hi.result.selected)) == (14, 27)


def test_demo_b_forced_against_unforced(dirs) -> None:
    def report(records):
        free, forced = records
        listed, parts = [], []
        for label, record in (("without forcing", free), ("with C033 and C024 forced in", forced)):
            r = record.result
            values = dict(spend=round(r.spend, 2), weighted_relief=round(r.objective, 2))
            listed += claims(record, **values)
            parts.append(
                f"At a budget of 1000, {label}: spend {values['spend']:.2f}, "
                f"weighted relief {values['weighted_relief']:.2f}."
            )
        return dict(summary=" ".join(parts), claims=listed)

    steps = [run_step(1000), run_step(1000, force_in=["C033", "C024"]), ("compare_runs", {})]
    client = Demo(dirs["runs_dir"], steps, report)
    t = ask(QUESTIONS["b"], client, DEMO, **dirs)
    assert t.status == "checked"
    free, forced = (read_run(i, dirs["runs_dir"]) for i in client.run_ids)
    assert (round(free.result.spend, 2), round(free.result.objective, 2)) == (688.10, 1573.57)
    assert (round(forced.result.spend, 2), round(forced.result.objective, 2)) == (687.88, 1329.87)
    assert {"C033", "C024"} <= set(forced.result.selected)
    assert not {"C033", "C024"} & set(free.result.selected)


def test_demo_c_infeasible_request_states_the_minimum_budget(dirs) -> None:
    def report(records):
        (record,) = records
        return dict(
            summary="At a budget of 600 this request cannot be met: forcing in C033, C034 and "
            "C024 costs more than the budget leaves after must-fund. The budget must be at "
            "least 697.01.",
            claims=claims(record, required_minimum_budget=697.01),
        )

    steps = [run_step(600, force_in=["C033", "C034", "C024"])]
    client = Demo(dirs["runs_dir"], steps, report)
    t = ask(QUESTIONS["c"], client, DEMO, **dirs)
    assert t.status == "checked"
    record = read_run(client.run_ids[0], dirs["runs_dir"])
    assert record.outcome == "rejected"
    assert record.reasons[0].code == "FORCED_COST_EXCEEDS_BUDGET"
    assert round(record.required_minimum_budget, 2) == 697.01
    assert record.result is None
