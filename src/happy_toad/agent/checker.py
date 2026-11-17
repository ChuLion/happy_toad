"""Consistency checker: claims against stored runs, summary numbers against claims.

Rules are in docs/SPEC.md (M3: tolerances, and what counts as a number in the summary).
"""

import re
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, computed_field

from happy_toad.agent.report import (
    ATTRIBUTION_METRICS,
    DIFF_BASE,
    EFFECT_METRICS,
    PAIR_METRICS,
    REVISION_METRICS,
    Claim,
    Report,
)
from happy_toad.constants import BASE_YEAR, HORIZON_YEARS
from happy_toad.reasons import ReasonCode
from happy_toad.services.run import RunRecord, load_version
from happy_toad.services.runs import has_plan, metrics, read_run

MONEY_TOLERANCE = 0.005  # shown to 2 decimals
PERCENT_TOLERANCE = 0.05  # shown to 1 decimal
FLOAT_SLACK = 1e-9  # tolerances are inclusive: 26.3 vs 26.25 differs by 0.05000000000000071
MONEY_METRICS = (
    "weighted_relief",
    "spend",
    "required_minimum_budget",
    "must_fund_cost",
    "forced_cost",
    "target_budget",
    "diff_spend",
    "diff_weighted_relief",
    "effect_relief",
    "effect_spend",
    "total_relief",
    "total_spend",
)
TOLERANCE = {m: MONEY_TOLERANCE for m in MONEY_METRICS} | {
    "pct_resolved": PERCENT_TOLERANCE,
    "diff_pct_resolved": PERCENT_TOLERANCE,
    "max_pct_resolvable": PERCENT_TOLERANCE,
    "pct_of_region": PERCENT_TOLERANCE,
}
INPUT_METRICS = ("n_sectors", "must_fund_cost", "forced_cost")
REQUEST_NUMBERS = (
    "budget",
    "market_floor_mult",
    "market_cap_mult",
    "target_pct_resolved",
    "region_total_sectors",
)
RUN_ID_TEXT = re.compile(r"\d{8}T\d{6}-[0-9a-f]{8}")
LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)](?=\s)")
# A number must not touch a letter. The quantifiers are possessive, so a failed "0.5x" cannot
# give back ".5" and match "0"; it is skipped whole. Punctuation chains ("1,2,3") stay checked.
NUMBER = re.compile(r"(?<![\w.])[-+]?\d++(?:,\d{3})*+(?:\.\d+)?+%?+(?!\w)")
YEAR = re.compile(r"\d{4}")
CANDIDATE_ID = re.compile(r"\bC\d{3}\b")  # the generator's candidate ids (C001, ...)
MODEL_YEARS = range(BASE_YEAR, BASE_YEAR + HORIZON_YEARS)  # 2027-2031 (M4 fix d)
NOT_CHECKED = "not checked because no claim validated"
NOT_IN_CONVERSATION = "run was not executed or read in this conversation"


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
    missing: list[str] = []  # claims the report must make but does not
    candidates: list[str] = []  # candidate ids in the summary that no cited run contains (fix e)

    @computed_field
    @property
    def ok(self) -> bool:
        return (
            all(c.ok for c in self.claims)
            and all(n.ok for n in self.numbers)
            and not self.missing
            and not self.candidates
        )

    def errors(self) -> list[str]:
        """One line per failure, for the model and for display."""
        bad_claims = [
            f"claim {c.claim.metric} of {c.claim.run_id}: {c.message}"
            for c in self.claims
            if not c.ok
        ]
        unchecked = [n for n in self.numbers if n.message == NOT_CHECKED]
        bad_numbers = [
            f"number {n.text} in the summary: {n.message}"
            for n in self.numbers
            if not n.ok and n.message != NOT_CHECKED
        ]
        if unchecked:
            bad_numbers.append(f"{len(unchecked)} summary numbers {NOT_CHECKED}")
        return bad_claims + self.missing + bad_numbers + self.candidates


def _strip_run_ids(text: str, run_ids: Iterable[str]) -> str:
    """Remove run ids and, for known runs, their timestamp and suffix written on their own."""
    text = RUN_ID_TEXT.sub(" ", text)
    for run_id in run_ids:
        for part in run_id.split("-"):
            text = re.sub(rf"(?<![\w.]){re.escape(part)}(?!\w)", " ", text)
    return text


def find_numbers(text: str, run_ids: Iterable[str] = ()) -> list[tuple[str, float]]:
    """Numbers in a summary as (text, value); identifiers, years and list markers are skipped."""
    text = LIST_MARKER.sub(" ", _strip_run_ids(text, run_ids))
    found = []
    for m in NUMBER.finditer(text):
        token = m.group()
        if YEAR.fullmatch(token) and int(token) in MODEL_YEARS:
            continue
        found.append((token, float(token.rstrip("%").replace(",", ""))))
    return found


def stored_value(record: RunRecord, metric: str):
    """The value of a run metric in a stored run, or None if the run has none."""
    if metric == "required_minimum_budget":
        return record.required_minimum_budget
    r = record.result
    if metric == "status":
        return record.outcome if r is None else r.status
    if r is None:
        return None
    values = {
        "weighted_relief": r.objective,
        "spend": r.spend,
        "n_selected": None if r.selected is None else len(r.selected),
        "n_resolved": r.resolved,
        "n_unresolved": None if r.resolved is None else r.total_sectors - r.resolved,
        "pct_resolved": r.pct_resolved,
        "pct_of_region": r.pct_of_region,
        "target_met": r.target_met,
        "target_budget": r.target_budget,
        "target_sectors": r.target_sectors,
        "max_resolvable": r.max_resolvable,
        "max_pct_resolvable": r.max_pct_resolvable,
    }
    return values[metric]


def input_value(record: RunRecord, metric: str, inputs_dir: Path):
    """Sector count, must-fund cost or forced-in cost, from the run's input version file."""
    data = load_version(record.input_version, inputs_dir)
    if data is None:
        return None
    if metric == "n_sectors":
        return len(data.sectors)
    if metric == "must_fund_cost":
        return data.must_fund_total
    costs = {c.id: c.cost for c in data.candidates}
    return sum(costs[i] for i in record.request.get("force_in") or [] if i in costs)


def difference(a: RunRecord, run_id_b: str, metric: str, runs_dir: Path):
    """Run b minus run a for a compared metric, as compare_runs reports it; None without plans."""
    b = read_run(run_id_b, runs_dir)
    if not (has_plan(a) and has_plan(b)):
        return None
    base = DIFF_BASE[metric]
    return metrics(b)[base] - metrics(a)[base]


def pair_value(a: RunRecord, run_id_b: str, metric: str, runs_dir: Path):
    """A diff_ metric (b minus a), or n_added / n_dropped; None unless both runs have plans."""
    if metric in DIFF_BASE:
        return difference(a, run_id_b, metric, runs_dir)
    b = read_run(run_id_b, runs_dir)
    if not (has_plan(a) and has_plan(b)):
        return None
    chosen_a, chosen_b = set(a.result.selected), set(b.result.selected)
    return len(chosen_b - chosen_a) if metric == "n_added" else len(chosen_a - chosen_b)


INPUT_COUNTS = {
    "n_sectors_added": "sectors_added",
    "n_sectors_removed": "sectors_removed",
    "n_triggers_moved": "triggers_moved",
    "n_costs_changed": "costs_changed",
    "n_offloads_changed": "offloads_changed",
}


def revision_value(record: RunRecord, claim: Claim):
    """(value, reason when none) of a revision metric; effects are looked up by their kind."""
    rev = record.revision
    if rev is None:
        return None, "the run has no value for this metric"
    if claim.metric in ATTRIBUTION_METRICS and not rev.complete:
        return None, "attribution incomplete: a step was not proven optimal"
    if claim.metric in EFFECT_METRICS:
        step = next(s for s in rev.steps if s.name == claim.entity)
        return getattr(step, claim.metric), "the step has no effect"
    if claim.metric in INPUT_COUNTS:
        return len(getattr(rev.inputs, INPUT_COUNTS[claim.metric])), ""
    return getattr(rev, claim.metric), "the run has no value for this metric"


def values_match(metric: str, claimed, stored) -> bool:
    """Exact for counts, strings and booleans; within the displayed-rounding tolerance otherwise."""
    if metric in TOLERANCE:
        return (
            isinstance(claimed, int | float)
            and abs(claimed - stored) <= TOLERANCE[metric] + FLOAT_SLACK
        )
    return claimed == stored and type(claimed) is type(stored)


def _sector_counts_differ(a: RunRecord, run_id_b: str, runs_dir: Path) -> bool:
    b = read_run(run_id_b, runs_dir)
    return has_plan(a) and has_plan(b) and a.result.total_sectors != b.result.total_sectors


def _stored(claim: Claim, record: RunRecord, runs_dir: Path, inputs_dir: Path):
    if claim.metric in REVISION_METRICS:
        return revision_value(record, claim)
    if claim.metric == "diff_pct_resolved" and _sector_counts_differ(
        record, claim.run_id_b, runs_dir
    ):
        return None, "different sector counts; use the shared-sector counts"
    if claim.metric in PAIR_METRICS:
        return pair_value(record, claim.run_id_b, claim.metric, runs_dir), "both runs need a plan"
    if claim.metric in INPUT_METRICS:
        return input_value(record, claim.metric, inputs_dir), "input version not found"
    return stored_value(record, claim.metric), "the run has no value for this metric"


def check_claim(
    claim: Claim, runs_dir: Path, inputs_dir: Path, known: set[str] | None = None
) -> ClaimCheck:
    """Check one claim; with `known`, every run it cites must be one of those runs."""
    cited = {claim.run_id, claim.run_id_b} - {None}
    if known is not None and not cited <= known:
        return ClaimCheck(claim=claim, ok=False, message=NOT_IN_CONVERSATION)
    record = read_run(claim.run_id, runs_dir)
    if record is None:
        return ClaimCheck(claim=claim, ok=False, message="run not found")
    stored, why_none = _stored(claim, record, runs_dir, inputs_dir)
    if stored is None:
        return ClaimCheck(claim=claim, ok=False, message=why_none)
    if not values_match(claim.metric, claim.value, stored):
        message = f"claimed {claim.value!r} ({type(claim.value).__name__}), stored {stored!r}"
        return ClaimCheck(claim=claim, ok=False, message=message)
    return ClaimCheck(claim=claim, ok=True, message="matches")


def _run_ids(report: Report) -> list[str]:
    ids = [c.run_id for c in report.claims] + [c.run_id_b for c in report.claims if c.run_id_b]
    return list(dict.fromkeys(ids))


# Gate codes whose messages hold only the gate's own figures and request values. Other codes
# echo text the agent chose (a version name, candidate ids, schema input), so they add nothing.
GATE_FIGURES = {
    ReasonCode.BUDGET_NOT_POSITIVE,
    ReasonCode.BUDGET_ABOVE_CAP,
    ReasonCode.FORCED_COST_EXCEEDS_BUDGET,
}


def allowed_numbers(
    report: Report, runs_dir: Path, executed: Iterable[str] = ()
) -> list[tuple[float, float]]:
    """(value, tolerance) pairs a summary number may equal: claim values, and the request values
    and rejection-message numbers of the cited runs and of the runs in the conversation (M4 fix
    k). Numbers that are only in the question are not allowed.

    A difference may be written without its sign ("243.70 less").
    """
    allowed = []
    for claim in report.claims:
        if isinstance(claim.value, int | float) and not isinstance(claim.value, bool):
            tol = TOLERANCE.get(claim.metric, 0.0)
            allowed.append((float(claim.value), tol))
            if claim.metric in DIFF_BASE or claim.metric in ATTRIBUTION_METRICS:
                allowed.append((abs(float(claim.value)), tol))
    for run_id in dict.fromkeys([*_run_ids(report), *executed]):
        record = read_run(run_id, runs_dir)
        if record is None:
            continue
        for name in REQUEST_NUMBERS:
            if _number(record.request.get(name)):
                allowed.append((float(record.request[name]), 0.0))
        for reason in record.reasons:
            if reason.code in GATE_FIGURES:
                allowed += [(value, 0.0) for _, value in find_numbers(reason.message)]
    return allowed


def _number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def untraced_candidates(report: Report, runs_dir: Path, executed: Iterable[str] = ()) -> list[str]:
    """Candidate ids in the summary that are in no selection or force list of a cited run or of a
    run in the conversation (fix e, widened by the owner after round 2); ids only in the question
    stay untraced."""
    traced: set[str] = set()
    for run_id in dict.fromkeys([*_run_ids(report), *executed]):
        record = read_run(run_id, runs_dir)
        if record is None:
            continue
        for key in ("force_in", "force_out"):
            if isinstance(record.request.get(key), list):
                traced |= {str(x) for x in record.request[key]}
        if record.result is not None and record.result.selected:
            traced |= set(record.result.selected)
        if record.revision is not None:
            traced |= {c for s in record.revision.steps for c in s.selected or []}
    named = dict.fromkeys(CANDIDATE_ID.findall(report.summary))
    return [
        f"candidate {cid} in the summary is not in the selection or force lists of a run in "
        "this conversation"
        for cid in named
        if cid not in traced
    ]


def _needs_minimum_budget(record: RunRecord) -> bool:
    blocked = record.outcome == "rejected" or (
        record.result is not None and record.result.status == "Infeasible"
    )
    return blocked and record.required_minimum_budget is not None


def missing_minimum_budgets(valid: Report, run_ids: Iterable[str], runs_dir: Path) -> list[str]:
    """A rejected or infeasible run with a required_minimum_budget must have that claim."""
    claimed = {c.run_id for c in valid.claims if c.metric == "required_minimum_budget"}
    missing = []
    for run_id in run_ids:
        record = read_run(run_id, runs_dir)
        if record is not None and _needs_minimum_budget(record) and run_id not in claimed:
            missing.append(
                f"run {run_id} is {record.outcome if record.result is None else 'infeasible'} "
                f"and has required_minimum_budget {record.required_minimum_budget}; "
                "the report must claim it (metric required_minimum_budget)"
            )
    return missing


def check_report(
    report: Report,
    runs_dir: Path,
    inputs_dir: Path = Path("data/inputs"),
    conversation_runs: Iterable[str] | None = None,
) -> CheckResult:
    """Check every claim against its stored run and every summary number against the claims.

    `conversation_runs` are the runs the agent executed or read. When given, a claim citing any
    other run fails; with the cited runs they decide which minimum budgets must be claimed and
    which run ids are not numbers. None (re-checking a saved report) skips the first rule.
    """
    known = None if conversation_runs is None else set(conversation_runs)
    claims = [check_claim(c, runs_dir, inputs_dir, known) for c in report.claims]
    valid = Report(summary=report.summary, claims=[c.claim for c in claims if c.ok])
    run_ids = list(dict.fromkeys([*(conversation_runs or ()), *_run_ids(report)]))
    allowed = allowed_numbers(valid, runs_dir, conversation_runs or ())
    nothing_validated = bool(claims) and not valid.claims
    numbers = []
    for text, value in find_numbers(report.summary, run_ids):
        if nothing_validated:
            numbers.append(NumberCheck(text=text, ok=False, message=NOT_CHECKED))
            continue
        match = any(abs(value - v) <= tol + FLOAT_SLACK for v, tol in allowed)
        message = "matches" if match else "does not match any validated claim or request value"
        numbers.append(NumberCheck(text=text, ok=match, message=message))
    missing = missing_minimum_budgets(valid, run_ids, runs_dir)
    candidates = untraced_candidates(valid, runs_dir, conversation_runs or ())
    return CheckResult(claims=claims, numbers=numbers, missing=missing, candidates=candidates)
