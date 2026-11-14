"""Small builders for known-answer test inputs. Triggers default to BASE_YEAR (weight 1)."""

from happy_toad.constants import BASE_YEAR
from happy_toad.data.hashing import build_input_set
from happy_toad.data.schemas import Candidate, InputSet, MustFundProject, Offload, Sector


def make_set(sectors, candidates, offloads, must_fund=()) -> InputSet:
    """Build an InputSet from plain tuples.

    sectors: (id, shortfall) or (id, shortfall, trigger_year); candidates: (id, cost);
    offloads: (candidate_id, sector_id, amount); must_fund: list of costs.
    """
    return build_input_set(
        "test",
        [
            Sector(
                id=s[0], market="m", shortfall=s[1], trigger_year=s[2] if len(s) > 2 else BASE_YEAR
            )
            for s in sectors
        ],
        [Candidate(id=c[0], type="t", cost=c[1]) for c in candidates],
        [Offload(candidate_id=c, sector_id=s, amount=a) for c, s, a in offloads],
        [MustFundProject(id=f"M{i}", cost=c) for i, c in enumerate(must_fund, 1)],
    )
