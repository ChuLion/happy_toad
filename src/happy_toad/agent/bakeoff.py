"""Run every demo question against every candidate model, repeated, and tabulate what happened."""

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from happy_toad.agent.client import ChatClient
from happy_toad.agent.config import Profile
from happy_toad.agent.demo import QUESTIONS
from happy_toad.agent.loop import ask


@dataclass
class Row:
    profile: str
    model: str
    question: str
    status: str
    tools: list[str]
    schema_errors: int
    check_failures: list[str]
    turns: int
    prompt_tokens: int
    completion_tokens: int
    cost: float | None
    providers: list[str]
    seconds: float
    price: dict | None  # per-token prices as listed when the run was made
    error: str | None
    repeat: int = 1
    refusals: int = 0  # submit_report calls the model had to correct (schema or checker)
    quantizations: list[str] = field(default_factory=list)

    def listed_cost(self) -> float | None:
        """Tokens times the per-token prices listed at run time."""
        if not self.price:
            return None
        return self.prompt_tokens * float(self.price["prompt"]) + self.completion_tokens * float(
            self.price["completion"]
        )


def _schema_errors(transcript) -> int:
    """Tool inputs or reports the schema refused: SCHEMA_INVALID records and bad reports."""
    count = 0
    for turn in transcript.turns:
        for c in turn.tool_calls:
            text = json.dumps(c["result"], default=str)
            count += "SCHEMA_INVALID" in text or "does not fit the schema" in text
    return count


def _refusals(transcript) -> int:
    calls = [
        c for turn in transcript.turns for c in turn.tool_calls if c["name"] == "submit_report"
    ]
    return sum(c["result"].get("accepted") is False for c in calls)


def _row(profile: Profile, key: str, repeat: int, transcript, price) -> Row:
    t = transcript
    failures = t.checks[-1].errors() if t.checks and not t.checks[-1].ok else []
    return Row(
        profile=profile.name,
        model=profile.model,
        question=key,
        status=t.status,
        tools=[c["name"] for turn in t.turns for c in turn.tool_calls],
        schema_errors=_schema_errors(t),
        check_failures=failures,
        turns=len(t.turns),
        prompt_tokens=t.total_tokens["prompt"],
        completion_tokens=t.total_tokens["completion"],
        cost=t.cost,
        providers=sorted({x.provider or "unknown" for x in t.turns}),
        seconds=t.elapsed_seconds,
        price=price,
        error=t.error,
        repeat=repeat,
        refusals=_refusals(t),
        quantizations=sorted({x.quantization or "unknown" for x in t.turns}),
    )


def _error_row(profile: Profile, key: str, repeat: int, price, message: str) -> Row:
    return Row(
        profile.name, profile.model, key, "error", [], 0, [], 0, 0, 0, None, [], 0.0, price,
        message, repeat,
    )  # fmt: skip


def run_bakeoff(
    profiles: dict[str, Profile],
    make_client: Callable[[Profile], ChatClient],
    questions: dict[str, str] = QUESTIONS,
    *,
    inputs_dir: Path,
    runs_dir: Path,
    transcripts_dir: Path,
    prices: dict[str, dict] | None = None,
    repeats: int = 1,
    stop_on_error: bool = False,
    on_row: Callable[[Row], None] = lambda row: None,
) -> list[Row]:
    """One row per profile, question and repeat. A client that cannot be built is an error row."""
    prices = prices or {}
    rows = []
    for profile in profiles.values():
        for key, question in questions.items():
            for repeat in range(1, repeats + 1):
                price = prices.get(profile.model)
                try:
                    client = make_client(profile)
                except RuntimeError as err:
                    row = _error_row(profile, key, repeat, price, str(err))
                else:
                    t = ask(
                        question,
                        client,
                        profile,
                        inputs_dir=inputs_dir,
                        runs_dir=runs_dir,
                        transcripts_dir=transcripts_dir,
                    )
                    row = _row(profile, key, repeat, t, price)
                rows.append(row)
                on_row(row)
                if stop_on_error and row.status == "error":
                    return rows
    return rows


def table(rows: list[Row]) -> str:
    """A plain-text table, one line per row."""
    head = (
        "model | q | # | status | turns | refusals | tools | tokens in/out | cost | s | providers"
    )
    lines = [head]
    for r in rows:
        cost = "n/a" if r.cost is None else f"{r.cost:.5f}"
        lines.append(
            f"{r.model} | {r.question} | {r.repeat} | {r.status} | {r.turns} | {r.refusals} | "
            f"{','.join(r.tools)} | {r.prompt_tokens}/{r.completion_tokens} | {cost} | "
            f"{r.seconds:.1f} | {','.join(r.providers)}"
        )
    return "\n".join(lines)


def _failure_reasons(rows: list[Row]) -> str:
    counts = Counter()
    for r in rows:
        if r.status != "checked":
            detail = r.error or "; ".join(r.check_failures) or ""
            counts[f"{r.status}: {detail[:90]}"] += 1
    return " / ".join(f"{n}x {text}" for text, n in counts.items()) or "none"


def summary(rows: list[Row]) -> str:
    """One block per model and question: checked count, refusals, turns, listed cost, time."""
    cells: dict[tuple[str, str], list[Row]] = {}
    for r in rows:
        cells.setdefault((r.model, r.question), []).append(r)
    lines = []
    for (model, question), group in cells.items():
        checked = sum(r.status == "checked" for r in group)
        costs = [r.listed_cost() for r in group]
        listed = "n/a" if None in costs else f"${sum(costs) / len(costs):.5f} mean"
        lines.append(
            f"{model} | {question} | checked {checked}/{len(group)} | "
            f"refusals {[r.refusals for r in group]} | turns {[r.turns for r in group]} | "
            f"listed cost {listed} | {sum(r.seconds for r in group) / len(group):.1f} s mean | "
            f"failures: {_failure_reasons(group)} | "
            f"providers {sorted({p for r in group for p in r.providers})} | "
            f"quantization {sorted({q for r in group for q in r.quantizations})}"
        )
    return "\n".join(lines)
