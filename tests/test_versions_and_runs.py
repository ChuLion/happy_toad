"""Version lister, run reader and run comparer (SPEC, M3 decision 2)."""

import pytest
from agent_helpers import make_run

from happy_toad.services.runs import CompareError, compare_runs, list_versions, read_run


def test_list_versions_returns_sorted_names(tmp_path) -> None:
    for name in ("v2", "v1", "notes"):
        (tmp_path / f"{name}.json").write_text("{}")
    (tmp_path / "readme.txt").write_text("x")
    assert list_versions(tmp_path) == ["notes", "v1", "v2"]


def test_the_change_list_is_not_offered_as_a_version(tmp_path) -> None:
    for name in ("v1", "v2", "changes_v1_to_v2"):
        (tmp_path / f"{name}.json").write_text("{}")
    assert list_versions(tmp_path) == ["v1", "v2"]


def test_list_versions_of_a_missing_folder_is_empty(tmp_path) -> None:
    assert list_versions(tmp_path / "nope") == []


def test_read_run_returns_the_stored_record(tmp_path) -> None:
    record = make_run(tmp_path)
    assert read_run(record.run_id, tmp_path / "runs") == record


def test_read_run_does_not_open_paths_or_missing_runs(tmp_path) -> None:
    make_run(tmp_path)
    (tmp_path / "secret.json").write_text("{}")
    assert read_run("../secret", tmp_path / "runs") is None
    assert read_run("20260101T000000-deadbeef", tmp_path / "runs") is None


def test_compare_runs_reports_differences_and_candidates(tmp_path) -> None:
    a = make_run(tmp_path, budget=12.0)
    b = make_run(tmp_path, budget=12.0, force_in=["Y1"], force_out=["X1"])
    diff = compare_runs(a, b)
    assert diff.run_id_a == a.run_id and diff.run_id_b == b.run_id
    assert diff.fields["spend"].a == pytest.approx(11) and diff.fields["spend"].b == pytest.approx(
        11
    )
    assert diff.fields["weighted_relief"].difference == pytest.approx(
        b.result.objective - a.result.objective
    )
    assert diff.fields["status"].a == "Optimal" and diff.fields["status"].difference is None
    assert diff.only_in_a == ["X1"] and diff.only_in_b == ["Y1"]


def test_compare_runs_refuses_a_run_without_a_plan(tmp_path) -> None:
    good = make_run(tmp_path)
    infeasible = make_run(tmp_path, force_in=["X1", "X2", "Y1"])
    with pytest.raises(CompareError, match=infeasible.run_id):
        compare_runs(good, infeasible)


def test_read_run_of_a_malformed_record_raises_input_error(tmp_path) -> None:
    from happy_toad.data.checks import InputError

    run_id = "20260101T000000-deadbeef"
    (tmp_path / f"{run_id}.json").write_text("{not json")
    with pytest.raises(InputError, match=run_id):
        read_run(run_id, tmp_path)
