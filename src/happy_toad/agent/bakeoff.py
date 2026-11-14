"""Run every demo question against every candidate model and tabulate what happened."""

import json
from collections.abc import Callable
from dataclasses import dataclass
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


def _schema_errors(transcript) -> int:
    """Tool inputs or reports the schema refused: SCHEMA_INVALID records and bad reports."""
    count = 0
    for turn in transcript.turns:
        for c in turn.tool_calls:
            text = json.dumps(c["result"], default=str)
            count += "SCHEMA_INVALID" in text or "does not fit the schema" in text
    return count


def _row(profile: Profile, key: str, transcript, price) -> Row:
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
    )


def run_bakeoff(
    profiles: dict[str, Profile],
    make_client: Callable[[Profile], ChatClient],
    questions: dict[str, str] = QUESTIONS,
    *,
    inputs_dir: Path,
    runs_dir: Path,
    transcripts_dir: Path,
    prices: dict[str, dict] | None = None,
) -> list[Row]:
    """One row per profile and question. A client that cannot be built is an error row."""
    prices = prices or {}
    rows = []
    for profile in profiles.values():
        for key, question in questions.items():
            try:
                client = make_client(profile)
            except RuntimeError as err:
                rows.append(
                    Row(
                        profile.name,
                        profile.model,
                        key,
                        "error",
                        [],
                        0,
                        [],
                        0,
                        0,
                        0,
                        None,
                        [],
                        0.0,
                        prices.get(profile.model),
                        str(err),
                    )  # fmt: skip
                )
                continue
            t = ask(
                question,
                client,
                profile,
                inputs_dir=inputs_dir,
                runs_dir=runs_dir,
                transcripts_dir=transcripts_dir,
            )
            rows.append(_row(profile, key, t, prices.get(profile.model)))
    return rows


def table(rows: list[Row]) -> str:
    """A plain-text table, one line per row."""
    head = "model | q | status | turns | tools | schema errs | tokens in/out | cost | s | providers"
    lines = [head]
    for r in rows:
        cost = "n/a" if r.cost is None else f"{r.cost:.5f}"
        lines.append(
            f"{r.model} | {r.question} | {r.status} | {r.turns} | {','.join(r.tools)} | "
            f"{r.schema_errors} | {r.prompt_tokens}/{r.completion_tokens} | {cost} | "
            f"{r.seconds:.1f} | {','.join(r.providers)}"
        )
    return "\n".join(lines)
