"""Revision analysis: plan of record vs refreshed forecast (docs/SPEC.md, M5).

5.1 compares the two versions' data; 5.3 builds in-between inputs in the fixed ORDER.
"""

from pydantic import BaseModel

from happy_toad.data.hashing import build_input_set
from happy_toad.data.schemas import InputSet

ORDER = ("costs", "offloads", "triggers", "sectors")


class InputComparison(BaseModel):
    """What differs between two versions, read from their data (ids sorted)."""

    sectors_added: list[str]
    sectors_removed: list[str]
    triggers_moved: list[str]
    costs_changed: list[str]
    offloads_changed: list[list[str]]
    unsupported: list[str]


def _rows(data: InputSet, sector_ids: set[str]) -> dict[tuple[str, str], float]:
    """Offload amounts by (candidate, sector) for the given sectors."""
    return {
        (o.candidate_id, o.sector_id): o.amount for o in data.offloads if o.sector_id in sector_ids
    }


def _unsupported(a: InputSet, b: InputSet, shared: set[str]) -> list[str]:
    """Differences outside the four change kinds."""
    found = []
    cand_a, cand_b = {c.id: c for c in a.candidates}, {c.id: c for c in b.candidates}
    found += [f"candidate {c} added" for c in sorted(cand_b.keys() - cand_a.keys())]
    found += [f"candidate {c} removed" for c in sorted(cand_a.keys() - cand_b.keys())]
    found += [
        f"candidate {c} type changed"
        for c in sorted(cand_a.keys() & cand_b.keys())
        if cand_a[c].type != cand_b[c].type
    ]
    if sorted(a.must_fund, key=lambda m: m.id) != sorted(b.must_fund, key=lambda m: m.id):
        found.append("must-fund projects changed")
    sec_a, sec_b = {s.id: s for s in a.sectors}, {s.id: s for s in b.sectors}
    for s in sorted(shared):
        if sec_a[s].market != sec_b[s].market:
            found.append(f"sector {s} market changed")
        if sec_a[s].shortfall != sec_b[s].shortfall:
            found.append(f"sector {s} shortfall changed")
    return found


def compare_inputs(a: InputSet, b: InputSet) -> InputComparison:
    """Differences between a and b, from the data only (never from a change list)."""
    sec_a, sec_b = {s.id: s for s in a.sectors}, {s.id: s for s in b.sectors}
    shared = sec_a.keys() & sec_b.keys()
    cost_a, cost_b = {c.id: c.cost for c in a.candidates}, {c.id: c.cost for c in b.candidates}
    rows_a, rows_b = _rows(a, shared), _rows(b, shared)
    return InputComparison(
        sectors_added=sorted(sec_b.keys() - sec_a.keys()),
        sectors_removed=sorted(sec_a.keys() - sec_b.keys()),
        triggers_moved=sorted(s for s in shared if sec_a[s].trigger_year != sec_b[s].trigger_year),
        costs_changed=sorted(c for c in cost_a.keys() & cost_b.keys() if cost_a[c] != cost_b[c]),
        offloads_changed=[
            list(k) for k in sorted(rows_a.keys() | rows_b.keys()) if rows_a.get(k) != rows_b.get(k)
        ],
        unsupported=_unsupported(a, b, shared),
    )


def apply_kinds(a: InputSet, b: InputSet, kinds) -> InputSet:
    """a with the named change kinds taken from b (b's differences must all be supported)."""
    sec_b = {s.id: s for s in b.sectors}
    shared = {s.id for s in a.sectors} & sec_b.keys()
    cost_b = {c.id: c.cost for c in b.candidates}

    candidates = [
        c.model_copy(update={"cost": cost_b[c.id]}) if "costs" in kinds else c for c in a.candidates
    ]
    sectors = [
        s.model_copy(update={"trigger_year": sec_b[s.id].trigger_year})
        if "triggers" in kinds and s.id in shared
        else s
        for s in a.sectors
    ]
    shared_rows = b.offloads if "offloads" in kinds else a.offloads
    offloads = [o for o in shared_rows if o.sector_id in shared]
    if "sectors" in kinds:
        sectors = [s for s in sectors if s.id in shared] + [
            s for s in b.sectors if s.id not in shared
        ]
        offloads += [o for o in b.offloads if o.sector_id not in shared]
    else:
        offloads += [o for o in a.offloads if o.sector_id not in shared]
    version = "+".join([a.version_id, *kinds])
    return build_input_set(version, sectors, candidates, offloads, list(a.must_fund))
