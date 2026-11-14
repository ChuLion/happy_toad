"""Report schema and consistency checker (SPEC, M3 decisions 5 and 6 and the number definition)."""

import pytest
from agent_helpers import make_run
from pydantic import ValidationError

from happy_toad.agent.checker import check_report, find_numbers
from happy_toad.agent.report import Claim, Report


def claim(run, metric, value, unit):
    return Claim(metric=metric, value=value, unit=unit, run_id=run.run_id, entity="plan")


@pytest.fixture
def run(tmp_path):
    return make_run(tmp_path)  # budget 12: X1 + X2, spend 11, relief 20, 2 of 3 sectors resolved


def check(run, tmp_path, summary, *claims):
    return check_report(
        Report(summary=summary, claims=list(claims)), tmp_path / "runs", tmp_path / "inputs"
    )


def test_schema_rejects_unknown_metric_and_extra_fields(run) -> None:
    with pytest.raises(ValidationError):
        Claim(metric="profit", value=1, unit="none", run_id=run.run_id, entity="plan")
    with pytest.raises(ValidationError):
        Claim(metric="spend", value=1, unit="cost_units", run_id=run.run_id, entity="plan", x=1)


def test_entity_defaults_to_plan_and_unit_is_derived_from_the_metric(run) -> None:
    wrong = Claim(metric="spend", value=1, unit="currency", run_id=run.run_id, entity="Budget 800")
    assert (wrong.unit, wrong.entity) == ("cost_units", "plan")
    bare = Claim(metric="pct_resolved", value=1, run_id=run.run_id)
    assert (bare.unit, bare.entity) == ("percent", "plan")


def test_every_metric_matches_the_stored_run(run, tmp_path) -> None:
    claims = [
        claim(run, "weighted_relief", 20.0, "need_units"),
        claim(run, "spend", 11.0, "cost_units"),
        claim(run, "n_selected", 2, "count"),
        claim(run, "n_resolved", 2, "count"),
        claim(run, "pct_resolved", 66.7, "percent"),
        claim(run, "status", "Optimal", "none"),
    ]
    result = check(run, tmp_path, "ok", *claims)
    assert result.ok and all(c.ok for c in result.claims)


def test_tolerances_follow_the_displayed_rounding(run, tmp_path) -> None:
    assert check(run, tmp_path, "x", claim(run, "spend", 11.004, "cost_units")).ok
    assert not check(run, tmp_path, "x", claim(run, "spend", 11.01, "cost_units")).ok
    assert check(run, tmp_path, "x", claim(run, "pct_resolved", 66.7, "percent")).ok
    assert not check(run, tmp_path, "x", claim(run, "pct_resolved", 66.6, "percent")).ok
    assert not check(run, tmp_path, "x", claim(run, "n_selected", 3, "count")).ok
    assert not check(run, tmp_path, "x", claim(run, "status", "Infeasible", "none")).ok


def test_a_claim_about_a_missing_run_or_a_run_without_a_plan_fails(tmp_path) -> None:
    infeasible = make_run(tmp_path, force_in=["X1", "X2", "Y1"])
    bad = check_report(
        Report(
            summary="x",
            claims=[
                claim(infeasible, "spend", 0.0, "cost_units"),
                Claim(
                    metric="spend",
                    value=1,
                    unit="cost_units",
                    run_id="20260101T000000-deadbeef",
                    entity="plan",
                ),
            ],
        ),
        tmp_path / "runs",
    )
    assert [c.ok for c in bad.claims] == [False, False] and not bad.ok
    assert "no value" in bad.claims[0].message and "not found" in bad.claims[1].message


def test_required_minimum_budget_is_valid_only_when_the_run_has_one(tmp_path) -> None:
    infeasible = make_run(tmp_path, force_in=["X1", "X2", "Y1"])
    feasible = make_run(tmp_path)
    right = claim(infeasible, "required_minimum_budget", 17.0, "cost_units")
    assert check(infeasible, tmp_path, "at least 17.00", right).ok
    off = claim(infeasible, "required_minimum_budget", 17.01, "cost_units")
    assert not check(infeasible, tmp_path, "x", off).ok
    none = claim(feasible, "required_minimum_budget", 17.0, "cost_units")
    assert not check(feasible, tmp_path, "x", none).ok


def test_target_met_is_checked(tmp_path) -> None:
    run = make_run(tmp_path, target_pct_resolved=50.0)
    assert check(run, tmp_path, "x", claim(run, "target_met", True, "none")).ok
    assert not check(run, tmp_path, "x", claim(run, "target_met", False, "none")).ok


def test_find_numbers_ignores_identifiers_years_and_list_markers() -> None:
    text = (
        "1. Run 20260101T123456-deadbeef on v1 for C033, S001, M2 and market_e in 2027-2031.\n"
        "2) Spend 485.59 and 1,284.34 at 66.7% with 14 candidates, change -3.50, year 2030."
    )
    assert [t for t, _ in find_numbers(text)] == ["485.59", "1,284.34", "66.7%", "14", "-3.50"]
    assert dict(find_numbers("1,284.34 and 66.7%")) == {"1,284.34": 1284.34, "66.7%": 66.7}


def test_a_four_digit_amount_with_decimals_is_a_number_not_a_year() -> None:
    assert [t for t, _ in find_numbers("spend 2030.00 in 2030")] == ["2030.00"]


def test_every_summary_number_must_match_a_claim_or_a_request_value(run, tmp_path) -> None:
    claims = [claim(run, "spend", 11.0, "cost_units"), claim(run, "n_selected", 2, "count")]
    ok = check(
        run, tmp_path, "At a budget of 12 the plan funds 2 candidates, spend 11.00.", *claims
    )
    assert ok.ok and all(n.ok for n in ok.numbers)
    bad = check(run, tmp_path, "Spend 11.00 saves 9.00 over the other plan.", *claims)
    assert not bad.ok and [n.text for n in bad.numbers if not n.ok] == ["9.00"]


def test_summary_numbers_use_the_tolerance_of_the_matching_metric(run, tmp_path) -> None:
    c = claim(run, "pct_resolved", 66.7, "percent")
    assert check(run, tmp_path, "66.7% resolved", c).ok
    assert not check(run, tmp_path, "66.9% resolved", c).ok


def test_summary_without_numbers_and_without_claims_passes(run, tmp_path) -> None:
    assert check(run, tmp_path, "I can only report on runs; I cannot say what to fund.").ok


def test_the_tolerance_is_inclusive_despite_float_error() -> None:
    """Found live: 26.3 against a stored 26.25 is one display-rounding step and must pass."""
    from happy_toad.agent.checker import values_match

    assert values_match("pct_resolved", 26.3, 26.25)
    assert values_match("pct_resolved", 26.2, 26.25)
    assert values_match("spend", 11.005, 11.0)
    assert not values_match("pct_resolved", 26.31, 26.25)
    assert [t for t, _ in find_numbers("26.3%")] == ["26.3%"]


def test_n_sectors_is_checked_against_the_real_sector_count_of_the_inputs(run, tmp_path) -> None:
    right = claim(run, "n_sectors", 3, "count")  # the toy version has sectors sX1, sX2, sY1
    assert check(run, tmp_path, "3 sectors are modelled.", right).ok
    assert not check(run, tmp_path, "x", claim(run, "n_sectors", 4, "count")).ok


def test_n_sectors_fails_when_the_input_version_is_missing(run, tmp_path) -> None:
    (tmp_path / "inputs" / "test.json").unlink()
    result = check(run, tmp_path, "x", claim(run, "n_sectors", 3, "count"))
    assert not result.ok and "input version" in result.claims[0].message


def test_resolved_of_total_passes_when_both_are_claims(run, tmp_path) -> None:
    claims = [claim(run, "n_resolved", 2, "count"), claim(run, "n_sectors", 3, "count")]
    assert check(run, tmp_path, "2 of 3 sectors resolved.", *claims).ok
    assert not check(run, tmp_path, "2 of 80 sectors resolved.", *claims).ok


def money_claim(metric, value, unit):
    return Claim(metric=metric, value=value, unit=unit, run_id="r", entity="plan")


def test_plain_decimal_strings_are_coerced_for_numeric_metrics() -> None:
    assert money_claim("spend", "485.59", "cost_units").value == 485.59
    assert money_claim("weighted_relief", "-3", "need_units").value == -3.0
    assert money_claim("pct_resolved", "26.25", "percent").value == 26.25
    count = money_claim("n_resolved", "21", "count")
    assert count.value == 21 and type(count.value) is int


@pytest.mark.parametrize("bad", ["$485.59", "1,284.34", "21 sectors", "", " 5", "1e3", "5."])
def test_anything_but_a_plain_decimal_string_is_rejected_for_a_money_metric(bad) -> None:
    with pytest.raises(ValidationError):
        money_claim("spend", bad, "cost_units")


@pytest.mark.parametrize("bad", ["21.5", "21 sectors", "1,284", "-3"])
def test_counts_must_be_whole_numbers(bad) -> None:
    with pytest.raises(ValidationError):
        money_claim("n_selected", bad, "count")


def test_bools_are_never_coerced_and_text_metrics_keep_their_strings() -> None:
    assert money_claim("spend", True, "cost_units").value is True
    assert money_claim("status", "Optimal", "none").value == "Optimal"
    assert money_claim("target_met", "true", "none").value == "true"


def test_a_mismatch_message_shows_the_types(run, tmp_path) -> None:
    result = check(run, tmp_path, "No numbers.", claim(run, "status", "Infeasible", "none"))
    assert result.claims[0].message == "claimed 'Infeasible' (str), stored 'Optimal'"


def test_when_no_claim_validates_the_numbers_are_unchecked_and_reported_once(run, tmp_path) -> None:
    wrong = claim(run, "spend", 99.0, "cost_units")
    result = check(run, tmp_path, "Spend is 99.00 and relief is 20.00.", wrong)
    assert not result.ok
    assert all(n.message.startswith("not checked") for n in result.numbers)
    lines = result.errors()
    assert len(lines) == 2 and "no claim validated" in lines[1]


def test_numbers_are_still_unmatched_when_a_claim_validated(run, tmp_path) -> None:
    result = check(run, tmp_path, "Spend is 11.00 and 77.", claim(run, "spend", 11.0, "cost_units"))
    assert [n.ok for n in result.numbers] == [True, False]
    assert "does not match" in result.numbers[1].message


def test_defaults_are_listed_like_coercions() -> None:
    import json

    from happy_toad.agent.report import defaults

    raw = [
        dict(metric="spend", value=1, unit="currency", run_id="r", entity="Budget 800"),
        dict(metric="n_selected", value=2, run_id="r"),
        dict(metric="spend", value=1, unit="cost_units", run_id="r", entity="plan"),
    ]
    report = Report(summary="x", claims=raw)
    found = defaults(json.dumps({"summary": "x", "claims": raw}), report)
    assert found == [
        {"field": "unit", "metric": "spend", "run_id": "r", "from": "currency", "to": "cost_units"},
        {"field": "entity", "metric": "spend", "run_id": "r", "from": "Budget 800", "to": "plan"},
        {"field": "unit", "metric": "n_selected", "run_id": "r", "from": None, "to": "count"},
        {"field": "entity", "metric": "n_selected", "run_id": "r", "from": None, "to": "plan"},
    ]


def two_runs(tmp_path):
    big = make_run(tmp_path)  # budget 12
    small = make_run(tmp_path, budget=6.0)
    return big, small


def diff_claim(a, b, metric, value):
    return Claim(metric=metric, value=value, run_id=a.run_id, run_id_b=b.run_id)


def test_comparison_claims_are_b_minus_a_as_compare_runs_reports(tmp_path) -> None:
    from happy_toad.services.runs import compare_runs

    a, b = two_runs(tmp_path)
    fields = compare_runs(a, b).fields
    claims = [
        diff_claim(a, b, "diff_spend", round(fields["spend"].difference, 2)),
        diff_claim(a, b, "diff_weighted_relief", round(fields["weighted_relief"].difference, 2)),
        diff_claim(a, b, "diff_n_selected", int(fields["n_selected"].difference)),
        diff_claim(a, b, "diff_n_resolved", int(fields["n_resolved"].difference)),
        diff_claim(a, b, "diff_pct_resolved", round(fields["pct_resolved"].difference, 1)),
    ]
    result = check_report(
        Report(summary="ok", claims=claims), tmp_path / "runs", tmp_path / "inputs"
    )
    assert result.ok, result.errors()
    wrong = diff_claim(a, b, "diff_spend", -round(fields["spend"].difference, 2) + 1)
    assert not check_report(Report(summary="x", claims=[wrong]), tmp_path / "runs").ok


def test_a_difference_may_appear_in_the_summary_without_its_sign(tmp_path) -> None:
    a, b = two_runs(tmp_path)
    from happy_toad.services.runs import compare_runs

    d = round(compare_runs(a, b).fields["spend"].difference, 2)
    claim_ = diff_claim(a, b, "diff_spend", d)
    summary = f"The smaller budget spends {abs(d):.2f} less."
    assert d < 0
    assert check_report(Report(summary=summary, claims=[claim_]), tmp_path / "runs").ok


def test_comparison_claims_need_a_second_run_and_others_must_not_have_one(run) -> None:
    with pytest.raises(ValidationError):
        Claim(metric="diff_spend", value=1, run_id=run.run_id)
    with pytest.raises(ValidationError):
        Claim(metric="spend", value=1, run_id=run.run_id, run_id_b=run.run_id)


def test_must_fund_and_forced_cost_are_checked_against_the_inputs(tmp_path) -> None:
    forced = make_run(tmp_path, force_in=["X1", "Y1"])  # toy costs 6 + 6; no must-fund projects
    claims = [
        claim(forced, "forced_cost", 12.0, "cost_units"),
        claim(forced, "must_fund_cost", 0.0, "cost_units"),
    ]
    result = check(forced, tmp_path, "Forced 12.00.", *claims)
    assert all(c.ok for c in result.claims), result.errors()
    off = check(forced, tmp_path, "x", claim(forced, "forced_cost", 11.0, "cost_units"))
    assert not off.claims[0].ok


def test_status_of_a_rejected_run_is_its_outcome(tmp_path) -> None:
    rejected = make_run(tmp_path, force_in=["X1", "X2", "Y1"])
    rmb = claim(rejected, "required_minimum_budget", 17.0, "cost_units")
    assert check(rejected, tmp_path, "x", claim(rejected, "status", "rejected", "none"), rmb).ok
    assert not check(rejected, tmp_path, "x", claim(rejected, "status", "Optimal", "none"), rmb).ok


def test_a_rejected_run_with_a_minimum_budget_must_be_claimed(tmp_path) -> None:
    rejected = make_run(tmp_path, force_in=["X1", "X2", "Y1"])
    runs = tmp_path / "runs"
    vague = Report(summary="The budget must be at least the required minimum budget.", claims=[])
    result = check_report(vague, runs, tmp_path / "inputs", conversation_runs=[rejected.run_id])
    assert not result.ok and any("required_minimum_budget" in e for e in result.errors())
    rmb = claim(rejected, "required_minimum_budget", 17.0, "cost_units")
    good = Report(summary="The budget must be at least 17.00.", claims=[rmb])
    assert check_report(good, runs, tmp_path / "inputs", conversation_runs=[rejected.run_id]).ok
    cited = Report(summary="x", claims=[claim(rejected, "status", "rejected", "none")])
    assert not check_report(cited, runs, tmp_path / "inputs").ok  # a cited run counts too


def test_run_ids_and_their_digit_only_suffixes_are_never_numbers(tmp_path) -> None:
    rid = "20261114T184501-78612358"
    text = f"Run {rid} and run 78612358 and 20261114T184501 spent 11.00."
    assert [t for t, _ in find_numbers(text, [rid])] == ["11.00"]


NOT_IN_CONVERSATION = "run was not executed or read in this conversation"


def test_a_claim_citing_a_run_from_outside_the_conversation_fails(run, tmp_path) -> None:
    report = Report(summary="Spend is 11.", claims=[claim(run, "spend", 11.0, "cost_units")])
    outside = check_report(report, tmp_path / "runs", tmp_path / "inputs", conversation_runs=[])
    assert not outside.ok
    assert outside.claims[0].message == NOT_IN_CONVERSATION
    inside = check_report(
        report, tmp_path / "runs", tmp_path / "inputs", conversation_runs=[run.run_id]
    )
    assert inside.ok, inside.errors()


def test_a_comparison_claim_fails_when_run_b_is_from_outside_the_conversation(tmp_path) -> None:
    from happy_toad.services.runs import compare_runs

    a, b = two_runs(tmp_path)
    value = round(compare_runs(a, b).fields["spend"].difference, 2)
    report = Report(summary="ok", claims=[diff_claim(a, b, "diff_spend", value)])
    result = check_report(report, tmp_path / "runs", conversation_runs=[a.run_id])
    assert not result.ok and result.claims[0].message == NOT_IN_CONVERSATION
