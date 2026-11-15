"""Per-market spend floors and caps (docs/SPEC.md, "Market floors and caps")."""

from collections import defaultdict
from collections.abc import Collection
from dataclasses import dataclass, field

from happy_toad.data.schemas import InputSet

FEASIBILITY_TOLERANCE = 1e-9


@dataclass(frozen=True)
class MarketLimits:
    """Spend floors and caps per market, in cost units. A missing market has no such limit."""

    floors: dict[str, float] = field(default_factory=dict)
    caps: dict[str, float] = field(default_factory=dict)


def candidate_markets(data: InputSet) -> dict[str, str]:
    """Market of each candidate: that of its largest offload row, ties to the lowest sector id."""
    market = {s.id: s.market for s in data.sectors}
    best: dict[str, tuple[float, str]] = {}
    for o in data.offloads:
        key = (-o.amount, o.sector_id)
        if o.candidate_id not in best or key < best[o.candidate_id]:
            best[o.candidate_id] = key
    return {cid: market[sector_id] for cid, (_, sector_id) in best.items()}


def fair_shares(data: InputSet, blend: float) -> dict[str, float]:
    """blend * (market's share of total shortfall) + (1 - blend) / number of markets."""
    shortfall: dict[str, float] = defaultdict(float)
    for s in data.sectors:
        shortfall[s.market] += s.shortfall
    total = sum(shortfall.values())
    return {m: blend * v / total + (1 - blend) / len(shortfall) for m, v in shortfall.items()}


def fair_share_limits(
    data: InputSet, avail: float, floor_mult: float | None, cap_mult: float | None, blend: float
) -> MarketLimits:
    """Floors and caps as multiples of fair share x avail; a None multiplier turns that side off."""
    share = fair_shares(data, blend)
    floors = {} if floor_mult is None else {m: floor_mult * f * avail for m, f in share.items()}
    caps = {} if cap_mult is None else {m: cap_mult * f * avail for m, f in share.items()}
    return MarketLimits(floors, caps)


def market_spend(data: InputSet, ids: Collection[str] | None = None) -> dict[str, float]:
    """Cost per market of the given candidates, or of all of them when `ids` is None.

    Candidates with no offload row belong to no market.
    """
    market = candidate_markets(data)
    total: dict[str, float] = defaultdict(float)
    for c in data.candidates:
        if c.id in market and (ids is None or c.id in ids):
            total[market[c.id]] += c.cost
    return dict(total)


def clamp_floors(data: InputSet, limits: MarketLimits) -> MarketLimits:
    """Floors cannot exceed what the market's candidates cost in total."""
    cost = market_spend(data)
    floors = {m: min(f, cost.get(m, 0.0)) for m, f in limits.floors.items()}
    return MarketLimits(floors, limits.caps)
