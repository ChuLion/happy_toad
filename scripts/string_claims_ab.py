"""Does the clarify sentence in submit_report change string-valued claims? (needs the API key)

Usage: uv run python scripts/string_claims_ab.py [N]   (N runs of demo question a, with and without)
Counts claim values the model wrote as JSON strings for numeric metrics, from the raw arguments.
"""

import json
import sys
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from happy_toad.agent.bakeoff import provenance
from happy_toad.agent.client import OpenRouterClient, fetch_quantizations
from happy_toad.agent.config import BAKEOFF
from happy_toad.agent.demo import QUESTIONS
from happy_toad.agent.loop import ask
from happy_toad.agent.tools import CLARIFY_SENTENCE, TOOLS
from happy_toad.data.generator import make_v1
from happy_toad.data.loader import save_input_set

TEXT = {"status", "target_met"}


def without_sentence() -> list[dict]:
    tools = deepcopy(TOOLS)
    spec = next(t for t in tools if t["function"]["name"] == "submit_report")["function"]
    spec["description"] = spec["description"].replace(" " + CLARIFY_SENTENCE, "")
    assert CLARIFY_SENTENCE not in spec["description"]
    return tools


def string_claims(transcript) -> int:
    count = 0
    for turn in transcript.turns:
        for c in turn.tool_calls:
            if c["name"] == "submit_report":
                for claim in json.loads(c["arguments"]).get("claims", []):
                    count += claim.get("metric") not in TEXT and isinstance(claim.get("value"), str)
    return count


def main(n: int) -> None:
    profile = BAKEOFF["gemma_31b"]
    listing = fetch_quantizations(profile.model)
    print("provenance", json.dumps({k: v for k, v in provenance().items() if k != "frozen_files"}))
    with TemporaryDirectory() as tmp:
        inputs = Path(tmp) / "inputs"
        inputs.mkdir()
        save_input_set(make_v1(seed=42), inputs / "v1.json")
        for label, tools in (("with", TOOLS), ("without", without_sentence())):
            for i in range(1, n + 1):
                t = ask(
                    QUESTIONS["a"],
                    OpenRouterClient(profile, quantizations=listing),
                    profile,
                    inputs_dir=inputs,
                    runs_dir=Path("runs"),
                    transcripts_dir=Path("transcripts"),
                    tools=tools,
                )
                providers = sorted({x.provider or "?" for x in t.turns})
                print(
                    f"{label} #{i}: {t.status}, turns {len(t.turns)}, "
                    f"string-valued numeric claims {string_claims(t)}, "
                    f"coercions {len(t.coercions)}, api_error {t.api_error}, providers {providers}",
                    flush=True,
                )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
