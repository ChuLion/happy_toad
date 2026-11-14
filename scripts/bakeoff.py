"""Run the demo questions against every bake-off model (needs OPENROUTER_API_KEY).

Usage: uv run python scripts/bakeoff.py [profile ...]   (default: all four candidates)
Writes bakeoff/<timestamp>.json (rows plus the prices listed at run time) and prints a table.
"""

import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from happy_toad.agent.bakeoff import run_bakeoff, table
from happy_toad.agent.client import OpenRouterClient
from happy_toad.agent.config import BAKEOFF
from happy_toad.data.generator import make_v1
from happy_toad.data.loader import save_input_set

MODELS_URL = "https://openrouter.ai/api/v1/models"


def listed_prices(model_ids: list[str]) -> dict[str, dict]:
    """Per-token prices as listed right now (some are promotional, so they are saved per run)."""
    with urllib.request.urlopen(MODELS_URL) as response:
        data = json.load(response)["data"]
    return {m["id"]: m["pricing"] for m in data if m["id"] in model_ids}


def main(names: list[str]) -> None:
    profiles = {n: BAKEOFF[n] for n in names or BAKEOFF}
    prices = listed_prices([p.model for p in profiles.values()])
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    with TemporaryDirectory() as tmp:
        inputs = Path(tmp) / "inputs"
        inputs.mkdir()
        save_input_set(make_v1(seed=42), inputs / "v1.json")
        rows = run_bakeoff(
            profiles,
            OpenRouterClient,
            inputs_dir=inputs,
            runs_dir=Path("runs"),
            transcripts_dir=Path("transcripts"),
            prices=prices,
        )
    out = Path("bakeoff")
    out.mkdir(exist_ok=True)
    (out / f"{stamp}.json").write_text(
        json.dumps({"rows": [vars(r) for r in rows], "prices": prices}, indent=2)
    )
    print(table(rows))


if __name__ == "__main__":
    main(sys.argv[1:])
