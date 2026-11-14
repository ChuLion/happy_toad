"""Unresolved-sectors report (SPEC, M2A decision 8)."""

import pytest
from happy_toad.services.unresolved import unresolved_sectors
from helpers import make_set

from happy_toad.constants import BASE_YEAR


@pytest.fixture
def data():
    return make_set(
        [
            ("a", 10, BASE_YEAR, "M1"),  # weight 1
            ("b", 10, BASE_YEAR + 1, "M2"),  # weight 1/2
            ("c", 10, BASE_YEAR + 1, "M2"),  # weight 1/2
            ("d", 10, BASE_YEAR, "M1"),
        ],
        [("C1", 1)],
        [("C1", "a", 1)],
    )


def test_lists_sectors_with_gap_above_tolerance_by_weighted_gap(data) -> None:
    relief = {"a": 7.0, "b": 0.0, "c": 6.0, "d": 10.0}
    rows = unresolved_sectors(data, relief, BASE_YEAR)
    # weighted gaps: a 3.0, b 5.0, c 2.0; d is resolved
    assert [r.sector_id for r in rows] == ["b", "a", "c"]
    assert rows[0].weighted_gap == pytest.approx(5.0) and rows[0].weight == pytest.approx(0.5)
    assert (rows[0].market, rows[0].shortfall, rows[0].relief, rows[0].gap) == ("M2", 10, 0, 10)


def test_tolerance_is_1e_minus_6(data) -> None:
    relief = {"a": 10 - 1e-6, "b": 10 - 2e-6, "c": 10.0, "d": 10.0}
    assert [r.sector_id for r in unresolved_sectors(data, relief, BASE_YEAR)] == ["b"]


def test_ties_are_broken_by_sector_id(data) -> None:
    relief = {"a": 0.0, "b": 0.0, "c": 0.0, "d": 0.0}
    rows = unresolved_sectors(data, relief, BASE_YEAR)
    assert [r.sector_id for r in rows] == ["a", "d", "b", "c"]  # weighted gap 10, 10, 5, 5


def test_nothing_unresolved_gives_an_empty_list(data) -> None:
    assert unresolved_sectors(data, {s.id: s.shortfall for s in data.sectors}, BASE_YEAR) == []
