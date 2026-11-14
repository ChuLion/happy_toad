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


def test_schema_rejects_unknown_metric_wrong_unit_and_extra_fields(run) -> None:
    with pytest.raises(ValidationError):
        Claim(metric="profit", value=1, unit="none", run_id=run.run_id, entity="plan")
    with pytest.raises(ValidationError):
        Claim(metric="spend", value=1, unit="percent", run_id=run.run_id, entity="plan")
    with pytest.raises(ValidationError):
        Claim(metric="spend", value=1, unit="cost_units", run_id=run.run_id, entity="plan", x=1)
    with pytest.raises(ValidationError):
        Claim(metric="spend", value=1, unit="cost_units", run_id=run.run_id, entity="X1")


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
