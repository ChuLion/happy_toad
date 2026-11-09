"""Load-time checks on an input set. All problems are collected and reported together."""

import math
from collections import Counter
from collections.abc import Iterator

from happy_toad.data.hashing import compute_hash
from happy_toad.data.schemas import InputSet

DEFAULT_BASE_YEAR = 2026


class InputError(ValueError):
    """Raised when an input set fails one or more load-time checks."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def _duplicates(label: str, ids: list[str]) -> Iterator[str]:
    for value, n in Counter(ids).items():
        if n > 1:
            yield f"duplicate {label} id {value!r}"


def _id_problems(data: InputSet) -> Iterator[str]:
    yield from _duplicates("sector", [s.id for s in data.sectors])
    yield from _duplicates("candidate", [c.id for c in data.candidates])
    yield from _duplicates("must-fund", [m.id for m in data.must_fund])
    pairs = [f"{o.candidate_id}/{o.sector_id}" for o in data.offloads]
    yield from _duplicates("offload pair", pairs)


def _reference_problems(data: InputSet) -> Iterator[str]:
    sector_ids = {s.id for s in data.sectors}
    candidate_ids = {c.id for c in data.candidates}
    for o in data.offloads:
        if o.candidate_id not in candidate_ids:
            yield f"offload refers to unknown candidate {o.candidate_id!r}"
        if o.sector_id not in sector_ids:
            yield f"offload refers to unknown sector {o.sector_id!r}"


def _finite_problems(data: InputSet) -> Iterator[str]:
    numbers = [(f"cost of {i.id!r}", i.cost) for i in [*data.candidates, *data.must_fund]]
    numbers += [(f"offload amount {o.candidate_id}/{o.sector_id}", o.amount) for o in data.offloads]
    numbers += [(f"shortfall of {s.id!r}", s.shortfall) for s in data.sectors]
    for label, value in numbers:
        if not math.isfinite(value):
            yield f"{label} must be finite, got {value}"


def _value_problems(data: InputSet, base_year: int) -> Iterator[str]:
    for item in [*data.candidates, *data.must_fund]:
        if item.cost <= 0:
            yield f"cost of {item.id!r} must be > 0, got {item.cost}"
    for o in data.offloads:
        if o.amount < 0:
            yield f"offload amount {o.candidate_id}/{o.sector_id} must be >= 0, got {o.amount}"
    for s in data.sectors:
        if s.shortfall < 0:
            yield f"shortfall of {s.id!r} must be >= 0, got {s.shortfall}"
        if s.trigger_year < base_year:
            yield f"trigger_year of {s.id!r} is {s.trigger_year}, before base_year {base_year}"


def _hash_problems(data: InputSet) -> Iterator[str]:
    actual = compute_hash(data)
    if data.content_hash != actual:
        yield f"content_hash mismatch: stored {data.content_hash!r}, recomputed {actual!r}"


def check_input_set(data: InputSet, base_year: int = DEFAULT_BASE_YEAR) -> None:
    """Raise InputError listing every failed check; return None if the set is valid."""
    problems = [
        *_id_problems(data),
        *_reference_problems(data),
        *_finite_problems(data),
        *_value_problems(data, base_year),
        *_hash_problems(data),
    ]
    if problems:
        raise InputError(problems)
