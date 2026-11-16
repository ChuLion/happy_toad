"""The solve request and its hash (docs/SPEC.md, M2A)."""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SolveRequest(BaseModel):
    """One question for the optimizer. Value checks against the data live in the gate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_version: str
    budget: float
    force_in: list[str] = []
    force_out: list[str] = []
    label: str = ""
    market_floor_mult: float | None = Field(default=None, ge=0)
    market_cap_mult: float | None = Field(default=None, ge=0)
    region_total_sectors: int | None = Field(default=None, ge=1)
    target_pct_resolved: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Report only: target_met says whether the plan resolves at least this percent "
        "of sectors. It does not change the plan.",
    )

    @field_validator("force_in", "force_out")
    @classmethod
    def _sorted_unique(cls, ids: list[str]) -> list[str]:
        return sorted(set(ids))


def request_hash(request: SolveRequest) -> str:
    """SHA-256 of the canonical JSON of every field except the label."""
    fields = request.model_dump(exclude={"label"})
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
