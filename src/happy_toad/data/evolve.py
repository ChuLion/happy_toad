"""Derive v2, the refreshed forecast, from v1, the plan of record.

A mid-year update: re-estimated costs, moved trigger years and new sectors (plus changed
offloads), every change recorded in a change list.
"""

import numpy as np

from happy_toad.data.config import DEFAULT_CONFIG, GeneratorConfig
from happy_toad.data.generator import draw_market, draw_resolving_offload, draw_sector
from happy_toad.data.hashing import build_input_set
from happy_toad.data.schemas import InputSet

Change = dict


def _scaled(rng: np.random.Generator, value: float) -> float:
    """Value times a factor from 0.5-0.9 or 1.1-1.5, so the result always differs."""
    low, high = (0.5, 0.9) if rng.random() < 0.5 else (1.1, 1.5)
    return round(float(value * rng.uniform(low, high)), 2)


def _pick(rng: np.random.Generator, n_items: int, n: int) -> list[int]:
    return [int(i) for i in rng.choice(n_items, size=n, replace=False)]


def _new_sectors(rng, cfg, v1: InputSet) -> tuple[list, list, list[Change]]:
    """New sectors, each relieved by exactly one existing candidate (one new offload row)."""
    sectors, offloads, changes = [], [], []
    for k in range(cfg.new_sectors):
        sector = draw_sector(rng, cfg, f"S{len(v1.sectors) + k + 1:03d}", draw_market(rng, cfg))
        owner = v1.candidates[int(rng.integers(len(v1.candidates)))]
        row = draw_resolving_offload(rng, cfg, owner.id, sector)
        sectors.append(sector)
        offloads.append(row)
        changes.append(
            {"kind": "sector_added", "sector": sector.model_dump(), "offloads": [row.model_dump()]}
        )
    return sectors, offloads, changes


def _moved_triggers(rng, cfg, v1: InputSet) -> tuple[dict, list[Change]]:
    years = range(cfg.base_year, cfg.last_year + 1)
    new_year, changes = {}, []
    for i in _pick(rng, len(v1.sectors), cfg.moved_triggers):
        s = v1.sectors[i]
        options = [y for y in years if y != s.trigger_year]
        new_year[s.id] = int(rng.choice(options))
        changes.append(
            {
                "kind": "trigger_moved",
                "sector_id": s.id,
                "old": s.trigger_year,
                "new": new_year[s.id],
            }
        )
    return new_year, changes


def _changed_costs(rng, cfg, v1: InputSet) -> tuple[dict, list[Change]]:
    new_cost, changes = {}, []
    for i in _pick(rng, len(v1.candidates), cfg.cost_changes):
        c = v1.candidates[i]
        new_cost[c.id] = _scaled(rng, c.cost)
        changes.append(
            {"kind": "cost_changed", "candidate_id": c.id, "old": c.cost, "new": new_cost[c.id]}
        )
    return new_cost, changes


def _changed_offloads(rng, cfg, v1: InputSet) -> tuple[dict, list[Change]]:
    new_amount, changes = {}, []
    for i in _pick(rng, len(v1.offloads), cfg.offload_changes):
        o = v1.offloads[i]
        new_amount[(o.candidate_id, o.sector_id)] = _scaled(rng, o.amount)
        changes.append(
            {
                "kind": "offload_changed",
                "candidate_id": o.candidate_id,
                "sector_id": o.sector_id,
                "old": o.amount,
                "new": new_amount[(o.candidate_id, o.sector_id)],
            }
        )
    return new_amount, changes


def make_v2(
    v1: InputSet, seed: int, cfg: GeneratorConfig = DEFAULT_CONFIG
) -> tuple[InputSet, list[Change]]:
    """Return (v2, change list). v2 = v1 + new sectors, moved triggers, cost and offload changes."""
    rng = np.random.default_rng([seed, 2])
    added_sectors, added_offloads, added_changes = _new_sectors(rng, cfg, v1)
    year, year_changes = _moved_triggers(rng, cfg, v1)
    cost, cost_changes = _changed_costs(rng, cfg, v1)
    amount, amount_changes = _changed_offloads(rng, cfg, v1)

    sectors = [
        s.model_copy(update={"trigger_year": year.get(s.id, s.trigger_year)}) for s in v1.sectors
    ]
    candidates = [c.model_copy(update={"cost": cost.get(c.id, c.cost)}) for c in v1.candidates]
    offloads = [
        o.model_copy(update={"amount": amount.get((o.candidate_id, o.sector_id), o.amount)})
        for o in v1.offloads
    ]
    v2 = build_input_set(
        "v2", sectors + added_sectors, candidates, offloads + added_offloads, list(v1.must_fund)
    )
    return v2, added_changes + year_changes + cost_changes + amount_changes
