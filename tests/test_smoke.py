"""Smoke test: the package imports and the CLI app exists."""

from happy_toad.cli import app


def test_cli_app_exists() -> None:
    assert app is not None
