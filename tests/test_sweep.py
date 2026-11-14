"""Tests for the budget sweep and the `sweep` CLI command."""

import pytest
from helpers import make_set
from typer.testing import CliRunner

from happy_toad.cli import app
from happy_toad.data.loader import save_input_set
from happy_toad.engine.sweep import default_budgets, parse_budgets

runner = CliRunner(env={"COLUMNS": "200"})  # wide enough that rich does not wrap headers


@pytest.fixture
def input_file(tmp_path):
    """Total candidate cost 9, must-fund 2. C2 (cost 4, offload 6) is the better single pick."""
    data = make_set(
        [("S1", 10)], [("C1", 5), ("C2", 4)], [("C1", "S1", 3), ("C2", "S1", 6)], must_fund=[2]
    )
    path = tmp_path / "in.json"
    save_input_set(data, path)
    return path


def body_rows(output: str) -> list[list[str]]:
    """Cells of each table body row (rich draws body rows with │)."""
    lines = [ln for ln in output.splitlines() if ln.startswith("│")]
    return [[c.strip() for c in ln.strip("│").split("│")] for ln in lines]


def sweep(path, budgets: str | None = None):
    args = ["sweep", str(path)] + (["--budgets", budgets] if budgets else [])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    return result.output


def test_parse_budgets() -> None:
    assert parse_budgets("0, 50,100.5") == [0.0, 50.0, 100.5]


def test_default_budgets_are_5_to_100_percent_plus_must_fund() -> None:
    budgets = default_budgets(total_candidate_cost=200.0, must_fund_total=20.0)
    assert len(budgets) == 20
    assert budgets[0] == pytest.approx(0.05 * 200 + 20)
    assert budgets[-1] == pytest.approx(1.00 * 200 + 20)


def test_one_row_per_budget_with_expected_columns(input_file) -> None:
    out = sweep(input_file, "2,6,20")
    for column in ("budget", "must_fund", "status", "spend", "weighted relief", "# selected"):
        assert column in out
    for column in ("resolved", "% resolved"):
        assert column in out
    assert len(body_rows(out)) == 3


def test_row_values(input_file) -> None:
    rows = body_rows(sweep(input_file, "2,6,20"))
    # [budget, must_fund, status, spend, weighted relief, # selected, resolved, % resolved]
    assert rows[0] == ["2.00", "2.00", "Optimal", "0.00", "0.000", "0", "0/1", "0.0%"]  # nothing
    assert rows[1] == ["6.00", "2.00", "Optimal", "4.00", "6.000", "1", "0/1", "0.0%"]  # C2 only
    assert rows[2] == ["20.00", "2.00", "Optimal", "9.00", "9.000", "2", "0/1", "0.0%"]  # both


def test_resolved_counts_sectors_whose_shortfall_is_fully_relieved(tmp_path) -> None:
    data = make_set(
        [("S1", 10), ("S2", 10)],
        [("C1", 5), ("C2", 5)],
        [("C1", "S1", 10), ("C2", "S2", 4)],
    )
    path = tmp_path / "in.json"
    save_input_set(data, path)
    rows = body_rows(sweep(path, "5,10"))
    assert rows[0][-2:] == ["1/2", "50.0%"]  # C1 resolves S1 only
    assert rows[1][-2:] == ["1/2", "50.0%"]  # C2 adds 4 to S2, still short


def test_percent_resolved_is_resolved_over_total_sectors(tmp_path) -> None:
    sectors = [("S1", 10), ("S2", 10), ("S3", 10)]
    data = make_set(sectors, [("C1", 5)], [("C1", "S1", 10)])
    path = tmp_path / "in.json"
    save_input_set(data, path)
    assert body_rows(sweep(path, "5"))[0][-2:] == ["1/3", "33.3%"]


def test_infeasible_budget_shows_status_and_dashes(input_file) -> None:
    rows = body_rows(sweep(input_file, "0,6"))
    assert rows[0] == ["0.00", "2.00", "Infeasible", "-", "-", "-", "-", "-"]
    assert rows[1][2] == "Optimal"


def test_header_line_has_totals(input_file) -> None:
    out = sweep(input_file, "6")
    assert "total candidate cost 9.00" in out
    assert "must-fund 2.00" in out


def test_default_budgets_used_when_omitted(input_file) -> None:
    rows = body_rows(sweep(input_file))
    assert len(rows) == 20
    assert [r[0] for r in rows][0] == "2.45"  # 5% of 9 = 0.45, plus must-fund 2


def test_sweep_is_deterministic(input_file) -> None:
    assert sweep(input_file, "2,6,20") == sweep(input_file, "2,6,20")


def test_invalid_input_file_is_rejected(tmp_path, input_file) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(input_file.read_text().replace('"cost": 5.0', '"cost": 4.0'))  # breaks the hash
    result = runner.invoke(app, ["sweep", str(bad), "--budgets", "6"])
    assert result.exit_code == 1
    assert "content_hash" in result.output


def test_market_multipliers_are_passed_to_every_solve(input_file) -> None:
    """One market, so fair share is 1: floor = floor_mult * avail. Budget 6 -> avail 4."""
    args = ["sweep", str(input_file), "--budgets", "6", "--market-floor-mult", "1.0"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    rows = body_rows(result.output)
    assert rows[0][3] == "4.00"  # must spend at least 4: C2 (cost 4)


def test_infeasible_rows_name_their_cause_below_the_table(input_file) -> None:
    args = ["sweep", str(input_file), "--budgets", "6,20", "--market-floor-mult", "2.0"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    rows = body_rows(result.output)
    assert rows[0][2] == "Infeasible" and rows[0][3] == "-"
    assert "6.00: FLOORS_EXCEED_BUDGET" in result.output
    assert "20.00" not in result.output.split("┘")[-1]  # only infeasible budgets are listed


def test_cap_multiplier_option(input_file) -> None:
    args = ["sweep", str(input_file), "--budgets", "20", "--market-cap-mult", "0.2"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert body_rows(result.output)[0][3] == "0.00"  # cap 0.2 * 18 = 3.6 is below every cost
