"""Render model summaries: escape all HTML, then render only **bold** and bullet lists."""

import html
import re

BOLD = re.compile(r"\*\*(.+?)\*\*")
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")


def _inline(line: str) -> str:
    return BOLD.sub(r"<strong>\1</strong>", html.escape(line))


def _block(lines: list[str]) -> str:
    """One blank-line-separated block: runs of bullets become lists, other lines a paragraph."""
    out, text, items = [], [], []
    for line in lines + [""]:
        bullet = BULLET.match(line)
        if bullet:
            items.append(f"<li>{_inline(bullet.group(1))}</li>")
            if text:
                out.append("<p>" + "<br>".join(text) + "</p>")
                text = []
            continue
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if line.strip():
            text.append(_inline(line.strip()))
    if text:
        out.append("<p>" + "<br>".join(text) + "</p>")
    return "".join(out)


def render(text: str) -> str:
    """Safe HTML for a summary: model text can never add its own markup."""
    blocks = re.split(r"\n\s*\n", text.strip())
    return "".join(_block(b.splitlines()) for b in blocks)
