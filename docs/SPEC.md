# SPEC

## M1 — Synthetic data and the optimizer core

### Goal
Given synthetic input data and a total budget, choose which candidate solutions to fund so that
weighted shortfall relief is maximized. Deliver: schemas, generator, load-time checks, a PuLP
model, known-answer tests, and a CLI budget sweep. No AI agent work in M1.

### Terms
- **Sector**: an area with a `shortfall` (amount of need) that becomes binding in its
  `trigger_year`. Has a `market` label (informational in M1).
- **Candidate**: a fundable solution with a `cost` and a `type` label (informational in M1).
- **Offload**: how much of a sector's shortfall a candidate relieves if funded. Many-to-many.
- **Must-fund project**: a project with a `cost` that is always paid. It is paid out of the
  budget before any candidate is considered.
- **Budget**: the *total* available, including must-fund projects.
- **Input set**: one versioned bundle of all of the above.

Units: shortfall, offload and cost are plain floats. The unit meaning is documented in the README
(1.9); the code does no unit conversion.

### Schemas (pydantic v2)
All five models use `model_config = ConfigDict(frozen=True, extra="forbid")`: instances cannot be
mutated after creation and unknown fields are rejected. (Frozen is shallow: the lists inside an
`InputSet` can still be mutated; treat them as read-only.)

| Model | Fields |
|---|---|
| Sector | `id: str`, `market: str`, `shortfall: float`, `trigger_year: int` |
| Candidate | `id: str`, `type: str`, `cost: float` |
| Offload | `candidate_id: str`, `sector_id: str`, `amount: float` |
| MustFundProject | `id: str`, `cost: float` |
| InputSet | `version_id: str`, `content_hash: str`, `sectors`, `candidates`, `offloads`, `must_fund` |

### Canonical JSON and content hash
Canonical JSON is the data lists (`sectors`, `candidates`, `offloads`, `must_fund`) serialized
with **sorted keys**, compact separators, and **every list sorted by id** (offloads sorted by
`(candidate_id, sector_id)`). `version_id` and `content_hash` are excluded. `content_hash` is the
SHA-256 hex digest of that string, so identical content gives an identical hash regardless of
`version_id` or list order.

### Load-time checks
1. Every `Offload.candidate_id` and `Offload.sector_id` resolves to an existing Candidate/Sector.
2. IDs are unique within each collection; at most one Offload per (candidate, sector) pair.
3. All costs `> 0` (candidates and must-fund projects).
4. All offload amounts `>= 0`.
5. Sector `shortfall >= 0`.
6. `trigger_year >= base_year` is **rejected** otherwise (earlier triggers are an error, not
   clamped). `base_year` defaults to 2026.
7. The stored `content_hash` equals the hash recomputed from the loaded content, so an input
   file edited by hand (or corrupted) is rejected.

All problems found are reported together in one `InputError`, not just the first.

### Formulation
Sets and data: sectors `s`, candidates `c`; `shortfall[s]`, `offload[c,s]` (0 if no row),
`cost[c]`, `budget`, `must_fund_total = sum of must-fund costs`, `base_year`.

Decision variables:

    x[c] in {0,1}        candidate c is funded
    r[s] >= 0            relief delivered to sector s

Objective (as solved, with cost tie-break):

    maximize sum_s weight[s] * r[s]  -  ε * sum_c cost[c] * x[c]
    weight[s] = 1 / (trigger_year[s] - base_year + 1)

Constraints:

    r[s] <= shortfall[s]                          for each sector s
    r[s] <= sum_c offload[c,s] * x[c]             for each sector s
    sum_c cost[c] * x[c] <= budget - must_fund_total

Notes:
- **Tie-break.** Among solutions with equal weighted relief the cheaper one wins; a candidate
  adding no relief is never funded. `ε` is computed per solve:

      avail = budget - must_fund_total
      ε = δ / (10 × avail),   δ = 1e-4  (weighted-relief units)

  Since spend <= avail, `ε × max spend <= δ/10 < δ`: the cost term can never outweigh a
  relief difference of `δ` or more. If `avail <= 0` then `ε = 0` (nothing is fundable, or the
  model is infeasible, so no tie-break is needed).
- **Solver tolerance must stay below the ε term.** CBC `gapAbs` and `gapRel` are set explicitly
  (both 0) so the solver never stops at a solution that is "close enough" and silently ignores
  the tie-break. If tests 3 or 5 fail because ε is lost in solver tolerance, raise `δ` to `1e-3`,
  re-run test 7, and log the change in DEVLOG.
- **Alternative considered:** a two-stage lexicographic solve (maximize relief, then minimize
  cost at fixed relief). See DECISIONS.md D2.
- **Reported objective is weighted relief only**: `sum_s weight[s] * r[s]`, recomputed from the
  solution, never the solver's tie-break objective.
- Sectors that trigger sooner get larger weight (trigger at `base_year` -> weight 1).
- Relief is capped by need (row 1) and by what funded candidates supply (row 2), so a candidate
  shared across sectors counts toward every sector it relieves.
- If `must_fund_total > budget` the right-hand side of the budget row is negative, so no
  selection is feasible. A **pre-solve check** returns `Infeasible` immediately in that case,
  without calling the solver (CBC may report `Undefined` for such a model, and we do not widen
  the status mapping to cover it).
- `base_year`, `δ` and `ε` are model parameters, not part of the input data.

### Solver result object
| Field | Meaning |
|---|---|
| `status` | one of `Optimal`, `Infeasible`, `TimeLimit`, `Error` |
| `objective` | weighted relief only (see above); `None` if there is no plan |
| `selected` | funded candidate ids; `None` if there is no plan (an empty list means "a plan that funds nothing") |
| `relief` | relief per sector id; `None` if there is no plan |
| `spend` | candidate spend only (excludes must-fund); `None` if there is no plan |
| `solve_time` | seconds |
| `budget` | total budget given |
| `must_fund_total` | sum of must-fund costs |
| `base_year` | as used |
| `version_id`, `content_hash` | of the input set solved |
| `solver_settings` | `threads`, `timeLimit`, `gapRel`, `gapAbs`, `epsilon`, `delta` as used |

Pinned solver settings: `threads=1`, `timeLimit=30` seconds, `gapRel=0`, `gapAbs=0`. All are
recorded in `solver_settings` so a run can be reproduced.

**No plan vs empty plan.** `selected=None` means the solver produced no plan (`Infeasible`,
`Error`, or `TimeLimit` with no incumbent). `selected=[]` means a real plan that funds nothing
(e.g. zero budget).

**Status mapping.** A separate pure function `map_status(solve_status)` turns PuLP's
`LpSolveStatus` (PuLP 4.2 reports it on the object returned by `solve()`, alongside
`has_solution`) into one of our statuses: `Optimal` -> `Optimal`; `GapLimit` -> `Optimal`;
`Infeasible` -> `Infeasible`; `TimeLimit` -> `TimeLimit`; everything else -> `Error`.
- `GapLimit` is mapped to `Optimal` because CBC reports "Optimal (within gap tolerance)" whenever
  its gap test ends the search, and we pin both gap tolerances to 0, so that is a proven optimum.
  (Found in M1 1.6: CBC logged `integer gap of -3.55e-15 less than 0` and `Gap: 0`.)
- **Caveat:** `GapLimit` -> `Optimal` holds only while `gapRel` and `gapAbs` are 0. If they are
  ever loosened, `GapLimit` no longer proves optimality and the mapping must change (the
  `map_status` docstring says the same).
- A time-limit stop is always `TimeLimit`, never `Optimal`. Whether a plan is reported depends on
  `has_solution`: with an incumbent the best-found plan is reported; without one `selected`,
  `objective`, `relief` and `spend` are `None`.
- `map_status` is unit-tested with **mocked** statuses (every `LpSolveStatus` member is covered);
  the plan/no-plan branches are tested by patching `LpProblem.solve`. We do not force a real
  timeout.

### Dependencies
PuLP 4.2 no longer bundles the CBC binary. It comes from the `cbcbox` package via
`pulp[cbc]` (DECISIONS D3). The solver is `pulp.COIN_CMD` pointing at that binary.

### Known-answer tests (written before the model)
1. **Zero budget** (no must-fund): nothing selected, objective 0.
2. **Ample budget**: `budget = sum of all candidate costs + must_fund_total` (never `inf`);
   every sector's relief equals `min(shortfall, total possible offload)`.
3. **Shared candidate**: one candidate relieving 2 sectors, cheaper than two single-sector
   candidates, with a budget large enough to fund **all three**, so that only the tie-break can
   explain why the shared one is selected and the singles are not.
4. **Must-fund above budget**: status `Infeasible` (via the pre-solve check), `selected=None`.
5. **Zero marginal relief**: a candidate that adds no relief (e.g. its sector is already fully
   covered by another funded candidate) is not funded, thanks to the tie-break.
6. **Greedy trap**: budget 10, all weights 1, three sectors with one candidate each:
   A cost 6 / relief 6, B cost 5 / relief 4.5, C cost 5 / relief 4.5 (sector shortfalls large
   enough not to cap). Greedy by relief-per-cost picks A and stops at relief 6. Expected optimum:
   `{B, C}`, objective 9.
7. **Tie-break never beats real relief**: one candidate costing the entire available budget
   (`avail`) with weighted relief just above `δ` (e.g. `1.5e-4`) must be selected. Guards
   against ε trading real relief for savings.

### Budget sweep and CLI
`happy-toad sweep <input.json> [--budgets 0,50,100,...]` loads the input set (running all
load-time checks; a failure prints the problems and exits 1) and solves once per budget, in the
order given. Budgets are **total** budgets, including must-fund.

If `--budgets` is omitted, the default is 5%, 10%, ..., 60% of total candidate cost (12 budgets),
each **plus the must-fund total**.

Output: a header line with the version, total candidate cost and must-fund total, then a rich
table with columns `budget`, `must_fund`, `status`, `spend`, `weighted relief`, `# selected`.
One row per budget. A budget with no plan (e.g. `Infeasible`) shows its status and `-` in the
plan columns. Output is deterministic (CBC single thread, no timing column).

Tests: one row per budget, row values, Infeasible rows, header totals, default budgets,
determinism, rejection of a tampered input file.

### Synthetic data generator
`happy-toad generate --seed N` (default 42) writes `v1.json`, `v2.json` and
`changes_v1_to_v2.json` to `data/inputs/` (gitignored; regenerate with the same seed).
Seeded with `numpy.random.default_rng`; same seed -> byte-identical files. All parameters live in
`GeneratorConfig` (`data/config.py`). Floats are rounded to 2 decimals. Defaults:

| Item | Default |
|---|---|
| Size | 60 sectors (`S001`..), 120 candidates (`C001`..), 5 must-fund (`M1`..) |
| Trigger year | 2026-2035, `2026 + floor(10 * Beta(1, 2.5))` (skewed near) |
| Shortfall | uniform 10-100 |
| Labels | 4 markets `market_a..d`, 3 types `type_a..c`, uniform |
| Candidate reach | each candidate relieves 1-4 sectors (random sectors) |
| Offload per row | 20-80% of that sector's shortfall (uniform) |
| Candidate cost | (candidate total offload) x uniform(0.7, 1.3) |
| Must-fund | total = 10% (`must_fund_share`) of total candidate cost, split by random weights |
| Under-served | 17.5% of sectors (10 of 60) are designated under-served |

**Under-served construction.** A designated sector gets exactly one offload row, which is at most
80% of its shortfall, so it can never be fully covered. Other sectors can also end up
under-served by chance; across seeds 1, 2, 3, 42 the total was 11-14 of 60 (18-23%).

**v2** is derived from v1 (`make_v2`) with these deliberate changes, each recorded in
`changes_v1_to_v2.json` (one entry per change, with `kind`, ids, `old`, `new`):
- `sector_added` x3: new constrained sectors, each with a single offload row (so under-served);
  the entry holds the full sector and its offload row.
- `trigger_moved` x6: distinct sectors, new year in 2026-2035 (never below `base_year`), always
  different from the old year.
- `cost_changed` x10: distinct candidates, cost scaled by 0.5-0.9 or 1.1-1.5.
- `offload_changed` x8: distinct existing offload rows, amount scaled the same way.
Nothing else changes (must-fund projects, labels, other fields are identical).

**Tests.** Same seed gives identical data and files; v1 and v2 pass all load-time checks; v2
differs from v1 in exactly the listed ways (an independent diff of v1 vs v2 is compared to the
change list); counts and ranges match the table.

### Out of scope for M1
Agent layer, natural-language interface, scenario comparison, multi-year budgets, persistence of
runs (`runs/` is reserved but unused), mypy.

### Done when
All tests pass in CI, the CLI prints the sweep table, this file holds the formulation, and
`docs/DEVLOG.md` records the session.

### Subtask 1.9 — README and tag
README gets an M1 section: how to generate data, run the sweep, run tests; unit meaning for
shortfall/offload/cost; and an explicit note that `weight = 1/(trigger_year - base_year + 1)` is
a modelling assumption, not a calibrated value. Then tag `v0.1`.
