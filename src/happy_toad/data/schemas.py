"""Pydantic schemas for the optimizer inputs. Value checks live in the load-time checks (1.4)."""

from pydantic import BaseModel


class Sector(BaseModel):
    """An area with a shortfall that becomes binding in its trigger year."""

    id: str
    market: str
    shortfall: float
    trigger_year: int


class Candidate(BaseModel):
    """A fundable solution."""

    id: str
    type: str
    cost: float


class Offload(BaseModel):
    """How much of a sector's shortfall a candidate relieves if funded."""

    candidate_id: str
    sector_id: str
    amount: float


class MustFundProject(BaseModel):
    """A project that is always paid, before any candidate."""

    id: str
    cost: float


class InputSet(BaseModel):
    """One versioned bundle of all optimizer inputs."""

    version_id: str
    content_hash: str
    sectors: list[Sector]
    candidates: list[Candidate]
    offloads: list[Offload]
    must_fund: list[MustFundProject]
