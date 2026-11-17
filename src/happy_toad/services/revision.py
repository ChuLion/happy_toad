"""Revision analysis: plan of record vs refreshed forecast (docs/SPEC.md, M5).

5.1 compares the two versions' data; 5.3 builds in-between inputs in the fixed ORDER.
"""

import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from happy_toad.data.checks import InputError
from happy_toad.data.hashing import build_input_set
from happy_toad.data.schemas import InputSet
from happy_toad.engine.model import solve
from happy_toad.engine.relief import RESOLVED_TOLERANCE, resolved_count, sector_relief
from happy_toad.engine.result import DEFAULT_SETTINGS, SolverSettings
from happy_toad.reasons import Reason, ReasonCode
from happy_toad.services.request import SolveRequest
from happy_toad.services.revision_result import InputComparison, RevisionResult, RevisionStep
from happy_toad.services.run import RunRecord, base_fields, load_version, run_request, save_record

ORDER = ("costs", "offloads", "triggers", "sectors")
ORDER_TEXT = " -> ".join(ORDER)


class RevisionRequest(BaseModel):
    """One revision: the same total budget (including must-fund) on both versions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    budget: float
    plan_of_record: str = "v1"
    refreshed_forecast: str = "v2"


def _rows(data: InputSet, sector_ids: set[str]) -> dict[tuple[str, str], float]:
    """Offload amounts by (candidate, sector) for the given sectors."""
    return {
        (o.candidate_id, o.sector_id): o.amount for o in data.offloads if o.sector_id in sector_ids
    }


def _unsupported(a: InputSet, b: InputSet, shared: set[str]) -> list[str]:
    """Differences outside the four change kinds."""
    found = []
    cand_a, cand_b = {c.id: c for c in a.candidates}, {c.id: c for c in b.candidates}
    found += [f"candidate {c} added" for c in sorted(cand_b.keys() - cand_a.keys())]
    found += [f"candidate {c} removed" for c in sorted(cand_a.keys() - cand_b.keys())]
    found += [
        f"candidate {c} type changed"
        for c in sorted(cand_a.keys() & cand_b.keys())
        if cand_a[c].type != cand_b[c].type
    ]
    if sorted(a.must_fund, key=lambda m: m.id) != sorted(b.must_fund, key=lambda m: m.id):
        found.append("must-fund projects changed")
    sec_a, sec_b = {s.id: s for s in a.sectors}, {s.id: s for s in b.sectors}
    for s in sorted(shared):
        if sec_a[s].market != sec_b[s].market:
            found.append(f"sector {s} market changed")
        if sec_a[s].shortfall != sec_b[s].shortfall:
            found.append(f"sector {s} shortfall changed")
    return found


def compare_inputs(a: InputSet, b: InputSet) -> InputComparison:
    """Differences between a and b, from the data only (never from a change list)."""
    sec_a, sec_b = {s.id: s for s in a.sectors}, {s.id: s for s in b.sectors}
    shared = sec_a.keys() & sec_b.keys()
    cost_a, cost_b = {c.id: c.cost for c in a.candidates}, {c.id: c.cost for c in b.candidates}
    rows_a, rows_b = _rows(a, shared), _rows(b, shared)
    return InputComparison(
        sectors_added=sorted(sec_b.keys() - sec_a.keys()),
        sectors_removed=sorted(sec_a.keys() - sec_b.keys()),
        triggers_moved=sorted(s for s in shared if sec_a[s].trigger_year != sec_b[s].trigger_year),
        costs_changed=sorted(c for c in cost_a.keys() & cost_b.keys() if cost_a[c] != cost_b[c]),
        offloads_changed=[
            list(k) for k in sorted(rows_a.keys() | rows_b.keys()) if rows_a.get(k) != rows_b.get(k)
        ],
        unsupported=_unsupported(a, b, shared),
    )


def apply_kinds(a: InputSet, b: InputSet, kinds) -> InputSet:
    """a with the named change kinds taken from b (b's differences must all be supported)."""
    sec_b = {s.id: s for s in b.sectors}
    shared = {s.id for s in a.sectors} & sec_b.keys()
    cost_b = {c.id: c.cost for c in b.candidates}

    candidates = [
        c.model_copy(update={"cost": cost_b[c.id]}) if "costs" in kinds else c for c in a.candidates
    ]
    sectors = [
        s.model_copy(update={"trigger_year": sec_b[s.id].trigger_year})
        if "triggers" in kinds and s.id in shared
        else s
        for s in a.sectors
    ]
    shared_rows = b.offloads if "offloads" in kinds else a.offloads
    offloads = [o for o in shared_rows if o.sector_id in shared]
    if "sectors" in kinds:
        sectors = [s for s in sectors if s.id in shared] + [
            s for s in b.sectors if s.id not in shared
        ]
        offloads += [o for o in b.offloads if o.sector_id not in shared]
    else:
        offloads += [o for o in a.offloads if o.sector_id not in shared]
    version = "+".join([a.version_id, *kinds])
    return build_input_set(version, sectors, candidates, offloads, list(a.must_fund))


def n_changes(comparison: InputComparison, kind: str) -> int:
    """How many changes of one kind the comparison holds."""
    c = comparison
    return {
        "costs": len(c.costs_changed),
        "offloads": len(c.offloads_changed),
        "triggers": len(c.triggers_moved),
        "sectors": len(c.sectors_added) + len(c.sectors_removed),
    }[kind]


def _step_from_run(name: str, applied: list[str], count: int, record: RunRecord) -> RevisionStep:
    r = record.result
    return RevisionStep(
        name=name,
        applied=applied,
        n_changes=count,
        content_hash=record.content_hash,
        status=r.status,
        objective=r.objective,
        spend=r.spend,
        resolved=r.resolved,
        selected=r.selected,
    )


def _solved_step(name, applied, count, data: InputSet, budget, settings) -> RevisionStep:
    result = solve(data, budget, settings=settings)
    planned = result.selected is not None
    return RevisionStep(
        name=name,
        applied=applied,
        n_changes=count,
        content_hash=data.content_hash,
        status=result.status,
        objective=result.objective,
        spend=result.spend,
        resolved=resolved_count(data, set(result.selected)) if planned else None,
        selected=result.selected,
    )


def _steps(a, b, comparison, run_a, run_b, budget, settings) -> list[RevisionStep]:
    """plan_of_record, the three in-memory steps, then the refreshed forecast run."""
    steps = [_step_from_run("plan_of_record", [], 0, run_a)]
    for i, kind in enumerate(ORDER[:-1], 1):
        applied, count = list(ORDER[:i]), n_changes(comparison, kind)
        if count == 0:
            steps.append(
                steps[-1].model_copy(update={"name": kind, "applied": applied, "n_changes": 0})
            )
        else:
            data = apply_kinds(a, b, applied)
            steps.append(_solved_step(kind, applied, count, data, budget, settings))
    last = ORDER[-1]
    steps.append(_step_from_run(last, list(ORDER), n_changes(comparison, last), run_b))
    return steps


def _with_effects(steps: list[RevisionStep]) -> list[RevisionStep]:
    out = [steps[0]]
    for prev, step in zip(steps, steps[1:], strict=False):
        out.append(
            step.model_copy(
                update={
                    "effect_relief": step.objective - prev.objective,
                    "effect_spend": step.spend - prev.spend,
                    "effect_n_resolved": step.resolved - prev.resolved,
                }
            )
        )
    return out


def _resolved_in(data: InputSet, selected: list[str] | None, sector_ids: set[str]) -> int | None:
    """Resolved sectors among `sector_ids` for a plan, or None without a plan."""
    if selected is None:
        return None
    relief = sector_relief(data, set(selected))
    return sum(
        relief[s.id] >= s.shortfall - RESOLVED_TOLERANCE for s in data.sectors if s.id in sector_ids
    )


def _result(a, b, comparison, run_a, run_b, steps) -> RevisionResult:
    complete = all(s.status == "Optimal" for s in steps)
    if complete:
        steps = _with_effects(steps)
    first, last = steps[0], steps[-1]
    shared = {s.id for s in a.sectors} & {s.id for s in b.sectors}
    new = set(comparison.sectors_added)
    return RevisionResult(
        order=list(ORDER),
        order_text=ORDER_TEXT,
        run_id_a=run_a.run_id,
        run_id_b=run_b.run_id,
        inputs=comparison,
        steps=steps,
        complete=complete,
        total_relief=last.objective - first.objective if complete else None,
        total_spend=last.spend - first.spend if complete else None,
        total_n_resolved=last.resolved - first.resolved if complete else None,
        n_sectors_shared=len(shared),
        n_resolved_shared_a=_resolved_in(a, first.selected, shared),
        n_resolved_shared_b=_resolved_in(b, last.selected, shared),
        n_sectors_new=len(new),
        n_resolved_new=_resolved_in(b, last.selected, new),
    )


def _request_hash(request: RevisionRequest) -> str:
    return hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()


def run_revision(
    request: RevisionRequest,
    inputs_dir: Path = Path("data/inputs"),
    runs_dir: Path = Path("runs"),
    settings: SolverSettings = DEFAULT_SETTINGS,
    transcript_id: str | None = None,
) -> RunRecord:
    """Compare, run both ends, attribute in ORDER and write one revision record."""
    started = time.perf_counter()
    fields = base_fields(
        request.model_dump(),
        _request_hash(request),
        request.refreshed_forecast,
        settings,
        transcript_id,
    )

    def finish(outcome: str, **changes) -> RunRecord:
        return save_record(fields | {"kind": "revision"} | changes, outcome, started, runs_dir)

    names = (request.plan_of_record, request.refreshed_forecast)
    try:
        a, b = (load_version(name, inputs_dir) for name in names)
    except InputError as err:
        return finish("error", error=str(err))
    missing = [n for n, d in zip(names, (a, b), strict=True) if d is None]
    if missing:
        reasons = [
            Reason(code=ReasonCode.VERSION_NOT_FOUND, message=f"no input version {n!r}")
            for n in missing
        ]
        return finish("rejected", reasons=reasons)
    fields["content_hash"] = b.content_hash
    comparison = compare_inputs(a, b)
    if comparison.unsupported:
        message = "changes outside costs, offloads, triggers and sectors: " + "; ".join(
            comparison.unsupported
        )
        reason = Reason(code=ReasonCode.REVISION_UNSUPPORTED_CHANGE, message=message)
        return finish("rejected", reasons=[reason])
    if apply_kinds(a, b, ORDER).content_hash != b.content_hash:
        return finish(
            "error", error="applying every change kind did not reproduce the refreshed forecast"
        )

    ends = [
        run_request(
            SolveRequest(input_version=n, budget=request.budget),
            inputs_dir,
            runs_dir,
            settings,
            transcript_id,
        )
        for n in names
    ]
    for end in ends:
        if end.outcome == "error":
            return finish("error", error=f"run {end.run_id}: {end.error}")
        if end.outcome == "rejected":
            return finish("rejected", reasons=end.reasons)
    run_a, run_b = ends
    steps = _steps(a, b, comparison, run_a, run_b, request.budget, settings)
    return finish("completed", revision=_result(a, b, comparison, run_a, run_b, steps))
