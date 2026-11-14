"""Run service: one attempt end to end, always leaving one JSON record in runs/."""

import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from happy_toad.data.checks import InputError
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


class RunRecord(BaseModel):
    """One attempt: written to runs/<run_id>.json whatever the outcome."""

    run_id: str
    created_at: str
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


def new_run_id(created: datetime) -> str:
    """UTC timestamp plus 8 hex characters."""
    return f"{created:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


def write_record(record: RunRecord, runs_dir: Path) -> None:
    """Write one record as indented JSON to runs/<run_id>.json."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / f"{record.run_id}.json").write_text(record.model_dump_json(indent=2))


def load_version(version: str, inputs_dir: Path) -> InputSet | None:
    """The input set for a version name, or None if there is no such file. Raises InputError."""
    path = inputs_dir / f"{version}.json"
    if not VERSION_NAME.fullmatch(version) or not path.exists():
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
    created = datetime.now(UTC)
    fields = dict(
        run_id=new_run_id(created),
        created_at=created.isoformat(),
        request=request.model_dump(),
        request_hash=request_hash(request),
        input_version=request.input_version,
        content_hash=None,
        settings=settings.as_dict(),
        reasons=[],
        error=None,
        result=None,
        timing={},
        warnings=[],
    )

    def finish(outcome: str, **changes) -> RunRecord:
        fields.update(changes)
        fields["timing"] = {**fields["timing"], "total": time.perf_counter() - started}
        record = RunRecord(outcome=outcome, **fields)
        write_record(record, runs_dir)
        return record

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
