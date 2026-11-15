# web: replay and local live page

Everything here sits outside `src/happy_toad`. The page and the server only ever see the dict
from `web.view.build_view(transcript, run_records)`; its shape is `web.schema.View`
(`schema_version` 1).

## Static replay
```
uv run python -m scripts.export_replay ../happy_toad/transcripts/<a>.json ../happy_toad/transcripts/<c>.json \
    --runs-dir ../happy_toad/runs
```
Writes `web/replay.json` and `web/replay.html` (the JSON inlined, no external requests, no keys).
Open `web/replay.html` directly in a browser. It is labelled "Replay of real runs on synthetic
data, not a live demo."

## Local live mode
```
uv run happy-toad generate --seed 42      # once, if data/inputs is empty
OPENROUTER_API_KEY=... uv run python -m web.server     # http://127.0.0.1:8765
```
- Bound to 127.0.0.1 only. The key is read from the server's environment and never sent to the
  browser.
- Calls `happy_toad.agent.loop.ask` (the function `happy-toad ask` uses) with the `demo`
  profile and the CLI's `make_client`. Tool-call steps stream to the page through the loop's
  `on_event` hook as they happen; the final view follows.
- Questions are capped at 500 characters; one request at a time (a second gets HTTP 429).
- Standard library only; no new dependency.

## Wording
Synthetic data. A run is "checked" when the checker traced every number in the summary to a
stored run; "not checked" otherwise. Never "guaranteed".

## Tests
`uv run pytest web/tests` (not in the default `testpaths`, which is in pyproject).
