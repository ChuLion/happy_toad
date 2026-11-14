"""Request schema, request hash and the validation gate (SPEC, M2A)."""

import math

import pytest
from helpers import make_set
from pydantic import ValidationError

from happy_toad.constants import BASE_YEAR
from happy_toad.reasons import ReasonCode
from happy_toad.services.gate import check_request
from happy_toad.services.request import SolveRequest, request_hash


@pytest.fixture
def data():
    """Total candidate cost 17, must-fund 3 (so the cap is 1.5 * 20 = 30)."""
    return make_set(
        [("sX1", 10, BASE_YEAR, "X"), ("sY1", 10, BASE_YEAR + 4, "Y")],
        [("X1", 6), ("X2", 5), ("Y1", 6)],
        [("X1", "sX1", 10), ("X2", "sX1", 4), ("Y1", "sY1", 10)],
        must_fund=[3],
    )


def req(**kwargs) -> SolveRequest:
    return SolveRequest(**{"input_version": "test", "budget": 12.0, **kwargs})


def codes(request, data) -> list[str]:
    return [r.code for r in check_request(request, data)]


def test_request_defaults_and_normalized_id_lists() -> None:
    r = req(force_in=["X2", "X1", "X2"])
    assert r.force_in == ["X1", "X2"] and r.force_out == []
    assert r.label == "" and r.market_floor_mult is None and r.market_cap_mult is None
    assert r.region_total_sectors is None and r.target_pct_resolved is None


@pytest.mark.parametrize(
    "bad",
    [
        {"target_pct_resolved": 101},
        {"target_pct_resolved": -1},
        {"market_floor_mult": -0.1},
        {"market_cap_mult": -1},
        {"region_total_sectors": 0},
        {"unknown_field": 1},
    ],
)
def test_field_rules_are_enforced_by_the_schema(bad) -> None:
    with pytest.raises(ValidationError):
        req(**bad)


def test_request_hash_ignores_label_and_id_order_but_not_content() -> None:
    a = req(label="first", force_in=["X1", "X2"])
    b = req(label="second", force_in=["X2", "X1"])
    assert request_hash(a) == request_hash(b)
    assert request_hash(a) != request_hash(req(force_in=["X1", "X2"], budget=13.0))
    assert request_hash(a) != request_hash(req(force_in=["X1", "X2"], market_cap_mult=1.5))
    assert len(request_hash(a)) == 64


def test_valid_request_has_no_reasons(data) -> None:
    assert check_request(req(), data) == []


def test_missing_version_is_reported_and_data_checks_are_skipped() -> None:
    assert codes(req(force_in=["nope"]), None) == [ReasonCode.VERSION_NOT_FOUND]
    assert codes(req(budget=-1, force_in=["nope"]), None) == [
        ReasonCode.VERSION_NOT_FOUND,
        ReasonCode.BUDGET_NOT_POSITIVE,
    ]


@pytest.mark.parametrize("budget", [0, -5, math.nan])
def test_budget_must_be_positive(data, budget) -> None:
    assert ReasonCode.BUDGET_NOT_POSITIVE in codes(req(budget=budget), data)


def test_budget_cap_is_1_5_times_candidate_cost_plus_must_fund(data) -> None:
    assert codes(req(budget=20), data) == []  # fund everything: allowed
    assert codes(req(budget=30), data) == []  # exactly at the cap
    assert codes(req(budget=30.01), data) == [ReasonCode.BUDGET_ABOVE_CAP]
    assert codes(req(budget=math.inf), data) == [ReasonCode.BUDGET_ABOVE_CAP]


def test_unknown_candidates_are_reported_with_their_ids(data) -> None:
    reasons = check_request(req(force_in=["X1", "ZZ"], force_out=["QQ"]), data)
    assert [r.code for r in reasons] == [ReasonCode.UNKNOWN_CANDIDATE]
    assert "ZZ" in reasons[0].message and "QQ" in reasons[0].message


def test_force_conflict(data) -> None:
    reasons = check_request(req(budget=15, force_in=["X1", "Y1"], force_out=["Y1"]), data)
    assert [r.code for r in reasons] == [ReasonCode.FORCE_CONFLICT]
    assert "Y1" in reasons[0].message


def test_forced_cost_includes_must_fund(data) -> None:
    assert codes(req(budget=12, force_in=["X1", "Y1"]), data) == [
        ReasonCode.FORCED_COST_EXCEEDS_BUDGET  # 3 + 6 + 6 = 15 > 12
    ]
    assert codes(req(budget=15, force_in=["X1", "Y1"]), data) == []
    assert codes(req(budget=2), data) == [ReasonCode.FORCED_COST_EXCEEDS_BUDGET]  # must-fund 3


def test_the_gate_returns_all_reasons_not_just_the_first(data) -> None:
    request = req(budget=-1, force_in=["X1", "ZZ"], force_out=["X1"])
    assert codes(request, data) == [
        ReasonCode.BUDGET_NOT_POSITIVE,
        ReasonCode.UNKNOWN_CANDIDATE,
        ReasonCode.FORCE_CONFLICT,
        ReasonCode.FORCED_COST_EXCEEDS_BUDGET,
    ]
