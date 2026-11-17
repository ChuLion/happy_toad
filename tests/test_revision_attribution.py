"""M5 5.2 and 5.3: step inputs, ordered attribution and the revision record (docs/SPEC.md, M5)."""

import pytest
from helpers import make_set
from revision_helpers import BUDGET, toy_a, toy_b, toy_dirs

from happy_toad.constants import BASE_YEAR
from happy_toad.data.files import write_inputs
from happy_toad.data.loader import load_input_set
from happy_toad.reasons import ReasonCode
from happy_toad.services import revision as revision_module
from happy_toad.services.revision import ORDER, RevisionRequest, apply_kinds, run_revision
from happy_toad.services.runs import read_run

# --- step construction -------------------------------------------------------------------------


def test_the_order_is_costs_offloads_triggers_sectors():
    assert ORDER == ("costs", "offloads", "triggers", "sectors")


def test_each_kind_takes_only_its_own_changes_from_b():
    a, b = toy_a(), toy_b()
    costs = apply_kinds(a, b, ["costs"])
    assert {c.id: c.cost for c in costs.candidates} == {"A": 7, "B": 6}
    assert {(o.candidate_id, o.sector_id): o.amount for o in costs.offloads}[("B", "s2")] == 8

    offloads = apply_kinds(a, b, ["costs", "offloads"])
    rows = {(o.candidate_id, o.sector_id): o.amount for o in offloads.offloads}
    assert rows == {("A", "s1"): 10, ("B", "s2"): 10}  # no row for s3 before the sectors step

    triggers = apply_kinds(a, b, ["costs", "offloads", "triggers"])
    assert {s.id: s.trigger_year for s in triggers.sectors} == {
        "s1": BASE_YEAR,
        "s2": BASE_YEAR + 1,
    }


def test_steps_have_derived_version_ids_and_their_own_content_hash():
    a, b = toy_a(), toy_b()
    step = apply_kinds(a, b, ["costs", "offloads"])
    assert step.version_id == "a+costs+offloads"
    assert step.content_hash not in (a.content_hash, b.content_hash)


def test_applying_every_kind_gives_b():
    a, b = toy_a(), toy_b()
    assert apply_kinds(a, b, list(ORDER)).content_hash == b.content_hash


def test_applying_every_kind_to_generated_v1_gives_v2(tmp_path):
    write_inputs(42, tmp_path)
    v1, v2 = load_input_set(tmp_path / "v1.json"), load_input_set(tmp_path / "v2.json")
    assert apply_kinds(v1, v2, list(ORDER)).content_hash == v2.content_hash


# --- the toy attribution (hand-worked table in the SPEC) -----------------------------------


@pytest.fixture
def toy(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    request = RevisionRequest(budget=BUDGET, plan_of_record="a", refreshed_forecast="b")
    return run_revision(request, inputs, runs), runs


def test_toy_steps_match_the_hand_worked_table(toy):
    rev = toy[0].revision
    assert [s.name for s in rev.steps] == ["plan_of_record", *ORDER]
    assert [s.selected for s in rev.steps] == [["A"], ["B"], ["B"], ["B"], ["B"]]
    assert [s.objective for s in rev.steps] == pytest.approx([10, 8, 10, 5, 9])
    assert [s.resolved for s in rev.steps] == [1, 0, 1, 1, 2]
    assert [s.effect_relief for s in rev.steps[1:]] == pytest.approx([-2, 2, -5, 4])
    assert [s.effect_n_resolved for s in rev.steps[1:]] == [-1, 1, 0, 1]
    assert [s.effect_spend for s in rev.steps[1:]] == pytest.approx([0, 0, 0, 0])
    assert rev.steps[0].effect_relief is None


def test_toy_totals_split_and_order(toy):
    rev = toy[0].revision
    assert rev.complete
    assert rev.order == list(ORDER)
    assert rev.order_text == "costs -> offloads -> triggers -> sectors"
    assert rev.total_relief == pytest.approx(-1)
    assert (rev.total_n_resolved, rev.total_spend) == (1, pytest.approx(0))
    assert (rev.n_sectors_shared, rev.n_resolved_shared_a, rev.n_resolved_shared_b) == (2, 1, 1)
    assert (rev.n_sectors_new, rev.n_resolved_new) == (1, 1)


def test_effects_add_up_exactly_to_the_total(toy):
    rev = toy[0].revision
    assert sum(s.effect_relief for s in rev.steps[1:]) == pytest.approx(rev.total_relief, abs=1e-9)
    assert sum(s.effect_n_resolved for s in rev.steps[1:]) == rev.total_n_resolved


def test_steps_record_applied_kinds_and_hashes(toy):
    rev = toy[0].revision
    assert [s.applied for s in rev.steps] == [
        [],
        ["costs"],
        ["costs", "offloads"],
        ["costs", "offloads", "triggers"],
        list(ORDER),
    ]
    assert rev.steps[0].content_hash == toy_a().content_hash
    assert rev.steps[-1].content_hash == toy_b().content_hash
    assert [s.n_changes for s in rev.steps] == [0, 1, 1, 1, 1]


def test_the_record_is_stored_with_both_ends_as_scenario_runs(toy):
    record, runs = toy
    assert (record.kind, record.outcome, record.result) == ("revision", "completed", None)
    assert record.input_version == "b" and record.content_hash == toy_b().content_hash
    assert read_run(record.run_id, runs).revision == record.revision
    a_run, b_run = (
        read_run(record.revision.run_id_a, runs),
        read_run(record.revision.run_id_b, runs),
    )
    assert (a_run.kind, a_run.input_version, a_run.request["budget"]) == ("scenario", "a", BUDGET)
    assert (b_run.kind, b_run.input_version, b_run.request["budget"]) == ("scenario", "b", BUDGET)
    assert record.revision.inputs.sectors_added == ["s3"]


def test_a_kind_without_changes_is_not_solved_again(tmp_path, monkeypatch):
    no_triggers = make_set(  # toy b with s2's trigger left at BASE_YEAR
        [("s1", 10), ("s2", 10), ("s3", 4)],
        [("A", 7), ("B", 6)],
        [("A", "s1", 10), ("B", "s2", 10), ("B", "s3", 4)],
    ).model_copy(update={"version_id": "b"})
    inputs, runs = toy_dirs(tmp_path, b=no_triggers)
    calls = []
    real = revision_module.solve
    monkeypatch.setattr(revision_module, "solve", lambda *a, **k: calls.append(1) or real(*a, **k))
    rev = run_revision(
        RevisionRequest(budget=BUDGET, plan_of_record="a", refreshed_forecast="b"), inputs, runs
    ).revision
    triggers = rev.steps[3]
    assert (triggers.n_changes, triggers.effect_relief, triggers.effect_n_resolved) == (0, 0, 0)
    assert triggers.content_hash == rev.steps[2].content_hash
    assert len(calls) == 2  # costs and offloads only; the two ends are scenario runs


# --- incomplete attribution and rejections ----------------------------------------------------


def test_a_step_not_proven_optimal_makes_the_attribution_incomplete(tmp_path, monkeypatch):
    inputs, runs = toy_dirs(tmp_path)
    real = revision_module.solve

    def time_limit_on_offloads(data, *args, **kwargs):
        result = real(data, *args, **kwargs)
        if data.version_id.endswith("+offloads"):
            return result.model_copy(update={"status": "TimeLimit"})
        return result

    monkeypatch.setattr(revision_module, "solve", time_limit_on_offloads)
    rev = run_revision(
        RevisionRequest(budget=BUDGET, plan_of_record="a", refreshed_forecast="b"), inputs, runs
    ).revision
    assert not rev.complete
    assert all(s.effect_relief is None and s.effect_n_resolved is None for s in rev.steps)
    assert (rev.total_relief, rev.total_spend, rev.total_n_resolved) == (None, None, None)
    assert rev.inputs.costs_changed == ["A"]  # the input comparison is still reported


def test_a_missing_version_is_rejected(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    record = run_revision(
        RevisionRequest(budget=BUDGET, plan_of_record="a", refreshed_forecast="zz"), inputs, runs
    )
    assert record.outcome == "rejected"
    assert [r.code for r in record.reasons] == [ReasonCode.VERSION_NOT_FOUND]


def test_unsupported_changes_are_rejected(tmp_path):
    b = make_set([("s1", 12), ("s2", 10)], [("A", 6), ("B", 6)], [("A", "s1", 10), ("B", "s2", 8)])
    inputs, runs = toy_dirs(tmp_path, b=b.model_copy(update={"version_id": "b"}))
    record = run_revision(
        RevisionRequest(budget=BUDGET, plan_of_record="a", refreshed_forecast="b"), inputs, runs
    )
    assert record.outcome == "rejected"
    assert [r.code for r in record.reasons] == [ReasonCode.REVISION_UNSUPPORTED_CHANGE]
    assert "s1" in record.reasons[0].message


def test_a_gate_rejection_of_either_end_rejects_the_revision(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    record = run_revision(
        RevisionRequest(budget=-1, plan_of_record="a", refreshed_forecast="b"), inputs, runs
    )
    assert record.outcome == "rejected"
    assert ReasonCode.BUDGET_NOT_POSITIVE in {r.code for r in record.reasons}


def test_the_request_defaults_to_v1_and_v2_and_requires_a_budget():
    request = RevisionRequest(budget=1000)
    assert (request.plan_of_record, request.refreshed_forecast) == ("v1", "v2")
    with pytest.raises(ValueError):
        RevisionRequest()
    with pytest.raises(ValueError):
        RevisionRequest(budget=1000, force_in=["C001"])


# --- end to end, real CBC solver on the shipped v1 and v2 -----------------------------------


@pytest.mark.parametrize("budget", [800.0, 1000.0])
def test_end_to_end_on_shipped_v1_and_v2_with_cbc(tmp_path, budget):
    inputs = tmp_path / "inputs"
    write_inputs(42, inputs)
    record = run_revision(RevisionRequest(budget=budget), inputs, tmp_path / "runs")
    rev = record.revision
    v2 = load_input_set(inputs / "v2.json")
    assert record.outcome == "completed" and rev.complete
    assert [s.status for s in rev.steps] == ["Optimal"] * 5
    assert rev.steps[-1].content_hash == v2.content_hash
    assert [s.n_changes for s in rev.steps] == [0, 10, 8, 6, 3]
    effects = sum(s.effect_relief for s in rev.steps[1:])
    assert effects == pytest.approx(rev.total_relief, abs=1e-9)
    assert sum(s.effect_n_resolved for s in rev.steps[1:]) == rev.total_n_resolved
    a, b = read_run(rev.run_id_a, tmp_path / "runs"), read_run(rev.run_id_b, tmp_path / "runs")
    assert rev.steps[0].objective == pytest.approx(a.result.objective)
    assert rev.steps[-1].objective == pytest.approx(b.result.objective)
    assert rev.n_sectors_shared == 80 and rev.n_sectors_new == 3
