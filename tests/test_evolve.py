"""Tests for v2 generation, the change list, and writing files."""

from collections import Counter

import pytest

from happy_toad.data.checks import check_input_set
from happy_toad.data.config import DEFAULT_CONFIG as CFG
from happy_toad.data.evolve import make_v2
from happy_toad.data.files import write_inputs
from happy_toad.data.generator import make_v1
from happy_toad.data.loader import load_input_set


@pytest.fixture(scope="module")
def pair():
    v1 = make_v1(seed=1)
    v2, changes = make_v2(v1, seed=1)
    return v1, v2, changes


def by_kind(changes, kind):
    return [c for c in changes if c["kind"] == kind]


def test_change_counts(pair) -> None:
    _, _, changes = pair
    counts = Counter(c["kind"] for c in changes)
    assert counts == {
        "sector_added": CFG.new_sectors,
        "trigger_moved": CFG.moved_triggers,
        "cost_changed": CFG.cost_changes,
        "offload_changed": CFG.offload_changes,
    }


def test_v2_passes_load_checks_and_has_new_version_id(pair) -> None:
    _, v2, _ = pair
    check_input_set(v2, CFG.base_year)
    assert v2.version_id == "v2"


def test_moved_triggers_never_before_base_year_and_really_move(pair) -> None:
    _, _, changes = pair
    for c in by_kind(changes, "trigger_moved"):
        assert c["new"] >= CFG.base_year
        assert c["new"] != c["old"]


def test_v2_differs_from_v1_in_exactly_the_listed_ways(pair) -> None:
    v1, v2, changes = pair
    s1, s2 = {s.id: s for s in v1.sectors}, {s.id: s for s in v2.sectors}
    c1, c2 = {c.id: c for c in v1.candidates}, {c.id: c for c in v2.candidates}
    o1 = {(o.candidate_id, o.sector_id): o.amount for o in v1.offloads}
    o2 = {(o.candidate_id, o.sector_id): o.amount for o in v2.offloads}

    added = {c["sector"]["id"] for c in by_kind(changes, "sector_added")}
    assert set(s2) - set(s1) == added and set(s1) <= set(s2)
    new_rows = {
        (r["candidate_id"], r["sector_id"]): r["amount"]
        for c in by_kind(changes, "sector_added")
        for r in c["offloads"]
    }
    assert {k: o2[k] for k in set(o2) - set(o1)} == new_rows
    for c in by_kind(changes, "sector_added"):
        assert s2[c["sector"]["id"]].model_dump() == c["sector"]

    moved = {c["sector_id"]: (c["old"], c["new"]) for c in by_kind(changes, "trigger_moved")}
    assert {
        i: (s1[i].trigger_year, s2[i].trigger_year)
        for i in s1
        if s1[i].trigger_year != s2[i].trigger_year
    } == moved
    assert all(
        s1[i].model_dump(exclude={"trigger_year"}) == s2[i].model_dump(exclude={"trigger_year"})
        for i in s1
    )

    costs = {c["candidate_id"]: (c["old"], c["new"]) for c in by_kind(changes, "cost_changed")}
    assert {i: (c1[i].cost, c2[i].cost) for i in c1 if c1[i].cost != c2[i].cost} == costs
    assert set(c1) == set(c2)
    assert all(c1[i].model_dump(exclude={"cost"}) == c2[i].model_dump(exclude={"cost"}) for i in c1)

    amounts = {
        (c["candidate_id"], c["sector_id"]): (c["old"], c["new"])
        for c in by_kind(changes, "offload_changed")
    }
    assert {k: (o1[k], o2[k]) for k in o1 if o1[k] != o2[k]} == amounts
    assert set(o1) <= set(o2)
    assert v1.must_fund == v2.must_fund


def test_write_inputs_is_deterministic_and_loadable(tmp_path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    write_inputs(seed=7, out_dir=a)
    write_inputs(seed=7, out_dir=b)
    names = ["v1.json", "v2.json", "changes_v1_to_v2.json"]
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes()
    load_input_set(a / "v1.json")
    load_input_set(a / "v2.json")
    write_inputs(seed=8, out_dir=b)
    assert (a / "v1.json").read_bytes() != (b / "v1.json").read_bytes()
