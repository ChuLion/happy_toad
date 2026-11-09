# happy_toad

Portfolio project: an AI agent layer over a budget-constrained capital-allocation optimizer.
All data is synthetic. Use generic terms only (sectors, candidate solutions, offload, trigger
year, must-fund projects). Never mention real companies, internal tools, or proprietary methods.

## Working rules
- One milestone at a time. Current: M1 (see docs/SPEC.md). Do not start later milestones.
- Spec first (docs/SPEC.md), then tests, then code. Small commits, clear messages.
- Ask before adding any dependency beyond: pydantic, numpy, pulp, typer, rich, pytest,
  pytest-cov, ruff (mypy optional).
- After each subtask: plain-English summary + 2 questions the owner should answer unaided.
- Keep docs/DEVLOG.md updated (date, what was done, what the owner changed or rejected).
- Never commit secrets. `.env` is gitignored; `.env.example` is committed.
- Keep code simple and readable over clever. Short modules, short functions.

## Commands
- `uv sync` install; `uv run pytest` tests; `uv run ruff check .` / `uv run ruff format .` lint.
- Always `uv run`, never bare `python`; `uv add`, never `pip install`.

## Layout
`src/happy_toad/{data,engine}`, `cli.py`, `tests/`, `data/inputs/`, `runs/` (gitignored),
`docs/{SPEC,DECISIONS,DEVLOG}.md`.
