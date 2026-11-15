"""The one HTML page, with its boot data (replay views or live settings) inlined."""

import json
from pathlib import Path

TEMPLATE = Path(__file__).with_name("page.html")


def render_page(boot: dict) -> str:
    """page.html with boot JSON inlined; "</" escaped so data cannot close the script tag."""
    data = json.dumps(boot).replace("</", "<\\/")
    return TEMPLATE.read_text().replace("__BOOT__", data)
