"""Compare the optimizer with a greedy relief-per-cost baseline on generated v1.

Run: uv run python scripts/compare_greedy.py [seed]
Budgets are 20%, 50%, 80% of total candidate cost, plus the must-fund total (budget is total).
Greedy repeatedly funds the affordable candidate with the best marginal weighted relief per cost.
"""

import sys

from rich.console import Console
from rich.table import Table

from happy_toad.constants import BASE_YEAR
from happy_toad.data.generator import make_v1
from happy_toad.data.schemas import InputSet
from happy_toad.engine.model import solve
from happy_toad.engine.relief import weighted_relief


def greedy(data: InputSet, avail: float) -> tuple[set[str], float]:
    """Return (chosen candidate ids, weighted relief)."""
    chosen: set[str] = set()
    spend, current = 0.0, 0.0
    while True:
        best = None
        for c in data.candidates:
            if c.id in chosen or spend + c.cost > avail:
                continue
            gain = weighted_relief(data, chosen | {c.id}, BASE_YEAR) - current
            if gain > 0 and (best is None or gain / c.cost > best[0]):
                best = (gain / c.cost, c)
        if best is None:
            return chosen, current
        chosen.add(best[1].id)
        spend += best[1].cost
        current += best[0] * best[1].cost


def main(seed: int) -> None:
    data = make_v1(seed)
    total_cost = data.candidate_total
    must_fund = data.must_fund_total
    table = Table(title=f"Optimizer vs greedy (v1, seed {seed})")
    for col in ("share", "budget", "status", "opt relief", "greedy relief", "gap %", "opt time s"):
        table.add_column(col, justify="right")
    for share in (0.2, 0.5, 0.8):
        avail = share * total_cost
        result = solve(data, budget=avail + must_fund)
        _, greedy_relief = greedy(data, avail)
        gap = 100 * (result.objective - greedy_relief) / result.objective
        table.add_row(
            f"{share:.0%}", f"{avail + must_fund:.1f}", result.status, f"{result.objective:.3f}",
            f"{greedy_relief:.3f}", f"{gap:.2f}", f"{result.solve_time:.2f}",
        )  # fmt: skip
    Console().print(table)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 42)
