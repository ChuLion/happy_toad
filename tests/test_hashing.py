"""Tests for canonical JSON and content hashing."""

import json

from happy_toad.data.hashing import build_input_set, canonical_json
from happy_toad.data.schemas import Candidate, MustFundProject, Offload, Sector

S1 = Sector(id="S1", market="north", shortfall=10.0, trigger_year=2028)
S2 = Sector(id="S2", market="south", shortfall=4.0, trigger_year=2030)
C1 = Candidate(id="C1", type="build", cost=5.0)
C2 = Candidate(id="C2", type="upgrade", cost=3.0)
O1 = Offload(candidate_id="C1", sector_id="S1", amount=3.0)
O2 = Offload(candidate_id="C1", sector_id="S2", amount=1.0)
O3 = Offload(candidate_id="C2", sector_id="S1", amount=2.0)
M1 = MustFundProject(id="M1", cost=2.0)


def make(version_id: str = "v1", reverse: bool = False):
    lists = [[S1, S2], [C1, C2], [O1, O2, O3], [M1]]
    if reverse:
        lists = [lst[::-1] for lst in lists]
    return build_input_set(version_id, *lists)


def test_canonical_json_sorts_keys_and_lists_by_id() -> None:
    parsed = json.loads(canonical_json(make(reverse=True)))
    assert [s["id"] for s in parsed["sectors"]] == ["S1", "S2"]
    assert [(o["candidate_id"], o["sector_id"]) for o in parsed["offloads"]] == [
        ("C1", "S1"),
        ("C1", "S2"),
        ("C2", "S1"),
    ]
    assert list(parsed["sectors"][0]) == sorted(parsed["sectors"][0])


def test_canonical_json_excludes_version_and_hash() -> None:
    parsed = json.loads(canonical_json(make()))
    assert "version_id" not in parsed
    assert "content_hash" not in parsed


def test_hash_ignores_version_id_and_list_order() -> None:
    assert make("v1").content_hash == make("v2", reverse=True).content_hash


def test_hash_changes_when_content_changes() -> None:
    changed = build_input_set("v1", [S1, S2], [C1, C2.model_copy(update={"cost": 4.0})], [O1], [M1])
    assert changed.content_hash != make().content_hash


def test_hash_is_sha256_hex() -> None:
    assert len(make().content_hash) == 64
