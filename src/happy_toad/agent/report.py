"""The report the agent submits: claims as data plus a summary (SPEC, M3 decision 5)."""

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    "must_fund_cost",
    "forced_cost",
    "target_budget",
    "target_sectors",
    "max_resolvable",
    "max_pct_resolvable",
    "diff_spend",
    "diff_weighted_relief",
    "diff_n_selected",
    "diff_n_resolved",
    "diff_pct_resolved",
]
Unit = Literal["need_units", "cost_units", "count", "percent", "none"]

DIFF_BASE = {
    "diff_spend": "spend",
    "diff_weighted_relief": "weighted_relief",
    "diff_n_selected": "n_selected",
    "diff_n_resolved": "n_resolved",
    "diff_pct_resolved": "pct_resolved",
}
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
    "must_fund_cost": "cost_units",
    "forced_cost": "cost_units",
    "target_budget": "cost_units",
    "target_sectors": "count",
    "max_resolvable": "count",
    "max_pct_resolvable": "percent",
}
METRIC_UNITS |= {diff: METRIC_UNITS[base] for diff, base in DIFF_BASE.items()}

SIGNED_COUNTS = {"diff_n_selected", "diff_n_resolved"}
COUNT_METRICS = {"n_selected", "n_resolved", "n_sectors", "target_sectors", "max_resolvable"}
COUNT_METRICS |= SIGNED_COUNTS
TEXT_METRICS = {"status", "target_met"}
PLAIN_DECIMAL = re.compile(r"-?\d+(\.\d+)?", re.ASCII)
WHOLE_NUMBER = re.compile(r"\d+", re.ASCII)
SIGNED_WHOLE = re.compile(r"-?\d+", re.ASCII)
DEFAULTED = ("unit", "entity")


def _plain_number(metric: str, value: str) -> float | int:
    """A plain-number string as a number for a numeric metric ("485.59", "21"); nothing else."""
    if metric in COUNT_METRICS:
        pattern = SIGNED_WHOLE if metric in SIGNED_COUNTS else WHOLE_NUMBER
        if pattern.fullmatch(value):
            return int(value)
        raise ValueError(f"{metric} must be a whole number, not {value!r}")
    if PLAIN_DECIMAL.fullmatch(value):
        return float(value)
    raise ValueError(f"{metric} must be a plain number such as 485.59, not {value!r}")


class Claim(BaseModel):
    """One checkable statement about a stored run (diff_* metrics: run_id_b minus run_id)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: Metric
    value: float | int | str | bool
    unit: Unit | None = Field(default=None, description="Optional; set from the metric.")
    run_id: str
    run_id_b: str | None = Field(
        default=None,
        description="Only for diff_* metrics: the second run; value is run_id_b minus run_id, "
        "as compare_runs reports it.",
    )
    entity: Literal["plan"] = "plan"

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        """Unit from the metric, entity always "plan", plain-number strings as numbers."""
        if not isinstance(data, dict) or data.get("metric") not in METRIC_UNITS:
            return data
        metric, value = data["metric"], data.get("value")
        data = {**data, "unit": METRIC_UNITS[metric], "entity": "plan"}
        if metric not in TEXT_METRICS and isinstance(value, str):
            data["value"] = _plain_number(metric, value)
        return data

    @model_validator(mode="after")
    def _second_run_only_for_differences(self):
        if (self.metric in DIFF_BASE) != (self.run_id_b is not None):
            raise ValueError("run_id_b is required for diff_* metrics and allowed only for them")
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


def defaults(arguments: str, report: Report) -> list[dict]:
    """Claims whose unit or entity the schema set or replaced, with what the model sent."""
    raw = json.loads(arguments)["claims"]
    return [
        {"field": f, "metric": c.metric, "run_id": c.run_id, "from": r.get(f), "to": getattr(c, f)}
        for r, c in zip(raw, report.claims, strict=True)
        for f in DEFAULTED
        if r.get(f) != getattr(c, f)
    ]
