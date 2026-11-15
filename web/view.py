"""build_view: one transcript plus its run records in, the page's view dict out."""

import json
from pathlib import Path

from happy_toad.agent.tools import TOOLS
from happy_toad.agent.transcript import Transcript
from happy_toad.services.run import RunRecord
from happy_toad.services.runs import metrics, read_run
from web.format import (
    NO_FIGURES,
    NO_FIGURES_LINE,
    call_args,
    call_outcome,
    check_line,
    correction,
    no_report_line,
    verdict,
)
from web.markdown import render
from web.redact import redact_all
from web.schema import SCHEMA_VERSION

KNOWN_TOOLS = {t["function"]["name"] for t in TOOLS}
OUTCOME_LIMIT = 200  # characters of an unknown tool's result shown


def step(call: dict) -> dict:
    """One tool call as tool, short args, outcome; the CLI's wording for known tools."""
    name = call["name"]
    if name in KNOWN_TOOLS:
        args, outcome = call_args(name, call["arguments"]), call_outcome(name, call["result"])
    else:
        args = call["arguments"][:OUTCOME_LIMIT]
        outcome = json.dumps(call["result"], default=str)[:OUTCOME_LIMIT]
    return redact_all({"tool": name, "args": args, "outcome": outcome})


def _checks(t: Transcript, label: str | None) -> dict | None:
    if not t.checks:
        return None
    last = t.checks[-1]
    return {
        "claims": len(last.claims),
        "claims_ok": sum(c.ok for c in last.claims),
        "numbers": len(last.numbers),
        "numbers_matched": sum(n.ok for n in last.numbers),
        "unmatched_numbers": [n.text for n in last.numbers if not n.ok],
        "line": NO_FIGURES_LINE if label == NO_FIGURES else check_line(last),
        "mismatches": last.errors(),
    }


def _correction_view(t: Transcript) -> dict:
    submits = [c for turn in t.turns for c in turn.tool_calls if c["name"] == "submit_report"]
    return {"happened": len(submits) > 1, "note": correction(t)}


def _run(record: RunRecord) -> dict:
    values = {"budget": record.request.get("budget")}
    if record.kind == "target_budget":
        values["target_budget"] = record.result.target_budget if record.result else None
    values["required_minimum_budget"] = record.required_minimum_budget
    if record.result is not None and record.result.spend is not None:
        values |= metrics(record)
    run = {"run_id": record.run_id, "input_version": record.input_version}
    return run | {"outcome": record.outcome, "values": values}


def _claim(c) -> dict:
    return {"metric": c.metric, "value": c.value, "run_id": c.run_id, "run_id_b": c.run_id_b}


def build_view(transcript: Transcript, run_records: list[RunRecord]) -> dict:
    """The view dict (web.schema.View), with keys and account ids redacted."""
    t = transcript
    label = verdict(t)
    report = t.report if label else None
    providers = ", ".join(t.providers) or "no provider"
    view = {
        "schema_version": SCHEMA_VERSION,
        "transcript_id": t.transcript_id,
        "question": t.question,
        "steps": [step(c) for turn in t.turns for c in turn.tool_calls],
        "summary": report.summary if report else None,
        "summary_html": render(report.summary) if report else None,
        "status": label,
        "detail": t.status if label else no_report_line(t),
        "checks": _checks(t, label),
        "claims": [_claim(c) for c in report.claims] if report else [],
        "correction": _correction_view(t),
        "runs": [_run(r) for r in run_records],
        "footer": {
            "model": t.model,
            "provider": providers,
            "turns": len(t.turns),
            "cost": t.cost,
            "seconds": round(t.elapsed_seconds, 1),
        },
    }
    return redact_all(view)


def referenced_runs(t: Transcript, runs_dir: Path) -> list[RunRecord]:
    """The stored records of runs named in tool results, in first-seen order."""
    ids: list[str] = []
    for turn in t.turns:
        for call in turn.tool_calls:
            for key in ("run_id", "run_id_a", "run_id_b", "follow_up_run_id"):
                value = call["result"].get(key)
                if isinstance(value, str) and value not in ids:
                    ids.append(value)
    return [r for r in (read_run(i, runs_dir) for i in ids) if r is not None]
