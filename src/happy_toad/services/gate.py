"""Validation gate: checks a request against the input data and returns every problem found."""

import math

from happy_toad.constants import BUDGET_CAP_FACTOR
from happy_toad.data.schemas import InputSet
from happy_toad.reasons import Reason, ReasonCode
from happy_toad.services.request import SolveRequest


def _reason(code: ReasonCode, message: str) -> Reason:
    return Reason(code=code, message=message)


def _budget_reasons(request: SolveRequest, data: InputSet | None) -> list[Reason]:
    reasons = []
    if not request.budget > 0:
        reasons.append(
            _reason(ReasonCode.BUDGET_NOT_POSITIVE, f"budget {request.budget} is not > 0")
        )
    if data is not None and request.budget > 0:
        cap = BUDGET_CAP_FACTOR * (data.candidate_total + data.must_fund_total)
        if request.budget > cap:
            reasons.append(
                _reason(
                    ReasonCode.BUDGET_ABOVE_CAP,
                    f"budget {request.budget} is above the cap {cap:.2f} "
                    f"({BUDGET_CAP_FACTOR} x candidate cost plus must-fund); check units",
                )
            )
    return reasons


def _force_reasons(request: SolveRequest, data: InputSet) -> list[Reason]:
    known = {c.id: c.cost for c in data.candidates}
    asked = sorted(set(request.force_in) | set(request.force_out))
    reasons = []
    unknown = [i for i in asked if i not in known]
    if unknown:
        reasons.append(_reason(ReasonCode.UNKNOWN_CANDIDATE, f"unknown candidate ids: {unknown}"))
    both = sorted(set(request.force_in) & set(request.force_out))
    if both:
        reasons.append(_reason(ReasonCode.FORCE_CONFLICT, f"in both force lists: {both}"))
    forced = sum(known[i] for i in request.force_in if i in known)
    must_fund = data.must_fund_total
    if not math.isnan(request.budget) and must_fund + forced > request.budget:
        reasons.append(
            _reason(
                ReasonCode.FORCED_COST_EXCEEDS_BUDGET,
                f"must-fund {must_fund:.2f} plus forced-in {forced:.2f} exceeds the budget "
                f"{request.budget}",
            )
        )
    return reasons


def check_request(request: SolveRequest, data: InputSet | None) -> list[Reason]:
    """All reasons the request cannot run (empty if it can). `data` is None if no such version."""
    reasons = []
    if data is None:
        reasons.append(
            _reason(ReasonCode.VERSION_NOT_FOUND, f"no input version {request.input_version!r}")
        )
    reasons += _budget_reasons(request, data)
    if data is not None:
        reasons += _force_reasons(request, data)
    return reasons
