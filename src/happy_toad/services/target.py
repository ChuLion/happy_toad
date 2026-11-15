"""Target-budget search: request, gate, search record and follow-up run (docs/SPEC.md, M2B)."""

import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from happy_toad.constants import BASE_YEAR
from happy_toad.data.checks import InputError
from happy_toad.data.schemas import InputSet
from happy_toad.engine.relief import resolved_count, sector_relief, weighted_relief
from happy_toad.engine.result import DEFAULT_SETTINGS, SolverSettings
from happy_toad.engine.target import (
    CheapestPlan,
    cheapest_plan,
    max_resolvable,
    round_up_cent,
    target_sectors,
)
from happy_toad.reasons import Reason, ReasonCode
from happy_toad.services.gate import check_target_request
from happy_toad.services.request import SolveRequest
from happy_toad.services.run import (
    RunRecord,
    RunResult,
    base_fields,
    load_version,
    run_request,
    save_record,
    write_record,
)
from happy_toad.services.unresolved import unresolved_sectors

LIMITS_REFUSED = (
    "{name} is not supported in the target-budget search: market floors and caps scale with the "
    "budget being searched for; use run_scenario with a budget to apply them"
)
BUDGET_REFUSED = (
    "budget is not supported in the target-budget search: the search finds the budget; use "
    "run_scenario to run a budget you choose"
)


class TargetBudgetRequest(BaseModel):
    """What budget does the cheapest plan need to resolve at least this percent of sectors?"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_version: str
    target_pct_resolved: float = Field(ge=0, le=100)
    force_in: list[str] = []
    force_out: list[str] = []
    label: str = ""

    @model_validator(mode="before")
    @classmethod
    def _no_budget_or_market_limits(cls, raw):
        if isinstance(raw, dict):
            for name in ("market_floor_mult", "market_cap_mult"):
                if name in raw:
                    raise ValueError(LIMITS_REFUSED.format(name=name))
            if "budget" in raw:
                raise ValueError(BUDGET_REFUSED)
        return raw

    @field_validator("force_in", "force_out")
    @classmethod
    def _sorted_unique(cls, ids: list[str]) -> list[str]:
        return sorted(set(ids))


def target_hash(request: TargetBudgetRequest) -> str:
    """SHA-256 of the canonical JSON of every field except the label, plus the kind."""
    fields = request.model_dump(exclude={"label"}) | {"kind": "target_budget"}
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def _unreachable(n: int, k: int, most: int) -> Reason:
    message = (
        f"at most {most} of {n} sectors ({100 * most / n:.1f}%) can be resolved with the "
        f"candidates not forced out; the target needs {k}"
    )
    return Reason(code=ReasonCode.TARGET_UNREACHABLE, message=message)


def _search_result(
    data: InputSet,
    request: TargetBudgetRequest,
    plan: CheapestPlan | None,
    budget: float | None,
    settings: SolverSettings,
) -> RunResult:
    """The search summarized like a run result; `plan` is None when the target is unreachable."""
    n = len(data.sectors)
    k = target_sectors(request.target_pct_resolved, n)
    most = max_resolvable(data, request.force_out)
    found = {
        "status": "Infeasible", "cause": _unreachable(n, k, most), "objective": None,
        "spend": None, "selected": None, "resolved": None, "pct_resolved": None,
        "target_met": False, "unresolved": None,
    }  # fmt: skip
    if plan is not None and plan.selected is not None:
        chosen = set(plan.selected)
        resolved = resolved_count(data, chosen)
        found = {
            "status": plan.status, "cause": None,
            "objective": weighted_relief(data, chosen, BASE_YEAR),
            "spend": sum(c.cost for c in data.candidates if c.id in chosen),
            "selected": plan.selected, "resolved": resolved, "pct_resolved": 100 * resolved / n,
            "target_met": resolved >= k,
            "unresolved": unresolved_sectors(data, sector_relief(data, chosen), BASE_YEAR),
        }  # fmt: skip
    elif plan is not None:  # the solver stopped before it found any plan
        found |= {"status": plan.status, "cause": None}
    times = plan.times if plan else {}
    return RunResult(
        **found,
        required_minimum_budget=None,
        total_sectors=n,
        pct_of_region=None,
        target_pct_resolved=request.target_pct_resolved,
        solve_time=sum(times.values()),
        stage_times=times,
        solver_settings=settings.as_dict(),
        target_budget=budget,
        target_sectors=k,
        max_resolvable=most,
        max_pct_resolvable=100 * most / n,
    )


def run_target(
    request: TargetBudgetRequest,
    inputs_dir: Path = Path("data/inputs"),
    runs_dir: Path = Path("runs"),
    settings: SolverSettings = DEFAULT_SETTINGS,
    transcript_id: str | None = None,
) -> RunRecord:
    """Gate, search and record; when a budget is found, also run the optimizer at it."""
    started = time.perf_counter()
    fields = base_fields(
        request.model_dump(), target_hash(request), request.input_version, settings, transcript_id
    )
    fields["kind"] = "target_budget"
    try:
        data = load_version(request.input_version, inputs_dir)
    except InputError as err:
        return save_record(fields | {"error": str(err)}, "error", started, runs_dir)
    if data is not None:
        fields["content_hash"] = data.content_hash
    reasons = check_target_request(request.input_version, request.force_in, request.force_out, data)
    if reasons:
        return save_record(fields | {"reasons": reasons}, "rejected", started, runs_dir)

    k = target_sectors(request.target_pct_resolved, len(data.sectors))
    if k > max_resolvable(data, request.force_out):
        result = _search_result(data, request, None, None, settings)
        return save_record(fields | {"result": result}, "completed", started, runs_dir)
    plan = cheapest_plan(data, k, request.force_in, request.force_out, settings=settings)
    budget = None
    if plan.status == "Optimal":
        budget = round_up_cent(data.must_fund_total + plan.cost)
    result = _search_result(data, request, plan, budget, settings)
    record = save_record(fields | {"result": result}, "completed", started, runs_dir)
    if budget is None:
        return record
    follow_up = SolveRequest(
        input_version=request.input_version,
        budget=budget,
        force_in=request.force_in,
        force_out=request.force_out,
    )
    follow_up_id = run_request(follow_up, inputs_dir, runs_dir, settings, transcript_id).run_id
    record = record.model_copy(update={"follow_up_run_id": follow_up_id})
    write_record(record, runs_dir)
    return record
