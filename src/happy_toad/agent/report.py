"""The report the agent submits: claims as data plus a summary (SPEC, M3 decision 5)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Metric = Literal[
    "weighted_relief",
    "spend",
    "required_minimum_budget",
    "n_selected",
    "n_resolved",
    "pct_resolved",
    "status",
    "target_met",
]
Unit = Literal["need_units", "cost_units", "count", "percent", "none"]

METRIC_UNITS: dict[str, str] = {
    "weighted_relief": "need_units",
    "spend": "cost_units",
    "required_minimum_budget": "cost_units",
    "n_selected": "count",
    "n_resolved": "count",
    "pct_resolved": "percent",
    "status": "none",
    "target_met": "none",
}


class Claim(BaseModel):
    """One checkable statement about a stored run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: Metric
    value: float | int | str | bool
    unit: Unit
    run_id: str
    entity: Literal["plan"]

    @model_validator(mode="after")
    def _unit_fits_metric(self):
        if METRIC_UNITS[self.metric] != self.unit:
            raise ValueError(f"metric {self.metric} takes unit {METRIC_UNITS[self.metric]}")
        return self


class Report(BaseModel):
    """The final answer: a summary and the claims behind every number in it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    claims: list[Claim]
