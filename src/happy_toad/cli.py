"""Command-line interface for happy_toad."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from happy_toad.agent.config import PROFILES
from happy_toad.agent.loop import ask as run_ask
from happy_toad.data.checks import InputError
from happy_toad.data.files import write_inputs
from happy_toad.data.loader import load_input_set
from happy_toad.engine.sweep import default_budgets, parse_budgets, run_sweep
from happy_toad.report import cause_lines, sweep_table

app = typer.Typer(help="happy_toad: budget-constrained capital-allocation optimizer.")


@app.callback()
def main() -> None:
    """Entry point; subcommands are added as milestones land."""


@app.command()
def generate(
    seed: Annotated[int, typer.Option(help="Random seed; same seed gives identical files.")] = 42,
    out_dir: Annotated[Path, typer.Option(help="Where to write the files.")] = Path("data/inputs"),
) -> None:
    """Generate synthetic v1, v2 and the v1-to-v2 change list."""
    write_inputs(seed, out_dir)
    typer.echo(f"Wrote v1.json, v2.json and changes_v1_to_v2.json to {out_dir}")


@app.command()
def sweep(
    input_path: Annotated[Path, typer.Argument(help="Input set JSON (from `generate`).")],
    budgets: Annotated[
        str | None,
        typer.Option(help="Comma-separated TOTAL budgets (incl. must-fund). Default: 5%-100%."),
    ] = None,
    market_floor_mult: Annotated[
        float | None,
        typer.Option(
            help="Per-market spend floor as a multiple of fair share x avail. Off if unset."
        ),
    ] = None,
    market_cap_mult: Annotated[
        float | None,
        typer.Option(
            help="Per-market spend cap as a multiple of fair share x avail. Off if unset."
        ),
    ] = None,
) -> None:
    """Solve at several budgets and print spend vs weighted relief."""
    try:
        data = load_input_set(input_path)
    except InputError as err:
        typer.echo(f"Invalid input: {err}", err=True)
        raise typer.Exit(1) from err
    total_cost = sum(c.cost for c in data.candidates)
    must_fund = sum(m.cost for m in data.must_fund)
    try:
        budget_list = parse_budgets(budgets) if budgets else default_budgets(total_cost, must_fund)
    except ValueError as err:
        raise typer.BadParameter(f"not a comma-separated list of numbers: {budgets!r}") from err

    console = Console()
    console.print(
        f"{data.version_id}: total candidate cost {total_cost:.2f} | must-fund {must_fund:.2f}"
    )
    options = dict(market_floor_mult=market_floor_mult, market_cap_mult=market_cap_mult)
    results = run_sweep(data, budget_list, **options)
    console.print(sweep_table(results, data))
    for line in cause_lines(results):
        console.print(f"Infeasible {line}")


def make_client(profile):
    """The live OpenRouter client; tests replace this with a fake."""
    from happy_toad.agent.client import OpenRouterClient

    return OpenRouterClient(profile)


def _show_event(kind: str, payload: dict) -> None:
    result = json.dumps(payload["result"], default=str)
    shown = result if len(result) <= 300 else result[:300] + " ..."
    typer.echo(f"-> {payload['name']}({payload['arguments']})\n   {shown}")


def _show_outcome(t) -> None:
    typer.echo(f"\nStatus: {t.status}" + (f" ({t.error})" if t.error else ""))
    if t.report is not None and t.status in ("checked", "unverified"):
        typer.echo(f"\nReport:\n{t.report.summary}")
    for check in t.checks[-1:]:
        for c in check.claims:
            typer.echo(
                f"  {'ok  ' if c.ok else 'FAIL'} {c.claim.metric} = {c.claim.value}: {c.message}"
            )
        for n in check.numbers:
            typer.echo(f"  {'ok  ' if n.ok else 'FAIL'} number {n.text}: {n.message}")
    if t.status == "unverified":
        typer.echo("UNVERIFIED: the numbers above did not all match the stored runs.")
    cost = "cost: not configured" if t.cost is None else f"cost: ${t.cost:.4f}"
    providers = sorted({x.provider or "unknown" for x in t.turns})
    tokens = t.total_tokens
    typer.echo(
        f"\n{len(t.turns)} turns, tokens {tokens['prompt']} in / {tokens['completion']} out, "
        f"{cost}, {t.elapsed_seconds:.1f}s, model {t.model}, provider {', '.join(providers)}"
    )


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="A plain-English question about the scenarios.")],
    profile: Annotated[
        str, typer.Option(help="demo (default), smoke (free) or a round name.")
    ] = "demo",
    inputs_dir: Annotated[Path, typer.Option()] = Path("data/inputs"),
    runs_dir: Annotated[Path, typer.Option()] = Path("runs"),
    transcripts_dir: Annotated[Path, typer.Option()] = Path("transcripts"),
) -> None:
    """Ask the agent a question; shows its tool calls, the checked report and the check results."""
    if profile not in PROFILES:
        raise typer.BadParameter(
            f"unknown profile {profile!r}; valid: {', '.join(PROFILES)}", param_hint="--profile"
        )
    chosen = PROFILES[profile]
    try:
        client = make_client(chosen)
    except RuntimeError as err:
        typer.echo(str(err))
        raise typer.Exit(2) from err
    t = run_ask(
        question,
        client,
        chosen,
        inputs_dir=inputs_dir,
        runs_dir=runs_dir,
        transcripts_dir=transcripts_dir,
        on_event=_show_event,
    )
    _show_outcome(t)
    raise typer.Exit(0 if t.status == "checked" else 1)
