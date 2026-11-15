"""Replay export: one view per transcript, labelled by question prefix unless a label is given."""

from pathlib import Path

from scripts.export_replay import export

FIXTURE = Path(__file__).parents[2] / "tests/fixtures/transcript_demo_c.json"


def test_label_defaults_to_the_question_prefix(tmp_path):
    boot = export([FIXTURE], tmp_path)
    assert boot["labels"] == ["On v1 at a total budget of 600, force in the three most expe..."]


def test_a_given_label_replaces_the_default(tmp_path):
    boot = export([FIXTURE, FIXTURE], tmp_path, {1: "Failed the check (some model)"})
    assert boot["labels"][1] == "Failed the check (some model)"
    assert boot["labels"][0].startswith("On v1 at a total budget of 600")
