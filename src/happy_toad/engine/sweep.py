"""Budget sweep: solve the same input set at several total budgets."""

from happy_toad.data.schemas import InputSet
from happy_toad.engine.model import solve
from happy_toad.engine.result import SolveResult


def parse_budgets(text: str) -> list[float]:
    """Parse a comma-separated list such as "0,50,100"."""
    return [float(part) for part in text.split(",")]


def default_budgets(total_candidate_cost: float, must_fund_total: float) -> list[float]:
    """Total budgets for 5%, 10%, ..., 100% of candidate cost, each plus the must-fund total."""
    return [
        share * total_candidate_cost + must_fund_total for share in (i / 20 for i in range(1, 21))
    ]


def run_sweep(data: InputSet, budgets: list[float]) -> list[SolveResult]:
    """One solve per budget, in the order given."""
    return [solve(data, budget) for budget in budgets]
