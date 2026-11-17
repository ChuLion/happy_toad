"""The flow diagram's path after a run: nodes reached and arcs used, from the view alone.

Runs the page's own flowPath function in node, on the replay's three real views.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).parents[1]
STEPS = ["question", "intake", "gate", "optimizer", "record", "explanation", "checker", "review"]

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def flow_path(view: dict) -> dict:
    """flowPath(view) from page.html, run in node."""
    page = (WEB / "page.html").read_text()
    source = page.split("// flowPath: begin")[1].split("// flowPath: end")[0]
    script = source + f"\nconsole.log(JSON.stringify(flowPath({json.dumps(view)})));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def replay_view(transcript_id: str) -> dict:
    views = json.loads((WEB / "replay.json").read_text())["views"]
    return next(v for v in views if v["transcript_id"] == transcript_id)


def test_a_rejected_run_does_not_reach_the_optimizer_and_uses_the_rejection_arc():
    path = flow_path(replay_view("20261114T210201-5276b834"))
    assert "optimizer" not in path["reached"]
    assert "rejected" in path["arcs"] and "rejected-path" in path["arcs"]


def test_a_checked_run_reaches_all_eight_nodes_and_uses_no_arcs():
    path = flow_path(replay_view("20261114T210145-c04c55d4"))
    assert sorted(path["reached"]) == sorted(STEPS)
    assert path["arcs"] == []


def test_a_report_refused_once_then_corrected_uses_the_checker_to_explanation_arc():
    view = replay_view("20261114T210201-5276b834")
    assert view["correction"]["happened"] and view["status"] == "CHECKED"
    assert "refused" in flow_path(view)["arcs"]


def test_a_run_with_no_answer_does_not_reach_human_review():
    view = replay_view("20261114T210145-c04c55d4") | {"status": None}
    assert "review" not in flow_path(view)["reached"]


def test_a_revision_run_reaches_the_optimizer():
    view = replay_view("20261114T210145-c04c55d4")
    steps = [
        {"tool": "explain_revision", "outcome": "order costs -> offloads -> triggers -> sectors: "
         "relief effects costs +1.00; total +1.00 [r1]"},
        *[s for s in view["steps"] if s["tool"] == "submit_report"],
    ]  # fmt: skip
    path = flow_path(view | {"steps": steps})
    assert {"gate", "optimizer", "record"} <= set(path["reached"])
