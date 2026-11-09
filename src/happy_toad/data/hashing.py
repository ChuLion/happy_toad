"""Canonical JSON and content hashing for input sets."""

import hashlib
import json

from happy_toad.data.schemas import (
    Candidate,
    InputSet,
    MustFundProject,
    Offload,
    Sector,
)


def canonical_json(data: InputSet) -> str:
    """Serialize the data lists with sorted keys and lists sorted by id (no version or hash)."""
    payload = {
        "sectors": sorted((s.model_dump() for s in data.sectors), key=lambda d: d["id"]),
        "candidates": sorted((c.model_dump() for c in data.candidates), key=lambda d: d["id"]),
        "offloads": sorted(
            (o.model_dump() for o in data.offloads),
            key=lambda d: (d["candidate_id"], d["sector_id"]),
        ),
        "must_fund": sorted((m.model_dump() for m in data.must_fund), key=lambda d: d["id"]),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_hash(data: InputSet) -> str:
    """SHA-256 hex digest of the canonical JSON."""
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def build_input_set(
    version_id: str,
    sectors: list[Sector],
    candidates: list[Candidate],
    offloads: list[Offload],
    must_fund: list[MustFundProject],
) -> InputSet:
    """Create an InputSet whose content_hash is the SHA-256 of its canonical JSON."""
    draft = InputSet(
        version_id=version_id,
        content_hash="",
        sectors=sectors,
        candidates=candidates,
        offloads=offloads,
        must_fund=must_fund,
    )
    return draft.model_copy(update={"content_hash": compute_hash(draft)})
