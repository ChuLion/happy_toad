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
- **Tie-break.** `ε` is small (default `1e-6`) so among solutions with equal weighted relief the
  cheaper one wins; a candidate adding no relief is never funded. `ε` must stay small enough that
  `ε * total candidate cost` is below any real relief difference we care about.
- **Reported objective is weighted relief only**: `sum_s weight[s] * r[s]`, recomputed from the
  solution, never the solver's tie-break objective.
- Sectors that trigger sooner get larger weight (trigger at `base_year` -> weight 1).
- Relief is capped by need (row 1) and by what funded candidates supply (row 2), so a candidate
  shared across sectors counts toward every sector it relieves.
- If `must_fund_total > budget` the right-hand side of the budget row is negative, so no
  selection is feasible: status `infeasible`.
- `base_year` and `ε` are model parameters, not part of the input data.

### Solver result object
| Field | Meaning |
|---|---|
| `status` | one of `optimal`, `infeasible`, `time_limit_feasible`, `time_limit_no_solution`, `error` |
| `objective` | weighted relief only (see above) |
| `selected` | funded candidate ids |
| `relief` | relief per sector id |
| `spend` | candidate spend only (excludes must-fund) |
| `solve_time` | seconds |
| `budget` | total budget given |
| `must_fund_total` | sum of must-fund costs |
| `base_year` | as used |
| `version_id`, `content_hash` | of the input set solved |
| `time_limit`, `threads` | solver settings used (CBC `timeLimit`, `threads`) |

Status mapping from PuLP/CBC: solved to optimality -> `optimal`; PuLP "Infeasible" ->
`infeasible`; stopped by `timeLimit` with an integer-feasible incumbent -> `time_limit_feasible`
(results are reported, flagged as possibly suboptimal); stopped by `timeLimit` with no incumbent
-> `time_limit_no_solution`; anything else -> `error`. PuLP can report "Optimal" after a time
limit stop, so the mapping also checks the solution status; this is verified by a test.

### Known-answer tests (written before the model)
1. **Zero budget** (no must-fund): nothing selected, objective 0.
2. **Unlimited budget**: every sector's relief equals `min(shortfall, total possible offload)`.
3. **Shared candidate**: one candidate relieving 2 sectors, cheaper than two single-sector
   candidates: the shared one is selected, the singles are not.
4. **Must-fund above budget**: status `infeasible`.
5. **Zero marginal relief**: a candidate that adds no relief (e.g. its sector is already fully
   covered by another funded candidate) is not funded, thanks to the tie-break.
6. **Greedy trap**: budget 10, all weights 1, three sectors with one candidate each:
   A cost 6 / relief 6, B cost 5 / relief 4.5, C cost 5 / relief 4.5 (sector shortfalls large
   enough not to cap). Greedy by relief-per-cost picks A and stops at relief 6. Expected optimum:
   `{B, C}`, objective 9.

### Budget sweep and CLI
`happy-toad sweep <input.json> --budgets 0,50,100,...` solves once per budget (budget = total
including must-fund) and prints a rich table with columns: `budget`, `must_fund`, `status`,
`spend`, `weighted relief`, `# selected`. Infeasible budgets appear as rows with their status.

### Synthetic data generator
`happy-toad generate --seed N` writes `v1` and `v2` JSON to `data/inputs/`. Seeded with
`numpy.random.default_rng`; same seed -> identical files.
- About 60 sectors, 120 candidates; each candidate relieves 1-4 sectors.
- N must-fund projects (default 5).
- Some sectors are deliberately **under-served**: total possible offload < shortfall, so the
  shortfall cap never binds for them.
- `v2` is derived from `v1` with deliberate changes: new constrained sectors, moved trigger
  years, changed candidate costs, changed offloads. Moved triggers never go below `base_year`.

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
