"""Generator parameters. Defaults are documented in docs/SPEC.md."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratorConfig:
    """All knobs of the synthetic data generator.

    The number of candidates is not a knob: it is derived from the coverage draw (see generator).
    """

    base_year: int = 2026
    last_year: int = 2035
    n_sectors: int = 60
    n_must_fund: int = 5
    must_fund_share: float = 0.10
    shortfall_range: tuple[float, float] = (10.0, 100.0)
    offload_share_range: tuple[float, float] = (0.6, 1.2)
    markets: tuple[str, ...] = ("market_a", "market_b", "market_c", "market_d")
    market_need_rates: tuple[float, ...] = (0.07, 0.11, 0.14, 0.18)
    multi_solution_share: float = 0.20
    multi_cover_range: tuple[int, int] = (2, 3)
    types: tuple[str, ...] = ("type_a", "type_b", "type_c")
    type_spend_shares: tuple[float, ...] = (0.85, 0.10, 0.05)
    type_cost_ratios: tuple[float, ...] = (1.0, 0.33, 0.1)
    type_reach: tuple[tuple[int, int], ...] = ((2, 4), (1, 1), (1, 1))
    unit_cost: float = 100.0
    cost_factor_range: tuple[float, float] = (0.7, 1.3)
    new_sectors: int = 3
    moved_triggers: int = 6
    cost_changes: int = 10
    offload_changes: int = 8


DEFAULT_CONFIG = GeneratorConfig()
