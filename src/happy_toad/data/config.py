"""Generator parameters. Defaults are documented in docs/SPEC.md."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratorConfig:
    """All knobs of the synthetic data generator."""

    base_year: int = 2026
    last_year: int = 2035
    n_sectors: int = 60
    n_candidates: int = 120
    n_must_fund: int = 5
    must_fund_share: float = 0.10
    under_served_share: float = 0.175
    shortfall_range: tuple[float, float] = (10.0, 100.0)
    offload_share_range: tuple[float, float] = (0.2, 0.8)
    cost_factor_range: tuple[float, float] = (0.7, 1.3)
    max_sectors_per_candidate: int = 4
    markets: tuple[str, ...] = ("market_a", "market_b", "market_c", "market_d")
    types: tuple[str, ...] = ("type_a", "type_b", "type_c")
    new_sectors: int = 3
    moved_triggers: int = 6
    cost_changes: int = 10
    offload_changes: int = 8


DEFAULT_CONFIG = GeneratorConfig()
