# Decisions

Short records of design choices and why. Newest last.

## D1 — uv, pydantic v2, PuLP+CBC, typer+rich
Plain, widely known tools; CBC ships with PuLP so no external solver install.

## D2 — Cost minimization via a two-stage solve (not an ε penalty)
**Decision:** solve in two stages. Stage 1 maximizes weighted relief to get `R*`. Stage 2 minimizes
spend subject to weighted relief >= `R* - δ/10` (`δ = 1e-4`), with CBC gaps at 0 in both stages and
one 30 s time limit across both.

**The claim we make:** *optimal relief within δ/10, then minimum spend among plans that deliver it.*

**What we tried first.** One solve with a cost penalty in the objective:
`maximize relief - ε * spend`, `ε = δ / (10 * (budget - must_fund_total))`. It was chosen for
simplicity (one solve per sweep point), and a note said to raise `δ` to 1e-3 if it failed.

**Why it failed.** It failed at scale, and the sweep found it, not the unit tests. On generated v1
at budgets of about 4900 and up, candidates adding exactly zero relief were funded (spend rose while
relief stayed 1183.0580317). Tests 3, 5 and 7 passed only because their numbers are small. With
`avail` near 4475, `ε` is about 2e-9, so a 68-unit candidate carries a penalty of about 1.5e-7 on an
objective of about 1183: a relative size of 1e-10, below what CBC resolves. The design guaranteed
the penalty can never *outweigh* relief; it did not guarantee the solver can *see* it.

**What we measured before changing course.**
- Raising `δ` to 1e-3 fixed one budget (4922.39) but left 2 zero-marginal candidates at every
  larger budget.
- Setting CBC's `increment` to 1e-9 removed them at the large budgets but not at 4922.39, and spend
  then drifted down as the budget grew (4016, 3949, 3885): plans were still not minimum-spend.
- The plateau spend also differed between platforms (macOS 4090.14, Linux 4064.59), a sign that the
  solver was returning arbitrary members of a near-tied set.

Tuning `δ` or solver options cannot fix a scale mismatch, so the cost has to be optimized as its own
objective.

**Why two stages work.** Stage 2's objective is spend (hundreds to thousands), and plans differ by
at least about 0.01, so there is no scale problem. Stage 2 is always feasible because the stage-1
plan satisfies its relief row; the code asserts this. The slack `δ/10` must be well above CBC's
feasibility tolerance (about 1e-7) so the row is not lost in rounding, and well below `δ` so the
solver gives up less than the smallest relief difference we care about.

**Cost / limits.** Two solves per sweep point (each 0.03-2.2 s on v1). A stage-2 timeout returns the
stage-1 plan with `TimeLimit` (relief-optimal, not minimum spend). Stage 2 may give up at most
`δ/10` of relief to save spend.

**Alternative considered:** post-solve pruning (drop funded candidates whose removal costs less than
`δ`). Simpler, but it only removes zero-marginal candidates and does not make plans minimum-spend.

**Guards:** known-answer tests 1-7 plus the scale regression tests in SPEC (every funded candidate
adds more than `δ`; plateau spend is constant; relief is within the slack of the stage-1 optimum).

## D3 — CBC via `pulp[cbc]` (cbcbox)
PuLP 4.2 no longer ships a CBC binary: `listSolvers(onlyAvailable=True)` was empty and
`PULP_CBC_CMD` is gone. Chosen: `uv add 'pulp[cbc]'`, which adds the `cbcbox` binary wheel.
Same setup locally and in CI, no system install. Alternatives considered: system CBC via
brew/apt (setup outside uv, CBC version can differ per machine) and switching to HiGHS (departs
from the CBC spec). Owner approved the new dependency.

## D4 — A candidate's market is the market of its largest offload row
Market floors and caps limit candidate spend per market, so every candidate needs one market.
Chosen: the market of its largest offload row, ties to the lowest sector id. About 10-15 of the
~51 generated candidates (10, 12, 15, 11 on seeds 1, 2, 3, 42) have rows in more than one market,
so a cross-market candidate's **full cost counts against one market**. That overstates one market's
spend and understates the others; it is a deliberate simplification, listed in the README
limitations. Alternatives considered: splitting the cost in proportion to the offload rows (makes
the per-market constraints continuous in cost shares but harder to explain and to test with
known answers) and a home market stored on the candidate (a schema change, not needed in M1).
A candidate with no offload rows belongs to no market and is not limited.

**Guards:** known-answer tests 8-11 (SPEC) and unit tests for the market assignment, fair share,
clamp and pre-solve checks in `tests/test_market_limits.py`.

## D5 — The request gate returns all reasons, not just the first
A request can be wrong in several ways at once (a negative budget and an unknown candidate id, say).
Stopping at the first problem would make the caller fix and resubmit one error at a time, and the
M3 agent would need several round trips to find out what to ask the human. Chosen: `check_request`
runs every check it can and returns every reason, in a fixed order (version, budget, candidate
ids, force conflict, forced cost), each with a code and a message. Checks that need the data are
skipped only when the version is missing. Cost: a few redundant reasons (a budget of -1 also
"cannot cover" any forced-in cost), which are harmless because each has its own code.
Alternative considered: fail fast with one reason (simpler, but hides problems). Rejected requests
never reach the solver and are still written as run records.

**Guards:** `tests/test_request_and_gate.py` (each code alone, all together, missing version).
