"""The PuLP/CBC model: maximize weighted shortfall relief within the budget (see docs/SPEC.md)."""

import pulp

from happy_toad.data.schemas import InputSet
from happy_toad.engine.result import DEFAULT_SETTINGS, SolveResult, SolverSettings
from happy_toad.engine.status import map_status

BASE_YEAR = 2026


def compute_epsilon(avail: float, delta: float) -> float:
    """Tie-break weight per unit cost: delta / (10 * avail), or 0 if nothing is fundable."""
    return delta / (10 * avail) if avail > 0 else 0.0


def sector_weights(data: InputSet, base_year: int) -> dict[str, float]:
    """weight[s] = 1 / (trigger_year - base_year + 1)."""
    return {s.id: 1 / (s.trigger_year - base_year + 1) for s in data.sectors}


def build_model(data: InputSet, avail: float, base_year: int, eps: float):
    """Build the MILP. Returns (problem, x by candidate id, r by sector id)."""
    weight = sector_weights(data, base_year)
    prob = pulp.LpProblem("happy_toad", pulp.LpMaximize)
    x = prob.add_variable_dicts("x", [c.id for c in data.candidates], cat="Binary")
    r = prob.add_variable_dicts("r", [s.id for s in data.sectors], lowBound=0)

    prob.objective = pulp.lpSum(weight[s.id] * r[s.id] for s in data.sectors) - eps * pulp.lpSum(
        c.cost * x[c.id] for c in data.candidates
    )
    for s in data.sectors:
        supply = pulp.lpSum(
            o.amount * x[o.candidate_id] for o in data.offloads if o.sector_id == s.id
        )
        prob.add(r[s.id] <= s.shortfall, f"need_{s.id}")
        prob.add(r[s.id] <= supply, f"supply_{s.id}")
    prob.add(pulp.lpSum(c.cost * x[c.id] for c in data.candidates) <= avail, "budget")
    return prob, x, r


def make_solver(settings: SolverSettings) -> pulp.COIN_CMD:
    """CBC with the pinned settings."""
    return pulp.COIN_CMD(
        msg=False,
        threads=settings.threads,
        timeLimit=settings.time_limit,
        gapRel=settings.gap_rel,
        gapAbs=settings.gap_abs,
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
    eps = compute_epsilon(avail, settings.delta)
    meta = dict(
        budget=budget,
        must_fund_total=must_fund_total,
        base_year=base_year,
        version_id=data.version_id,
        content_hash=data.content_hash,
        solver_settings={
            "threads": settings.threads,
            "timeLimit": settings.time_limit,
            "gapRel": settings.gap_rel,
            "gapAbs": settings.gap_abs,
            "epsilon": eps,
            "delta": settings.delta,
        },
    )
    no_plan = dict(objective=None, selected=None, relief=None, spend=None)
    if avail < 0:  # pre-solve check: must-fund alone exceeds the budget
        return SolveResult(status="Infeasible", solve_time=0.0, **no_plan, **meta)

    prob, x, r = build_model(data, avail, base_year, eps)
    stats = prob.solve(make_solver(settings))
    status = map_status(stats.status)
    if not stats.has_solution:
        return SolveResult(status=status, solve_time=stats.time, **no_plan, **meta)

    weight = sector_weights(data, base_year)
    relief = {s.id: r[s.id].value() for s in data.sectors}
    selected = [c.id for c in data.candidates if x[c.id].value() > 0.5]
    plan = dict(
        objective=sum(weight[s] * v for s, v in relief.items()),
        selected=selected,
        relief=relief,
        spend=sum(c.cost for c in data.candidates if c.id in selected),
    )
    return SolveResult(status=status, solve_time=stats.time, **plan, **meta)
