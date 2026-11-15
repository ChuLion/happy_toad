"""Command-line interface for happy_toad."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from happy_toad.agent.config import PROFILES
from happy_toad.agent.loop import ask as run_ask
from happy_toad.agent.transcript import redact
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
    if label := verdict(t):
        typer.echo(f"\nVerdict: {label}")
    cost = "cost: not configured" if t.cost is None else f"cost: ${t.cost:.4f}"
    providers = sorted({x.provider or "unknown" for x in t.turns})
    tokens = t.total_tokens
    typer.echo(
        f"\n{len(t.turns)} turns, tokens {tokens['prompt']} in / {tokens['completion']} out, "
        f"{cost}, {t.elapsed_seconds:.1f}s, model {t.model}, provider {', '.join(providers)}"
    )


def _scenario_args(args: dict) -> str:
    parts = [str(args.get("input_version", "?")), f"budget {args.get('budget')}"]
    for key, value in args.items():
        if key in ("input_version", "budget", "label") or value in (None, []):
            continue
        shown = ", ".join(map(str, value)) if isinstance(value, list) else value
        parts.append(f"{key.replace('_', ' ')} {shown}")
    return ", ".join(parts)


def _call_args(name: str, raw: str) -> str:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return "(unreadable arguments)"
    if not isinstance(args, dict):
        return "(unreadable arguments)"
    if name == "run_scenario":
        return _scenario_args(args)
    if name == "submit_report":
        return f"{len(args.get('claims') or [])} claims"
    return " ".join(f"{v}" for v in args.values())


def _run_outcome(result: dict) -> str:
    r = result.get("result")
    if result.get("outcome") == "completed" and r is not None and r.get("spend") is not None:
        text = f"{r['status']}, spend {r['spend']:.2f}, weighted relief {r['objective']:.2f}"
    else:
        codes = " ".join(x["code"] for x in result.get("reasons") or [])
        status = r["status"] if r else result.get("outcome")
        text = " ".join(filter(None, [status, codes, result.get("error")]))
    if result.get("required_minimum_budget") is not None:
        text += f", minimum budget {result['required_minimum_budget']}"
    return f"{text} [{result.get('run_id')}]"


def _compare_outcome(result: dict) -> str:
    fields = result.get("fields", {})
    diffs = [
        f"{name.replace('_', ' ')} {f['difference']:+.2f}"
        for name, f in fields.items()
        if name in ("spend", "weighted_relief") and f.get("difference") is not None
    ]
    return "compared: " + (", ".join(diffs) or "no plan differences")


def _call_outcome(name: str, result: dict) -> str:
    if name == "submit_report":
        n = len(result.get("errors") or []) or 1
        problems = "1 problem" if n == 1 else f"{n} problems"
        return "accepted" if result.get("accepted") else f"refused ({problems})"
    if name in ("run_scenario", "get_run") and "run_id" in result:
        return _run_outcome(result)
    if result.get("error"):
        return f"error: {result['error']}"
    if name == "list_input_versions":
        return ", ".join(result.get("versions", []))
    if name == "compare_runs":
        return _compare_outcome(result)
    return "ok"


def _say(console: Console, text: str, **style) -> None:
    """Print plain text (no rich markup), with account ids redacted."""
    console.print(redact(text), markup=False, highlight=False, soft_wrap=True, **style)


def compact_tool_call(call: dict, console: Console) -> None:
    """One line per tool call: name, key arguments, outcome."""
    name = call["name"]
    parts = [name, _call_args(name, call["arguments"]), "->", _call_outcome(name, call["result"])]
    _say(console, " ".join(filter(None, parts)))


def _correction(t) -> str | None:
    """What the first submit_report got wrong, when it was refused and a later one accepted."""
    submits = [c for turn in t.turns for c in turn.tool_calls if c["name"] == "submit_report"]
    if t.status != "checked" or len(submits) < 2 or submits[0]["result"].get("accepted"):
        return None
    if "errors" not in submits[0]["result"]:
        return "First report refused, then corrected: it did not fit the report schema"
    first = t.checks[0]
    parts = []
    if numbers := [n.text for n in first.numbers if not n.ok]:
        parts.append("unmatched numbers " + ", ".join(numbers))
    if claims := [f"{c.claim.metric} {c.claim.value}" for c in first.claims if not c.ok]:
        parts.append("mismatched claims " + ", ".join(claims))
    if first.missing:
        parts.append(f"{len(first.missing)} missing minimum-budget claims")
    return "First report refused, then corrected: " + "; ".join(parts)


def _counts(check) -> list[str]:
    errors = check.errors()
    matched = sum(n.ok for n in check.numbers)
    mismatches = "1 mismatch" if len(errors) == 1 else f"{len(errors)} mismatches"
    head = (
        f"{len(check.claims)} claims, {matched} numbers matched against stored runs, {mismatches}"
    )
    return [head] + [f"  {e}" for e in errors]


NO_FIGURES = "NO NUMBERS TO CHECK"
BADGE_STYLE = {
    "CHECKED": "bold reverse green",
    "NOT CHECKED": "bold reverse red",
    NO_FIGURES: "bold reverse",
}
EXIT_CODE = {"CHECKED": 0, NO_FIGURES: 3}  # anything else: 1


def verdict(t) -> str | None:
    """The one verdict for both outputs and the exit code; None when there is no report to show.

    CHECKED needs a verified claim or number; an answer with neither is NO NUMBERS TO CHECK.
    """
    if t.report is None or t.status not in ("checked", "unverified"):
        return None
    if t.status != "checked":
        return "NOT CHECKED"
    last = t.checks[-1]
    return NO_FIGURES if not last.claims and not last.numbers else "CHECKED"


def exit_code(t) -> int:
    """0 CHECKED, 3 NO NUMBERS TO CHECK, 1 otherwise (SPEC, M3 decision 10)."""
    return EXIT_CODE.get(verdict(t), 1)


def _footer(t) -> str:
    providers = ", ".join(sorted({x.provider or "unknown" for x in t.turns})) or "no provider"
    cost = "cost not configured" if t.cost is None else f"${t.cost:.4f}"
    return f"{t.model} | {providers} | {len(t.turns)} turns | {cost} | {t.elapsed_seconds:.1f} s"


def compact_outcome(t, console: Console) -> None:
    """Summary panel with a badge (CHECKED, NOT CHECKED or NO NUMBERS TO CHECK), counts, footer."""
    if label := verdict(t):
        badge = Text(f" {label} ", style=BADGE_STYLE[label])
        console.print(Panel(Text(redact(t.report.summary)), title=badge, title_align="left"))
        if note := _correction(t):
            _say(console, note)
        no_figures = label == NO_FIGURES
        lines = ["No checkable figures in this answer"] if no_figures else _counts(t.checks[-1])
        for line in lines:
            _say(console, line)
    else:
        detail = t.error or (f"HTTP {t.api_error['status']}" if t.api_error else None)
        _say(console, f"Status: {t.status}" + (f" ({detail})" if detail else ""))
    _say(console, _footer(t), style="dim")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help="A plain-English question about the scenarios.")],
    profile: Annotated[
        str, typer.Option(help="demo (default), smoke (free) or a round name.")
    ] = "demo",
    inputs_dir: Annotated[Path, typer.Option()] = Path("data/inputs"),
    runs_dir: Annotated[Path, typer.Option()] = Path("runs"),
    transcripts_dir: Annotated[Path, typer.Option()] = Path("transcripts"),
    verbose: Annotated[bool, typer.Option(help="Full tool results and every check.")] = False,
) -> None:
    """Ask the agent a question; shows its tool calls, the checked report and the check results."""
    if profile not in PROFILES:
        raise typer.BadParameter(
            f"unknown profile {profile!r}; valid: {', '.join(PROFILES)}", param_hint="--profile"
        )
    chosen = PROFILES[profile]
    console = Console()
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
        on_event=_show_event if verbose else lambda _kind, call: compact_tool_call(call, console),
    )
    if verbose:
        _show_outcome(t)
    else:
        compact_outcome(t, console)
    raise typer.Exit(exit_code(t))
