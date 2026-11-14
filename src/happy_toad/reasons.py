"""Reason codes: why a request is rejected, or why a solve is infeasible."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ReasonCode(StrEnum):
    """Codes from the request gate and from the infeasibility explanation (docs/SPEC.md, M2A)."""

    VERSION_NOT_FOUND = "VERSION_NOT_FOUND"
    BUDGET_NOT_POSITIVE = "BUDGET_NOT_POSITIVE"
    BUDGET_ABOVE_CAP = "BUDGET_ABOVE_CAP"
    UNKNOWN_CANDIDATE = "UNKNOWN_CANDIDATE"
    FORCE_CONFLICT = "FORCE_CONFLICT"
    FORCED_COST_EXCEEDS_BUDGET = "FORCED_COST_EXCEEDS_BUDGET"
    FLOORS_EXCEED_BUDGET = "FLOORS_EXCEED_BUDGET"
    CAP_BELOW_FLOOR = "CAP_BELOW_FLOOR"
    FORCED_IN_EXCEEDS_CAP = "FORCED_IN_EXCEEDS_CAP"
    FLOOR_UNREACHABLE = "FLOOR_UNREACHABLE"
    CAUSE_UNKNOWN = "CAUSE_UNKNOWN"
    SCHEMA_INVALID = "SCHEMA_INVALID"  # an agent tool input that does not fit the request schema


class Reason(BaseModel):
    """A code and a human-readable message."""

    model_config = ConfigDict(frozen=True)

    code: ReasonCode
    message: str
