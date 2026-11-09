"""Map PuLP's solve status to happy_toad's status names."""

from pulp.constants import LpSolveStatus


def map_status(solve_status: LpSolveStatus) -> str:
    """Return Optimal, Infeasible, TimeLimit or Error.

    Only a proven optimum is "Optimal". CBC reports "Optimal (within gap tolerance)" (GapLimit)
    when its gap test ends the search; we pin both gap tolerances to 0, so that is a proven
    optimum too. A time-limit stop is always "TimeLimit", whether or not a plan was found.
    Anything unexpected (unbounded, interrupted, ...) is "Error".
    """
    match solve_status:
        case LpSolveStatus.Optimal | LpSolveStatus.GapLimit:
            return "Optimal"
        case LpSolveStatus.Infeasible:
            return "Infeasible"
        case LpSolveStatus.TimeLimit:
            return "TimeLimit"
        case _:
            return "Error"
