"""Relief of a set of funded candidates, computed directly from the input data."""

from happy_toad.data.schemas import InputSet


def sector_weights(data: InputSet, base_year: int) -> dict[str, float]:
    """weight[s] = 1 / (trigger_year - base_year + 1)."""
    return {s.id: 1 / (s.trigger_year - base_year + 1) for s in data.sectors}


def sector_relief(data: InputSet, chosen: set[str]) -> dict[str, float]:
    """Relief per sector if exactly the `chosen` candidates are funded: min(shortfall, supply)."""
    supply = {s.id: 0.0 for s in data.sectors}
    for o in data.offloads:
        if o.candidate_id in chosen:
            supply[o.sector_id] += o.amount
    return {s.id: min(s.shortfall, supply[s.id]) for s in data.sectors}


def weighted(relief: dict[str, float], weight: dict[str, float]) -> float:
    """Sum over sectors of weight * relief."""
    return sum(weight[s] * v for s, v in relief.items())


def weighted_relief(data: InputSet, chosen: set[str], base_year: int) -> float:
    """Weighted relief if exactly the `chosen` candidates are funded."""
    return weighted(sector_relief(data, chosen), sector_weights(data, base_year))
