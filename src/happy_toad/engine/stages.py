"""The two MILPs of the two-stage solve (see docs/SPEC.md and DECISIONS D2).

Stage 1 maximizes weighted relief. Stage 2 minimizes spend subject to keeping that relief (within
the relief slack). Both share the same variables and constraints.
"""

import pulp

from happy_toad.data.schemas import InputSet
from happy_toad.engine.relief import sector_weights
from happy_toad.engine.result import SolverSettings


def _core(data: InputSet, avail: float, sense: int):
    """Variables x[c] (funded) and r[s] (relief), plus the three constraint families."""
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
    return prob, x, r


def build_stage1(data: InputSet, avail: float, base_year: int):
    """Maximize weighted relief. Returns (problem, x by candidate id)."""
    prob, x, r = _core(data, avail, pulp.LpMaximize)
    weight = sector_weights(data, base_year)
    prob.objective = pulp.lpSum(weight[s.id] * r[s.id] for s in data.sectors)
    return prob, x


def build_stage2(data: InputSet, avail: float, base_year: int, min_relief: float):
    """Minimize spend subject to weighted relief >= min_relief. Returns (problem, x)."""
    prob, x, r = _core(data, avail, pulp.LpMinimize)
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
