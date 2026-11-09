"""Command-line interface for happy_toad."""

from pathlib import Path
from typing import Annotated

import typer

from happy_toad.data.files import write_inputs

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
