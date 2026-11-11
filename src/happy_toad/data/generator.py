"""Seeded generator for the base (v1) synthetic input set.

Structure first: sectors get a coverage count (how many candidates can relieve them), the coverage
slots are dealt to candidates of three types, and the number of candidates falls out of that.
"""

import numpy as np

from happy_toad.data.config import DEFAULT_CONFIG, GeneratorConfig
from happy_toad.data.hashing import build_input_set
from happy_toad.data.schemas import Candidate, InputSet, MustFundProject, Offload, Sector

Plan = list[tuple[str, list[int]]]  # (candidate type, indices of the sectors it relieves)


def market_counts(cfg: GeneratorConfig) -> list[int]:
    """Sectors per market, proportional to the need rates (largest remainder rounding)."""
    raw = [r / sum(cfg.market_need_rates) * cfg.n_sectors for r in cfg.market_need_rates]
    counts = [int(x) for x in raw]
    by_remainder = sorted(range(len(raw)), key=lambda i: raw[i] - counts[i], reverse=True)
    for i in by_remainder[: cfg.n_sectors - sum(counts)]:
        counts[i] += 1
    return counts


def draw_trigger_year(rng: np.random.Generator, cfg: GeneratorConfig) -> int:
    """Trigger year in [base_year, last_year], skewed towards the near years (Beta(1, 2.5))."""
    span = cfg.last_year - cfg.base_year + 1
    return cfg.base_year + min(int(span * rng.beta(1, 2.5)), span - 1)


def draw_market(rng: np.random.Generator, cfg: GeneratorConfig) -> str:
    """A market drawn with probability proportional to its need rate."""
    p = np.array(cfg.market_need_rates) / sum(cfg.market_need_rates)
    return str(rng.choice(cfg.markets, p=p))


def draw_sector(rng: np.random.Generator, cfg: GeneratorConfig, sector_id: str, market: str):
    """A sector with random shortfall and trigger year."""
    return Sector(
        id=sector_id,
        market=market,
        shortfall=round(float(rng.uniform(*cfg.shortfall_range)), 2),
        trigger_year=draw_trigger_year(rng, cfg),
    )


def make_sectors(rng: np.random.Generator, cfg: GeneratorConfig) -> list[Sector]:
    """Sectors whose market counts follow the need rates exactly, in shuffled order."""
    labels = [m for m, n in zip(cfg.markets, market_counts(cfg), strict=True) for _ in range(n)]
    markets = rng.permutation(labels)
    return [draw_sector(rng, cfg, f"S{i + 1:03d}", str(m)) for i, m in enumerate(markets)]


def draw_offload(
    rng: np.random.Generator, cfg: GeneratorConfig, candidate_id: str, sector: Sector
) -> Offload:
    """An offload of offload_share_range of the sector's shortfall."""
    share = rng.uniform(*cfg.offload_share_range)
    return Offload(
        candidate_id=candidate_id,
        sector_id=sector.id,
        amount=round(float(share * sector.shortfall), 2),
    )


def coverage_slots(rng: np.random.Generator, cfg: GeneratorConfig) -> list[int]:
    """One slot per (sector, candidate that relieves it). Most sectors have exactly one slot."""
    cover = np.ones(cfg.n_sectors, dtype=int)
    n_multi = round(cfg.multi_solution_share * cfg.n_sectors)
    multi = rng.choice(cfg.n_sectors, size=n_multi, replace=False)
    cover[multi] = rng.integers(cfg.multi_cover_range[0], cfg.multi_cover_range[1] + 1, n_multi)
    return [int(s) for s, k in enumerate(cover) for _ in range(k)]


def type_counts(cfg: GeneratorConfig, n_slots: int) -> list[int]:
    """Candidates per type so that spend shares match, given a mean reach of each type."""
    counts_per_cost = [
        s / r for s, r in zip(cfg.type_spend_shares, cfg.type_cost_ratios, strict=True)
    ]
    mean_reach = [(lo + hi) / 2 for lo, hi in cfg.type_reach]
    scale = n_slots / sum(c * m for c, m in zip(counts_per_cost, mean_reach, strict=True))
    return [round(scale * c) for c in counts_per_cost]


def fit_sizes(rng: np.random.Generator, ranges: list[tuple[int, int]], total: int) -> list[int]:
    """Draw a size in each (low, high) range, then nudge random ones until they sum to total."""
    sizes = [int(rng.integers(lo, hi + 1)) for lo, hi in ranges]
    while (diff := total - sum(sizes)) != 0:
        step = 1 if diff > 0 else -1
        room = [i for i, (lo, hi) in enumerate(ranges) if lo <= sizes[i] + step <= hi]
        sizes[int(rng.choice(room))] += step
    return sizes


def deal(rng: np.random.Generator, slots: list[int], sizes: list[int]) -> list[list[int]]:
    """Shuffle the slots into groups of the given sizes, reshuffling until no group repeats one."""
    cuts = np.cumsum(sizes)[:-1]
    while True:
        groups = np.split(rng.permutation(slots), cuts)
        if all(len(set(g)) == len(g) for g in groups):
            return [[int(s) for s in g] for g in groups]


def make_plan(rng: np.random.Generator, cfg: GeneratorConfig) -> Plan:
    """Which candidate types exist and which sectors each relieves."""
    slots = coverage_slots(rng, cfg)
    counts = type_counts(cfg, len(slots))
    kinds = [t for t, n in zip(cfg.types, counts, strict=True) for _ in range(n)]
    ranges = [cfg.type_reach[cfg.types.index(t)] for t in kinds]
    order = [int(i) for i in rng.permutation(len(kinds))]
    kinds, ranges = [kinds[i] for i in order], [ranges[i] for i in order]
    groups = deal(rng, slots, fit_sizes(rng, ranges, len(slots)))
    return list(zip(kinds, groups, strict=True))


def make_offloads(
    rng: np.random.Generator, cfg: GeneratorConfig, sectors: list[Sector], plan: Plan
) -> list[Offload]:
    return [
        draw_offload(rng, cfg, f"C{k + 1:03d}", sectors[i])
        for k, (_, group) in enumerate(plan)
        for i in group
    ]


def make_candidates(rng: np.random.Generator, cfg: GeneratorConfig, plan: Plan) -> list[Candidate]:
    """Cost = unit_cost x the type's cost ratio x a random factor."""
    ratio = dict(zip(cfg.types, cfg.type_cost_ratios, strict=True))
    return [
        Candidate(
            id=f"C{k + 1:03d}",
            type=kind,
            cost=round(float(cfg.unit_cost * ratio[kind] * rng.uniform(*cfg.cost_factor_range)), 2),
        )
        for k, (kind, _) in enumerate(plan)
    ]


def make_must_fund(
    rng: np.random.Generator, cfg: GeneratorConfig, candidates: list[Candidate]
) -> list[MustFundProject]:
    """Must-fund projects whose total is must_fund_share of total candidate cost."""
    target = cfg.must_fund_share * sum(c.cost for c in candidates)
    weights = rng.uniform(0.5, 1.5, size=cfg.n_must_fund)
    costs = target * weights / weights.sum()
    return [MustFundProject(id=f"M{i + 1}", cost=round(float(c), 2)) for i, c in enumerate(costs)]


def make_v1(seed: int, cfg: GeneratorConfig = DEFAULT_CONFIG) -> InputSet:
    """Generate the base input set; the same seed always gives the same data."""
    rng = np.random.default_rng(seed)
    sectors = make_sectors(rng, cfg)
    plan = make_plan(rng, cfg)
    offloads = make_offloads(rng, cfg, sectors, plan)
    candidates = make_candidates(rng, cfg, plan)
    must_fund = make_must_fund(rng, cfg, candidates)
    return build_input_set("v1", sectors, candidates, offloads, must_fund)
