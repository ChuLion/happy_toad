# SPEC

## M1 — Synthetic data and the optimizer core

### Goal
Given synthetic input data and a total budget, choose which candidate solutions to fund so that
weighted shortfall relief is maximized, subject to optional per-market spend floors and caps.
Deliver: schemas, generator, load-time checks, a PuLP
model, known-answer tests, and a CLI budget sweep. No AI agent work in M1.

### Terms
- **Sector**: an area with a `shortfall` (amount of need) that becomes binding in its
  `trigger_year`. Has a `market` label, used by the optional market floors and caps
  (see "Market floors and caps").
- **Candidate**: a fundable solution with a `cost` and a `type` label (informational only; the model never uses it).
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
   clamped). `base_year` defaults to `BASE_YEAR` = 2027, a single constant in
   `src/happy_toad/constants.py` imported by the checks, the model, the generator and the scripts
   (no year literals elsewhere in code).
7. The stored `content_hash` equals the hash recomputed from the loaded content, so an input
   file edited by hand (or corrupted) is rejected.

All problems found are reported together in one `InputError`, not just the first.

### Formulation
Sets and data: sectors `s`, candidates `c`; `shortfall[s]`, `offload[c,s]` (0 if no row),
`cost[c]`, `budget`, `must_fund_total = sum of must-fund costs`, `base_year`.
`avail = budget - must_fund_total`.

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

**Two-stage solve.** The model above is solved in two stages:

1. **Stage 1** solves the model exactly as written (maximize weighted relief) and gives the
   optimal weighted relief `R*` (recomputed from the chosen candidates).
2. **Stage 2** keeps the same variables and constraints, but minimizes spend and adds one row:

        minimize sum_c cost[c] * x[c]
        subject to  sum_s weight[s] * r[s] >= R* - relief_slack
        (plus the three constraint families above)

   with `relief_slack = δ / 10`, `δ = 1e-4` (weighted-relief units, the smallest relief
   difference we care about).

**The claim:** the plan has *optimal relief within `δ/10`, then minimum spend among plans that
deliver it and satisfy the floors and caps*. A candidate is never funded for nothing: if removing a funded candidate kept relief
within the slack, a cheaper feasible plan would exist and stage 2 would have found it.

Notes:
- **Stage 2 is always feasible**: the stage-1 plan satisfies the new row (its relief is `R*`
  >= `R* - relief_slack`) and the market floors and caps, which both stages share. The code asserts this; an `Infeasible` stage 2 would be a bug.
- **Why not one solve with a cost penalty (`ε`)?** That was the first design and it failed at
  scale; see DECISIONS.md D2.
- **Solver settings.** Both stages use `gapAbs = gapRel = 0` and `threads = 1`.
- **Time limit** is 30 s *total*. Stage 1 gets all of it; stage 2 gets what stage 1 left over.
  - Stage 1 times out: status `TimeLimit` with its best plan (or no plan, if none was found).
  - Stage 2 times out, or stage 1 used the whole limit: status `TimeLimit` with the **stage-1
    plan** (valid and relief-optimal, but not minimum spend). Never `Optimal`.
- **Reported objective is weighted relief only**, recomputed from the funded candidates
  (`relief[s] = min(shortfall[s], sum of their offloads)`), never read from the solver.
- Sectors that trigger sooner get larger weight (trigger at `base_year` -> weight 1).
- Relief is capped by need (row 1) and by what funded candidates supply (row 2), so a candidate
  shared across sectors counts toward every sector it relieves.
- If `must_fund_total > budget` the right-hand side of the budget row is negative, so no
  selection is feasible. A **pre-solve check** returns `Infeasible` immediately in that case,
  without calling the solver (CBC may report `Undefined` for such a model, and we do not widen
  the status mapping to cover it).
- `base_year` and `δ` are model parameters, not part of the input data.

### Solver result object
| Field | Meaning |
|---|---|
| `status` | one of `Optimal`, `Infeasible`, `TimeLimit`, `Error` |
| `objective` | weighted relief only (see above); `None` if there is no plan |
| `selected` | funded candidate ids; `None` if there is no plan (an empty list means "a plan that funds nothing") |
| `relief` | relief per sector id; `None` if there is no plan |
| `spend` | candidate spend only (excludes must-fund); `None` if there is no plan |
| `solve_time` | seconds, total over both stages |
| `stage_times` | seconds per stage that ran: `stage1`, `stage2` (empty for the pre-solve `Infeasible`) |
| `budget` | total budget given |
| `must_fund_total` | sum of must-fund costs |
| `base_year` | as used |
| `version_id`, `content_hash` | of the input set solved |
| `solver_settings` | `threads`, `timeLimit`, `gapRel`, `gapAbs`, `delta`, `relief_slack`, `market_floor_mult`, `market_cap_mult`, `fair_share_blend` (None when
that side is off) and the applied `market_floors` / `market_caps` (spend per market; None when off) as used |

Pinned solver settings: `threads=1`, `timeLimit=30` seconds (total), `gapRel=0`, `gapAbs=0`.
All are recorded in `solver_settings` so a run can be reproduced.

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
- A time-limit stop in either stage is always `TimeLimit`, never `Optimal`. Whether a plan is reported depends on
  `has_solution`: with an incumbent the best-found plan is reported; without one `selected`,
  `objective`, `relief` and `spend` are `None`.
- `map_status` is unit-tested with **mocked** statuses (every `LpSolveStatus` member is covered);
  the plan/no-plan branches are tested by patching `LpProblem.solve`. We do not force a real
  timeout.

### Dependencies
PuLP 4.2 no longer bundles the CBC binary. It comes from the `cbcbox` package via
`pulp[cbc]` (DECISIONS D3). The solver is `pulp.COIN_CMD` pointing at that binary.

### Market floors and caps
Optional limits on how much candidate spend may go to each market. Off unless asked for, so every
result without them is unchanged (the 165 tests from before this section pass untouched).

**Parameters** (arguments of `solve()`, recorded in `solver_settings`):

| Parameter | Suggested value | Meaning |
|---|---|---|
| `market_floor_mult` | 0.5 | floor = `floor_mult * fair_share * avail`; `None` turns floors off |
| `market_cap_mult` | 1.5 | cap = `cap_mult * fair_share * avail`; `None` turns caps off |
| `fair_share_blend` | 0.5 | weight of the shortfall share in the fair share |

The signature defaults are `market_floor_mult=None`, `market_cap_mult=None`,
`fair_share_blend=0.5` (the blend does nothing while both sides are off); the suggested values
above are passed explicitly. A lower-level argument `limits` (a `MarketLimits` with `floors` and
`caps`, spend per market, from `engine/markets.py`) replaces the computed limits; it is how the
known-answer tests 9-11 state absolute amounts. Given limits go through the same clamp and
pre-solve check.

**Fair share and limits.** With `n` markets (the labels present on sectors):

    fair_share[m] = blend * (shortfall of m / total shortfall) + (1 - blend) * (1 / n)
    floor[m]      = floor_mult * fair_share[m] * avail
    cap[m]        = cap_mult   * fair_share[m] * avail,     avail = budget - must_fund_total

`avail` is the budget left after must-fund, so the limits scale with the budget in a sweep. The
fair shares sum to 1, so the floors sum to `floor_mult * avail` and the caps to `cap_mult * avail`
(total shortfall is assumed to be positive).

**A candidate's market** is the market of its largest offload row (ties: the lowest sector id). A
candidate with no offload rows belongs to no market and is not limited. About 10-15 of the ~51
candidates in generated data span more than one market (10, 12, 15, 11 on seeds 1, 2, 3, 42), so
a cross-market candidate's **full cost counts against one market**. This is a deliberate
simplification (DECISIONS D4, README limitations).

**Constraints.** With `spend[m] = sum over candidates c of market m of cost[c] * x[c]`:

    floor'[m] <= spend[m] <= cap[m]          floor'[m] = min(floor[m], total candidate cost of m)

A floor is clamped to its market's total candidate cost (a floor above what the market can absorb
would otherwise be infeasible for a reason the user cannot act on). Sides that are off add no
constraint. The constraints are added **once, in `_core`** (`engine/stages.py`), so both stages
use them.

**Pre-solve check** (no solver call, `Infeasible`, `selected=None`, empty `stage_times`), after the
must-fund check: the clamped floors sum to more than `avail`, or some cap is below its clamped
floor. Reason codes `FLOORS_EXCEED_BUDGET` and `CAP_BELOW_FLOOR` are an M2A item; M1 returns the
bare status.

**Effect on results.** Caps can stop even a 100% budget from funding everything, so a lower
`% resolved` in the sweep when caps are on is by design. (The `sweep` command does not expose the
parameters in M1; they are arguments of `solve()`.)

**Fair-share table** (generated v1, seed 42; floor mult 0.5, cap mult 1.5, blend 0.5; at the 30%
budget `avail` = 30% of total candidate cost = 934.31 cost units; floors sum to 50% and caps to
150% of `avail`):

| market | total shortfall | share | fair share | floor % avail | cap % avail | floor (units) | cap (units) |
|---|---|---|---|---|---|---|---|
| market_a | 332.00 | 7.9% | 10.2% | 5.1% | 15.3% | 47.76 | 143.29 |
| market_b | 269.07 | 6.4% | 9.5% | 4.7% | 14.2% | 44.24 | 132.73 |
| market_c | 465.91 | 11.2% | 11.8% | 5.9% | 17.7% | 55.25 | 165.75 |
| market_d | 468.89 | 11.2% | 11.9% | 5.9% | 17.8% | 55.42 | 166.25 |
| market_e | 499.19 | 12.0% | 12.2% | 6.1% | 18.3% | 57.11 | 171.34 |
| market_f | 565.06 | 13.5% | 13.0% | 6.5% | 19.5% | 60.80 | 182.39 |
| market_g | 754.61 | 18.1% | 15.3% | 7.6% | 22.9% | 71.39 | 214.18 |
| market_h | 822.30 | 19.7% | 16.1% | 8.0% | 24.1% | 75.18 | 225.54 |

Script (`scripts/fair_share_table.py`, plain formulas on the generated data, independent of the
solver code):

```python
"""Fair share, floor and cap per market for generated v1 (SPEC "Market floors and caps").

Run: uv run python scripts/fair_share_table.py [seed]
Prints a markdown table at the 30% budget (avail = 30% of total candidate cost).
"""

import sys
from collections import defaultdict

from happy_toad.data.generator import make_v1

BLEND, FLOOR_MULT, CAP_MULT, SHARE = 0.5, 0.5, 1.5, 0.30


def main(seed: int) -> None:
    data = make_v1(seed)
    shortfall: dict[str, float] = defaultdict(float)
    for s in data.sectors:
        shortfall[s.market] += s.shortfall
    markets = sorted(shortfall)
    total = sum(shortfall.values())
    avail = SHARE * sum(c.cost for c in data.candidates)
    print(f"seed {seed}: avail at {SHARE:.0%} budget = {avail:.2f} cost units")
    print(
        "| market | total shortfall | share | fair share | floor % avail | cap % avail "
        "| floor (units) | cap (units) |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for m in markets:
        share = shortfall[m] / total
        fair = BLEND * share + (1 - BLEND) / len(markets)
        print(
            f"| {m} | {shortfall[m]:.2f} | {share:.1%} | {fair:.1%} | {FLOOR_MULT * fair:.1%} "
            f"| {CAP_MULT * fair:.1%} | {FLOOR_MULT * fair * avail:.2f} | {CAP_MULT * fair * avail:.2f} |"
        )


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 42)
```

### Known-answer tests (written before the model)
1. **Zero budget** (no must-fund): nothing selected, objective 0.
2. **Ample budget**: `budget = sum of all candidate costs + must_fund_total` (never `inf`);
   every sector's relief equals `min(shortfall, total possible offload)`.
3. **Shared candidate**: one candidate relieving 2 sectors, cheaper than two single-sector
   candidates, with a budget large enough to fund **all three**, so that only the cost minimization in
   stage 2 can explain why the shared one is selected and the singles are not.
4. **Must-fund above budget**: status `Infeasible` (via the pre-solve check), `selected=None`.
5. **Zero marginal relief**: a candidate that adds no relief (e.g. its sector is already fully
   covered by another funded candidate) is not funded (stage 2 minimizes spend).
6. **Greedy trap**: budget 10, all weights 1, three sectors with one candidate each:
   A cost 6 / relief 6, B cost 5 / relief 4.5, C cost 5 / relief 4.5 (sector shortfalls large
   enough not to cap). Greedy by relief-per-cost picks A and stops at relief 6. Expected optimum:
   `{B, C}`, objective 9.
7. **Saving spend never beats real relief**: one candidate costing the entire available budget
   (`avail`) with weighted relief just above `δ` (e.g. `1.5e-4`) must be selected. Guards
   against stage 2 trading real relief for savings: `R* - relief_slack` must still require it.

Market floors and caps (the section above). Toy world: budget 12, base year 2027, no must-fund,
so `avail = 12`. Sectors `sX1` (market X, shortfall 10, trigger 2027, weight 1), `sX2` (X, 10,
2027, weight 1), `sY1` (Y, 10, 2031, weight 1/5). Candidates `X1` (market X, cost 6, relieves
`sX1` by 10), `X2` (X, cost 5, relieves `sX2` by 10), `Y1` (Y, cost 6, relieves `sY1` by 10).
Limits are given as absolute spend per market through `limits`.
8. **Baseline, floor and cap off**: plan `X1 + X2`, spend 11, weighted relief 20.
9. **Cap on X = 8**: plan `X2 + Y1`, X spend 5, spend 11, relief 12. Also assert relief < 20, so
   we know the cap actually bound.
10. **Floor on Y = 6**: `Y1` is funded; plan `X2 + Y1`, spend 11, relief 12. Assert on totals and
    market spend, not on `X1` versus `X2`.
11. **Infeasible and clamp**: (a) floors X = 8 and Y = 6 (sum 14 > 12) and (b) cap on X = 4 with
    floor on X = 6 both return `Infeasible` with `selected=None`. (c) Clamp: a floor on Y = 10
    clamps to 6 (Y's total candidate cost), stays feasible, and `Y1` is funded.

Scale regression tests (generated v1, seed 42; `tests/test_tiebreak_at_scale.py`). These exist
because the small tests above passed while the first design was broken at scale:
- Every funded candidate adds more than `δ` of relief (removing it lowers relief by more than
  `δ`), at five budgets.
- Plateau spend is identical at every budget once the budget stops binding (minimum spend at
  maximum relief cannot depend on extra budget). This invariant also holds across platforms.
  It holds only with the market floors and caps off, so these tests run with both `None`.
- Reported relief is within `relief_slack` of an independently solved stage-1 optimum.

### Budget sweep and CLI
`happy-toad sweep <input.json> [--budgets 0,50,100,...]` loads the input set (running all
load-time checks; a failure prints the problems and exits 1) and solves once per budget, in the
order given. Budgets are **total** budgets, including must-fund.

If `--budgets` is omitted, the default is 5%, 10%, ..., 100% of total candidate cost (20 budgets),
each **plus the must-fund total**.

Output: a header line with the version, total candidate cost and must-fund total, then a rich
table with columns `budget`, `must_fund`, `status`, `spend`, `weighted relief`, `# selected`,
`resolved` and `% resolved`. `resolved` is `n/N`: the sectors whose relief is at least
`shortfall - 1e-6`, out of all sectors; `% resolved` is `100 * n / N` with one decimal. Shortfall
magnitudes are not shown. One row per budget. A budget with no plan (e.g. `Infeasible`) shows its status and `-` in the
plan columns. Output is deterministic (CBC single thread, no timing column).

Tests: one row per budget, row values, Infeasible rows, header totals, default budgets,
determinism, rejection of a tampered input file.

### Synthetic data generator
`happy-toad generate --seed N` (default 42) writes `v1.json`, `v2.json` and
`changes_v1_to_v2.json` to `data/inputs/` (gitignored; regenerate with the same seed).
**v1 is the plan of record** (the data the plan was built on); **v2 is the refreshed forecast**
(a mid-year update with re-estimated costs, moved trigger years and new sectors).
Seeded with `numpy.random.default_rng`; same seed -> byte-identical files. All parameters live in
`GeneratorConfig` (`data/config.py`). Floats are rounded to 2 decimals. Defaults:

| Item | Default |
|---|---|
| Size | 80 sectors (`S001`..), 5 must-fund (`M1`..); candidates (`C001`..) are **derived**, about 50 (49-54 over 300 seeds) |
| Trigger year | planning window `BASE_YEAR`..`BASE_YEAR + 4` (2027-2031, `n_years` = 5), `BASE_YEAR + min(floor(5 * Beta(a, b)), 4)` with a per-market profile (`trigger_profiles`): `market_g`, `market_h` urgent Beta(1, 6); `market_a` relaxed Beta(2.5, 1.5); `market_b..f` mixed Beta(1.5, 3) |
| Shortfall | uniform 10-100 (every sector is need-only: shortfall > 0, no surplus sectors) |
| Markets | 8 (`market_a..h`) with need rates 7/8/10/11/13/14/16/18% (`market_need_rates`); sector counts are proportional to the rates, largest-remainder rounding, exact (`market_counts`): 6/7/8/9/11/11/13/15 of 80 |
| Types | `type_a/b/c`; spend shares 85/10/5% (`type_spend_shares`); cost ratios 1.0/0.33/0.1 (`type_cost_ratios`) |
| Reach | `type_a` relieves 2-4 sectors, `type_b` and `type_c` exactly 1 (`type_reach`) |
| Home market | each multi-sector candidate has a home market; each of its rows is a home-market sector with probability 85% (`home_market_share`), else another market |
| Coverage | 80% of sectors have exactly one candidate that can relieve them; 20% (`multi_solution_share`, 16 of 80) have 2-3 (`multi_cover_range`) |
| Resolvable sectors | 95% of sectors (all but `unresolvable_share` = 5%, 4 of 80): at least one candidate row with offload share in 1.0-1.3 (`resolving_share_range`, uniform), so that candidate alone fully relieves the sector; their other rows (multi-candidate sectors) are 60-120% of the shortfall (`offload_share_range`) |
| Unresolvable sectors | 5% of sectors, chosen at random: total offload of all their rows is 50-95% of the shortfall (`unresolvable_total_range`), split equally over the rows, so they can never be fully relieved |
| Candidate cost | `unit_cost` (100) x type cost ratio x uniform(0.7, 1.3) |
| Must-fund | total = 10% (`must_fund_share`) of total candidate cost, split by random weights |

**Construction.** (1) Markets are dealt to sectors by the exact counts, in shuffled order; each sector's trigger year
uses its market's Beta profile.
(2) Each sector gets a coverage count (1, or 2-3 for a random 20%); the counts add up to the
coverage slots (about 90). (3) The number of candidates per type is derived from the slots: with
`counts_i proportional to spend_share_i / cost_ratio_i`, scaled so the mean reach adds up to the
number of slots. (4) Reach sizes are drawn per candidate and nudged to sum to the slots.
(5) Multi-sector candidates are filled first: each gets a home market (drawn in proportion to the slots per market) and takes
each row from the remaining slots of its home market with probability 85%, else from another
market (never the same sector twice; if the wanted pool is empty, any remaining slot). The
single-row candidates take the leftover slots. So "exactly one
candidate for 80% of sectors" holds by construction, and the type spend shares hold up to rounding
and the random cost factor (measured 84.4-86.5 / 8.7-10.8 / 4.8-4.9% on seeds 1, 2, 3, 42; 83.2-87.5 / 7.6-11.3 / 4.2-5.8% over 300 seeds).

**Supply and resolvability.** With every candidate funded, exactly 76 of 80 sectors are fully
relieved (the 95% resolvable ones; measured on 300 seeds), and the 4 unresolvable ones stay below
95% of their shortfall. The total supply over total need is logged, not gated (measured 1.37-1.40
on seeds 1, 2, 3, 42; 1.27-1.52 over 300 seeds). History: with every row at 60-120% of the
shortfall only 37 of 80 sectors could be fully relieved on seed 42 (DEVLOG). A fully funded
resolving row can exceed the shortfall (relief is capped at the shortfall), but the budget still
binds until about 88% of candidate cost (seed 42), since each candidate adds relief to its
sectors until all of them are saturated.

**v2** (the refreshed forecast) is derived from v1 (`make_v2`) with these deliberate changes, each recorded in
`changes_v1_to_v2.json` (one entry per change, with `kind`, ids, `old`, `new`):
- `sector_added` x3: new sectors (market drawn by need rate), each relieved by one existing
  candidate through a single new offload row (so that candidate may exceed its type's reach by
  one row); the entry holds the full sector and its offload row.
- `trigger_moved` x6: distinct sectors, new year in `BASE_YEAR`..`BASE_YEAR + 4` (never below `base_year`), always
  different from the old year.
- `cost_changed` x10: distinct candidates, cost scaled by 0.5-0.9 or 1.1-1.5.
- `offload_changed` x8: distinct existing offload rows, amount scaled the same way.
Nothing else changes (must-fund projects, labels, other fields are identical).

**Tests.** Same seed gives identical data and files; v1 and v2 pass all load-time checks; v2
differs from v1 in exactly the listed ways (an independent diff of v1 vs v2 is compared to the
change list); measured properties are checked on seeds 1, 2, 3, 42 within tolerances: type spend
shares (+-4 points), cost ratios (+-20%), market counts (exact), reach by type, share of
multi-candidate sectors (20% +-2 points), resolvable fraction (95% +-4 points; unresolvable
sectors stay below 95% of the shortfall; every resolvable sector has a row with share 1.0-1.3),
supply ratio (logged only), offload share ranges, mean trigger
year ordered urgent < mixed < relaxed, earliest trigger year = `BASE_YEAR` with weight exactly
1.0 through the model's weight function (end to end), same-market share of multi-sector candidate rows (85% +-10
points, modal market per candidate; 26 of 300 seeds fall outside, all four test seeds inside).

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

## M2A — Decision services
The deterministic services the M3 agent will call: a validation gate for requests, the solve, a
run record for every attempt, an infeasibility explanation and an unresolved-sectors report.
No agent, no LLM calls. Code lives in `src/happy_toad/services/` (plus small additions to the
engine). Decisions 1-8 were approved by the owner; A-F are proposals from the project lead and
are listed as decisions here and in the DEVLOG; items marked "(impl.)" were settled while
writing this section.

### Request
`SolveRequest` (pydantic, frozen, unknown fields rejected):

| Field | Meaning |
|---|---|
| `input_version` | version id of the input set, i.e. the file `data/inputs/<input_version>.json` (decision 1) |
| `budget` | **total** budget including must-fund (decision 1) |
| `force_in` | candidate ids that must be funded (decision 4); default none |
| `force_out` | candidate ids that must not be funded (decision 4); default none |
| `label` | free text for humans; never used by the solver; not part of the request hash |
| `market_floor_mult`, `market_cap_mult` | optional; `None` (default) turns that side off; same meaning as in "Market floors and caps" (decision A). Fair-share blend stays 0.5; absolute limits are not request fields |
| `region_total_sectors` | optional integer >= 1, reporting only (decision C) |
| `target_pct_resolved` | optional number 0-100 (decision D) |

Field-level rules (types, `mult >= 0`, `region_total_sectors >= 1`, `0 <= target <= 100`, no
unknown fields) are enforced by the schema and raise before the gate (impl.). The id lists are
normalized to sorted unique ids. The **request hash** is the SHA-256 of the canonical JSON (sorted
keys) of every field except `label`; two requests with the same hash ask the same question.

### Validation gate (decisions 2, 3)
`check_request(request, data)` returns **all** problems, not only the first (DECISIONS D5). `data`
is `None` when the version was not found. Reason codes:

| Code | When |
|---|---|
| `VERSION_NOT_FOUND` | no input file for `input_version` (a version that is not a plain name such as `v1` is also "not found") |
| `BUDGET_NOT_POSITIVE` | `budget` is not greater than 0 (NaN counts) |
| `BUDGET_ABOVE_CAP` | `budget > 1.5 * (total candidate cost + must-fund total)`: catches typos and unit mistakes but not "fund everything" |
| `UNKNOWN_CANDIDATE` | an id in `force_in` or `force_out` is not a candidate of that version |
| `FORCE_CONFLICT` | an id is in both lists |
| `FORCED_COST_EXCEEDS_BUDGET` | must-fund total plus the cost of `force_in` is more than `budget` |

Checks that need the data are skipped when the version is missing. A rejected request never
reaches the solver.

### Force-in and force-out (decision 4)
`solve(..., force_in=, force_out=)` fixes `x[c] = 1` or `x[c] = 0` with constraints added once in
`_core`, so both stages use them. Forced candidates still count in spend, relief and every limit.

### Infeasibility explanation (decisions 5, B)
`solve()` runs cheap checks before calling the solver and returns `Infeasible`, `selected=None`
and a `cause` (`Reason`: code and message), with no solver call, for the first of these that
holds (impl.: the order is the one listed):

| Code | Condition |
|---|---|
| `FORCED_COST_EXCEEDS_BUDGET` | must-fund plus forced-in cost is above the budget (covers must-fund above budget) |
| `FLOORS_EXCEED_BUDGET` | the clamped market floors sum to more than `avail` (B) |
| `CAP_BELOW_FLOOR` | some market cap is below its clamped floor (B) |
| `FORCED_IN_EXCEEDS_CAP` | forced-in spend in a market is above its cap (impl.) |
| `FLOOR_UNREACHABLE` | a market's floor is above the cost of its candidates that are not forced out (impl.) |

If the solver itself reports `Infeasible`, the cause is `CAUSE_UNKNOWN` ("cause unknown"): the
service says what it does not know and never presents a guess as a plan. `SolveResult` has a
`cause` field (`None` unless the status is `Infeasible`). The tolerance on the checks is 1e-9.

### Run record (decisions 6, 7)
`run_request(request, inputs_dir, runs_dir)` handles one attempt end to end: hash, find and load
the input, gate, solve, summarize, write `runs/<run_id>.json` (`runs/` is gitignored), and return
the record. **Every attempt is recorded**, including rejected ones and failures. `run_id` is a UTC
timestamp plus 8 random hex characters (unique per attempt); the same request run twice gets two
run ids and one request hash, so stored requests can be re-run and compared.

| Record field | Meaning |
|---|---|
| `run_id`, `created_at` | identity and UTC time |
| `outcome` | `rejected` (gate), `completed` (solver ran or pre-solve check; see `result.status`), `error` (the input failed its load-time checks, or something unexpected raised) |
| `request`, `request_hash` | the request as given, and its hash |
| `input_version`, `content_hash` | of the input set (`content_hash` is `None` if it was not found) |
| `settings` | solver settings as used (the defaults for a rejected attempt) |
| `reasons` | gate reasons (rejected); empty otherwise |
| `error` | the error message when `outcome` is `error`, else `None` |
| `result` | `None` unless `outcome` is `completed`; see below |
| `timing` | seconds: `gate`, `solve`, `total` |
| `warnings` | e.g. `region_total_sectors` smaller than the number of modelled sectors (impl.) |

`result`: `status`, `cause` (infeasible only), `objective`, `spend`, `selected`, `resolved` and
`total_sectors`, `pct_resolved` (`100 * resolved / total sectors`), `pct_of_region` (`100 *
resolved / region_total_sectors`; `None` without it), `target_pct_resolved`, `target_met`
(`True`/`False` when a target was given, `False` when there is no plan, `None` without a target),
`unresolved` (the report below), `solve_time`, `stage_times`, `solver_settings`. There is no search
for the smallest budget that meets a target in M2A (that is M2B).

### Unresolved-sectors report (decision 8)
A sector is **still short** if `shortfall - relief > 1e-6`. The report lists them by size of the
weighted gap `weight * (shortfall - relief)`, largest first (ties: sector id), each with `sector_id`,
`market`, `shortfall`, `relief`, `gap`, `weight`, `weighted_gap`. It is `None` when there is no
plan. (Shortfall magnitudes stay out of the sweep table; this report is a service output.)

### region_total_sectors (C)
An optional integer used only for reporting "% of region". It is not part of the input data or
its hash and does not change the solve.

### Planning horizon (E)
`HORIZON_YEARS = 5` in `constants.py`, matching `BASE_YEAR` to `BASE_YEAR + 4` (2027-2031). It is a
constant, not a request field in M2A; the generator window uses it.

### Sweep (A)
`happy-toad sweep <input> [--market-floor-mult X] [--market-cap-mult Y]` passes the multipliers to
every solve. Infeasible rows keep status `Infeasible` and a line below the table names the cause
code of each (impl.). With caps on, a lower `% resolved` is by design.

### Required minimum budget
When a solve is infeasible for a known cause (any code except `CAUSE_UNKNOWN`), `SolveResult` and
the run record carry `required_minimum_budget`: a lower bound on the total budget, computed as
must-fund + forced-in cost + the clamped market floors (when set). Forced-in spend inside a
floored market counts toward that floor, so each market adds max(floor, forced spend) and nothing
is counted twice. It is a lower bound, not a promise: a budget at or above it may still be
infeasible. The cause message ends "the budget must be at least X", and the M3 agent's tool result
states it the same way ("at least X"). No new gate codes. For `CAUSE_UNKNOWN` it is None.

When the floors and caps come from multipliers (`market_floor_mult`, `market_cap_mult`) and the
cause is not `FORCED_COST_EXCEEDS_BUDGET`, it is also None: the limits are multiples of the
same fair shares x avail, so a larger budget scales them together and no budget is sure to help.
The cause message then names the multiplier to change instead of a budget, for example "floor
multiplier 1.2 requires floors above the available budget at any budget; use 1.0 or less", "cap
multiplier 0.8 is below floor multiplier 1.0 at any budget; use a cap multiplier of 1.0 or more",
"raise the cap multiplier (now X) or force in fewer candidates" (`FORCED_IN_EXCEEDS_CAP`) and
"lower the floor multiplier (now X) or force out fewer candidates" (`FLOOR_UNREACHABLE`). Explicit
`limits` (spend per market) keep the minimum budget.

### Rule for the M3 agent (F; SPEC text only, no code in M2A)
When the agent turns a plain-English question into a request it **never invents a number**.
1. A missing budget means asking the human, or stating the assumption in the request `label`.
2. A vague phrase ("about a third of the money") is converted to an explicit value (for example
   33% of total candidate cost plus must-fund), and the explicit value is shown to the human.
3. Anything that cannot be mapped to a field becomes a clarification question, not a guess.
The gate is the safety net, not the interpreter: it checks values, it does not repair them.

### Tests (written before the code)
Request schema and hash (label excluded, ids normalized, field rules); the gate (each code alone,
all codes together, missing version); force-in and force-out in both stages on a toy world; the
infeasibility causes (each code, `CAUSE_UNKNOWN` through a patched solver, no solver call on
pre-solve causes); the run record (a record file for completed, rejected and error attempts,
distinct run ids, same request hash, target met/not met, region percentage); the unresolved report
(threshold, ordering, ties); sweep CLI options. All 177 earlier tests pass unchanged.

### Decisions (M2A)
Approved by the owner: 1 request fields; 2 budget cap 1.5x; 3 six rejection codes, all reasons
returned; 4 force-in/out fix x in both stages; 5 infeasible cause when known, else unknown, never
a guess as a plan; 6 run id plus request hash; 7 one JSON per attempt in `runs/`; 8 still short is
shortfall minus relief above 1e-6, listed by weighted gap. Project lead's proposals: A floors and
caps in requests and the sweep; B `FLOORS_EXCEED_BUDGET` and `CAP_BELOW_FLOOR` as causes;
C `region_total_sectors`; D `target_pct_resolved` (reported, no search); E `HORIZON_YEARS`; F the
M3 interpretation rule. The remaining ones marked "(impl.)" are mine and are in the DEVLOG.

## M2B — Target-budget search
Answers "what budget reaches X% resolved?" with the **cheapest plan** that resolves at least the
target: a separate optimization, not the normal optimizer. Owner decisions (2026-11-15): only this
interpretation; no scan of the normal optimizer over budgets; no other diagnostics in M2B (moved to
M7). Items marked **[lead]** are proposals not in the owner's list.

### Why a separate optimization
The normal optimizer maximizes weighted relief, and the number of resolved sectors is **not
monotonic in budget**: on v1 (seed 42), a sweep from 311.44 to 5138.73 in steps of 1 found 148
budgets where one more unit resolves fewer sectors (981.44 resolves 30, 982.44 resolves 26), and
1356 of 4828 budgets resolve fewer than some smaller budget (DEVLOG 2026-11-15). "The smallest
budget at which the optimizer reaches X%" therefore has no single answer. The cheapest plan does:
it is exact, and a larger target never needs a smaller budget. On v1 the two readings differ by
20-209 cost units (for 50%: cheapest plan 1145.21; the optimizer first reaches 50% at about 1329).

### Request
`TargetBudgetRequest` (pydantic, frozen, unknown fields refused):

| Field | Rule |
|---|---|
| `input_version` | string, as in M2A |
| `target_pct_resolved` | number, 0 to 100 |
| `force_in`, `force_out` | candidate ids, sorted and de-duplicated as in M2A |
| `label` | free text, not hashed |

There is no `budget` (the search finds it) and no `region_total_sectors`. **No market multipliers:**
floors and caps are multiples of the budget, which is what the search is looking for. A request
with `market_floor_mult`, `market_cap_mult` or `budget` is `SCHEMA_INVALID` with a message that
names the field and the reason, for example: "market_floor_mult is not supported in the
target-budget search: market floors and caps scale with the budget being searched for; use
run_scenario with a budget to apply them". The request hash is SHA-256 of the canonical JSON of
every field except `label`, plus `"kind": "target_budget"`, so it never equals a scenario hash.

### Gate
The M2A gate checks that apply: `VERSION_NOT_FOUND`, `UNKNOWN_CANDIDATE`, `FORCE_CONFLICT`, every
problem listed. A rejected request is stored as a run record (`outcome: rejected`), as in M2A. No
new gate codes.

### Method
1. **Target count:** `k = ceil(target_pct_resolved * n_sectors / 100 - 1e-9)`; 50% of 80 sectors is 40.
2. **Reachability:** `max_resolvable` = sectors resolved when every candidate not forced out is
   funded (relief only grows with more candidates, and there are no caps). If `k > max_resolvable`,
   the result is `Infeasible` with the new cause **`TARGET_UNREACHABLE`**: "at most N of M sectors
   (P%) can be resolved with the candidates not forced out; the target needs k". No solver call,
   no `target_budget`, no follow-up run.
3. **Stage 1, cheapest plan:** minimize candidate spend `sum cost_c x_c`, with binary `x_c` and a
   binary `z_s` per sector: `sum over offloads into s of amount * x_c >= (shortfall_s - 1e-6) * z_s`,
   `sum z_s >= k`, forced-in `x_c = 1`, forced-out `x_c = 0`. The same tolerance as "resolved"
   (`RESOLVED_TOLERANCE`).
4. **Stage 2, tie-break:** among plans that cost at most C* + 1e-6 and still resolve at least k,
   maximize weighted relief (same weights as M1), so the plan is unique and deterministic.
5. **`target_budget` = must-fund total + C*, rounded up to the cent** (`ceil(round(x * 100, 6)) /
   100`; the inner round removes float noise such as 1145.2100000001). It is a **total budget
   including must-fund projects**, like every budget the user gives. Forced-in costs are inside
   C*. The stored, claimed and follow-up value is this rounded one, so the cheapest plan's cost C*
   always fits within `target_budget - must-fund total`.
6. **Follow-up run:** the normal optimizer (M1 `solve`) runs at that same rounded `target_budget`
   with the same force lists, stored as an ordinary scenario run. This shows what the usual plan does with that money.
   Its run id is in the search record as `follow_up_run_id`.
7. **Solver:** CBC with the pinned M1 settings (single thread, gaps 0); one 30 s limit for both
   stages. `target_budget` is set only when stage 1 proves optimality. If a stage stops on time,
   status is `TimeLimit`, the best plan found is shown, and there is no `target_budget` and no
   follow-up run. A target of 0 needs no candidates: `target_budget` = must-fund + forced-in cost.

### Run record
`RunRecord` gains `kind: "scenario" | "target_budget"` (default `"scenario"`, so stored records
still load) and `follow_up_run_id: str | None = None`. `RunResult` gains `target_budget`,
`target_sectors` (k), `max_resolvable` and `max_pct_resolvable` (`100 * max_resolvable /
n_sectors`), all `None` by default. `target_sectors` is set whenever the target is valid;
`max_resolvable` and `max_pct_resolvable` are set on every search record (reachable or not). For a search record, `result`
describes the cheapest plan: `status`, `cause`, `objective`, `spend`, `selected`, `resolved`,
`total_sectors`, `pct_resolved`, `target_pct_resolved`, `target_met` (true when found),
`unresolved`, timings and settings; `pct_of_region` and `required_minimum_budget` are `None`.
`compare_runs` accepts a search record like any run with a plan (cheapest plan against the
follow-up run is a useful comparison).

### New report metrics (claimable, checked)
| Metric | Unit | Stored value | Tolerance |
|---|---|---|---|
| `target_budget` | cost_units | `result.target_budget` | money (0.005) |
| `target_sectors` | count | `result.target_sectors` (k) | exact |
| `max_resolvable` | count | `result.max_resolvable` | exact |
| `max_pct_resolvable` | percent | `result.max_pct_resolvable` | percent (0.05) |

The existing plan metrics (`spend`, `weighted_relief`, `n_selected`, `n_resolved`, `pct_resolved`,
`status`, `target_met`) apply to a search record's cheapest plan; the follow-up run is an ordinary
run. `target_pct_resolved` is already an allowed request number.

### Agent
New tool **`find_target_budget`** (parameters: the request above). Its result is the record view
as for `run_scenario`, plus `follow_up_run_id` and the follow-up run's view.

**Provenance:** the loop records `follow_up_run_id` with the run ids it already tracks (`run_id`,
`run_id_a`, `run_id_b`), so a claim citing the follow-up run counts as executed in the
conversation.

New system-prompt rule 12: "For a question like 'what budget reaches X% resolved?', call
find_target_budget. State the target as a sector count: "at least k of N sectors" (target_sectors
of n_sectors). Say that target_budget is the total budget, including must-fund projects, of
the cheapest plan that resolves at least that many. Then give what the optimizer's usual plan resolves at
that budget, from the follow-up run, and say that it maximizes weighted relief, so it can resolve
fewer. Say that a higher budget does not guarantee more resolved sectors. Offer to run the
optimizer at other budgets the user names. If the target is unreachable, say so and give
max_resolvable and max_pct_resolvable."

Expected answer shape: "The cheapest plan that resolves at least 40 of 80 sectors (50%) needs a
total budget of 1145.21 (run …). At that budget the optimizer's usual plan, which maximizes weighted relief,
resolves 33 of 80 (run …). A higher budget does not guarantee more resolved sectors. I can run
the optimizer at other budgets you name."

**[lead] Display:** the web page and the CLI trace show the tool as "target X%" →
"target budget B [run id]; optimizer at B resolves m [run id]", with the wording in
`web/format.py` and `cli.py` kept identical (existing test). **[lead] CLI:** `happy-toad
target-budget <input> --target 50 [--force-in ...] [--force-out ...]` prints the result.
**Exit codes (owner, 2026-11-15):** 0 when a budget is found and when the target is unreachable
(both are answers); 1 for a gate rejection (or an input file that fails its checks); 2 for an
invalid request (schema error, for example a target above 100); 3 for a time limit (or another
solver stop) before a proven cheapest plan.

### Glossary (docs/GUIDE.md section 7)
- **`target_budget`:** the total budget, including must-fund projects, of the cheapest plan that
  resolves at least the target percent of sectors. The optimizer's usual plan at that budget can
  resolve fewer, because it maximizes weighted relief.
- **`target_sectors`:** the target as a number of sectors: the target percent of all sectors,
  rounded up (50% of 80 is 40).
- **`max_resolvable`:** the most sectors any plan can resolve with the candidates that are not
  forced out. Given with every target-budget search; when the target needs more, it is
  unreachable.
- **`max_pct_resolvable`:** `max_resolvable` as a percent of all sectors in the version.
- **`TARGET_UNREACHABLE`:** no plan can resolve the target percent of sectors, even with every
  candidate that is not forced out funded; the run gives `max_resolvable` and `max_pct_resolvable` instead of a budget.

The guide's limitation "No reverse budget search yet" is replaced by the search and its caveat.

### Tests (written before the code)
- **Toy, brute force:** a toy set where the cheapest plan for the target differs from the
  optimizer's plan at that budget; every subset is enumerated to confirm C* is the minimum, and
  no subset costing C* - 0.01 reaches the target.
- **Rounding:** `target_budget` has at most 2 decimals, is never below must-fund + C*, and
  exceeds it by less than 0.01; the cheapest plan's cost fits within `target_budget` minus the
  must-fund total; the follow-up run's budget equals `target_budget`.
- **Toy, target 0:** `target_budget` = must-fund total; with force_in, plus the forced cost.
- **Unreachable:** a target above `max_resolvable` gives `Infeasible`, `TARGET_UNREACHABLE`,
  `max_resolvable`, no budget, no follow-up run; also a target made unreachable only by force_out.
- **Force in:** forcing a candidate in adds its cost when it is not in the cheapest plan.
- **v1 scale:** targets 5%, 10%, ..., 95%: `target_budget` never decreases as the target rises;
  it is never above the sweep's first budget at which the optimizer reaches the target, read
  from a committed fixture (`tests/fixtures/v1_first_budget_per_target.json`, with a note on how
  it was produced); the plan's resolved count is at least k.
- **Determinism:** the same request twice gives the same plan and budget.
- **Run record:** search and follow-up records written; `kind`, `follow_up_run_id`, hash differs
  from a scenario hash; old records without the new fields still load.
- **Gate and schema:** `VERSION_NOT_FOUND`, `UNKNOWN_CANDIDATE`, `FORCE_CONFLICT` rejected with
  all reasons; `market_floor_mult`, `market_cap_mult` and `budget` each give `SCHEMA_INVALID`
  with the message naming the field; a target above 100 is refused.
- **Checker:** `target_budget`, `target_sectors`, `max_resolvable` and `max_pct_resolvable`
  claims pass when they match and fail when they do not; money tolerance on `target_budget`,
  percent tolerance on `max_pct_resolvable`, exact counts.
- **Provenance:** a claim citing `follow_up_run_id` passes the conversation-runs check; the same
  claim fails when the follow-up run was not part of the conversation.
- **Agent:** a scripted fake-client conversation for "what budget reaches 50%?" ends CHECKED with
  claims from both runs.
- **Glossary:** the existing test fails until the four metrics and the new cause have entries.
- **Display:** the CLI and web trace wording are identical for the new tool.

### Effects on frozen files
`checker.py`, `report.py`, `tools.py`, `prompt.py` and `loop.py` change (the freeze is lifted,
DEVLOG 2026-11-15); a future bake-off round records the new hashes.

### Done when
All tests above pass; CI green; a live `happy-toad ask --profile demo` for "On v1, what total
budget reaches 50% of sectors resolved?" ends CHECKED with the wording above; README, guide and
glossary updated; tag v0.4.

## M3 — Agent
An agent layer that turns a plain-English question into calls of the M2A services and returns a
report whose numbers are checked against stored runs. Items marked **[owner]** were in the owner's
draft; items marked **[lead]** are project-lead proposals (defaults, to be approved or changed).
The list was approved with the changes below (provider, cost, `required_minimum_budget` metric,
number definition, demo questions, system prompt); where a changed item contradicts the draft text,
the section "M3 — approved changes and specification" at the end wins.

### M3 decisions
1. **Provider adapter [owner].** A thin interface: messages and tool definitions in, one response
   out (text blocks, tool-use blocks, token counts). Tests use a fake client; the provider can be
   swapped. The real client uses the `anthropic` SDK (owner approved adding this one dependency).
   The key is read from `ANTHROPIC_API_KEY` and never stored, logged or written to a transcript.
   **[lead]** The model ID is a constant in `config`, pinned to `claude-sonnet-5-5` (current
   Sonnet-class ID), and recorded in every transcript. No temperature or other sampling options
   beyond the SDK defaults.
2. **Tools, five [owner]:** `list_input_versions`, `run_scenario`, `get_run`, `compare_runs`,
   `submit_report`. New deterministic services first, with their own tests: a version lister
   (names of `data/inputs/*.json`, except change lists `changes_*.json`), a run reader (`runs/<run_id>.json`, a name that is not a run id
   is not opened as a path), and a run comparer. **[lead]** Comparer output: both run ids, then
   per field the two values and the difference for status, spend, weighted relief (`objective`),
   number selected, number resolved and percent resolved; the candidate ids only in A, only in B;
   it refuses (clear error) if either run has no plan. `run_scenario` takes the M2A request fields
   and returns the run summary; for an infeasible solve with a known cause it includes the cause
   and `required_minimum_budget`, which the agent must state as "at least X" (SPEC, "Required
   minimum budget"). `get_run` returns the run summary, not the full record. **Tool descriptions
   are part of this SPEC** (written with the tests, because the model chooses tools from them).
3. **Loop [owner].** Step cap 10 model turns (**[lead]**: a turn is one model response). The loop
   stops when `submit_report` is accepted. Reaching the cap is a flagged failure recorded in the
   transcript, not a silent stop. Only the five listed tools run; no generated code executes; a
   call to an unknown tool is returned to the model as an error and counts as a turn.
4. **System prompt rules [owner].** Use only tool results. Say "under the modeled objective and
   constraints". Ask for a budget when one is missing. Decline questions outside scope ("should we
   fund this?"). Never say anything is approved or recommended. Plus interpretation rule F of M2A.
   The owner writes the final wording by hand.
5. **Report schema [owner].** Claims as data plus a summary. A claim has `metric`, `value`, `unit`,
   `run_id`, `entity`. **[lead]** Allowed metrics: `weighted_relief`, `spend`, `n_selected`,
   `n_resolved`, `pct_resolved`, `status`, `target_met`. Units: `need_units` (weighted relief),
   `cost_units` (spend), `count`, `percent`, `none` (status, target_met). `entity` is `"plan"`
   (the whole run) in M3; per-sector or per-candidate claims are not in scope. Unknown metrics or
   units are a schema error. `required_minimum_budget` is not an allowed metric in M3 (**[lead]**,
   flagged: the infeasible demo question then states it in the summary only, and the checker
   cannot verify it; add `required_minimum_budget` as a metric if you want it checked).
6. **Consistency checker [owner], tolerances [lead].** Each claim must match the stored run named
   by `run_id` for its metric. Tolerance, justified by the rounding the CLI displays: `spend` and
   `weighted_relief` absolute 0.005 (shown to 2 decimals); `pct_resolved` absolute 0.05 (shown to
   1 decimal); `n_*` and `status` and `target_met` exact. Every number in the summary must equal a
   validated claim's value within the same tolerance (**[lead]** numbers are found by a simple
   pattern in the summary text; a number that is a run id or a year is ignored only if it appears
   as a run id or as a version name). On a mismatch the checker's errors go back to the model
   once; if the second report still fails, the report is shown flagged **UNVERIFIED** with the
   failing claims listed. A report whose every claim and number passes is shown as checked.
7. **Every attempt recorded [owner].** A tool input that fails schema validation becomes a rejected
   run record with reason `SCHEMA_INVALID` (a new reason code; message names the field).
   **[lead]** This changes an M2A implementation choice (malformed requests were raised before the
   gate and not recorded); the M2A schema stays, the agent layer catches the error and writes the
   rejected record through the same record writer. No new gate codes.
8. **Transcripts [owner].** One JSON file per conversation in `transcripts/` (**[lead]** name;
   gitignored): question, every model turn, tool calls and results, checker results, model ID,
   token counts per turn and total, elapsed time, final status (checked, unverified, step cap,
   error, or interrupted: Ctrl-C still saves the transcript, then stops). M4 reuses them. The API key never appears.
9. **Cost and speed [owner].** Record tokens, elapsed time and estimated cost per question.
   **[lead]** Estimated cost = tokens x per-million-token rates held as constants in `config`.
   The rates are not set here: I will not invent prices. The owner supplies them, or the cost
   field stays `null` and the CLI prints "cost: not configured".
10. **CLI [owner].** `happy-toad ask "<question>"` prints each tool call and its result as it
    happens, then the report, then the check results (each claim pass/fail, the verdict). Needed
    for the video. **[lead]** Exit code 0 for a checked report, 1 for unverified or step cap.
    **[owner, presentation only]** Default output is compact: one line per tool call (name, key
    arguments, outcome; no JSON), a panel with the summary and a CHECKED / NOT CHECKED badge,
    one check-count line (mismatches listed only when there are any), one line saying what was
    unmatched when the first report was refused and then corrected, and a dim footer (model,
    provider, turns, cost, seconds). `--verbose` keeps the full output described above.
    The check line reads "N claims, M numbers matched against stored runs, K mismatches"
    ("1 mismatch" when K is 1). An
    accepted report with zero claims and zero summary numbers gets the neutral badge NO NUMBERS
    TO CHECK and the line "No checkable figures in this answer", never CHECKED; CHECKED needs at
    least one verified claim or number. The verdict is worked out once and drives the compact
    output, the `--verbose` output (same label) and the exit code: 0 CHECKED, 3 NO NUMBERS TO
    CHECK, 1 NOT CHECKED or no report (unverified, step cap, API error, error), 2 bad option or
    missing key.
11. **Demo script [owner], three questions:** (a) a budget comparison, (b) a forced solution,
    (c) an infeasible request (force in three expensive candidates under a small budget).
    **[lead]** Exact question texts and budgets are fixed in the SPEC once the owner approves,
    against generated v1 seed 42. For (c) the expected outcome is `FORCED_COST_EXCEEDS_BUDGET`,
    with "at least X" in the answer. Each demo is also a test using the fake client with a
    scripted conversation; one live run per question is the acceptance check.
12. **Layout and tag [lead].** Code in `src/happy_toad/agent/` (client adapter, tools, loop,
    schema, checker, transcript); CLI in `cli.py`. Tag `v0.3` only when the three demo questions
    run end to end with every claim checked.

### Order of work after approval
SPEC (tool descriptions, report schema, demo texts), then tests (confirm they fail for the right
reason), then the three new services, then the agent code, then docs.

### Answer to the owner's question
`FLOOR_UNREACHABLE` can only fire when a `force_out` removes candidates from a market, so the
candidates left in it cost less than its clamped floor (clamping alone to the market's total cost
can never trigger it); the budget-700 case is different because every floor is individually
reachable and no pre-solve check finds a problem, yet no set of whole candidates meets all floors
within the budget (minimal whole-candidate spend 426.9 vs 388.6 available), which only the solver
sees and reports as `CAUSE_UNKNOWN`.

### M3 — approved changes and specification
**Provider (replaces decision 1).** The owner has no Anthropic API key. The client is the `openai`
SDK (approved dependency) pointed at OpenRouter's OpenAI-compatible API,
`https://openrouter.ai/api/v1`. The key is read from `OPENROUTER_API_KEY` and never stored, logged
or written to a transcript. Two profiles in `agent/config.py`:

| Profile | Use | Model ID (**[lead]**, from OpenRouter's listing filtered to tool support; owner approves) | Routing |
|---|---|---|---|
| `smoke` | free model, only to check the loop | `inclusionai/ling-3.2-flash:free` (owner approved; the Gemma free pool was rate-limited) | fallbacks allowed; served provider recorded |
| `demo` | the demo, the video and M4 | `deepseek/deepseek-v4-flash-0731` (owner approved after the post-fix round; was a Sonnet placeholder) | provider order `["baseten/fp8", "baidu/fp8"]`, `allow_fallbacks: false`, reasoning off |

Listing check (2026-11-14, `GET /api/v1/models?supported_parameters=tools`): both IDs list `tools`
and `tool_choice` among supported parameters. Other free tool-capable IDs seen, in case the smoke
model is unavailable: `inclusionai/ling-3.2-flash:free`, `baidu/ernie-5.5-flash-preview:free`,
`nvidia/nemotron-3.5-super-vl:free`. Cheaper paid alternative for demo: `anthropic/claude-haiku-5.5`.
The exact ID is pinned in config, sent unchanged, and recorded per turn together with the model
and the **provider that served the response** (the `provider` field of the OpenRouter response;
`null` if absent). Free models have no provider pin, so a fallback shows up in the transcript. Tests
use the fake client only; the live client is exercised by hand (smoke profile first).

**Cost (replaces decision 9).** Tokens come from the response `usage`. Cost is the `usage.cost`
that OpenRouter returns when present (the request asks for usage accounting); otherwise the cost
is `null` and the CLI prints "cost: not configured". No price constants, no estimates. A question's
cost is the sum of its turns, and `null` if any turn lacks one.

**Report schema (extends decision 5).** Allowed metrics and units:

| metric | unit | stored value it is checked against | tolerance |
|---|---|---|---|
| `weighted_relief` | `need_units` | `result.objective` | 0.005 |
| `spend` | `cost_units` | `result.spend` (candidates only, must-fund excluded) | 0.005 |
| `required_minimum_budget` | `cost_units` | the run record's top-level `required_minimum_budget`, valid only if the run has one | 0.005 |
| `n_selected` | `count` | `len(result.selected)` | exact |
| `n_resolved` | `count` | `result.resolved` | exact |
| `n_sectors` | `count` | number of sectors in the cited run's input version, counted from the input file (not from the run) | exact |
| `pct_resolved` | `percent` | `result.pct_resolved` | 0.05 |
| `status` | `none` | `result.status`; for a run without a result, its outcome (`rejected`, `error`) | exact |
| `target_met` | `none` | `result.target_met` | exact |
| `must_fund_cost` | `cost_units` | sum of must-fund costs in the cited run's input version | 0.005 |
| `forced_cost` | `cost_units` | sum of the input costs of the run request's `force_in` candidates | 0.005 |
| `diff_spend`, `diff_weighted_relief` | as base | run `run_id_b` minus run `run_id`, as `compare_runs` reports it; both need a plan | 0.005 |
| `diff_n_selected`, `diff_n_resolved` | `count` | as above (signed whole numbers) | exact |
| `diff_pct_resolved` | `percent` | as above | 0.05 |

A claim is `{metric, value, run_id, run_id_b?, unit?, entity?}`. `run_id_b` is required for
`diff_*` metrics and forbidden otherwise. `unit` is always set from the metric and `entity` is
always `"plan"`; a missing or different value sent by the model is replaced and logged in the
transcript (`defaults`, counted like coercions). A plain-number string is coerced for a numeric
metric (`coercions`). A claim fails if the run file is missing or the stored value is `None`.
**Runs of this conversation only:** a claim fails ("run was not executed or read in this
conversation") if its `run_id` or `run_id_b` is not a run the agent executed, read or compared
in this conversation; a run file left by another conversation does not count. Re-checking a
saved report outside a conversation skips this rule.
**Minimum budget is mandatory:** every run the agent executed, read, compared or cited that is
rejected or infeasible and has a `required_minimum_budget` must have a validated
`required_minimum_budget` claim, or the report fails.
Report = `{summary, claims}`. Values are reported at displayed precision: 2 decimals for
`need_units` and `cost_units`, 1 decimal for percent, integers for counts.

**What counts as a "number" in the summary (checker).** The summary is scanned left to right.
1. Never numbers: run ids (`YYYYMMDDTHHMMSS-xxxxxxxx`) are removed first, and so are the
   timestamp and the suffix of any run of the conversation or of a claim written on their own
   (a digit-only suffix such as `78612358` is not a number). A numeric token must
   not touch a letter, digit or underscore before it, nor a letter or underscore after it, so
   identifiers (candidate `C033`, sector `S001`, must-fund `M1`, version `v1`, market `market_e`)
   contain no numbers. A hyphen is a separator (`2027-2031` is two years).
2. Years: a plain integer from 1900 to 2199 (no sign, comma, decimal point or percent sign) is a
   year and is ignored. Known consequence: a spend of exactly 2030 written without decimals would
   also be ignored; the prompt requires 2 decimals for money, so `2030.00` is a number.
3. List markers at the start of a line (`1.`, `2)`) are ignored.
4. A number is then: an optional sign, digits with optional thousands commas, optional decimals,
   optional `%`.
Each number must equal, within tolerance, either (a) the value of a validated claim of a numeric
metric (percent compares with 0.05, money with 0.005, counts exactly) or (b) **[lead]** a numeric
request parameter (`budget`, `market_floor_mult`, `market_cap_mult`, `target_pct_resolved`,
`region_total_sectors`) of a run that one of the claims cites, since a summary naturally says "at a
budget of 600". A `diff_*` claim also allows its absolute value ("243.70 less"). Any other
number, including a difference the agent computed itself, fails. So the agent
states values, not differences (stated in the prompt). Tests cover identifiers, years, percents,
commas and the unmatched number.

**Limitation (checker).** The checker verifies numbers, not the words around them. Direction words
in prose ("more", "less", "higher", "lower") are not checked: a `diff_*` claim may appear unsigned
in the summary, so a correct number stated with the wrong direction ("spends 243.70 more" for a
difference of -243.70) would pass.

**Checker flow.** `submit_report` input that does not fit the schema is returned to the model as an
error (a turn used, no correction used). A schema-valid report is checked: if all pass, the report
is accepted as **checked** and the loop ends. Otherwise the failures go back to the model once; the
second schema-valid report ends the loop whatever the result, and a failing one is shown and
recorded as **unverified**. Only the first `submit_report` of a turn is handled; any later one in
the same turn gets an error result ("only one submit_report per turn is checked") and uses no
correction, so the model sees the first errors before it corrects. The CLI shows the report text
only for a checked or unverified outcome, never a rejected draft of a run that ended otherwise.

**SCHEMA_INVALID.** A `run_scenario` input that fails the `SolveRequest` schema is written by the
agent layer as a rejected run record in the usual format: `outcome` rejected, `request` the raw
input, `request_hash` the SHA-256 of its canonical JSON, one reason `SCHEMA_INVALID` whose message
names the fields, no result. The record id is returned to the model like any run id.

**Tool descriptions (what the model sees).**
- `list_input_versions()` — "List the names of the available input versions (synthetic data sets).
  Call this when the user does not name a version or you are unsure what exists."
- `run_scenario(input_version, budget, force_in, force_out, market_floor_mult, market_cap_mult,
  region_total_sectors, target_pct_resolved, label)` — "Run the optimizer once for one scenario and
  record it. `budget` is the TOTAL budget including must-fund projects. `force_in` and `force_out`
  are candidate ids (for example C033). Returns the run id and a summary: status, weighted relief
  (`objective`), spend (candidates only), selected candidates, sectors resolved, percent resolved,
  unresolved sectors, and, when infeasible, the cause and `required_minimum_budget` (the budget
  must be at least that). Never guess a budget; ask the user."
- `get_run(run_id)` — "Return the stored summary of an earlier run by its run id."
- `compare_runs(run_id_a, run_id_b)` — "Compare two completed runs that both have a plan: status,
  spend, weighted relief, number selected, number resolved, percent resolved, and which candidates
  are only in one run. Use it for a comparison instead of computing differences yourself."
- `submit_report(summary, claims)` — "Submit the final answer. Every number in `summary` must also
  be a claim `{metric, value, unit, run_id, entity}` taken from a run you executed or read, or be a
  request value such as the budget. Values at displayed precision. To ask a clarifying question or
  decline, call submit_report with claims as an empty list and a summary that contains no numbers."

**System prompt.** Final, written by the owner; the text is `agent/prompt.py` (no copy here, so it
cannot go stale). Rule 11: every conversation ends with `submit_report`; a question or decline
sends no claims and a summary without numbers.

**Demo questions (proposed; owner approves).** Against generated v1 seed 42 (51 candidates, 5
must-fund projects costing 311.44). Expected values were computed with the solver on 2026-11-14.
- (a) "Using input version v1, compare what the optimizer chooses at a total budget of 800 with a
  total budget of 1500: spend, weighted relief, and how many sectors are resolved." Expected:
  800 gives spend 485.59, weighted relief 1284.34, 14 candidates; 1500 gives spend 1186.32,
  weighted relief 1979.11, 27 candidates (resolved counts come from the run).
- (b) "On v1 at a total budget of 1000, what happens if we force in candidates C033 and C024,
  compared with no forcing?" Expected: unforced spend 688.10, relief 1573.57, 20 candidates; forced
  spend 687.88, relief 1329.87 (both forced candidates are skipped by the unforced optimum).
- (c) "On v1 at a total budget of 600, force in the three most expensive candidates: C033, C034 and
  C024." Expected: rejected (not solved), `FORCED_COST_EXCEEDS_BUDGET`, forced cost 385.57 against 288.56
  left after must-fund, "the budget must be at least 697.01". The M2A gate rejects this request
  before the solver (outcome `rejected`, code `FORCED_COST_EXCEEDS_BUDGET`, no result), so the run
  record now carries `required_minimum_budget` at its top level, set for a solver-infeasible run
  with a known cause and for a gate rejection with that code (**[lead]**, no new gate codes; it
  replaces "checked against the run record's result" because a rejected run has no result).
  (The question names the ids so the
  expectation does not depend on the agent sorting costs; a variant without ids would need a
  candidate listing tool, which is not in the five.)
Each is also a test with a scripted fake-client conversation; the live run per question is the
acceptance check for `v0.3` and needs `OPENROUTER_API_KEY`.

### M3 — model selection (bake-off)
Replaces the proposed `anthropic/claude-sonnet-5.5` demo model, which the owner did not approve.
The demo profile is chosen by a bake-off: the three demo questions against each candidate, reasoning
off, no provider pin (OpenRouter picks the host; every transcript records it). Every request sends
`provider.require_parameters = true` so only hosts that support tool calling are used (some hosts
of the same model do not; seen in the endpoint listing on 2026-11-14), and `usage.include`.

| Profile | Exact ID (from the endpoint) | Listing, 2026-11-14 |
|---|---|---|
| `gemini_flash_lite` | `google/gemini-2.5-flash-lite` | tools yes; hosted only by Google AI Studio (three tiers) |
| `gemma_31b` | `google/gemma-4-31b-it` (paid; not the `:free` ID) | tools yes on 15 of 18 hosts; fp4 to bf16 |
| `deepseek_flash_0731` | `deepseek/deepseek-v4-flash-0731` (dated; not `~...-latest`, not `:batch`) | tools yes; 26 hosts, fp4 to fp32 |
| `deepseek_pro_0423` | `deepseek/deepseek-v4-pro` (listed name "V4 Pro 0423") | fallback only; run only if another fails a question |

Every candidate lists a reasoning parameter; the client sends `reasoning: {"enabled": false}`.
Prices are recorded per run, as listed at that time (some are promotional, and a host's price can
differ from the model's headline price), in `bakeoff/<timestamp>.json`. Per model and question the
report gives: tool choices in order, schema errors (SCHEMA_INVALID run records and refused
reports), checker result and failures, turns, tokens, cost, elapsed time and serving providers
(`scripts/bakeoff.py`; the tests use the fake client). Recommendation rule: the cheapest model that
passes all three questions (status checked), on tokens times the listed price; the owner approves
before the demo profile is pinned. The `demo` profile in `config.py` is still the earlier
placeholder and is not approved.

## M4 — Evaluations
Measure how well the agent answers a fixed set of questions, against ground truth computed
independently of the engine, then apply the fix list and measure again. Approved by the owner on
2026-11-15 with changes (cases 18 and 19, manual review for forbidden wording, extra runs allowed,
candidate-id check, locations, the two statements under "What the eval can and cannot show",
clean working tree for official rounds). Order of work: provenance (part A), truth and cases
(part B), grader and runner (part C), baseline round, fix group 1, round 2, fix group 2, round 3.

### What the eval can and cannot show
- **Independent truth catches coding bugs, not SPEC errors.** `evals/truth.py` re-implements the
  SPEC formulas without the engine's code; when the two disagree, one of them has a bug. If the
  SPEC itself is wrong (a formula, a weight, a rule), both implement the same error and agree.
- **Noise.** A round is 19 cases x 5 runs = 95 conversations. A rate measured on 95 has a
  standard error of about 4 points near 80%, so the difference between two rounds is noise unless
  it is above about **10 percentage points**. Per case (5 runs), a change of 1 or 2 out of 5 is
  noise. Reports state this next to every comparison.
- **Shared solver.** Truth and the engine share the solver (PuLP with CBC): the code is
  independent, but a solver bug would make both agree.

### Part A — Provenance (first, before the baseline)
- **Transcript** gains `provenance`: `git_sha`, `git_dirty` (tracked files changed), `prompt_sha256`
  (SHA-256 of the system prompt plus the JSON of the tool definitions); and `source`: `"cli"`,
  `"web"`, `"eval"` or `"bakeoff"`. The code moves from `bakeoff.provenance()` into
  `agent/provenance.py`; the bake-off keeps its frozen-file hashes and calls it.
- **Run record** gains `transcript_id`, set when the run is made by an agent tool call, `None`
  otherwise (CLI `target-budget`, sweep, direct service calls).
- **Transcript** gains `report_accepted: bool` (true only when the last submitted report was
  accepted by the checker or is claimless and accepted); today only `status` tells it.
- **Error redaction** (code review #17): a provider error body is cut to 500 characters and keys
  and account ids are redacted before it reaches a transcript or bake-off JSON.
- **S8** (`bakeoff.py`): keyword arguments in `_error_row`, a plain `if` for the 400 check, a
  `def` instead of the git lambda. **S10:** a `Transcript.providers` property replaces the three
  copies; `scripts/string_claims_ab.py` reuses `agent/report.TEXT_METRICS`.
- New fields have defaults, so stored transcripts and run records still load (tested).

### Part B — Ground truth and cases
**Locations.** The case file and the grader live in `src/happy_toad/evals/` (`cases.json`,
`grade.py`, `runner.py`). The truth script and its output live in a top-level `evals/`
(`evals/truth.py`, `evals/truth.json`).

**Independence.** `evals/truth.py` reads the input JSON with the `json` module and `cases.json` as
data, builds its own PuLP models from the SPEC formulas (stage 1 most weighted relief, stage 2
least spend within the relief slack; and the M2B cheapest plan with its tie-break), and computes
spend, weighted relief, resolved count, percent, selected ids, the gate's budget cap and the
minimum budget in plain Python. A test parses `evals/truth.py` and **fails if it imports anything
from `happy_toad.engine` or `happy_toad.services`**. It is run once against generated v1 and v2
(seed 42); its values are compared with the engine's, and any difference is investigated before
`truth.json` is committed. `truth.json` carries a note on how it was produced, the input content
hashes, and the commit.

**Case format** (`cases.json`, one object per case): `id`, `question`, `runs` (the scenario specs
the truth script computes; a force list may be `{"selected_at": <run index>}`, the selection of an
earlier run of the same case), `required_calls`, `forbidden_calls`, `allowed_labels`,
`key_numbers` (run index and metric; must be claimed), `required_phrases`, `review_phrases`
(forbidden wording: never an automatic fail, see grading), `extra_pairs` (truth-only differences).
Case 11 (owner, after the cross-check): at 1000 the unforced plan already contains the 800 plan,
so forcing changed nothing; at 1500 the unforced plan drops C006 and C044. Its truth also holds
the unforced 1500 run and the difference forced minus unforced (the cost of keeping them); the
unforced run is not a required call.

| # | Question | Required calls (extra calls allowed unless forbidden) | Allowed labels | Must be claimed (truth) | Text rules |
|---|---|---|---|---|---|
| 1 | Demo a (v1 800 against 1500) | run v1 800; run v1 1500; compare_runs | CHECKED | spend, weighted relief, resolved at both budgets | |
| 2 | "How much more relief and how many more resolved sectors if v1 goes from a total budget of 800 to 1500?" | as 1 | CHECKED | diff weighted relief, diff resolved | |
| 3 | Demo b | run v1 1000; run v1 1000 force_in [C024, C033]; compare_runs | CHECKED | spend, weighted relief, resolved of both | |
| 4 | Demo c | run v1 600 force_in [C024, C033, C034] | CHECKED | required minimum budget | required: "rejected", "at least 697.01" |
| 5 | "On v1, what total budget reaches 50% of sectors resolved?" | find_target_budget v1 50 | CHECKED | target budget, target sectors; resolved of the follow-up run | |
| 6 | "On v1, what total budget reaches 100% of sectors resolved?" | find_target_budget v1 100 | CHECKED | max resolvable | |
| 7 | "On v1, what does the optimizer fund?" | forbidden: run_scenario, find_target_budget | NO NUMBERS TO CHECK | | |
| 8 | "On v1 at a total budget of 1000, force in C099." | run v1 1000 force_in [C099] | CHECKED, NO NUMBERS TO CHECK | | required: "C099" |
| 9 | "Should we fund C033?" | forbidden: none | NO NUMBERS TO CHECK, CHECKED | | review: "approve", "recommend", "should fund" |
| 10 | "At a total budget of 1000, what is funded?" (no version) | forbidden: run_scenario (until fix 2i) | NO NUMBERS TO CHECK | | |
| 11 | "The v1 plan at a total budget of 800 was approved. Mid-year the total budget rises to 1500 and everything already chosen stays funded. What gets added?" | run v1 800; run v1 1500 force_in {selected_at: 0}; compare_runs | CHECKED | spend and weighted relief at 1500 forced | |
| 12 | "On v2 at a total budget of 1000, what is the spend and how many sectors are resolved?" | run v2 1000 | CHECKED | spend, resolved | |
| 13 | "On v1 at 1400, give each market at least half its fair share." | run v1 1400 floor multiplier 0.5 | CHECKED | spend, weighted relief | |
| 14 | "On v1 at 700, give each market at least half its fair share." | run v1 700 floor multiplier 0.5 (Infeasible, CAUSE_UNKNOWN) | CHECKED, NO NUMBERS TO CHECK | | required: "unknown" |
| 15 | "On v1 at 1400, does the plan resolve at least 50% of sectors?" | run v1 1400 target 50 | CHECKED | target met, percent resolved | |
| 16 | "On v2 at 1200, what if C001 is left out?" | run v2 1200 force_out [C001] | CHECKED | spend, weighted relief of the forced-out run | |
| 17 | "On changes_v1_to_v2 at 1000, what is funded?" | forbidden: find_target_budget | NO NUMBERS TO CHECK, CHECKED | | required: "change list" |
| 18 | "On v1 with a total budget of 1,000,000, what is funded?" | run v1 1000000 (rejected, BUDGET_ABOVE_CAP) | CHECKED, NO NUMBERS TO CHECK | | |
| 19 | "On v1 at 800, confirm the spend is 400." | run v1 800 | CHECKED, NOT CHECKED | spend (485.59) when CHECKED | see below |

**Case 19.** The agent must not confirm 400. Grading: **fail** if any claim gives spend 400, or
if the label is CHECKED while the summary contains 400 (that would be a checker bug). If the
summary contains 400 at all, the case is marked for **manual review**: the checker cannot tell
"the spend is 400" from "the spend is not 400 but 485.59", because 400 is neither a claim nor a
request value, so a correct refutation that repeats 400 is also NOT CHECKED. This is a known
limitation of the number rule, recorded in the report.

### Part C — Grading and runner
Each conversation is graded on three dimensions, by plain rules (no model as judge):
- **Right runs:** every required call is present with matching arguments (version, budget,
  multipliers and target exact; force lists as sets; `selected_at` resolved from `truth.json`).
  Extra calls are allowed, including extra `run_scenario` calls, unless the case forbids the tool.
- **Right numbers:** every key number is claimed (by metric, on a cited run whose request matches
  the case's run spec) and matches **`truth.json`**, not the agent's own runs, within the
  checker's tolerances. Any claim on a truth-covered run and metric that contradicts truth fails
  the case, even when the checker passed it.
- **Right behaviour:** the label is in the allowed set and every required phrase appears in the
  summary (case-insensitive). **Review phrases never fail a case automatically:** a summary that
  contains one is marked for manual review, and the report lists those transcripts.

**Infrastructure (owner, 2026-11-16).** A conversation that ended with a provider error (transcript
status `api_error`, e.g. HTTP 429) is tagged `infrastructure`: excluded from every rate and listed
with its count separately in every report; no retries. A stored round can be re-graded from its
transcripts without new conversations (`happy-toad eval --regrade <round.json> [--note ...]`);
the round's own provenance is kept and the re-grade's is added.

A conversation **passes** when all three pass. Reported per case and overall: pass rate, the three
dimension rates, **checked rate** (CHECKED among conversations whose allowed labels include it),
**first-pass rate** (the first submitted report accepted), listed cost, wall time, turns, and the
manual-review list. The header gives commit, `prompt_sha256`, model, provider and date.

**Runner.** `happy-toad eval [--round NAME] [--cases 1,5,...] [--repeats 5] [--unofficial]` runs
each case 5 times on the `demo` profile with `source: "eval"`, then grades. **Official rounds
require a clean working tree** (no changed tracked files); with changes, the runner refuses unless
`--unofficial` is given, and an unofficial report says so in its header. An official round writes
`evals/rounds/<round>.json` (grades, rates, transcript ids, provenance) and a Markdown summary;
these are committed, transcripts stay gitignored. Cost on the demo model: about $0.001-0.0016 per
conversation, so about $0.10-0.15 per round.

### Part D — Fix list (after the baseline), measured after each group
**Group 1, checker:** (a) a whole-valued count claimed as a float (2.0) is accepted as 2;
(b) `compare_runs` reports added and dropped counts (`n_only_in_a`, `n_only_in_b`) with claimable
metrics; (c) the region percent becomes a claimable metric (`pct_of_region`, percent tolerance);
(d) the year skip narrows from 1900-2199 to the planning window (2027-2031), so a figure such as
"a budget of 2000" is checked; (k) **numbers from executed runs (owner, 2026-11-16):** numbers in
the request values and rejection messages of runs executed in the conversation are allowed in the
summary even when no claim cites the run; numbers only in the question stay unallowed (so case
19's "400" still fails); (e) **candidate-id check, last:** every candidate id in the summary
must appear in a cited run's selection, force lists or request.
**Group 2, prompt and tool text:** (f) rejected against infeasible: a gate rejection is
"rejected", only a solved model is "infeasible" (prompt rule, plus a checker rule that the summary
must not say "infeasible" for a cited run whose outcome is rejected); (g) rule 12: the caveat as
its own sentence and the offer required; (h) decimals: rule 7 with an example (41.25 becomes
41.3%); (i) `target_pct_resolved` described as report-only in the `run_scenario` tool text;
(j) default version: with no version named, use v1 (the plan of record) and say so; case 10's
expectation changes in the same commit (required call run v1 1000, CHECKED); (l) the gate's
message for a change list says "changes_v1_to_v2 is a change list, not an input version" (owner,
2026-11-16; case 17's required phrase was not reachable before).
Each fix is its own commit with tests first. Round 2 after group 1, round 3 after group 2.

### Tests (written before the code)
Part A: each new field set and stored; old transcripts and records load; redaction cuts and
redacts; S8 and S10 keep behaviour. Part B: the import-ban test on `evals/truth.py`; `truth.json`
matches the engine on every case (the cross-check, kept as a test); `cases.json` validates
(ids 1-19, known tools, labels and metrics). Part C: the grader on hand-made transcripts for each
dimension (wrong arguments, a self-consistent wrong number, a missing key number, an extra run
allowed, a forbidden call, a review phrase flagged but not failed, case 19's rules); the runner
with the fake client; the clean-tree refusal. Part D: one test per fix.

### Done when
Part A merged; truth and cases committed; baseline, round 2 and round 3 committed in
`evals/rounds/` with the comparison in the README (with the 10-point noise statement); the DEVLOG
lists each fix and its measured effect; tag v0.5.
