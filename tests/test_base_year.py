"""End to end: the planning window starts at BASE_YEAR and the model weights it as 1.0."""

import pytest

from happy_toad.constants import BASE_YEAR
from happy_toad.data.generator import make_v1
from happy_toad.engine.model import solve
from happy_toad.engine.relief import sector_weights


@pytest.mark.parametrize("seed", [1, 2, 3, 42])
def test_earliest_trigger_year_is_base_year_and_weighs_exactly_one(seed) -> None:
    data = make_v1(seed)
    assert min(s.trigger_year for s in data.sectors) == BASE_YEAR
    result = solve(data, budget=sum(m.cost for m in data.must_fund))
    assert result.base_year == BASE_YEAR
    weights = sector_weights(data, result.base_year)
    first = [s for s in data.sectors if s.trigger_year == BASE_YEAR]
    assert first and all(weights[s.id] == 1.0 for s in first)
    assert all(weights[s.id] < 1.0 for s in data.sectors if s.trigger_year > BASE_YEAR)
