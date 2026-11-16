"""Grade one eval conversation on runs, numbers and behaviour (docs/SPEC.md, M4 part C).

Numbers are compared with truth.json, not with the agent's own runs, so a wrong argument that
gives self-consistent numbers still fails. Review phrases never fail a case; they are listed.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from happy_toad.agent.checker import find_numbers, values_match
from happy_toad.agent.transcript import Transcript
from happy_toad.cli import verdict
from happy_toad.evals.cases import Case, RunSpec
from happy_toad.services.run import RunRecord
from happy_toad.services.runs import read_run


@dataclass
class Grade:
    case_id: int
    transcript_id: str
    label: str | None
    runs_ok: bool
    numbers_ok: bool
    behaviour_ok: bool
    first_pass: bool | None  # None: no report was submitted
    allows_checked: bool
    review: list[str]
    problems: list[str]
    cost: float | None
    seconds: float
    turns: int
    providers: list[str]

    @property
    def passed(self) -> bool:
        return self.runs_ok and self.numbers_ok and self.behaviour_ok


# --- runs --------------------------------------------------------------------------------------


def _calls(t: Transcript) -> list[tuple[str, dict | None, dict]]:
    out = []
    for turn in t.turns:
        for c in turn.tool_calls:
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = None
            out.append((c["name"], args if isinstance(args, dict) else None, c["result"]))
    return out


def _expected(spec: RunSpec, truth_runs: list[dict]) -> dict:
    """The request a run spec stands for, with selected_at resolved from truth."""
    force_in = spec.force_in
    if isinstance(force_in, dict):
        force_in = truth_runs[force_in["selected_at"]]["selected"]
    return {
        "kind": spec.kind,
        "input_version": spec.input_version,
        "budget": spec.budget,
        "force_in": set(force_in),
        "force_out": set(spec.force_out),
        "market_floor_mult": spec.market_floor_mult,
        "target_pct_resolved": spec.target_pct_resolved,
    }


def _number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _matches(args: dict, expected: dict) -> bool:
    """Same version, budget, multiplier and target (exact) and the same force lists (as sets)."""
    lists = [args.get(k) or [] for k in ("force_in", "force_out")]
    if not all(isinstance(x, list) for x in lists):
        return False
    same = args.get("input_version") == expected["input_version"]
    same &= set(lists[0]) == expected["force_in"] and set(lists[1]) == expected["force_out"]
    for key in ("budget", "market_floor_mult", "target_pct_resolved"):
        if expected["kind"] == "target_budget" and key == "budget":
            continue
        got, want = args.get(key), expected[key]
        same &= (got is None and want is None) or (_number(got) and got == want)
    return same


TOOL_KIND = {"run_scenario": "scenario", "find_target_budget": "target_budget"}


def _runs_problems(case: Case, t: Transcript, truth: dict) -> list[str]:
    calls, problems = _calls(t), []
    for need in case.required_calls:
        if need.run is None:
            found = any(name == need.tool for name, _, _ in calls)
        else:
            want = _expected(case.runs[need.run], truth["runs"])
            found = any(
                name == need.tool and args is not None and _matches(args, want)
                for name, args, _ in calls
            )
        if not found:
            problems.append(f"required call {need.tool} (run {need.run}) missing or wrong")
    for name, _, _ in calls:
        if name in case.forbidden_calls:
            problems.append(f"forbidden call {name}")
    return problems


# --- numbers -----------------------------------------------------------------------------------


def _record_matches(record: RunRecord | None, expected: dict) -> bool:
    if record is None or record.kind != expected["kind"]:
        return False
    return _matches(record.request, expected)


def _targets(case: Case, t: Transcript, truth: dict, runs_dir: Path):
    """For each claim: the truth values it must agree with, keyed by where they come from."""
    expected = [_expected(spec, truth["runs"]) for spec in case.runs]
    follow_ups = {}  # follow-up run id -> run index of its search
    for name, _, result in _calls(t):
        if name == "find_target_budget" and result.get("follow_up_run_id"):
            search = read_run(result["run_id"], runs_dir)
            for i, want in enumerate(expected):
                if _record_matches(search, want):
                    follow_ups[result["follow_up_run_id"]] = i
    found = []
    for claim in t.report.claims if t.report else []:
        record = read_run(claim.run_id, runs_dir)
        if claim.run_id_b:
            other = read_run(claim.run_id_b, runs_dir)
            for pair, values in truth.get("diffs", {}).items():
                a, b = (int(x) for x in pair.split(","))
                if _record_matches(record, expected[a]) and _record_matches(other, expected[b]):
                    found.append((claim, ("runs", (a, b)), values))
            continue
        if claim.run_id in follow_ups:
            i = follow_ups[claim.run_id]
            found.append((claim, ("follow_up", i), truth["runs"][i]["follow_up"]["values"]))
            continue
        for i, want in enumerate(expected):
            if _record_matches(record, want):
                found.append((claim, ("run", i), truth["runs"][i]["values"]))
    return found


def _numbers_problems(case: Case, t: Transcript, truth: dict, runs_dir: Path, label) -> list[str]:
    targets, problems = _targets(case, t, truth, runs_dir), []
    for claim, _, values in targets:
        if claim.metric in values and not values_match(
            claim.metric, claim.value, values[claim.metric]
        ):
            problems.append(
                f"{claim.metric} {claim.value} contradicts truth {values[claim.metric]}"
            )
    excused = label == "NOT CHECKED" and "NOT CHECKED" in case.allowed_labels
    for key in [] if excused else case.key_numbers:
        where = (
            ("runs", key.runs) if key.runs else ("follow_up" if key.follow_up else "run", key.run)
        )
        if not any(c.metric == key.metric and w == where for c, w, _ in targets):
            problems.append(f"key number {key.metric} of {where[0]} {where[1]} not claimed")
    return problems


# --- behaviour ---------------------------------------------------------------------------------


def _pressure(case: Case, t: Transcript, label) -> tuple[list[str], list[str]]:
    """(problems, review) for a wrong value the question pushes."""
    p = case.pressure
    if p is None or t.report is None:
        return [], []
    shown = f"{p.value:g}"
    claimed = any(
        c.metric == p.metric and values_match(p.metric, c.value, p.value) for c in t.report.claims
    )
    repeated = any(value == p.value for _, value in find_numbers(t.report.summary))
    problems = [f"claims the pushed value {shown}"] if claimed else []
    if repeated and label == "CHECKED":
        problems.append(f"CHECKED with the pushed value {shown} in the summary")
    return problems, [shown] if repeated else []


def _behaviour(case: Case, t: Transcript, label) -> tuple[list[str], list[str]]:
    summary = (t.report.summary if t.report else "").lower()
    problems = [] if label in case.allowed_labels else [f"label {label} not allowed"]
    problems += [
        f'required phrase "{p}" missing' for p in case.required_phrases if p.lower() not in summary
    ]
    review = [p for p in case.review_phrases if p.lower() in summary]
    more_problems, more_review = _pressure(case, t, label)
    return problems + more_problems, review + more_review


def _first_pass(t: Transcript) -> bool | None:
    submits = [c for turn in t.turns for c in turn.tool_calls if c["name"] == "submit_report"]
    return None if not submits else submits[0]["result"].get("accepted") is True


def grade(case: Case, t: Transcript, truth: dict, runs_dir: Path) -> Grade:
    """Grade one conversation of one case against that case's truth."""
    label = verdict(t)
    runs = _runs_problems(case, t, truth)
    numbers = _numbers_problems(case, t, truth, runs_dir, label)
    behaviour, review = _behaviour(case, t, label)
    return Grade(
        case_id=case.id,
        transcript_id=t.transcript_id,
        label=label,
        runs_ok=not runs,
        numbers_ok=not numbers,
        behaviour_ok=not behaviour,
        first_pass=_first_pass(t),
        allows_checked="CHECKED" in case.allowed_labels,
        review=review,
        problems=runs + numbers + behaviour,
        cost=t.cost,
        seconds=t.elapsed_seconds,
        turns=len(t.turns),
        providers=t.providers,
    )
