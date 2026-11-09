"""Smoke test: the package imports and the CLI app exists."""

from happy_toad.cli import app


def test_cli_app_exists() -> None:
    assert app is not None


def test_generate_command_writes_files(tmp_path) -> None:
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, ["generate", "--seed", "3", "--out-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "changes_v1_to_v2.json",
        "v1.json",
        "v2.json",
    ]
