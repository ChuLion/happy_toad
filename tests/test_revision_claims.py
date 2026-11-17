"""M5 claims: revision metrics, the entity rule, the order rule and D5 (docs/SPEC.md, M5)."""

import pytest
from helpers import make_set
from pydantic import ValidationError
from revision_helpers import BUDGET, toy_dirs

from happy_toad.agent.checker import check_report
from happy_toad.agent.report import Claim, Report
from happy_toad.services.request import SolveRequest
from happy_toad.services.revision import RevisionRequest, run_revision
from happy_toad.services.run import run_request

ORDER_SENTENCE = "In the order costs, offloads, triggers, sectors: "


@pytest.fixture
def rev(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    request = RevisionRequest(budget=BUDGET, plan_of_record="a", refreshed_forecast="b")
    return run_revision(request, inputs, runs)


def check(tmp_path, summary, *claims):
    report = Report(summary=summary, claims=list(claims))
    return check_report(report, tmp_path / "runs", tmp_path / "inputs")


def effect(rev, kind, value, metric="effect_relief"):
    return Claim(metric=metric, value=value, run_id=rev.run_id, entity=kind)


# --- schema ------------------------------------------------------------------------------------


def test_effect_claims_must_name_a_change_kind(rev):
    assert effect(rev, "costs", -2).entity == "costs"
    with pytest.raises(ValidationError):
        Claim(metric="effect_relief", value=-2, run_id=rev.run_id)  # no entity
    with pytest.raises(ValidationError):
        effect(rev, "plan", -2)
    with pytest.raises(ValidationError):
        effect(rev, "markets", -2)


def test_other_metrics_still_force_entity_plan(rev):
    assert (
        Claim(metric="total_relief", value=-1, run_id=rev.run_id, entity="costs").entity == "plan"
    )
    assert Claim(metric="n_sectors_added", value=1, run_id=rev.run_id).entity == "plan"


def test_units_and_signed_counts(rev):
    assert effect(rev, "costs", -2).unit == "need_units"
    assert effect(rev, "costs", 0, "effect_spend").unit == "cost_units"
    assert effect(rev, "costs", "-1", "effect_n_resolved").value == -1
    assert Claim(metric="total_n_resolved", value="-1", run_id=rev.run_id).value == -1
    assert Claim(metric="n_resolved_new", value=1, run_id=rev.run_id).unit == "count"


def test_there_is_no_percent_due_to_metric(rev):
    with pytest.raises(ValidationError):
        Claim(metric="pct_effect_relief", value=50, run_id=rev.run_id, entity="costs")


# --- checking against the record ----------------------------------------------------------------


def test_every_revision_metric_matches_the_toy_record(rev, tmp_path):
    claims = [
        effect(rev, "costs", -2.0),
        effect(rev, "offloads", 2.0),
        effect(rev, "triggers", -5.0),
        effect(rev, "sectors", 4.0),
        effect(rev, "costs", -1, "effect_n_resolved"),
        effect(rev, "triggers", 0.0, "effect_spend"),
        Claim(metric="total_relief", value=-1.0, run_id=rev.run_id),
        Claim(metric="total_n_resolved", value=1, run_id=rev.run_id),
        Claim(metric="total_spend", value=0.0, run_id=rev.run_id),
        Claim(metric="n_sectors_added", value=1, run_id=rev.run_id),
        Claim(metric="n_sectors_removed", value=0, run_id=rev.run_id),
        Claim(metric="n_triggers_moved", value=1, run_id=rev.run_id),
        Claim(metric="n_costs_changed", value=1, run_id=rev.run_id),
        Claim(metric="n_offloads_changed", value=1, run_id=rev.run_id),
        Claim(metric="n_sectors_shared", value=2, run_id=rev.run_id),
        Claim(metric="n_resolved_shared_a", value=1, run_id=rev.run_id),
        Claim(metric="n_resolved_shared_b", value=1, run_id=rev.run_id),
        Claim(metric="n_sectors_new", value=1, run_id=rev.run_id),
        Claim(metric="n_resolved_new", value=1, run_id=rev.run_id),
    ]
    summary = ORDER_SENTENCE + "see the claims."
    result = check(tmp_path, summary, *claims)
    assert result.ok, [c.message for c in result.claims if not c.ok]


def test_a_wrong_kind_fails(rev, tmp_path):
    assert not check(tmp_path, ORDER_SENTENCE, effect(rev, "offloads", -2.0)).ok


def test_revision_metrics_on_a_scenario_run_and_run_metrics_on_a_revision_fail(rev, tmp_path):
    scenario = rev.revision.run_id_a
    bad = Claim(metric="total_relief", value=-1.0, run_id=scenario)
    assert not check(tmp_path, ORDER_SENTENCE, bad).ok
    assert not check(tmp_path, "x", Claim(metric="spend", value=6.0, run_id=rev.run_id)).ok


def test_an_incomplete_attribution_has_nothing_to_claim(rev, tmp_path):
    record_path = tmp_path / "runs" / f"{rev.run_id}.json"
    incomplete = rev.model_copy(
        update={
            "revision": rev.revision.model_copy(
                update={
                    "complete": False,
                    "total_relief": None,
                    "steps": [
                        s.model_copy(update={"effect_relief": None}) for s in rev.revision.steps
                    ],
                }
            )
        }
    )
    record_path.write_text(incomplete.model_dump_json())
    result = check(tmp_path, ORDER_SENTENCE, effect(rev, "costs", -2.0))
    assert not result.ok
    assert "attribution incomplete" in result.claims[0].message


# --- the order rule -------------------------------------------------------------------------------


def test_attribution_claims_need_the_order_in_the_summary(rev, tmp_path):
    claim = effect(rev, "costs", -2.0)
    assert check(tmp_path, ORDER_SENTENCE + "costs moved relief by -2.00.", claim).ok
    assert not check(tmp_path, "Costs moved relief by -2.00.", claim).ok
    wrong_order = "Order: sectors, triggers, offloads, costs. Costs moved relief by -2.00."
    assert not check(tmp_path, wrong_order, claim).ok
    total = Claim(metric="total_relief", value=-1.0, run_id=rev.run_id)
    assert not check(tmp_path, "Relief fell by 1.00.", total).ok


def test_the_order_rule_does_not_apply_to_input_counts(rev, tmp_path):
    claim = Claim(metric="n_sectors_added", value=1, run_id=rev.run_id)
    assert check(tmp_path, "1 sector was added.", claim).ok


def test_an_effect_may_be_written_without_its_sign(rev, tmp_path):
    claim = effect(rev, "triggers", -5.0)
    assert check(tmp_path, ORDER_SENTENCE + "triggers cut relief by 5.00.", claim).ok


def test_a_percent_due_to_a_kind_fails_the_number_check(rev, tmp_path):
    claim = effect(rev, "costs", -2.0)
    summary = ORDER_SENTENCE + "costs moved relief by -2.00, 40% of the change."
    assert not check(tmp_path, summary, claim).ok


def test_candidates_selected_only_in_a_middle_step_are_traced(tmp_path):
    """a picks C001, the costs step picks C003, b picks C002: C003 is in no end run."""
    a = make_set(
        [("s1", 10), ("s2", 10)],
        [("C001", 6), ("C002", 6), ("C003", 6)],
        [("C001", "s1", 10), ("C002", "s2", 8), ("C003", "s1", 9)],
    )
    b = make_set(
        [("s1", 10), ("s2", 10)],
        [("C001", 7), ("C002", 6), ("C003", 6)],
        [("C001", "s1", 10), ("C002", "s2", 8), ("C003", "s1", 5)],
    )
    inputs, runs = toy_dirs(
        tmp_path, a.model_copy(update={"version_id": "a"}), b.model_copy(update={"version_id": "b"})
    )
    rev = run_revision(
        RevisionRequest(budget=6, plan_of_record="a", refreshed_forecast="b"), inputs, runs
    )
    assert [s.selected for s in rev.revision.steps[:3]] == [["C001"], ["C003"], ["C002"]]
    claim = effect(rev, "costs", -1.0)
    summary = ORDER_SENTENCE + "after costs, C003 replaces C001; relief moved by -1.00."
    assert check(tmp_path, summary, claim).ok


# --- D5: different sector counts ------------------------------------------------------------------


def test_diff_pct_resolved_across_different_sector_counts_fails(rev, tmp_path):
    a, b = rev.revision.run_id_a, rev.revision.run_id_b
    claim = Claim(metric="diff_pct_resolved", value=16.7, run_id=a, run_id_b=b)  # 50% -> 66.7%
    result = check(tmp_path, "Percent resolved rose 16.7 points.", claim)
    assert not result.ok
    assert "different sector counts" in result.claims[0].message


def test_diff_pct_resolved_with_the_same_sector_count_still_works(tmp_path):
    inputs, runs = toy_dirs(tmp_path)
    one = run_request(SolveRequest(input_version="b", budget=6), inputs, runs)  # 2 of 3
    two = run_request(SolveRequest(input_version="b", budget=13), inputs, runs)  # 3 of 3
    claim = Claim(metric="diff_pct_resolved", value=33.3, run_id=one.run_id, run_id_b=two.run_id)
    assert check(tmp_path, "Percent resolved rose 33.3 points.", claim).ok
