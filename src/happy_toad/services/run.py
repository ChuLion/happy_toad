"""Run service: one attempt end to end, always leaving one JSON record in runs/."""

import hashlib
import json
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from happy_toad.data.checks import InputError
from happy_toad.data.files import is_change_list
from happy_toad.data.loader import load_input_set
from happy_toad.data.schemas import InputSet
from happy_toad.engine.diagnose import required_minimum_budget
from happy_toad.engine.model import solve
from happy_toad.engine.relief import resolved_count
from happy_toad.engine.result import DEFAULT_SETTINGS, SolverSettings
from happy_toad.reasons import Reason, ReasonCode
from happy_toad.services.gate import check_request
from happy_toad.services.request import SolveRequest, request_hash
from happy_toad.services.unresolved import SectorGap, unresolved_sectors

VERSION_NAME = re.compile(r"[A-Za-z0-9_-]+")


class RunResult(BaseModel):
    """What the solve produced, summarized for a decision-maker."""

    status: str
    cause: Reason | None
    required_minimum_budget: float | None
    objective: float | None
    spend: float | None
    selected: list[str] | None
    resolved: int | None
    total_sectors: int
    pct_resolved: float | None
    pct_of_region: float | None
    target_pct_resolved: float | None
    target_met: bool | None
    unresolved: list[SectorGap] | None
    solve_time: float
    stage_times: dict[str, float]
    solver_settings: dict
    target_budget: float | None = None  # M2B search only, from here down
    target_sectors: int | None = None
    max_resolvable: int | None = None
    max_pct_resolvable: float | None = None


class RunRecord(BaseModel):
    """One attempt: written to runs/<run_id>.json whatever the outcome."""

    run_id: str
    created_at: str
    kind: Literal["scenario", "target_budget"] = "scenario"
    outcome: Literal["rejected", "completed", "error"]
    request: dict
    request_hash: str
    input_version: str
    content_hash: str | None
    required_minimum_budget: float | None = None
    settings: dict
    reasons: list[Reason]
    error: str | None
    result: RunResult | None
    timing: dict[str, float]
    warnings: list[str]
    follow_up_run_id: str | None = None  # M2B: the optimizer run at target_budget


def new_run_id(created: datetime) -> str:
    """UTC timestamp plus 8 hex characters."""
    return f"{created:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


def write_record(record: RunRecord, runs_dir: Path) -> None:
    """Write one record as indented JSON to runs/<run_id>.json."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{record.run_id}.json").write_text(record.model_dump_json(indent=2))


def base_fields(request: dict, hash_: str, input_version: str, settings: SolverSettings) -> dict:
    """The fields every new run record starts with: a fresh run id and nothing found yet."""
    created = datetime.now(UTC)
    return dict(
        run_id=new_run_id(created),
        created_at=created.isoformat(),
        request=request,
        request_hash=hash_,
        input_version=input_version,
        content_hash=None,
        settings=settings.as_dict(),
        reasons=[],
        error=None,
        result=None,
        timing={},
        warnings=[],
    )


def save_record(fields: dict, outcome: str, started: float, runs_dir: Path) -> RunRecord:
    """Build the record from its fields, add the total time and write it."""
    fields["timing"] = {**fields["timing"], "total": time.perf_counter() - started}
    record = RunRecord(outcome=outcome, **fields)
    write_record(record, runs_dir)
    return record


def record_invalid_request(
    raw: dict, message: str, runs_dir: Path, kind: str = "scenario"
) -> RunRecord:
    """Write a rejected record for an agent input that does not fit the request schema.

    The hash is over the raw input (sorted-key JSON), not `request_hash`, which needs a valid
    request; stored hashes stay as they were.
    """
    version = raw.get("input_version")
    fields = base_fields(
        raw,
        hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest(),
        version if isinstance(version, str) else "",
        DEFAULT_SETTINGS,
    )
    fields["reasons"] = [Reason(code=ReasonCode.SCHEMA_INVALID, message=message)]
    record = RunRecord(outcome="rejected", kind=kind, **fields)
    write_record(record, runs_dir)
    return record


def load_version(version: str, inputs_dir: Path) -> InputSet | None:
    """The input set for a version name, or None if there is no such version. Raises InputError."""
    path = inputs_dir / f"{version}.json"
    if not VERSION_NAME.fullmatch(version) or is_change_list(version) or not path.exists():
        return None
    return load_input_set(path)


def summarize(data: InputSet, request: SolveRequest, result) -> RunResult:
    """Resolved counts, target check, region percentage and the unresolved report."""
    total = len(data.sectors)
    planned = result.selected is not None
    resolved = resolved_count(data, set(result.selected)) if planned else None
    pct = 100 * resolved / total if planned else None
    target = request.target_pct_resolved
    region = request.region_total_sectors
    return RunResult(
        status=result.status,
        cause=result.cause,
        required_minimum_budget=result.required_minimum_budget,
        objective=result.objective,
        spend=result.spend,
        selected=result.selected,
        resolved=resolved,
        total_sectors=total,
        pct_resolved=pct,
        pct_of_region=100 * resolved / region if planned and region else None,
        target_pct_resolved=target,
        target_met=None if target is None else (planned and pct >= target),
        unresolved=unresolved_sectors(data, result.relief, result.base_year) if planned else None,
        solve_time=result.solve_time,
        stage_times=result.stage_times,
        solver_settings=result.solver_settings,
    )


def run_request(
    request: SolveRequest,
    inputs_dir: Path = Path("data/inputs"),
    runs_dir: Path = Path("runs"),
    settings: SolverSettings = DEFAULT_SETTINGS,
) -> RunRecord:
    """Gate, solve and record one request. Rejections and failures are recorded too."""
    started = time.perf_counter()
    fields = base_fields(
        request.model_dump(), request_hash(request), request.input_version, settings
    )

    def finish(outcome: str, **changes) -> RunRecord:
        return save_record(fields | changes, outcome, started, runs_dir)

    try:
        data = load_version(request.input_version, inputs_dir)
    except InputError as err:
        return finish("error", error=str(err))
    if data is not None:
        fields["content_hash"] = data.content_hash
    reasons = check_request(request, data)
    fields["timing"] = {"gate": time.perf_counter() - started}
    if reasons:
        forced = ReasonCode.FORCED_COST_EXCEEDS_BUDGET in {r.code for r in reasons}
        minimum = required_minimum_budget(data, request.force_in, None) if forced else None
        return finish("rejected", reasons=reasons, required_minimum_budget=minimum)

    try:
        result = solve(
            data,
            request.budget,
            settings=settings,
            market_floor_mult=request.market_floor_mult,
            market_cap_mult=request.market_cap_mult,
            force_in=request.force_in,
            force_out=request.force_out,
        )
        summary = summarize(data, request, result)
    except Exception as err:  # every attempt must leave a record, whatever went wrong
        return finish("error", error=f"{type(err).__name__}: {err}")
    region = request.region_total_sectors
    warnings = []
    if region is not None and region < len(data.sectors):
        warnings.append(
            f"region_total_sectors {region} is smaller than "
            f"the {len(data.sectors)} modelled sectors"
        )
    timing = {**fields["timing"], "solve": result.solve_time}
    return finish(
        "completed",
        result=summary,
        required_minimum_budget=result.required_minimum_budget,
        timing=timing,
        warnings=warnings,
    )
