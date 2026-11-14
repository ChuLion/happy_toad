"""Project-wide constants. The planning window starts at BASE_YEAR and lasts HORIZON_YEARS."""

BASE_YEAR = 2027
HORIZON_YEARS = 5  # trigger years run BASE_YEAR .. BASE_YEAR + HORIZON_YEARS - 1
BUDGET_CAP_FACTOR = (
    1.5  # the request gate rejects budgets above this x (candidate cost + must-fund)
)
