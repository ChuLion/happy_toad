"""Solver settings and the solve result."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True)
class SolverSettings:
    """Pinned CBC settings plus the tie-break delta (weighted-relief units)."""

    threads: int = 1
    time_limit: int = 30
    gap_rel: float = 0.0
    gap_abs: float = 0.0
    delta: float = 1e-4


DEFAULT_SETTINGS = SolverSettings()


class SolveResult(BaseModel):
    """Outcome of one solve. The plan fields are None when there is no plan (not an empty plan)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    objective: float | None
    selected: list[str] | None
    relief: dict[str, float] | None
    spend: float | None
    solve_time: float
    budget: float
    must_fund_total: float
    base_year: int
    version_id: str
    content_hash: str
    solver_settings: dict[str, float]
