"""Solver settings and the solve result."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from happy_toad.reasons import Reason


@dataclass(frozen=True)
class SolverSettings:
    """Pinned CBC settings plus delta, the smallest relief difference we care about.

    Stage 2 may give up at most relief_slack = delta / 10 of relief to save spend. The time limit
    (seconds) covers both stages together.
    """

    threads: int = 1
    time_limit: int = 30
    gap_rel: float = 0.0
    gap_abs: float = 0.0
    delta: float = 1e-4

    def as_dict(self) -> dict[str, float]:
        """The settings as recorded in results and run records."""
        return {
            "threads": self.threads,
            "timeLimit": self.time_limit,
            "gapRel": self.gap_rel,
            "gapAbs": self.gap_abs,
            "delta": self.delta,
            "relief_slack": self.relief_slack,
        }

    @property
    def relief_slack(self) -> float:
        """Relief stage 2 may give up: delta / 10."""
        return self.delta / 10


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
    stage_times: dict[str, float]
    budget: float
    must_fund_total: float
    base_year: int
    version_id: str
    content_hash: str
    solver_settings: dict[str, float | dict[str, float] | None]
    cause: Reason | None = None  # set when status is Infeasible
    required_minimum_budget: float | None = None  # lower bound, only for a known cause
