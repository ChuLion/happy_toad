"""Print a transcript's summary: turns, refusals, checker result, host per turn, final report.

Usage: uv run python scripts/show_transcript.py transcripts/<id>.json [...]
Everything printed passes through `redact`, so no OpenRouter account id is shown.
"""

import json
import sys
from pathlib import Path

from happy_toad.agent.transcript import Transcript, redact


def describe(t: Transcript) -> list[str]:
    lines = [f"{t.transcript_id} | {t.model} | status {t.status} | turns {len(t.turns)}"]
    for turn in t.turns:
        names = ", ".join(c["name"] for c in turn.tool_calls) or "(text)"
        lines.append(f"  turn {turn.index}: {turn.provider} ({turn.quantization}) -> {names}")
    refused = [
        c["result"]
        for turn in t.turns
        for c in turn.tool_calls
        if c["name"] == "submit_report" and c["result"].get("accepted") is False
    ]
    lines.append(f"  refusals: {len(refused)}")
    for r in refused:
        lines.append(f"    - {r.get('error', '')[:200] or '; '.join(r.get('errors', []))[:300]}")
    if t.checks:
        last = t.checks[-1]
        lines.append(f"  checker: ok={last.ok}, claims {sum(c.ok for c in last.claims)}/"
                     f"{len(last.claims)} valid, numbers {sum(n.ok for n in last.numbers)}/"
                     f"{len(last.numbers)} matched")  # fmt: skip
    if t.report:
        lines.append(f"  final summary: {t.report.summary}")
        for c in t.report.claims:
            second = f" vs {c.run_id_b}" if c.run_id_b else ""
            lines.append(f"    claim {c.metric} = {c.value} ({c.unit}) run {c.run_id}{second}")
    if t.error or t.api_error:
        lines.append(f"  error: {t.error or json.dumps(t.api_error)}")
    return lines


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(redact("\n".join(describe(Transcript.model_validate_json(Path(path).read_text())))))
