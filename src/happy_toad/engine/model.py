"""Two-stage solve: optimal relief within delta/10, then minimum spend among plans delivering it.

Stage 1 maximizes weighted relief (R*). Stage 2 minimizes spend subject to weighted relief >=
R* - relief_slack, where relief_slack = delta / 10. The time limit covers both stages together.
"""

from collections.abc import Collection

from happy_toad.constants import BASE_YEAR
from happy_toad.data.schemas import InputSet
from happy_toad.engine.diagnose import diagnose, multiplier_advice, required_minimum_budget
from happy_toad.engine.markets import MarketLimits, clamp_floors, fair_share_limits
from happy_toad.engine.relief import sector_relief, sector_weights, weighted, weighted_relief
from happy_toad.engine.result import DEFAULT_SETTINGS, SolveResult, SolverSettings
from happy_toad.engine.stages import build_stage1, build_stage2, chosen_ids, make_solver
from happy_toad.engine.status import map_status
from happy_toad.reasons import Reason, ReasonCode

UNKNOWN_CAUSE = Reason(
    code=ReasonCode.CAUSE_UNKNOWN,
    message="the solver reports the model infeasible; cause unknown",
)


def make_result(
    data, selected, status, base_year, meta, times, cause=None, minimum=None
) -> SolveResult:
    """Assemble a SolveResult. selected=None means no plan; relief and objective are recomputed."""
    plan = dict(objective=None, selected=None, relief=None, spend=None)
    if selected is not None:
        relief = sector_relief(data, set(selected))
        plan = dict(
            objective=weighted(relief, sector_weights(data, base_year)),
            selected=selected,
            relief=relief,
            spend=sum(c.cost for c in data.candidates if c.id in selected),
        )
    return SolveResult(
        status=status,
        solve_time=sum(times.values()),
        stage_times=times,
        base_year=base_year,
        cause=cause,
        required_minimum_budget=minimum,
        **plan,
        **meta,
    )


def solve(
    data: InputSet,
    budget: float,
    base_year: int = BASE_YEAR,
    settings: SolverSettings = DEFAULT_SETTINGS,
    *,
    market_floor_mult: float | None = None,
    market_cap_mult: float | None = None,
    fair_share_blend: float = 0.5,
    limits: MarketLimits | None = None,
    force_in: Collection[str] = (),
    force_out: Collection[str] = (),
) -> SolveResult:
    """Solve for a total budget (including must-fund) and return the plan and metadata.

    Market floors and caps are off unless a multiplier is given (None turns that side off) or
    explicit `limits` (spend per market) are passed, which replace the computed ones. Candidates
    in `force_in` are fixed to funded and those in `force_out` to not funded, in both stages.
    """
    must_fund_total = sum(m.cost for m in data.must_fund)
    avail = budget - must_fund_total
    from_multipliers = limits is None and (
        market_floor_mult is not None or market_cap_mult is not None
    )
    if from_multipliers:
        limits = fair_share_limits(
            data, avail, market_floor_mult, market_cap_mult, fair_share_blend
        )
    if limits is not None:
        limits = clamp_floors(data, limits)
    meta = dict(
        budget=budget,
        must_fund_total=must_fund_total,
        version_id=data.version_id,
        content_hash=data.content_hash,
        solver_settings={
            **settings.as_dict(),
            "market_floor_mult": market_floor_mult,
            "market_cap_mult": market_cap_mult,
            "fair_share_blend": fair_share_blend,
            "market_floors": (limits.floors or None) if limits else None,
            "market_caps": (limits.caps or None) if limits else None,
        },
    )
    times: dict[str, float] = {}

    def result(selected, status, cause=None, minimum=None):
        return make_result(data, selected, status, base_year, meta, times, cause, minimum)

    force_in, force_out = set(force_in), set(force_out)
    cause = diagnose(data, avail, force_in, force_out, limits)  # pre-solve: no solver call
    if (
        cause is not None
        and from_multipliers
        and cause.code != ReasonCode.FORCED_COST_EXCEEDS_BUDGET
    ):
        advice = multiplier_advice(cause.code, market_floor_mult, market_cap_mult)
        return result(
            None, "Infeasible", Reason(code=cause.code, message=f"{cause.message}; {advice}")
        )
    if cause is not None:
        minimum = required_minimum_budget(data, force_in, limits)
        said = Reason(
            code=cause.code, message=f"{cause.message}; the budget must be at least {minimum:.2f}"
        )
        return result(None, "Infeasible", said, minimum)

    prob1, x1 = build_stage1(data, avail, base_year, limits, force_in, force_out)
    stats1 = prob1.solve(make_solver(settings, settings.time_limit))
    times["stage1"] = stats1.time
    status = map_status(stats1.status)
    if not stats1.has_solution:
        return result(None, status, UNKNOWN_CAUSE if status == "Infeasible" else None)
    plan1 = chosen_ids(data, x1)
    if status != "Optimal":  # stage-1 timeout (or error): report its best plan
        return result(plan1, status)
    remaining = settings.time_limit - stats1.time
    if remaining <= 0:  # no time left for stage 2
        return result(plan1, "TimeLimit")

    r_star = weighted_relief(data, set(plan1), base_year)
    prob2, x2 = build_stage2(
        data, avail, base_year, r_star - settings.relief_slack, limits, force_in, force_out
    )
    stats2 = prob2.solve(make_solver(settings, remaining))
    times["stage2"] = stats2.time
    status2 = map_status(stats2.status)
    assert status2 != "Infeasible", "stage 2 must be feasible: the stage-1 plan satisfies it"
    if status2 != "Optimal":  # stage-2 timeout (or error): keep the stage-1 plan, never "Optimal"
        return result(plan1, status2)
    return result(chosen_ids(data, x2), "Optimal")
