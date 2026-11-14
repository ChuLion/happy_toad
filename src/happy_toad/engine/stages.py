"""The two MILPs of the two-stage solve (see docs/SPEC.md and DECISIONS D2).

Stage 1 maximizes weighted relief. Stage 2 minimizes spend subject to keeping that relief (within
the relief slack). Both share the same variables and constraints, including the optional market
floors and caps (added once, in _core).
"""

from collections import defaultdict

import pulp

from happy_toad.data.schemas import InputSet
from happy_toad.engine.markets import MarketLimits, candidate_markets
from happy_toad.engine.relief import sector_weights
from happy_toad.engine.result import SolverSettings


def _market_limits(prob, data: InputSet, x: dict, limits: MarketLimits) -> None:
    """Per-market spend floors and caps (markets without candidates add no constraint)."""
    market = candidate_markets(data)
    terms: dict[str, list] = defaultdict(list)
    for c in data.candidates:
        if c.id in market:
            terms[market[c.id]].append(c.cost * x[c.id])
    for m, amount in limits.floors.items():
        if m in terms:
            prob.add(pulp.lpSum(terms[m]) >= amount, f"floor_{m}")
    for m, amount in limits.caps.items():
        if m in terms:
            prob.add(pulp.lpSum(terms[m]) <= amount, f"cap_{m}")


def _core(data: InputSet, avail: float, sense: int, limits: MarketLimits | None = None):
    """Variables x[c] (funded) and r[s] (relief), the three constraint families, market limits."""
    prob = pulp.LpProblem("happy_toad", sense)
    x = prob.add_variable_dicts("x", [c.id for c in data.candidates], cat="Binary")
    r = prob.add_variable_dicts("r", [s.id for s in data.sectors], lowBound=0)
    for s in data.sectors:
        supply = pulp.lpSum(
            o.amount * x[o.candidate_id] for o in data.offloads if o.sector_id == s.id
        )
        prob.add(r[s.id] <= s.shortfall, f"need_{s.id}")
        prob.add(r[s.id] <= supply, f"supply_{s.id}")
    prob.add(pulp.lpSum(c.cost * x[c.id] for c in data.candidates) <= avail, "budget")
    if limits is not None:
        _market_limits(prob, data, x, limits)
    return prob, x, r


def build_stage1(data: InputSet, avail: float, base_year: int, limits: MarketLimits | None = None):
    """Maximize weighted relief. Returns (problem, x by candidate id)."""
    prob, x, r = _core(data, avail, pulp.LpMaximize, limits)
    weight = sector_weights(data, base_year)
    prob.objective = pulp.lpSum(weight[s.id] * r[s.id] for s in data.sectors)
    return prob, x


def build_stage2(
    data: InputSet,
    avail: float,
    base_year: int,
    min_relief: float,
    limits: MarketLimits | None = None,
):
    """Minimize spend subject to weighted relief >= min_relief. Returns (problem, x)."""
    prob, x, r = _core(data, avail, pulp.LpMinimize, limits)
    weight = sector_weights(data, base_year)
    prob.objective = pulp.lpSum(c.cost * x[c.id] for c in data.candidates)
    prob.add(pulp.lpSum(weight[s.id] * r[s.id] for s in data.sectors) >= min_relief, "relief_floor")
    return prob, x


def make_solver(settings: SolverSettings, time_limit: float) -> pulp.COIN_CMD:
    """CBC with the pinned settings and the given time limit (seconds)."""
    return pulp.COIN_CMD(
        msg=False,
        threads=settings.threads,
        timeLimit=time_limit,
        gapRel=settings.gap_rel,
        gapAbs=settings.gap_abs,
    )


def chosen_ids(data: InputSet, x: dict) -> list[str]:
    """Ids of the candidates the solver funded."""
    return [c.id for c in data.candidates if x[c.id].value() > 0.5]
