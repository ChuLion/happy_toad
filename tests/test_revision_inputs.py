"""M5 5.1: the input comparison, computed from the two versions' data (docs/SPEC.md, M5)."""

import json

from helpers import make_set
from revision_helpers import toy_a, toy_b

from happy_toad.constants import BASE_YEAR
from happy_toad.data.files import write_inputs
from happy_toad.data.loader import load_input_set
from happy_toad.services.revision import compare_inputs


def test_toy_pair_differences():
    c = compare_inputs(toy_a(), toy_b())
    assert c.sectors_added == ["s3"]
    assert c.sectors_removed == []
    assert c.triggers_moved == ["s2"]
    assert c.costs_changed == ["A"]
    assert c.offloads_changed == [["B", "s2"]]  # B-s3 belongs to the added sector
    assert c.unsupported == []


def test_identical_versions_have_no_differences():
    c = compare_inputs(toy_a(), toy_a())
    assert (c.sectors_added, c.sectors_removed, c.triggers_moved) == ([], [], [])
    assert (c.costs_changed, c.offloads_changed, c.unsupported) == ([], [], [])


def test_removed_sector_and_added_or_removed_rows_on_shared_sectors():
    a = make_set([("s1", 10), ("s2", 10)], [("A", 6), ("B", 6)], [("A", "s1", 10), ("B", "s2", 8)])
    b = make_set([("s1", 10)], [("A", 6), ("B", 6)], [("A", "s1", 10), ("B", "s1", 3)])
    c = compare_inputs(a, b)
    assert c.sectors_removed == ["s2"]
    assert c.offloads_changed == [["B", "s1"]]  # B-s2 goes with the removed sector
    assert c.unsupported == []


def test_changes_outside_the_four_kinds_are_listed_as_unsupported():
    a = toy_a()
    added_candidate = make_set(
        [("s1", 10), ("s2", 10)], [("A", 6), ("B", 6), ("C", 1)], [("A", "s1", 10), ("B", "s2", 8)]
    )
    new_shortfall = make_set(
        [("s1", 12), ("s2", 10)], [("A", 6), ("B", 6)], [("A", "s1", 10), ("B", "s2", 8)]
    )
    new_market = make_set(
        [("s1", 10, BASE_YEAR, "other"), ("s2", 10)],
        [("A", 6), ("B", 6)],
        [("A", "s1", 10), ("B", "s2", 8)],
    )
    must_fund = make_set(
        [("s1", 10), ("s2", 10)], [("A", 6), ("B", 6)], [("A", "s1", 10), ("B", "s2", 8)], [5]
    )
    for b in (added_candidate, new_shortfall, new_market, must_fund):
        assert compare_inputs(a, b).unsupported, b
    assert compare_inputs(added_candidate, a).unsupported  # a candidate removed


def test_generated_v1_v2_agrees_with_the_change_list(tmp_path):
    """The comparison reads only the data; the change list is an independent cross-check."""
    write_inputs(42, tmp_path)
    v1, v2 = load_input_set(tmp_path / "v1.json"), load_input_set(tmp_path / "v2.json")
    changes = json.loads((tmp_path / "changes_v1_to_v2.json").read_text())

    def ids(kind, key):
        return sorted(ch[key] for ch in changes if ch["kind"] == kind)

    c = compare_inputs(v1, v2)
    assert c.sectors_added == sorted(
        ch["sector"]["id"] for ch in changes if ch["kind"] == "sector_added"
    )
    assert c.sectors_removed == []
    assert c.triggers_moved == ids("trigger_moved", "sector_id")
    assert c.costs_changed == ids("cost_changed", "candidate_id")
    assert c.offloads_changed == sorted(
        [ch["candidate_id"], ch["sector_id"]] for ch in changes if ch["kind"] == "offload_changed"
    )
    assert c.unsupported == []
    assert (len(c.sectors_added), len(c.triggers_moved), len(c.costs_changed)) == (3, 6, 10)
    assert len(c.offloads_changed) == 8


def test_the_shipped_v1_to_v2_pair_passes_the_supported_change_check(tmp_path):
    """data/inputs holds generated seed 42; every v1 -> v2 difference is one of the four kinds."""
    write_inputs(42, tmp_path)
    v1, v2 = load_input_set(tmp_path / "v1.json"), load_input_set(tmp_path / "v2.json")
    assert compare_inputs(v1, v2).unsupported == []
