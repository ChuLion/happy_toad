"""Consistency checker: claims against stored runs, summary numbers against claims.

Rules are in docs/SPEC.md (M3: tolerances, and what counts as a number in the summary).
"""

import re
from pathlib import Path

from pydantic import BaseModel, computed_field

from happy_toad.agent.report import Claim, Report
from happy_toad.services.run import RunRecord
from happy_toad.services.runs import read_run

MONEY_TOLERANCE = 0.005  # shown to 2 decimals
PERCENT_TOLERANCE = 0.05  # shown to 1 decimal
TOLERANCE = {
    "weighted_relief": MONEY_TOLERANCE,
    "spend": MONEY_TOLERANCE,
    "required_minimum_budget": MONEY_TOLERANCE,
    "pct_resolved": PERCENT_TOLERANCE,
}
REQUEST_NUMBERS = (
    "budget",
    "market_floor_mult",
    "market_cap_mult",
    "target_pct_resolved",
    "region_total_sectors",
)
RUN_ID_TEXT = re.compile(r"\d{8}T\d{6}-[0-9a-f]{8}")
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)](?=\s)")
NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?(?!\w)")
YEAR = re.compile(r"\d{4}")


class ClaimCheck(BaseModel):
    claim: Claim
    ok: bool
    message: str


class NumberCheck(BaseModel):
    text: str
    ok: bool
    message: str


class CheckResult(BaseModel):
    claims: list[ClaimCheck]
    numbers: list[NumberCheck]

    @computed_field
    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.claims) and all(n.ok for n in self.numbers)

    def errors(self) -> list[str]:
        """One line per failure, for the model and for display."""
        bad_claims = [
            f"claim {c.claim.metric} of {c.claim.run_id}: {c.message}"
            for c in self.claims
            if not c.ok
        ]
        bad_numbers = [
            f"number {n.text} in the summary: {n.message}" for n in self.numbers if not n.ok
        ]
        return bad_claims + bad_numbers


def find_numbers(text: str) -> list[tuple[str, float]]:
    """Numbers in a summary as (text, value); identifiers, years and list markers are skipped."""
    text = RUN_ID_TEXT.sub(" ", text)
    text = LIST_MARKER.sub(" ", text)
    found = []
    for m in NUMBER.finditer(text):
        token = m.group()
        if YEAR.fullmatch(token) and 1900 <= int(token) <= 2199:
            continue
        found.append((token, float(token.rstrip("%").replace(",", ""))))
    return found


def stored_value(record: RunRecord, metric: str):
    """The value of a metric in a stored run, or None if the run has none."""
    if metric == "required_minimum_budget":
        return record.required_minimum_budget
    r = record.result
    if r is None:
        return None
    values = {
        "weighted_relief": r.objective,
        "spend": r.spend,
        "n_selected": None if r.selected is None else len(r.selected),
        "n_resolved": r.resolved,
        "pct_resolved": r.pct_resolved,
        "status": r.status,
        "target_met": r.target_met,
    }
    return values[metric]


def values_match(metric: str, claimed, stored) -> bool:
    """Exact for counts, strings and booleans; within the displayed-rounding tolerance otherwise."""
    if metric in TOLERANCE:
        return isinstance(claimed, int | float) and abs(claimed - stored) <= TOLERANCE[metric]
    return claimed == stored and type(claimed) is type(stored)


def check_claim(claim: Claim, runs_dir: Path) -> ClaimCheck:
    record = read_run(claim.run_id, runs_dir)
    if record is None:
        return ClaimCheck(claim=claim, ok=False, message="run not found")
    stored = stored_value(record, claim.metric)
    if stored is None:
        return ClaimCheck(claim=claim, ok=False, message="the run has no value for this metric")
    if not values_match(claim.metric, claim.value, stored):
        return ClaimCheck(claim=claim, ok=False, message=f"claimed {claim.value}, stored {stored}")
    return ClaimCheck(claim=claim, ok=True, message="matches")


def allowed_numbers(report: Report, runs_dir: Path) -> list[tuple[float, float]]:
    """(value, tolerance) pairs a summary number may equal: claim values and request values."""
    allowed = []
    for claim in report.claims:
        if isinstance(claim.value, int | float) and not isinstance(claim.value, bool):
            allowed.append((float(claim.value), TOLERANCE.get(claim.metric, 0.0)))
    for run_id in {c.run_id for c in report.claims}:
        record = read_run(run_id, runs_dir)
        for name in REQUEST_NUMBERS if record else ():
            if record.request.get(name) is not None:
                allowed.append((float(record.request[name]), 0.0))
    return allowed


def check_report(report: Report, runs_dir: Path) -> CheckResult:
    """Check every claim against its stored run and every summary number against the claims."""
    claims = [check_claim(c, runs_dir) for c in report.claims]
    valid = Report(summary=report.summary, claims=[c.claim for c in claims if c.ok])
    allowed = allowed_numbers(valid, runs_dir)
    numbers = []
    for text, value in find_numbers(report.summary):
        match = any(abs(value - v) <= max(tol, 1e-9) for v, tol in allowed)
        message = "matches" if match else "does not match any validated claim or request value"
        numbers.append(NumberCheck(text=text, ok=match, message=message))
    return CheckResult(claims=claims, numbers=numbers)
