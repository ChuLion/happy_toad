"""Command-line interface for happy_toad."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from happy_toad.data.checks import InputError
from happy_toad.data.files import write_inputs
from happy_toad.data.loader import load_input_set
from happy_toad.engine.sweep import default_budgets, parse_budgets, run_sweep
from happy_toad.report import sweep_table

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
    console.print(sweep_table(run_sweep(data, budget_list)))
