"""Export saved runs to web/replay.json and a self-contained web/replay.html.

Usage: uv run python -m scripts.export_replay <transcript.json> [...] --runs-dir runs
Every view passes through build_view, which redacts keys and account ids.
"""

import argparse
import json
from pathlib import Path

from happy_toad.agent.transcript import Transcript
from web.page import render_page
from web.view import build_view, referenced_runs

WEB = Path(__file__).parents[1] / "web"
LABEL_LENGTH = 60


def export(paths: list[Path], runs_dir: Path) -> dict:
    views = []
    for path in paths:
        t = Transcript.model_validate_json(path.read_text())
        views.append(build_view(t, referenced_runs(t, runs_dir)))
    labels = [v["question"][:LABEL_LENGTH] + "..." for v in views]
    return {"mode": "replay", "views": views, "labels": labels}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transcripts", nargs="+", type=Path)
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    args = parser.parse_args()
    boot = export(args.transcripts, args.runs_dir)
    (WEB / "replay.json").write_text(json.dumps(boot, indent=2))
    (WEB / "replay.html").write_text(render_page(boot))
    print(f"Wrote {len(boot['views'])} runs to web/replay.json and web/replay.html")


if __name__ == "__main__":
    main()
