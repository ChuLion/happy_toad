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
    "n_unresolved",
    "n_sectors",
    "pct_resolved",
    "pct_of_region",
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
    "n_added",
    "n_dropped",
    "n_sectors_added",
    "n_sectors_removed",
    "n_triggers_moved",
    "n_costs_changed",
    "n_offloads_changed",
    "effect_relief",
    "effect_spend",
    "effect_n_resolved",
    "total_relief",
    "total_spend",
    "total_n_resolved",
    "n_sectors_shared",
    "n_resolved_shared_a",
    "n_resolved_shared_b",
    "n_sectors_new",
    "n_resolved_new",
]
Kind = Literal["costs", "offloads", "triggers", "sectors"]  # M5: the attribution order
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
    "n_unresolved": "count",
    "n_sectors": "count",
    "pct_resolved": "percent",
    "pct_of_region": "percent",
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
METRIC_UNITS |= {"n_added": "count", "n_dropped": "count"}
SELECTION_PAIRS = {"n_added", "n_dropped"}  # candidates only in run_id_b, only in run_id
PAIR_METRICS = set(DIFF_BASE) | SELECTION_PAIRS

EFFECT_METRICS = {"effect_relief", "effect_spend", "effect_n_resolved"}  # entity = a kind
TOTAL_METRICS = {"total_relief", "total_spend", "total_n_resolved"}
REVISION_COUNTS = {
    "n_sectors_added", "n_sectors_removed", "n_triggers_moved", "n_costs_changed",
    "n_offloads_changed", "n_sectors_shared", "n_resolved_shared_a", "n_resolved_shared_b",
    "n_sectors_new", "n_resolved_new",
}  # fmt: skip
ATTRIBUTION_METRICS = EFFECT_METRICS | TOTAL_METRICS  # none when the attribution is incomplete
REVISION_METRICS = ATTRIBUTION_METRICS | REVISION_COUNTS
METRIC_UNITS |= {m: "count" for m in REVISION_COUNTS}
METRIC_UNITS |= {f"{p}_relief": "need_units" for p in ("effect", "total")}
METRIC_UNITS |= {f"{p}_spend": "cost_units" for p in ("effect", "total")}
METRIC_UNITS |= {f"{p}_n_resolved": "count" for p in ("effect", "total")}

SIGNED_COUNTS = {"diff_n_selected", "diff_n_resolved", "effect_n_resolved", "total_n_resolved"}
COUNT_METRICS = {"n_selected", "n_resolved", "n_sectors", "target_sectors", "max_resolvable"}
COUNT_METRICS |= {"n_unresolved"}
COUNT_METRICS |= SELECTION_PAIRS
COUNT_METRICS |= SIGNED_COUNTS
COUNT_METRICS |= REVISION_COUNTS
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
        description="Only for diff_*, n_added and n_dropped: the second run; a diff_ value is "
        "run_id_b minus run_id, n_added counts candidates only in run_id_b, n_dropped only in "
        "run_id; "
        "as compare_runs reports it.",
    )
    entity: Literal["plan"] | Kind = Field(
        default="plan",
        description="Only for effect_*: the change kind (costs, offloads, triggers, sectors); "
        "set to plan for every other metric.",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data):
        """Unit from the metric, entity "plan" (kept for effect_*), plain numbers as numbers."""
        if not isinstance(data, dict) or data.get("metric") not in METRIC_UNITS:
            return data
        metric, value = data["metric"], data.get("value")
        data = {**data, "unit": METRIC_UNITS[metric]}
        if metric not in EFFECT_METRICS:
            data["entity"] = "plan"
        if metric not in TEXT_METRICS and isinstance(value, str):
            data["value"] = _plain_number(metric, value)
        if metric in COUNT_METRICS and isinstance(value, float) and value.is_integer():
            data["value"] = int(value)  # 2.0 is the count 2 (M4 fix a)
        return data

    @model_validator(mode="after")
    def _effects_name_a_kind(self):
        if self.metric in EFFECT_METRICS and self.entity == "plan":
            raise ValueError("effect_* claims need the change kind as entity")
        return self

    @model_validator(mode="after")
    def _second_run_only_for_differences(self):
        if (self.metric in PAIR_METRICS) != (self.run_id_b is not None):
            raise ValueError(
                "run_id_b is required for diff_*, n_added and n_dropped and allowed only for them"
            )
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
