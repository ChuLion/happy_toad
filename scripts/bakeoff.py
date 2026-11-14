"""Run the demo questions against every bake-off model (needs OPENROUTER_API_KEY).

Usage: uv run python scripts/bakeoff.py [--repeats N] [profile ...]   (default: all candidates)
Writes bakeoff/<timestamp>.json (rows, plus the prices and quantizations listed at run time),
rewritten after every row, and prints each row, then a summary per model and question.
Stops at the first error row (a crash or a provider failure) so it can be looked at before more
money is spent.
"""

import argparse
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from happy_toad.agent.bakeoff import run_bakeoff, summary, table
from happy_toad.agent.client import OpenRouterClient, fetch_quantizations
from happy_toad.agent.config import BAKEOFF
from happy_toad.data.generator import make_v1
from happy_toad.data.loader import save_input_set

MODELS_URL = "https://openrouter.ai/api/v1/models"


def listed_prices(model_ids: list[str]) -> dict[str, dict]:
    """Per-token prices as listed right now (some are promotional, so they are saved per run)."""
    with urllib.request.urlopen(MODELS_URL) as response:
        data = json.load(response)["data"]
    return {m["id"]: m["pricing"] for m in data if m["id"] in model_ids}


def main(names: list[str], repeats: int) -> None:
    profiles = {n: BAKEOFF[n] for n in names or BAKEOFF}
    models = [p.model for p in profiles.values()]
    prices = listed_prices(models)
    listing = {m: fetch_quantizations(m) for m in models}
    out = Path("bakeoff")
    out.mkdir(exist_ok=True)
    target = out / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}.json"
    rows = []

    def save(row) -> None:
        rows.append(row)
        print(table([row]).splitlines()[-1], flush=True)
        body = {"repeats": repeats, "prices": prices, "quantization_listing": listing}
        target.write_text(json.dumps({**body, "rows": [vars(r) for r in rows]}, indent=2))

    with TemporaryDirectory() as tmp:
        inputs = Path(tmp) / "inputs"
        inputs.mkdir()
        save_input_set(make_v1(seed=42), inputs / "v1.json")
        run_bakeoff(
            profiles,
            lambda p: OpenRouterClient(p, quantizations=listing[p.model]),
            inputs_dir=inputs,
            runs_dir=Path("runs"),
            transcripts_dir=Path("transcripts"),
            prices=prices,
            repeats=repeats,
            stop_on_error=True,
            on_row=save,
        )
    print(summary(rows))
    print(f"saved {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("profiles", nargs="*", choices=list(BAKEOFF))
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    main(args.profiles, args.repeats)
