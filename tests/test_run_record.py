"""The run service: one JSON record per attempt (SPEC, M2A decisions 6, 7, C, D)."""

import json
import math

import pytest
from helpers import make_set

from happy_toad.constants import BASE_YEAR, HORIZON_YEARS
from happy_toad.data.config import DEFAULT_CONFIG
from happy_toad.data.loader import save_input_set
from happy_toad.reasons import ReasonCode
from happy_toad.services.request import SolveRequest, request_hash
from happy_toad.services.run import run_request


@pytest.fixture
def dirs(tmp_path):
    """inputs/ holds version "test" (sectors sX1 and sX2 resolvable by X1 and X2, sY1 not)."""
    inputs, runs = tmp_path / "inputs", tmp_path / "runs"
    inputs.mkdir()
    data = make_set(
        [("sX1", 10, BASE_YEAR, "X"), ("sX2", 10, BASE_YEAR, "X"), ("sY1", 10, BASE_YEAR + 4, "Y")],
        [("X1", 6), ("X2", 5), ("Y1", 6)],
        [("X1", "sX1", 10), ("X2", "sX2", 10), ("Y1", "sY1", 4)],
    )
    save_input_set(data, inputs / "test.json")
    return inputs, runs, data


def run(dirs, **kwargs):
    inputs, runs, _ = dirs
    request = SolveRequest(**{"input_version": "test", "budget": 12.0, **kwargs})
    return run_request(request, inputs, runs)


def test_horizon_matches_the_generator_window() -> None:
    assert HORIZON_YEARS == 5
    assert DEFAULT_CONFIG.last_year == BASE_YEAR + HORIZON_YEARS - 1


def test_completed_run_is_written_and_summarized(dirs) -> None:
    record = run(dirs, label="baseline")
    path = dirs[1] / f"{record.run_id}.json"
    assert path.exists() and json.loads(path.read_text())["run_id"] == record.run_id
    assert record.outcome == "completed" and record.reasons == []
    assert record.input_version == "test" and record.content_hash == dirs[2].content_hash
    assert record.request_hash == request_hash(SolveRequest(input_version="test", budget=12.0))
    assert record.request["label"] == "baseline"
    result = record.result
    assert result.status == "Optimal" and sorted(result.selected) == ["X1", "X2"]
    assert (result.resolved, result.total_sectors) == (2, 3)
    assert result.pct_resolved == pytest.approx(200 / 3)
    assert [u.sector_id for u in result.unresolved] == ["sY1"]
    assert result.unresolved[0].gap == pytest.approx(10) and result.cause is None
    assert set(record.timing) == {"gate", "solve", "total"}
    assert record.settings["threads"] == 1 and record.settings["timeLimit"] == 30


def test_rejected_request_is_recorded_with_all_reasons(dirs) -> None:
    record = run(dirs, budget=0, force_in=["ZZ"])
    assert record.outcome == "rejected" and record.result is None
    assert [r.code for r in record.reasons] == [
        ReasonCode.BUDGET_NOT_POSITIVE,
        ReasonCode.UNKNOWN_CANDIDATE,
    ]
    assert json.loads((dirs[1] / f"{record.run_id}.json").read_text())["outcome"] == "rejected"
    assert record.content_hash == dirs[2].content_hash  # the input was found and loaded


def test_unknown_version_is_rejected_and_recorded(dirs) -> None:
    record = run(dirs, input_version="v9")
    assert record.outcome == "rejected"
    assert [r.code for r in record.reasons] == [ReasonCode.VERSION_NOT_FOUND]
    assert record.content_hash is None and (dirs[1] / f"{record.run_id}.json").exists()


def test_version_that_is_a_path_is_not_found(dirs) -> None:
    record = run(dirs, input_version="../test")
    assert [r.code for r in record.reasons] == [ReasonCode.VERSION_NOT_FOUND]


def test_invalid_input_file_is_an_error_record(dirs) -> None:
    inputs = dirs[0]
    (inputs / "test.json").write_text((inputs / "test.json").read_text().replace("6.0", "7.0"))
    record = run(dirs)
    assert record.outcome == "error" and record.result is None
    assert "content_hash" in record.error
    assert (dirs[1] / f"{record.run_id}.json").exists()


def test_unexpected_failure_is_an_error_record(dirs, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr("happy_toad.services.run.solve", boom)
    record = run(dirs)
    assert record.outcome == "error" and "solver exploded" in record.error
    assert (dirs[1] / f"{record.run_id}.json").exists()


def test_same_request_twice_gives_two_run_ids_and_one_request_hash(dirs) -> None:
    first, second = run(dirs), run(dirs)
    assert first.run_id != second.run_id and first.request_hash == second.request_hash
    assert len(list(dirs[1].glob("*.json"))) == 2


def test_target_met_and_not_met(dirs) -> None:
    assert run(dirs, target_pct_resolved=60).result.target_met is True
    assert run(dirs, target_pct_resolved=70).result.target_met is False
    assert run(dirs).result.target_met is None


def test_target_is_not_met_when_there_is_no_plan(dirs) -> None:
    record = run(dirs, budget=12, force_in=["X1", "X2", "Y1"], target_pct_resolved=10)
    assert record.outcome == "rejected"  # the gate catches forced cost 17 > 12
    infeasible = run(dirs, market_floor_mult=2.0, target_pct_resolved=10)
    assert infeasible.result.status == "Infeasible"
    assert infeasible.result.target_met is False and infeasible.result.pct_resolved is None
    assert infeasible.result.cause.code == ReasonCode.FLOORS_EXCEED_BUDGET
    assert infeasible.result.unresolved is None


def test_region_percentage_and_warning(dirs) -> None:
    result = run(dirs, region_total_sectors=10).result
    assert result.pct_of_region == pytest.approx(20.0)  # 2 resolved of 10
    assert run(dirs).result.pct_of_region is None
    small = run(dirs, region_total_sectors=2)
    assert small.warnings and "region_total_sectors" in small.warnings[0]


def test_floors_and_caps_in_the_request_reach_the_solver(dirs) -> None:
    record = run(dirs, market_cap_mult=0.5)
    assert record.result.solver_settings["market_cap_mult"] == 0.5
    assert record.result.solver_settings["market_caps"] is not None
    assert record.result.pct_resolved < 200 / 3


def test_force_lists_reach_the_solver(dirs) -> None:
    record = run(dirs, force_out=["X1"])
    assert "X1" not in record.result.selected
    assert not math.isnan(record.timing["total"])


def test_malformed_input_file_is_an_error_record(dirs) -> None:
    inputs = dirs[0]
    (inputs / "test.json").write_text('{"version_id": "test", "sectors": ')
    record = run(dirs)
    assert record.outcome == "error" and record.result is None
    assert (dirs[1] / f"{record.run_id}.json").exists()


def test_input_file_that_breaks_the_schema_is_an_error_record(dirs) -> None:
    inputs = dirs[0]
    (inputs / "test.json").write_text('{"version_id": "test"}')
    record = run(dirs)
    assert record.outcome == "error" and "sectors" in record.error
