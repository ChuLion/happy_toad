"""Unresolved-sectors report: sectors still short after a plan, largest weighted gap first."""

from pydantic import BaseModel, ConfigDict

from happy_toad.data.schemas import InputSet
from happy_toad.engine.relief import RESOLVED_TOLERANCE, sector_weights


class SectorGap(BaseModel):
    """One sector that is still short."""

    model_config = ConfigDict(frozen=True)

    sector_id: str
    market: str
    shortfall: float
    relief: float
    gap: float
    weight: float
    weighted_gap: float


def unresolved_sectors(data: InputSet, relief: dict[str, float], base_year: int) -> list[SectorGap]:
    """Sectors with shortfall - relief above 1e-6, sorted by weight * gap (ties: sector id)."""
    weight = sector_weights(data, base_year)
    rows = [
        SectorGap(
            sector_id=s.id,
            market=s.market,
            shortfall=s.shortfall,
            relief=relief[s.id],
            gap=s.shortfall - relief[s.id],
            weight=weight[s.id],
            weighted_gap=weight[s.id] * (s.shortfall - relief[s.id]),
        )
        for s in data.sectors
        if s.shortfall - relief[s.id] > RESOLVED_TOLERANCE
    ]
    return sorted(rows, key=lambda r: (-r.weighted_gap, r.sector_id))
