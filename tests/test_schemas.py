"""Tests for the pydantic schemas."""

import pytest
from pydantic import ValidationError

from happy_toad.data.schemas import Candidate, InputSet, MustFundProject, Offload, Sector


def test_models_hold_their_fields() -> None:
    s = Sector(id="S1", market="north", shortfall=10.0, trigger_year=2028)
    c = Candidate(id="C1", type="build", cost=5.0)
    o = Offload(candidate_id="C1", sector_id="S1", amount=3.0)
    m = MustFundProject(id="M1", cost=2.0)
    assert (s.trigger_year, c.cost, o.amount, m.id) == (2028, 5.0, 3.0, "M1")


def test_input_set_holds_all_collections() -> None:
    data = InputSet(
        version_id="v1",
        content_hash="abc",
        sectors=[Sector(id="S1", market="north", shortfall=10.0, trigger_year=2028)],
        candidates=[Candidate(id="C1", type="build", cost=5.0)],
        offloads=[Offload(candidate_id="C1", sector_id="S1", amount=3.0)],
        must_fund=[MustFundProject(id="M1", cost=2.0)],
    )
    assert data.version_id == "v1"
    assert len(data.sectors) == len(data.candidates) == len(data.offloads) == 1


def test_wrong_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Sector(id="S1", market="north", shortfall="lots", trigger_year=2028)


def test_missing_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Candidate(id="C1", type="build")
