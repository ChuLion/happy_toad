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
