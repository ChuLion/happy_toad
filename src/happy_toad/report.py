"""Rich tables for CLI output."""

from rich.table import Table

from happy_toad.data.schemas import InputSet
from happy_toad.engine.relief import resolved_count
from happy_toad.engine.result import SolveResult

COLUMNS = (
    "budget",
    "must_fund",
    "status",
    "spend",
    "weighted relief",
    "# selected",
    "resolved",
    "% resolved",
)


def cause_lines(results: list[SolveResult]) -> list[str]:
    """One line per infeasible budget: the budget and its cause code."""
    return [f"{r.budget:.2f}: {r.cause.code}" for r in results if r.cause is not None]


def sweep_table(results: list[SolveResult], data: InputSet) -> Table:
    """One row per budget; plan columns show "-" when there is no plan.

    resolved = sectors whose relief reaches their shortfall, out of all sectors;
    % resolved = resolved / total sectors.
    """
    table = Table(collapse_padding=True, pad_edge=False)
    for name in COLUMNS:
        table.add_column(name, justify="right", min_width=max(len(w) for w in name.split()))
    for r in results:
        has_plan = r.selected is not None
        n_resolved = resolved_count(data, set(r.selected or []))
        table.add_row(
            f"{r.budget:.2f}",
            f"{r.must_fund_total:.2f}",
            r.status,
            f"{r.spend:.2f}" if has_plan else "-",
            f"{r.objective:.3f}" if has_plan else "-",
            str(len(r.selected)) if has_plan else "-",
            f"{n_resolved}/{len(data.sectors)}" if has_plan else "-",
            f"{100 * n_resolved / len(data.sectors):.1f}%" if has_plan else "-",
        )
    return table
