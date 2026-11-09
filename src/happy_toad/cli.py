"""Command-line interface for happy_toad."""

import typer

app = typer.Typer(help="happy_toad: budget-constrained capital-allocation optimizer.")


@app.callback()
def main() -> None:
    """Entry point; subcommands are added as milestones land."""
