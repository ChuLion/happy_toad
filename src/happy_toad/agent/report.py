"""The report the agent submits: claims as data plus a summary (SPEC, M3 decision 5)."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Metric = Literal[
    "weighted_relief",
    "spend",
    "required_minimum_budget",
    "n_selected",
    "n_resolved",
    "n_sectors",
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
    "n_sectors": "count",
    "pct_resolved": "percent",
    "status": "none",
    "target_met": "none",
}


COUNT_METRICS = {"n_selected", "n_resolved", "n_sectors"}
TEXT_METRICS = {"status", "target_met"}
PLAIN_DECIMAL = re.compile(r"-?\d+(\.\d+)?", re.ASCII)
WHOLE_NUMBER = re.compile(r"\d+", re.ASCII)


class Claim(BaseModel):
    """One checkable statement about a stored run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: Metric
    value: float | int | str | bool
    unit: Unit
    run_id: str
    entity: Literal["plan"]

    @model_validator(mode="before")
    @classmethod
    def _coerce_plain_numbers(cls, data):
        """A numeric metric may arrive as a plain-number string ("485.59", "21"); nothing else."""
        if not isinstance(data, dict):
            return data
        metric, value = data.get("metric"), data.get("value")
        if metric not in METRIC_UNITS or metric in TEXT_METRICS or not isinstance(value, str):
            return data
        count = metric in COUNT_METRICS
        if not (WHOLE_NUMBER if count else PLAIN_DECIMAL).fullmatch(value):
            kind = "a whole number" if count else "a plain number such as 485.59"
            raise ValueError(f"{metric} must be {kind}, not {value!r}")
        return {**data, "value": int(value) if count else float(value)}

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


def coercions(arguments: str, report: Report) -> list[dict]:
    """Claims whose value the schema turned from a string into a number."""
    raw = json.loads(arguments)["claims"]
    return [
        {"metric": c.metric, "run_id": c.run_id, "from": r["value"], "to": c.value}
        for r, c in zip(raw, report.claims, strict=True)
        if isinstance(r["value"], str) and not isinstance(c.value, str)
    ]
