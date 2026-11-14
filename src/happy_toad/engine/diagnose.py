"""Cheap infeasibility checks that run before the solver (SPEC, infeasibility explanation)."""

from collections import defaultdict
from collections.abc import Collection

from happy_toad.data.schemas import InputSet
from happy_toad.engine.markets import FEASIBILITY_TOLERANCE, MarketLimits, candidate_markets
from happy_toad.reasons import Reason, ReasonCode


def _reason(code: ReasonCode, message: str) -> Reason:
    return Reason(code=code, message=message)


def _market_spend(data: InputSet, ids: Collection[str]) -> dict[str, float]:
    """Cost of the given candidates per market."""
    market = candidate_markets(data)
    spend: dict[str, float] = defaultdict(float)
    for c in data.candidates:
        if c.id in ids and c.id in market:
            spend[market[c.id]] += c.cost
    return spend


def diagnose(
    data: InputSet,
    avail: float,
    force_in: Collection[str],
    force_out: Collection[str],
    limits: MarketLimits | None,
) -> Reason | None:
    """The first cause that makes the model certainly infeasible, or None if none is found.

    `limits` must already have its floors clamped. Checks run in the order of the SPEC table.
    """
    forced = sum(c.cost for c in data.candidates if c.id in force_in)
    if forced > avail + FEASIBILITY_TOLERANCE:
        return _reason(
            ReasonCode.FORCED_COST_EXCEEDS_BUDGET,
            f"forced-in cost {forced:.2f} exceeds the budget left after must-fund ({avail:.2f})",
        )
    if limits is None:
        return None
    floors, caps = limits.floors, limits.caps
    if sum(floors.values()) > avail + FEASIBILITY_TOLERANCE:
        return _reason(
            ReasonCode.FLOORS_EXCEED_BUDGET,
            f"market floors add up to {sum(floors.values()):.2f}, "
            f"more than the {avail:.2f} available",
        )
    for m, cap in sorted(caps.items()):
        if cap < floors.get(m, 0.0) - FEASIBILITY_TOLERANCE:
            return _reason(
                ReasonCode.CAP_BELOW_FLOOR,
                f"cap {cap:.2f} of {m} is below its floor {floors[m]:.2f}",
            )
    forced_spend = _market_spend(data, force_in)
    for m, cap in sorted(caps.items()):
        if forced_spend.get(m, 0.0) > cap + FEASIBILITY_TOLERANCE:
            return _reason(
                ReasonCode.FORCED_IN_EXCEEDS_CAP,
                f"forced-in spend {forced_spend[m]:.2f} in {m} exceeds its cap {cap:.2f}",
            )
    reachable = _market_spend(data, {c.id for c in data.candidates} - set(force_out))
    for m, floor in sorted(floors.items()):
        if floor > reachable.get(m, 0.0) + FEASIBILITY_TOLERANCE:
            return _reason(
                ReasonCode.FLOOR_UNREACHABLE,
                f"floor {floor:.2f} of {m} is more than its candidates that are not forced out "
                f"cost ({reachable.get(m, 0.0):.2f})",
            )
    return None


def required_minimum_budget(
    data: InputSet, force_in: Collection[str], limits: MarketLimits | None
) -> float:
    """Lower bound on the total budget: must-fund + forced-in cost + clamped floors.

    Forced-in spend inside a floored market counts toward that floor, so each market contributes
    max(floor, forced spend) and is not counted twice. `limits` must already have clamped floors.
    """
    must_fund = sum(m.cost for m in data.must_fund)
    forced = sum(c.cost for c in data.candidates if c.id in force_in)
    if limits is None:
        return must_fund + forced
    in_market = _market_spend(data, force_in)
    floors = limits.floors
    floored = sum(max(f, in_market.get(m, 0.0)) for m, f in floors.items())
    unfloored = sum(v for m, v in in_market.items() if m not in floors)
    return must_fund + floored + unfloored + (forced - sum(in_market.values()))


def multiplier_advice(code: ReasonCode, floor_mult: float | None, cap_mult: float | None) -> str:
    """Which multiplier to change when limits come from multipliers (no minimum budget exists).

    Floors and caps are both multiples of the same shares x avail, so a larger budget scales
    them together and cannot remove these causes.
    """
    if code == ReasonCode.FLOORS_EXCEED_BUDGET:
        return (
            f"floor multiplier {floor_mult} requires floors above the available budget at any "
            "budget; use 1.0 or less"
        )
    if code == ReasonCode.CAP_BELOW_FLOOR:
        return (
            f"cap multiplier {cap_mult} is below floor multiplier {floor_mult} at any budget; "
            f"use a cap multiplier of {floor_mult} or more"
        )
    if code == ReasonCode.FORCED_IN_EXCEEDS_CAP:
        return f"raise the cap multiplier (now {cap_mult}) or force in fewer candidates"
    return f"lower the floor multiplier (now {floor_mult}) or force out fewer candidates"
