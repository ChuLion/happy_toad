"""Definitions from the Glossary section of docs/GUIDE.md, for the claim-card tooltips."""

import re
from pathlib import Path

GUIDE = Path(__file__).parents[1] / "docs/GUIDE.md"
ENTRY = re.compile(r"^- \*\*`([A-Za-z_]+)`:\*\* (.*)$")


def _plain(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def definitions() -> dict[str, str]:
    """Name -> plain-text definition (capitalized, wrapped lines joined) for each backtick entry."""
    found, name = {}, None
    for line in GUIDE.read_text().split("## 7. Glossary", 1)[1].splitlines():
        entry = ENTRY.match(line)
        if entry:
            name = entry.group(1)
            found[name] = _plain(entry.group(2))
        elif name and line.startswith("  "):
            found[name] += " " + _plain(line.strip())
        else:
            name = None
    return {k: v[:1].upper() + v[1:] for k, v in found.items()}
