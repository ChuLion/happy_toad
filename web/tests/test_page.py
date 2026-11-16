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


def test_both_feedback_paths_are_drawn_back_to_the_agent():
    html = page()
    assert re.search(r'class="back"[^>]*data-branch="rejected"', html)
    assert re.search(r'class="back"[^>]*data-branch="mismatch"', html)
    assert "Rejected: back to the agent with every reason." in html
    assert "Refused: back to the agent, once" in html


def test_the_last_step_is_human_review():
    html = page()
    assert re.search(r'data-stage="review"[^>]*><b>Human review</b>', html)
    assert "<b>You</b>" not in html


def test_the_readme_diagram_has_both_feedback_paths_and_human_review():
    readme = (WEB.parent / "README.md").read_text()
    diagram = readme.split("```mermaid")[1].split("```")[0]
    assert "-. rejection reasons, back to the agent .-> I" in diagram
    assert "-. refused report, back to the agent once .-> E" in diagram
    assert "Human review" in diagram and "class I,E ai" in diagram
    assert "class G,O,R,C code" in diagram


def test_the_budget_is_labelled_a_ceiling_in_the_table_and_on_the_claim_cards():
    html = page()
    assert 'const BUDGET = "budget (ceiling)";' in html
    assert 'name === "budget" ? BUDGET' in html  # stored-runs table header
    assert "budgetLine(v, x)" in html  # each claim card names its run's budget
