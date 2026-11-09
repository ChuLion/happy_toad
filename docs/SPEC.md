# SPEC

## M1 — Synthetic data and the optimizer core

### Goal
Given synthetic input data and a budget, choose which candidate solutions to fund so that
weighted shortfall relief is maximized. Deliver: schemas, generator, load-time checks, a PuLP
model, known-answer tests, and a CLI budget sweep. No AI agent work in M1.

### Terms
- **Sector**: an area with a capacity `shortfall` (amount of need) that becomes binding in its
  `trigger_year`. Has a `market` label (informational in M1).
- **Candidate**: a fundable solution with a `cost` and a `type` label.
- **Offload**: how much of a sector's shortfall a candidate relieves if funded. Many-to-many:
  one candidate may relieve several sectors, one sector may be relieved by several candidates.
- **Must-fund project**: a project with a `cost` that is always paid; it reduces the budget
  available to candidates.
- **Input set**: one versioned bundle of all of the above (`version_id`, `content_hash`).

### Schemas (pydantic v2)
| Model | Fields |
|---|---|
| Sector | `id: str`, `market: str`, `shortfall: float`, `trigger_year: int` |
| Candidate | `id: str`, `type: str`, `cost: float` |
| Offload | `candidate_id: str`, `sector_id: str`, `amount: float` |
| MustFundProject | `id: str`, `cost: float` |
| InputSet | `version_id: str`, `content_hash: str`, `sectors`, `candidates`, `offloads`, `must_fund` |

`content_hash` is a SHA-256 of the canonical JSON of the data lists, so identical content gives
an identical hash regardless of `version_id`.

### Load-time checks
1. Every `Offload.candidate_id` and `Offload.sector_id` resolves to an existing Candidate/Sector.
2. IDs are unique within each collection; at most one Offload per (candidate, sector) pair.
3. All costs `> 0` (candidates and must-fund projects).
4. All offload amounts `>= 0`.
5. Sector `shortfall >= 0` and `trigger_year >= base_year` (needed so the weight below is defined
   and positive).

### Formulation
Sets and data: sectors `s`, candidates `c`; `shortfall[s]`, `offload[c,s]` (0 if no row),
`cost[c]`, `budget`, `must_fund_total = sum of must-fund costs`, `base_year`.

Decision variables:

    x[c] in {0,1}        candidate c is funded
    r[s] >= 0            relief delivered to sector s

Objective:

    maximize sum_s weight[s] * r[s]
    weight[s] = 1 / (trigger_year[s] - base_year + 1)

Constraints:

    r[s] <= shortfall[s]                          for each sector s
    r[s] <= sum_c offload[c,s] * x[c]             for each sector s
    sum_c cost[c] * x[c] <= budget - must_fund_total

Notes:
- Sectors that trigger sooner get larger weight (trigger at `base_year` -> weight 1).
- Relief is capped by need (first constraint) and by what funded candidates supply (second), so
  a candidate shared across sectors counts toward every sector it relieves.
- If `budget - must_fund_total < 0` the model is infeasible (no `x` can satisfy the budget row
  because costs are positive and `x = 0` gives `0 > negative`). Reported as status "Infeasible".
- `base_year` is a model parameter, not part of the input data.

### Solver output
A result object with: solver `status`, `objective`, `selected` candidate ids, `relief` per
sector, `spend` (candidate spend only), and `solve_time` in seconds.

### Known-answer tests (written before the model)
1. Budget 0 (no must-fund): nothing selected, objective 0.
2. Unlimited budget: every sector's relief equals `min(shortfall, total possible offload)`.
3. Shared candidate (relieves 2 sectors) cheaper than two single-sector candidates: shared one
   is selected, the two singles are not.
4. Must-fund total above budget: status Infeasible.

### Budget sweep and CLI
`happy-toad sweep <input.json> --budgets 0,50,100,...` solves once per budget and prints a rich
table: budget, spend, weighted relief (objective), number of candidates selected.

### Synthetic data generator
Seeded (`numpy` default_rng). About 60 sectors and 120 candidates; each candidate relieves 1-4
sectors. Version `v1` is the base; `v2` is derived from `v1` with deliberate changes: new
constrained sectors, moved trigger years, changed candidate costs, changed offloads. Written to
`data/inputs/` as JSON.

### Out of scope for M1
Agent layer, natural-language interface, scenario comparison, multi-year budgets, persistence of
runs (`runs/` is reserved but unused).

### Open questions for owner
1. `base_year` default (proposal: 2026), and is `trigger_year >= base_year` an acceptable
   load-time rule, or should earlier triggers be clamped to weight 1?
2. Units: shortfall, offload and cost are plain floats (no unit conversion). OK?
3. `market` and `type` are unused labels in M1. OK to keep them as plain strings?
4. mypy is listed as optional. Add it (dev dependency) or skip for M1?
