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

**v2** is derived from v1 (`make_v2`) with these deliberate changes, each recorded in
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

## M3 — Agent (decisions only; no tests or code until the owner approves this list)
An agent layer that turns a plain-English question into calls of the M2A services and returns a
report whose numbers are checked against stored runs. Items marked **[owner]** were in the owner's
draft; items marked **[lead]** are project-lead proposals (defaults, to be approved or changed).
The wording of the system prompt is written by the owner by hand; only its rules are listed here.

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
   (names of `data/inputs/*.json`), a run reader (`runs/<run_id>.json`, a name that is not a run id
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
   error). M4 reuses them. The API key never appears.
9. **Cost and speed [owner].** Record tokens, elapsed time and estimated cost per question.
   **[lead]** Estimated cost = tokens x per-million-token rates held as constants in `config`.
   The rates are not set here: I will not invent prices. The owner supplies them, or the cost
   field stays `null` and the CLI prints "cost: not configured".
10. **CLI [owner].** `happy-toad ask "<question>"` prints each tool call and its result as it
    happens, then the report, then the check results (each claim pass/fail, the verdict). Needed
    for the video. **[lead]** Exit code 0 for a checked report, 1 for unverified or step cap.
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
