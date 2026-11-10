"""Rich tables for CLI output."""

from rich.table import Table

from happy_toad.engine.result import SolveResult


def sweep_table(results: list[SolveResult]) -> Table:
    """One row per budget; plan columns show "-" when there is no plan."""
    table = Table()
    for name in ("budget", "must_fund", "status", "spend", "weighted relief", "# selected"):
        table.add_column(name, justify="right")
    for r in results:
        has_plan = r.selected is not None
        table.add_row(
            f"{r.budget:.2f}",
            f"{r.must_fund_total:.2f}",
            r.status,
            f"{r.spend:.2f}" if has_plan else "-",
            f"{r.objective:.3f}" if has_plan else "-",
            str(len(r.selected)) if has_plan else "-",
        )
    return table
