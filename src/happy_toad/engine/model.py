"""Two-stage solve: optimal relief within delta/10, then minimum spend among plans delivering it.

Stage 1 maximizes weighted relief (R*). Stage 2 minimizes spend subject to weighted relief >=
R* - relief_slack, where relief_slack = delta / 10. The time limit covers both stages together.
"""

from happy_toad.data.schemas import InputSet
from happy_toad.engine.relief import sector_relief, sector_weights, weighted, weighted_relief
from happy_toad.engine.result import DEFAULT_SETTINGS, SolveResult, SolverSettings
from happy_toad.engine.stages import build_stage1, build_stage2, chosen_ids, make_solver
from happy_toad.engine.status import map_status

BASE_YEAR = 2026


def make_result(data, selected, status, base_year, meta, times) -> SolveResult:
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
        **plan,
        **meta,
    )


def solve(
    data: InputSet,
    budget: float,
    base_year: int = BASE_YEAR,
    settings: SolverSettings = DEFAULT_SETTINGS,
) -> SolveResult:
    """Solve for a total budget (including must-fund) and return the plan and metadata."""
    must_fund_total = sum(m.cost for m in data.must_fund)
    avail = budget - must_fund_total
    meta = dict(
        budget=budget,
        must_fund_total=must_fund_total,
        version_id=data.version_id,
        content_hash=data.content_hash,
        solver_settings={
            "threads": settings.threads,
            "timeLimit": settings.time_limit,
            "gapRel": settings.gap_rel,
            "gapAbs": settings.gap_abs,
            "delta": settings.delta,
            "relief_slack": settings.relief_slack,
        },
    )
    times: dict[str, float] = {}

    def result(selected, status):
        return make_result(data, selected, status, base_year, meta, times)

    if avail < 0:  # pre-solve check: must-fund alone exceeds the budget
        return result(None, "Infeasible")

    prob1, x1 = build_stage1(data, avail, base_year)
    stats1 = prob1.solve(make_solver(settings, settings.time_limit))
    times["stage1"] = stats1.time
    status = map_status(stats1.status)
    if not stats1.has_solution:
        return result(None, status)
    plan1 = chosen_ids(data, x1)
    if status != "Optimal":  # stage-1 timeout (or error): report its best plan
        return result(plan1, status)
    remaining = settings.time_limit - stats1.time
    if remaining <= 0:  # no time left for stage 2
        return result(plan1, "TimeLimit")

    r_star = weighted_relief(data, set(plan1), base_year)
    prob2, x2 = build_stage2(data, avail, base_year, r_star - settings.relief_slack)
    stats2 = prob2.solve(make_solver(settings, remaining))
    times["stage2"] = stats2.time
    status2 = map_status(stats2.status)
    assert status2 != "Infeasible", "stage 2 must be feasible: the stage-1 plan satisfies it"
    if status2 != "Optimal":  # stage-2 timeout (or error): keep the stage-1 plan, never "Optimal"
        return result(plan1, status2)
    return result(chosen_ids(data, x2), "Optimal")
