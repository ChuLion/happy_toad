"""Tests for load-time checks and the JSON loader."""

import json

import pytest

from happy_toad.data.checks import InputError, check_input_set
from happy_toad.data.hashing import build_input_set
from happy_toad.data.loader import load_input_set, save_input_set
from happy_toad.data.schemas import Candidate, MustFundProject, Offload, Sector

BASE_YEAR = 2026


def good(**overrides):
    """A valid input set; keyword arguments replace one of the four lists."""
    lists = {
        "sectors": [Sector(id="S1", market="n", shortfall=10.0, trigger_year=2028)],
        "candidates": [Candidate(id="C1", type="build", cost=5.0)],
        "offloads": [Offload(candidate_id="C1", sector_id="S1", amount=3.0)],
        "must_fund": [MustFundProject(id="M1", cost=2.0)],
    }
    lists.update(overrides)
    return build_input_set("v1", **lists)


def rejects(data, text: str) -> None:
    with pytest.raises(InputError, match=text):
        check_input_set(data, BASE_YEAR)


def test_valid_set_passes() -> None:
    check_input_set(good(), BASE_YEAR)


def test_offload_with_unknown_candidate() -> None:
    rejects(good(offloads=[Offload(candidate_id="X", sector_id="S1", amount=1.0)]), "candidate")


def test_offload_with_unknown_sector() -> None:
    rejects(good(offloads=[Offload(candidate_id="C1", sector_id="X", amount=1.0)]), "sector")


def test_duplicate_ids() -> None:
    dup = [Candidate(id="C1", type="a", cost=1.0), Candidate(id="C1", type="b", cost=2.0)]
    rejects(good(candidates=dup), "duplicate")


def test_duplicate_offload_pair() -> None:
    o = Offload(candidate_id="C1", sector_id="S1", amount=1.0)
    rejects(good(offloads=[o, o]), "duplicate")


@pytest.mark.parametrize("cost", [0.0, -1.0])
def test_candidate_cost_must_be_positive(cost) -> None:
    rejects(good(candidates=[Candidate(id="C1", type="a", cost=cost)]), "cost")


def test_must_fund_cost_must_be_positive() -> None:
    rejects(good(must_fund=[MustFundProject(id="M1", cost=0.0)]), "cost")


def test_offload_amount_must_not_be_negative() -> None:
    rejects(good(offloads=[Offload(candidate_id="C1", sector_id="S1", amount=-1.0)]), "amount")


def test_zero_offload_is_allowed() -> None:
    check_input_set(
        good(offloads=[Offload(candidate_id="C1", sector_id="S1", amount=0.0)]), BASE_YEAR
    )


def test_shortfall_must_not_be_negative() -> None:
    rejects(
        good(sectors=[Sector(id="S1", market="n", shortfall=-1.0, trigger_year=2028)]), "shortfall"
    )


def test_trigger_before_base_year() -> None:
    rejects(
        good(sectors=[Sector(id="S1", market="n", shortfall=1.0, trigger_year=2025)]), "trigger"
    )


def test_all_problems_are_reported_together() -> None:
    bad = good(
        candidates=[Candidate(id="C1", type="a", cost=0.0)],
        offloads=[Offload(candidate_id="C1", sector_id="X", amount=-1.0)],
    )
    with pytest.raises(InputError) as err:
        check_input_set(bad, BASE_YEAR)
    assert len(err.value.problems) == 3


def test_stored_hash_must_match_content(tmp_path) -> None:
    path = tmp_path / "v1.json"
    save_input_set(good(), path)
    assert load_input_set(path, BASE_YEAR) == good()

    raw = json.loads(path.read_text())
    raw["candidates"][0]["cost"] = 4.0
    path.write_text(json.dumps(raw))
    with pytest.raises(InputError, match="content_hash"):
        load_input_set(path, BASE_YEAR)
