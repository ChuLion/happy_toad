"""Rich tables for CLI output."""

from rich.table import Table

from happy_toad.data.schemas import InputSet
from happy_toad.engine.relief import resolved_count, still_short
from happy_toad.engine.result import SolveResult

COLUMNS = (
    "budget",
    "must_fund",
    "status",
    "spend",
    "weighted relief",
    "# selected",
    "resolved",
    "still short",
)


def sweep_table(results: list[SolveResult], data: InputSet) -> Table:
    """One row per budget; plan columns show "-" when there is no plan.

    resolved = sectors fully relieved, out of all sectors; still short = shortfall left unrelieved.
    """
    table = Table(collapse_padding=True, pad_edge=False)
    for name in (
        "budget",
        "must_fund",
        "status",
        "spend",
        "weighted relief",
        "# selected",
        "resolved",
        "still short",
    ):
        table.add_column(name, justify="right", min_width=max(len(w) for w in name.split()))
    for r in results:
        has_plan = r.selected is not None
        chosen = set(r.selected or [])
        table.add_row(
            f"{r.budget:.2f}",
            f"{r.must_fund_total:.2f}",
            r.status,
            f"{r.spend:.2f}" if has_plan else "-",
            f"{r.objective:.3f}" if has_plan else "-",
            str(len(r.selected)) if has_plan else "-",
            f"{resolved_count(data, chosen)}/{len(data.sectors)}" if has_plan else "-",
            f"{still_short(data, chosen):.2f}" if has_plan else "-",
        )
    return table
