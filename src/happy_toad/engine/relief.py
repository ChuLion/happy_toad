"""Weighted relief of a set of funded candidates, computed directly from the input data."""

from happy_toad.data.schemas import InputSet
from happy_toad.engine.model import sector_weights


def weighted_relief(data: InputSet, chosen: set[str], base_year: int) -> float:
    """Weighted relief if exactly the `chosen` candidates are funded."""
    weight = sector_weights(data, base_year)
    supply = {s.id: 0.0 for s in data.sectors}
    for o in data.offloads:
        if o.candidate_id in chosen:
            supply[o.sector_id] += o.amount
    return sum(weight[s.id] * min(s.shortfall, supply[s.id]) for s in data.sectors)
