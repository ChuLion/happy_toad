"""Cheapest plan that resolves at least k sectors (docs/SPEC.md, M2B).

Stage 1 minimizes candidate cost subject to at least k resolved sectors. Stage 2 keeps that cost
(within COST_SLACK) and maximizes weighted relief, so ties are broken deterministically. The time
limit covers both stages together.
"""

import math
from collections.abc import Collection
from dataclasses import dataclass

import pulp

from happy_toad.constants import BASE_YEAR
from happy_toad.data.schemas import InputSet
from happy_toad.engine.relief import RESOLVED_TOLERANCE, resolved_count, sector_weights
from happy_toad.engine.result import DEFAULT_SETTINGS, SolverSettings
from happy_toad.engine.stages import chosen_ids, make_solver
from happy_toad.engine.status import map_status

COST_SLACK = 1e-6


@dataclass
class CheapestPlan:
    """Stage result: `cost` is the plan's candidate cost; proven minimal only when Optimal."""

    status: str
    selected: list[str] | None
    cost: float | None
    times: dict[str, float]


def target_sectors(target_pct: float, n_sectors: int) -> int:
    """The target as a sector count, rounded up: 50% of 80 is 40."""
    return math.ceil(target_pct * n_sectors / 100 - 1e-9)


def round_up_cent(amount: float) -> float:
    """Round up to the cent; the inner round removes float noise such as 1145.2100000001."""
    return math.ceil(round(amount * 100, 6)) / 100


def max_resolvable(data: InputSet, force_out: Collection[str] = ()) -> int:
    """Sectors resolved when every candidate that is not forced out is funded."""
    return resolved_count(data, {c.id for c in data.candidates} - set(force_out))


def _cost(data: InputSet, selected: list[str]) -> float:
    return sum(c.cost for c in data.candidates if c.id in selected)


def _model(data: InputSet, k: int, force_in, force_out, sense: int):
    """x[c] funded, z[s] resolved, r[s] relief; at least k sectors resolved; forced x fixed."""
    prob = pulp.LpProblem("target_budget", sense)
    x = prob.add_variable_dicts("x", [c.id for c in data.candidates], cat="Binary")
    z = prob.add_variable_dicts("z", [s.id for s in data.sectors], cat="Binary")
    r = prob.add_variable_dicts("r", [s.id for s in data.sectors], lowBound=0)
    for s in data.sectors:
        supply = pulp.lpSum(
            o.amount * x[o.candidate_id] for o in data.offloads if o.sector_id == s.id
        )
        prob.add(supply >= (s.shortfall - RESOLVED_TOLERANCE) * z[s.id], f"resolved_{s.id}")
        prob.add(r[s.id] <= s.shortfall, f"need_{s.id}")
        prob.add(r[s.id] <= supply, f"supply_{s.id}")
    prob.add(pulp.lpSum(z.values()) >= k, "target")
    for cid in force_in:
        prob.add(x[cid] == 1, f"force_in_{cid}")
    for cid in force_out:
        prob.add(x[cid] == 0, f"force_out_{cid}")
    cost = pulp.lpSum(c.cost * x[c.id] for c in data.candidates)
    return prob, x, r, cost


def cheapest_plan(
    data: InputSet,
    k: int,
    force_in: Collection[str] = (),
    force_out: Collection[str] = (),
    base_year: int = BASE_YEAR,
    settings: SolverSettings = DEFAULT_SETTINGS,
) -> CheapestPlan:
    """The cheapest plan resolving at least k sectors; ties go to the most weighted relief."""
    times: dict[str, float] = {}
    prob1, x1, _, cost1 = _model(data, k, force_in, force_out, pulp.LpMinimize)
    prob1.objective = cost1
    stats1 = prob1.solve(make_solver(settings, settings.time_limit))
    times["stage1"] = stats1.time
    status = map_status(stats1.status)
    if not stats1.has_solution:
        return CheapestPlan(status, None, None, times)
    plan1 = chosen_ids(data, x1)
    remaining = settings.time_limit - stats1.time
    if status != "Optimal" or remaining <= 0:
        return CheapestPlan(status if status != "Optimal" else "TimeLimit", plan1, None, times)

    prob2, x2, r2, cost2 = _model(data, k, force_in, force_out, pulp.LpMaximize)
    weight = sector_weights(data, base_year)
    prob2.objective = pulp.lpSum(weight[s.id] * r2[s.id] for s in data.sectors)
    prob2.add(cost2 <= _cost(data, plan1) + COST_SLACK, "cheapest_cost")
    stats2 = prob2.solve(make_solver(settings, remaining))
    times["stage2"] = stats2.time
    status2 = map_status(stats2.status)
    if status2 != "Optimal":
        return CheapestPlan(status2, plan1, None, times)
    plan2 = chosen_ids(data, x2)
    return CheapestPlan("Optimal", plan2, _cost(data, plan2), times)
