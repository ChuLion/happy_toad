"""Summary markdown: HTML is escaped first, then only bold and bullet lists are rendered."""

from web.markdown import render


def test_script_in_a_summary_is_escaped_not_run():
    html = render("Spend is 10 <script>alert(1)</script> **done**")
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<strong>done</strong>" in html


def test_markup_inside_bold_and_bullets_stays_escaped():
    html = render('**<img src=x onerror="a()">**\n- <b>x</b>')
    assert "<img" not in html and "<b>" not in html
    assert "<strong>&lt;img src=x onerror=&quot;a()&quot;&gt;</strong>" in html


def test_bold_and_bullet_lists():
    text = "**Spend** rises.\nSecond line.\n\n- one\n* **two**\n\nAfter."
    assert render(text) == (
        "<p><strong>Spend</strong> rises.<br>Second line.</p>"
        "<ul><li>one</li><li><strong>two</strong></li></ul>"
        "<p>After.</p>"
    )


def test_other_markdown_stays_literal():
    assert render("# Title and _x_ and `y`") == "<p># Title and _x_ and `y`</p>"
