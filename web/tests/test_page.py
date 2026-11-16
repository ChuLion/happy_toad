"""The page's visible name, architecture diagram and labels (pre-recording polish)."""

import re
from pathlib import Path

from web.page import render_page

NAME = "Capital Planning Scenario Assistant"
WEB = Path(__file__).parents[1]


def page() -> str:
    return render_page({"mode": "live", "max_chars": 10, "examples": {}})


def test_the_visible_name_is_the_new_one_on_the_live_page_and_the_replay():
    for html in (page(), (WEB / "replay.html").read_text()):
        assert f"<title>{NAME}</title>" in html
        assert f"<h1>{NAME}</h1>" in html
        assert not re.search(r"happy[_-]toad", html, re.I)


def test_the_readme_title_is_the_new_name():
    assert (WEB.parent / "README.md").read_text().startswith(f"# {NAME}\n")


def stage(html: str, name: str) -> str:
    """The opening tag of a diagram step."""
    return re.search(rf'<li [^>]*data-stage="{name}"[^>]*>', html).group(0)


def test_ai_steps_look_different_from_code_steps():
    html = page()
    for name in ("intake", "explanation"):
        assert 'class="ai"' in stage(html, name)
    for name in ("gate", "optimizer", "record", "checker"):
        assert 'class="code"' in stage(html, name)


def test_both_feedback_arcs_the_rejected_path_and_the_stored_runs_link_are_drawn():
    html = page()
    arcs = {
        "rejected": "Rejected: back to the agent with every reason",
        "refused": "Refused: back to the agent",
        "rejected-path": "rejected",
        "stored": "stored runs",
    }
    for arc, text in arcs.items():
        assert re.search(rf'data-arc="{arc}"[^>]*>\s*<span class="arc-label">{text}</span>', html)
    assert "once" not in html


def test_the_edges_are_labelled():
    html = page()
    assert '<span class="edge-label accepted">accepted</span>' in html
    assert (
        '<span class="edge-label labels">CHECKED, NOT CHECKED or NO NUMBERS TO CHECK</span>' in html
    )


def test_the_last_step_is_human_review():
    html = page()
    assert re.search(r'data-stage="review"[^>]*><b>Human review</b>', html)
    assert "<b>You</b>" not in html


def test_the_readme_diagram_has_both_feedback_paths_and_human_review():
    readme = (WEB.parent / "README.md").read_text()
    diagram = readme.split("```mermaid")[1].split("```")[0]
    assert "-. rejection reasons, back to the agent .-> I" in diagram
    assert "-. refused report, back to the agent .-> E" in diagram
    assert "Human review" in diagram and "class I,E ai" in diagram
    assert "class G,O,R,C code" in diagram


def test_the_budget_is_labelled_a_ceiling_in_the_table_and_on_the_claim_cards():
    html = page()
    assert 'const BUDGET = "budget (ceiling)";' in html
    assert 'name === "budget" ? BUDGET' in html  # stored-runs table header
    assert "budgetLine(v, x)" in html  # each claim card names its run's budget


def test_the_replay_uses_the_current_check_line():
    replay = (WEB / "replay.html").read_text()
    assert "matched against stored runs" not in replay
    assert "19 claims | 24 numbers checked | 0 mismatches" in replay


def test_the_readme_diagram_names_all_three_labels():
    readme = (WEB.parent / "README.md").read_text()
    diagram = readme.split("```mermaid")[1].split("```")[0]
    assert "C -->|CHECKED, NOT CHECKED or NO NUMBERS TO CHECK| H" in diagram


STEPS = ["Question", "Intake", "Gate", "Optimizer", "Run record", "Explanation", "Checker",
         "Human review"]  # fmt: skip


def test_the_guide_has_the_diagram_steps_in_order():
    guide = (WEB.parent / "docs/GUIDE.md").read_text()
    section = guide.split("## 4. From question to decision")[1].split("\n## ")[0]
    names = re.findall(r"^\d+\. \*\*([^.*(]+?)(?: \((?:AI|code)\))?\.\*\*", section, re.M)
    assert names == STEPS
    assert re.findall(r"<b>([^<]+)</b>", page().split('class="flow"')[1].split("</ol>")[0]) == STEPS
