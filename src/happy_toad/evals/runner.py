"""Run eval rounds and summarize them (docs/SPEC.md, M4 part C)."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from happy_toad.agent.client import ChatClient
from happy_toad.agent.config import Profile
from happy_toad.agent.loop import ask
from happy_toad.agent.provenance import provenance
from happy_toad.agent.transcript import Transcript
from happy_toad.evals.cases import Case, load_cases
from happy_toad.evals.grade import Grade, grade

NOISE = (
    "A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under "
    "about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise."
)


class RoundRefused(Exception):
    """A round that must not start: inputs differ from truth, or official on a dirty tree."""


def check_round_allowed(truth: dict, inputs_dir: Path, unofficial: bool) -> dict:
    """Refuse inputs that are not the ones truth was computed on, and dirty official rounds."""
    for version, expected in truth["inputs"].items():
        found = json.loads((inputs_dir / f"{version}.json").read_text())["content_hash"]
        if found != expected:
            raise RoundRefused(f"{version}: content hash {found} differs from truth.json")
    p = provenance()
    if not unofficial and (p["git_dirty"] or p["git_sha"] is None):
        raise RoundRefused(
            "official rounds need a clean working tree (uncommitted changes to tracked files, "
            "or no git); commit first, or pass --unofficial"
        )
    return p


def run_round(
    cases: list[Case],
    make_client: Callable[[Case], ChatClient],
    profile: Profile,
    *,
    repeats: int,
    truth: dict,
    inputs_dir: Path,
    runs_dir: Path,
    transcripts_dir: Path,
    on_grade: Callable[[Grade], None] = lambda g: None,
) -> list[Grade]:
    """Each case `repeats` times, as source "eval", graded against its truth."""
    grades = []
    for case in cases:
        for _ in range(repeats):
            t = ask(
                case.question,
                make_client(case),
                profile,
                inputs_dir=inputs_dir,
                runs_dir=runs_dir,
                transcripts_dir=transcripts_dir,
                source="eval",
            )
            grades.append(grade(case, t, truth["cases"][str(case.id)], runs_dir))
            on_grade(grades[-1])
    return grades


def _rate(flags: list[bool]) -> float | None:
    return None if not flags else sum(flags) / len(flags)


def _rates(all_grades: list[Grade]) -> dict:
    """Rates over the conversations that reached the model; provider errors are only counted."""
    grades = [g for g in all_grades if not g.infrastructure]
    costs = [g.cost for g in grades]
    known = None if any(c is None for c in costs) else sum(costs)
    n = len(grades)
    return {
        "n": n,
        "infrastructure": len(all_grades) - n,
        "pass_rate": _rate([g.passed for g in grades]),
        "runs_rate": _rate([g.runs_ok for g in grades]),
        "numbers_rate": _rate([g.numbers_ok for g in grades]),
        "behaviour_rate": _rate([g.behaviour_ok for g in grades]),
        "checked_rate": _rate([g.label == "CHECKED" for g in grades if g.allows_checked]),
        "first_pass_rate": _rate([g.first_pass for g in grades if g.first_pass is not None]),
        "cost_total": known,
        "seconds_mean": sum(g.seconds for g in grades) / n if n else None,
        "turns_mean": sum(g.turns for g in grades) / n if n else None,
    }


def summarize(grades: list[Grade]) -> dict:
    """Overall and per-case rates, the manual-review list and the noise statement."""
    ids = sorted({g.case_id for g in grades})
    return {
        "overall": _rates(grades),
        "per_case": {str(i): _rates([g for g in grades if g.case_id == i]) for i in ids},
        "review": [
            {"case": g.case_id, "transcript_id": g.transcript_id, "phrases": g.review}
            for g in grades
            if g.review and not g.infrastructure
        ],
        "infrastructure": [
            {"case": g.case_id, "transcript_id": g.transcript_id}
            for g in grades
            if g.infrastructure
        ],
        "noise": NOISE,
    }


def report(grades: list[Grade], name: str, official: bool, prov: dict, profile: Profile) -> dict:
    """The round report: header, summary and every grade."""
    header = {
        "round": name,
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "official": official,
        "provenance": prov,
        "profile": profile.name,
        "model": profile.model,
        "providers": sorted({p for g in grades for p in g.providers}),
    }
    rows = [g.__dict__ | {"passed": g.passed} for g in grades]
    return {"header": header} | summarize(grades) | {"grades": rows}


def regrade(
    stored: dict, truth: dict, runs_dir: Path, transcripts_dir: Path, notes: list[str]
) -> dict:
    """Grade a stored round's transcripts again (no new conversations); keep its header."""
    cases = {c.id: c for c in load_cases()}
    grades = []
    for row in stored["grades"]:
        path = transcripts_dir / f"{row['transcript_id']}.json"
        t = Transcript.model_validate_json(path.read_text())
        case = cases[row["case_id"]]
        grades.append(grade(case, t, truth["cases"][str(case.id)], runs_dir))
    header = stored["header"] | {
        "regraded": {
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "provenance": provenance(),
        },
        "notes": stored["header"].get("notes", []) + notes,
    }
    rows = [g.__dict__ | {"passed": g.passed} for g in grades]
    return {"header": header} | summarize(grades) | {"grades": rows}


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def _pct(rate: float | None) -> str:
    return "-" if rate is None else f"{100 * rate:.0f}%"


def markdown(r: dict) -> str:
    """A short Markdown summary of a round report."""
    h, o = r["header"], r["overall"]
    title = f"# Eval round {h['round']}" + ("" if h["official"] else " (UNOFFICIAL)")
    p = h["provenance"]
    lines = [
        title,
        "",
        f"{h['date']} | commit {p['git_sha']}{' (uncommitted changes)' if p['git_dirty'] else ''}"
        f" | prompt {p['prompt_sha256'][:12]} | "
        f"{h['model']} | {', '.join(h['providers']) or 'no provider'}",
        "",
        f"Pass {_pct(o['pass_rate'])} | runs {_pct(o['runs_rate'])} | numbers "
        f"{_pct(o['numbers_rate'])} | behaviour {_pct(o['behaviour_rate'])} | checked "
        f"{_pct(o['checked_rate'])} | first pass {_pct(o['first_pass_rate'])} | n {o['n']} | "
        f"infrastructure {o['infrastructure']} (excluded) | "
        f"cost {'-' if o['cost_total'] is None else f'${o["cost_total"]:.4f}'} | "
        f"mean {_num(o['seconds_mean'])} s, {_num(o['turns_mean'])} turns",
        "",
        r["noise"],
        "",
        "| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for case, c in r["per_case"].items():
        lines.append(
            f"| {case} | {c['n']} | {c['infrastructure']} | {_pct(c['pass_rate'])} | "
            f"{_pct(c['runs_rate'])} | "
            f"{_pct(c['numbers_rate'])} | {_pct(c['behaviour_rate'])} | "
            f"{_pct(c['checked_rate'])} | {_pct(c['first_pass_rate'])} |"
        )
    notes = h.get("notes") or []
    if "regraded" in h:
        notes = [
            f"regraded {h['regraded']['date']} at commit {h['regraded']['provenance']['git_sha']}"
        ] + notes
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    lines += ["", "## Failures", ""]
    lines += [
        f"- case {g['case_id']}, transcript {g['transcript_id']} ({g['label']}): "
        + "; ".join(g["problems"])
        for g in r["grades"]
        if not g["passed"] and not g["infrastructure"]
    ] or ["- none"]
    lines += ["", "## Infrastructure (provider errors, excluded from every rate)", ""]
    lines += [
        f"- case {x['case']}, transcript {x['transcript_id']}" for x in r["infrastructure"]
    ] or ["- none"]
    lines += ["", "## Manual review", ""]
    lines += [
        f"- case {x['case']}, transcript {x['transcript_id']}: {', '.join(x['phrases'])}"
        for x in r["review"]
    ] or ["- none"]
    return "\n".join(lines) + "\n"
