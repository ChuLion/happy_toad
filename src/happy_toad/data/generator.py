"""Seeded generator for the base (v1) synthetic input set."""

import numpy as np

from happy_toad.data.config import DEFAULT_CONFIG, GeneratorConfig
from happy_toad.data.hashing import build_input_set
from happy_toad.data.schemas import Candidate, InputSet, MustFundProject, Offload, Sector


def draw_trigger_year(rng: np.random.Generator, cfg: GeneratorConfig) -> int:
    """Trigger year in [base_year, last_year], skewed towards the near years (Beta(1, 2.5))."""
    span = cfg.last_year - cfg.base_year + 1
    return cfg.base_year + min(int(span * rng.beta(1, 2.5)), span - 1)


def draw_sector(rng: np.random.Generator, cfg: GeneratorConfig, sector_id: str) -> Sector:
    """A sector with random market, shortfall and trigger year."""
    return Sector(
        id=sector_id,
        market=str(rng.choice(cfg.markets)),
        shortfall=round(float(rng.uniform(*cfg.shortfall_range)), 2),
        trigger_year=draw_trigger_year(rng, cfg),
    )


def draw_offload(
    rng: np.random.Generator, cfg: GeneratorConfig, candidate_id: str, sector: Sector
) -> Offload:
    """An offload of 20-80% of the sector's shortfall."""
    share = rng.uniform(*cfg.offload_share_range)
    return Offload(
        candidate_id=candidate_id,
        sector_id=sector.id,
        amount=round(float(share * sector.shortfall), 2),
    )


def make_offloads(
    rng: np.random.Generator, cfg: GeneratorConfig, sectors: list[Sector]
) -> list[Offload]:
    """Offload rows: 1-4 per candidate; each under-served sector gets exactly one row.

    One row is at most 80% of the shortfall, so such a sector can never be fully covered.
    """
    n_under = round(cfg.under_served_share * len(sectors))
    under = list(rng.choice(len(sectors), size=n_under, replace=False))
    served = [s for i, s in enumerate(sectors) if i not in under]
    owners = rng.choice(cfg.n_candidates, size=n_under, replace=False)
    owner_of = {int(k): sectors[i] for k, i in zip(owners, under, strict=True)}

    rows: list[Offload] = []
    for k in range(cfg.n_candidates):
        cid = f"C{k + 1:03d}"
        n_rows = int(rng.integers(1, cfg.max_sectors_per_candidate + 1))
        if k in owner_of:
            rows.append(draw_offload(rng, cfg, cid, owner_of[k]))
            n_rows -= 1
        for i in rng.choice(len(served), size=n_rows, replace=False):
            rows.append(draw_offload(rng, cfg, cid, served[int(i)]))
    return rows


def make_candidates(
    rng: np.random.Generator, cfg: GeneratorConfig, offloads: list[Offload]
) -> list[Candidate]:
    """Candidates whose cost is proportional to their total offload."""
    total: dict[str, float] = {}
    for o in offloads:
        total[o.candidate_id] = total.get(o.candidate_id, 0.0) + o.amount
    return [
        Candidate(
            id=cid,
            type=str(rng.choice(cfg.types)),
            cost=max(0.01, round(float(t * rng.uniform(*cfg.cost_factor_range)), 2)),
        )
        for cid, t in sorted(total.items())
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
    sectors = [draw_sector(rng, cfg, f"S{i + 1:03d}") for i in range(cfg.n_sectors)]
    offloads = make_offloads(rng, cfg, sectors)
    candidates = make_candidates(rng, cfg, offloads)
    must_fund = make_must_fund(rng, cfg, candidates)
    return build_input_set("v1", sectors, candidates, offloads, must_fund)
