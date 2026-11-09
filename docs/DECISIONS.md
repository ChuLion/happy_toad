# Decisions

Short records of design choices and why. Newest last.

## D1 — uv, pydantic v2, PuLP+CBC, typer+rich
Plain, widely known tools; CBC ships with PuLP so no external solver install.

## D2 — Cost tie-break via ε, not a two-stage solve
ε = δ / (10 × (budget − must_fund_total)), δ = 1e-4 weighted relief; CBC gap tolerances
(`gapAbs`, `gapRel`) set explicitly below the ε term. Chosen for simplicity and one solve per
sweep point; the optimizer is the base layer, and the project's focus is the agent and its
checks.

Alternative considered: lexicographic two-stage solve (maximize relief, then minimize cost at
fixed relief). More rigorous and needs no ε, but doubles the solves per sweep point.

Guard: known-answer test 7 (a candidate costing the full available budget with relief just
above δ must be selected) ensures ε never trades real relief for savings. Fallback: if tests 3
or 5 fail because ε is lost in solver tolerance, raise δ to 1e-3, re-run test 7, log in DEVLOG.

## D3 — CBC via `pulp[cbc]` (cbcbox)
PuLP 4.2 no longer ships a CBC binary: `listSolvers(onlyAvailable=True)` was empty and
`PULP_CBC_CMD` is gone. Chosen: `uv add 'pulp[cbc]'`, which adds the `cbcbox` binary wheel.
Same setup locally and in CI, no system install. Alternatives considered: system CBC via
brew/apt (setup outside uv, CBC version can differ per machine) and switching to HiGHS (departs
from the CBC spec). Owner approved the new dependency.
