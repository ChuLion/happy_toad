# Dev log

## 2026-11-09 — M1 session 1
- 1.1 repo setup: uv project (Python 3.12, lock file), ruff, pytest + coverage, CI workflow
  (ruff + pytest on push), .gitignore, .env.example, CLAUDE.md, package skeleton, smoke test.
- Drafted docs/SPEC.md (M1). Stopped for owner review.
- Owner changes/rejections: none yet.

### Owner changes to the SPEC draft (same day)
- Added cost tie-break (ε·spend subtracted; reported objective is weighted relief only) and
  known-answer test 5 (zero marginal relief is not funded).
- Added test 6, the greedy trap (budget 10; A 6/6, B and C 5/4.5; expect {B, C}, objective 9).
- Result object extended: budget, must_fund_total, base_year, version_id, content_hash, solver
  settings (timeLimit, threads); time-limit statuses mapped.
- Canonical JSON defined: sorted keys, lists sorted by id.
- Budget is total including must-fund; sweep table gains status and must_fund columns.
- Generator: N must-fund projects, under-served sectors, v2 triggers never below base_year,
  `happy-toad generate --seed`.
- Open questions resolved: base_year 2026 and earlier triggers rejected; floats with units
  documented in README; keep labels; no mypy in M1.
- Added Done-when and subtask 1.9 (README with weight assumption, tag v0.1).

### Owner changes, round 2 (same day)
- Tie-break ε now computed per solve: ε = δ / (10 × (budget − must_fund_total)), δ = 1e-4;
  CBC gapAbs/gapRel set explicitly to 0; ε, δ and gaps recorded in the result's solver settings.
- Added known-answer test 7 (candidate costing the full available budget, relief just above δ,
  must be selected).
- Two-stage lexicographic solve recorded as the alternative considered (DECISIONS.md D2).
- Must-fund N = 5, total ≈ 10% of total candidate cost (generator parameter).
- Solver settings pinned: threads=1, timeLimit=30s, gapRel=0, gapAbs=0. Time-limit hits report
  status "TimeLimit" with best-found plan, never "Optimal".
- Fallback rule: if tests 3 or 5 fail due to ε lost in solver tolerance, raise δ to 1e-3, re-run
  test 7, log here.

### Owner changes, round 3 (same day)
- TimeLimit with no incumbent: status TimeLimit, selected=None, objective=None. `None` = no plan,
  `[]` = a plan that funds nothing.
- PuLP/CBC -> status mapping lives in its own function, unit-tested with mocked statuses (no
  forced real timeout).
- Test 2 budget = sum of candidate costs + must-fund (never inf).
- Test 3 budget funds all three candidates so only the tie-break decides.
- Test 4: if CBC returns Undefined rather than Infeasible, use a pre-solve check
  (must_fund_total > budget -> Infeasible) instead of widening the mapping. Written into the
  SPEC as the pre-solve check from the start.
- 1.2 schemas: tests first (test_schemas.py, test_hashing.py), then data/schemas.py and
  data/hashing.py (canonical_json, build_input_set). Value checks deferred to 1.4.

### Owner changes, round 4 (same day)
- Accepted the unconditional pre-solve check for must-fund > budget, and the 1.4-before-1.3 order.
- All five schemas: ConfigDict(frozen=True, extra="forbid"), with tests.
- 1.4 gains check 7: stored content_hash must equal the recomputed hash.
- 1.3 gains a test: generated v1 and v2 pass all load checks.
- 1.4 load-time checks: tests first (test_checks.py), then data/checks.py (check_input_set,
  InputError collecting all problems) and data/loader.py (save/load JSON; load runs the checks).
  Hash check proven by editing a cost in the saved JSON and expecting rejection.

### 2026-11-09 — 1.3 generator
- 1.4 addition: math.isfinite checks for cost, shortfall, offload amount (test first).
- 1.3: GeneratorConfig (data/config.py), make_v1 (data/generator.py), make_v2 + change list
  (data/evolve.py), write_inputs (data/files.py), `happy-toad generate --seed`. Tests first.
- Owner-specified defaults documented in SPEC (trigger years, shortfall, offload share, cost
  factor, labels, v2 change counts). Generated JSON is gitignored.
- Implementation notes: under-served sectors get exactly one offload row (<= 80% of shortfall)
  so they are guaranteed under-served; measured 11-14 of 60 under-served per seed because some
  other sectors end up under-served by chance.
- Stopped for owner review.

### 2026-11-09 — 1.5/1.6 optimizer
- Tests first: test_status.py (map_status, mocked statuses) and test_known_answers.py (tests
  1-7, plus weight, metadata, and no-plan vs empty-plan). Confirmed they failed (modules
  missing) before writing code.
- Found: PuLP 4.2 has no bundled CBC. Asked; owner approved `pulp[cbc]` (cbcbox). DECISIONS D3.
- PuLP 4.2 API: `solve()` returns LpSolveStats (status, has_solution), so map_status takes just
  the LpSolveStatus. Code: engine/{status,result,model}.py.
- Tests 5 and 7 passed first time; delta stays 1e-4 (no fallback to 1e-3 needed). Mutation
  check: with delta=0, tests 3 and 5 fail; with delta=1e-2, test 7 fails. The tie-break is
  really being tested.
- Test 2 returned "Error" at first. Root cause (CBC log): CBC exits via its gap test ("integer
  gap of -3.55e-15 less than 0") and writes "Optimal (within gap tolerance)", which PuLP 4.2
  reports as GapLimit. The plan was correct. Fix: GapLimit -> Optimal, valid because gaps are
  pinned at 0. Flagged to owner as a change to the mapping rule.
- Comparison script `scripts/compare_greedy.py` (not a test): optimizer vs greedy
  relief-per-cost (marginal gain, recomputed after each pick) on generated v1. Budget = share ×
  total candidate cost + must-fund total. Gap = (opt − greedy) / opt. All solves Optimal.

  | seed | 20% gap | 50% gap | 80% gap |
  |---|---|---|---|
  | 42 | 1.81% (895.0 vs 878.8) | 0 | 0 |
  | 1 | 0.88% (1083.7 vs 1074.1) | 0 | 0 |
  | 2 | 1.22% (1036.3 vs 1023.6) | 0 | 0 |

  Finding: at 50% and 80% both methods reach the same relief (the maximum), so the budget stops
  binding somewhere between 20% and 50%. Candidates overlap heavily (about 2.5x coverage), so the
  interesting part of the sweep (1.8) is low budgets, roughly 5-40% of candidate cost. The
  optimizer's edge over greedy is small (about 1-2%) on this data; the generator may need
  tighter coverage if we want a more dramatic demo. Not changed; owner's call.

### 2026-11-10 — first CI run
- Created private repo https://github.com/ChuLion/happy_toad and pushed `main`.
- First CI run (ubuntu-latest) passed: `uv sync --locked` (installed cbcbox 2.929), ruff check,
  ruff format --check, pytest: 80 passed. So the CBC dependency works on the CI runner.
- Annotations only: actions/checkout@v4 and setup-uv@v6 target Node 20 (deprecated), and
  ubuntu-latest migrates to Ubuntu 26 on 2026-10-19. Not changed.

### 2026-11-10 — 1.8 sweep
- Tests first (tests/test_sweep.py), then engine/sweep.py, report.py, `happy-toad sweep`.
- GapLimit caveat added to the map_status docstring and SPEC.
- Test 7 already asserted the reported objective equals 1.5e-4 at abs tolerance 1e-12
  (objective is recomputed from relief), so no change.
- Sample on generated v1 (seed 42): relief climbs 384.7 -> 1183.1 and plateaus from budget
  4922 on (spend plateaus at 4090 = 46% of candidate cost). The default 5%-60% range shows the
  whole curve.

### 2026-11-10 — tie-break failure at scale (found by the sweep)
- Found by the 1.8 budget sweep on generated v1, NOT by the unit tests: at budgets 4922.39 and
  above, candidates with exactly zero marginal relief are funded (e.g. budget 5369.89: relief is
  unchanged versus the previous budget, but spend rises). Tests 3/5/7 pass only because their
  numbers are small. Platform note (owner's report): plateau spend differs between macOS (4090.14)
  and Linux (4064.59), so the solver returns different optimal plans per platform.
- Regression test written (tests/test_tiebreak_at_scale.py, not committed yet): for every selected
  candidate, weighted relief without it must be lower by more than delta. Confirmed it fails now,
  on 3 of 5 budgets (4922.39, 5369.89, 6264.87). `weighted_relief` moved to engine/relief.py so the
  test and the comparison script share it.
- Measurement, delta = 1e-4 vs the spec fallback 1e-3 (12 default budgets): at 1e-4, 3 useless
  candidates (spend 49.11) at 4922.39 and 2 (spend 68.40) at each larger budget. At 1e-3 the
  4922.39 case is fixed but 2 zero-marginal candidates (C003, C026, spend 68.40) remain at 5369.89
  and above. So the delta fallback does NOT fix it.
- Root cause evidence: the penalty is eps * cost = 2.2e-8 * 68.4 = 1.5e-6 against an objective of
  about 1183, i.e. relative 1e-9, below CBC's numerical resolution. Setting CBC `increment` to
  1e-9 (cutoff increment) removes the zero-marginal candidates at 5369.89+ but not at 4922.39, and
  spend then wanders down with budget (4016, 3949, 3885), so plans are still not cost-minimal.
  Tuning delta/CBC options cannot fix a scale mismatch; options presented to the owner.

### 2026-11-10 — two-stage solve (owner chose it over post-solve pruning)
- Replaced the single-solve epsilon cost penalty with a two-stage solve (D2 rewritten): stage 1
  maximizes weighted relief (R*); stage 2 minimizes spend s.t. relief >= R* - delta/10; gaps 0;
  one 30 s limit across both stages. Claim: optimal relief within delta/10, then minimum spend
  among plans that deliver it.
- The tie-break failure was found by the budget sweep, not by the unit tests (tests 3/5/7 passed
  because their numbers are small). Evidence and the delta=1e-3 / CBC `increment` experiments are
  in the entry above and in D2.
- Test first: updated the settings test (epsilon -> relief_slack), added per-stage time tests,
  stage-2-timeout and stage-1-uses-all-time tests (via patching `LpProblem.solve`); confirmed they
  failed, then implemented engine/stages.py and rewrote engine/model.py. Relief and objective are
  now always recomputed from the funded candidates (engine/relief.py).
- Regression test committed with the fix (tests/test_tiebreak_at_scale.py): every funded candidate
  adds > delta; plateau spend identical across budgets (pinned 3743.94); relief within slack of an
  independent stage-1 solve. Tests 1-7 (test 7 included) all still pass. 103 tests.
- Stage 2 feasibility is asserted in the code. delta stays 1e-4 (the 1e-3 fallback is gone with
  epsilon).
- Re-ran on v1 seed 42: relief unchanged at every budget; plateau spend now 3743.94 from budget
  4922.39 on (before: 3984.49 then 4090.14 on macOS; 4064.59 on Linux per owner). Stage times
  0.03-2.2 s. Greedy comparison unchanged: gap at 20% = 1.81% (seed 42), 0.88% (seed 1), 1.22%
  (seed 2); 0 at 50% and 80%.
- Test-suite time went from about 1 s to about 15 s because the scale tests run real CBC solves.
- Owner change: regression-test threshold moved from delta to relief_slack (delta/10), the amount the
  method actually guarantees. Test renamed `..._adds_more_than_relief_slack`; still passes at all 5
  budgets on v1 seed 42.

## Generator realism block (settings and structure only, no new model features)
- Spec first (SPEC generator section rewritten), then tests (tests/test_generator.py: measured
  properties on seeds 1, 2, 3, 42), confirmed failing, then code. 139 tests pass.
- Changes: (a) candidate types by spend share 85/10/5, cost ratios 1.0/0.33/0.1, type_a reach 2-4
  and type_b/type_c reach 1; (b) markets by need rates 7/11/14/18% -> exactly 8/13/17/22 of 60
  sectors (counts proportional to the rates; shortfall stays uniform 10-100); (c) 80% of sectors
  have exactly one candidate able to relieve them, 20% have 2-3, by construction; (d) offload share
  of the sector shortfall widened (see below). `n_candidates`, `under_served_share` and
  `max_sectors_per_candidate` are gone; candidates are derived (38-39 on the four seeds).
- Owner decision (offload range): the brief's (0.1, 0.4) cannot give supply 1.0-1.3x need with
  this coverage: measured 0.31-0.36x on seeds 1, 2, 3, 42 (about 78 coverage rows over 60 sectors,
  mean share 0.25). Owner chose (0.6, 1.2): supply 1.14-1.27x. Cost: a single candidate can now
  fully relieve a sector (relief is capped at the shortfall).
- Measured on seeds 1, 2, 3, 42: type spend shares a/b/c 84.5-86.0 / 9.3-10.5 / 4.7-5.2%;
  12 of 60 sectors multi-candidate; 77-80 offload rows.
- Sweep default range extended from 5-60% to 5-100% of candidate cost (20 budgets), because the
  budget now binds much further out. Plateau test now uses the 90-100% budgets and its range test
  budgets were re-chosen across the new 20.
- v2 changes: `sector_added` picks its market by need rate; its one new offload row may take a
  candidate one row beyond its type's reach (documented in SPEC). v2 passes load checks and the
  v1-vs-v2 diff equals the change list (existing tests, unchanged).
- Re-run, v1 seed 42 (total candidate cost 2328.93, must-fund 232.90): relief rises from 242.286 at
  5% to 1344.323 and stops rising at spend 2021.76 (34 of 39 candidates, about 87% of candidate
  cost). Plateau spend re-pinned: 3743.94 -> 2021.76 (macOS; CI checks Linux). Sweep of 20 budgets
  takes about 5 s CPU.
- Greedy comparison (gap % = optimizer over greedy, budgets 20/50/80% of candidate cost):
  seed 42: 4.82 / 0.50 / 0.43 (before: 1.81 / 0 / 0); seed 1: 0.00 / 0.09 / 1.47
  (before: 0.88 / 0 / 0); seed 2: 0.93 / 2.10 / 0.60 (before: 1.22 / 0 / 0). The budget now binds
  at 50% and 80%, so the optimizer beats greedy there too. Solve times 0.06-0.24 s per budget.
- Decisions I made that you didn't specify (generator block):
  - `unit_cost = 100`: candidate cost = 100 x the type's cost ratio x uniform(0.7, 1.3).
  - Multi-candidate sectors get 2-3 candidates each (`multi_cover_range = (2, 3)`), drawn uniformly.
  - Need rates only set each market's share of sectors; shortfall stays uniform 10-100 for every
    market (so market does not change a sector's size).
  - Default sweep extended from 5-60% to 5-100% of candidate cost (20 budgets).
  - A v2 `sector_added` row may take a candidate one row beyond its type's reach.
  - A new v2 sector's market is drawn with probability proportional to the need rates.
  - Candidate ids are assigned after shuffling the types, so id order does not reveal type.
  - Candidate counts per type are rounded from the spend-share formula; reach sizes are then
    nudged at random to fit the coverage slots.
  - Test tolerances: spend shares +-4 points, cost ratios +-20%, multi-sector share +-2 points,
    on seeds 1, 2, 3, 42.

## Last data change before M2A: 8 markets, trigger profiles, home markets (2026-11-13)
- Spec first (SPEC generator section), then tests (tests/test_generator.py), confirmed failing, then
  code. 147 tests pass. Settings and structure only; no model changes.
- Done: (a) 8 markets `market_a..h`, need rates 7/8/10/11/13/14/16/18%, 80 sectors; (b) per-market
  trigger-year Beta profiles (`trigger_profiles`); (c) multi-sector candidates draw about 85% of
  their rows from a home market (`home_market_share`); (d) kept: 80/20 coverage, type spend 85/10/5,
  offload share (0.6, 1.2), 5 must-fund, derived candidate count.
- Numbers, v1 seed 42, old (4 markets, 60 sectors) vs new: sectors 60 -> 80; candidates 39 -> 51;
  total candidate cost 2328.93 -> 3004.30; must-fund 232.90 -> 300.43; max weighted relief
  1344.323 -> 1810.039; relief at 5% budget 242.286 -> 393.613; spend where relief stops rising
  2021.76 (34 of 39 candidates, about 87% of cost) -> 2822.92 (44 of 51, about 94%). Plateau test
  re-pinned 2021.76 -> 2822.92 and now uses the 95% and 100% budgets (BUDGETS[18:]).
- Greedy comparison, gap % at 20 / 50 / 80% of candidate cost (old -> new):
  seed 42: 4.82 / 0.50 / 0.43 -> 0.21 / 1.32 / 0.96;
  seed 1: 0.00 / 0.09 / 1.47 -> 0.49 / 1.25 / 0.13;
  seed 2: 0.93 / 2.10 / 0.60 -> 0.61 / 2.01 / 0.28.
  Solve times 0.07-0.31 s. The gap moved to the middle budgets.
- Measured on seeds 1, 2, 3, 42 (300 seeds in brackets): supply ratio 1.10-1.17 [1.03-1.28];
  spend shares a/b/c 84.4-86.5 / 8.7-10.8 / 4.8-4.9 [83.2-87.5 / 7.6-11.3 / 4.2-5.8]; candidates
  50-52 [49-54]; same-market share of multi-sector rows 0.80-0.87 [0.69-0.93, mean 0.81].
- FLAGGED (not loosened): small markets make two checks seed-dependent.
  - Trigger-year ordering urgent < mixed < relaxed. With the brief's example Beta(1, 4) for the
    urgent markets, seed 1 FAILS: urgent mean 2028.04 vs mixed 2027.96 (the expected gap is under a
    year and only 28 urgent sectors); over 300 seeds it fails on 9 (3%). I changed the urgent
    profile to Beta(1, 6) (see decisions); it passes on all 300 seeds, margins 0.7-1.9 years on
    the four test seeds. `market_a` has only 6 sectors, so its mean is noisy (2031.5-2032.8) but
    far from mixed (about 2028.2).
  - Same-market share of multi-sector candidate rows, 85% +-10 points: passes on the four test
    seeds (0.80-0.87) but 26 of 300 seeds (9%) fall outside 0.75-0.95. The measure takes each
    candidate's modal market as its home, which biases it upward for 2-row candidates, while
    pool exhaustion pulls it down (mean 0.81). Tolerance kept; do not run it on other seeds
    without expecting occasional failures.
  - Supply ratio 1.0-1.3: passes, but the 300-seed maximum is 1.279, close to the limit.
- Owner decisions, discrepancies in the brief:
  - Market counts: the brief's 5/6/8/9/11/12/13/14 sum to 78, not 80, and are not proportional to
    the rates. I derived counts by largest-remainder rounding of 80 x rate/sum(rates) (the rates
    sum to 97%): 6/7/8/9/11/11/13/15. The test asserts these. Say if you want your list (then
    n_sectors would be 78) or another rounding.
- Decisions I made that you didn't specify:
  - Urgent profile Beta(1, 6) instead of the example Beta(1, 4) (reason above; one-line revert in
    `config.py`). Relaxed Beta(2.5, 1.5) and mixed Beta(1, 2.5) as given.
  - Trigger profiles live in `trigger_profiles`, one (a, b) per market in market order; the year
    is `2026 + min(floor(10 * Beta), 9)` as before.
  - "Own market" is implemented per candidate: a home market drawn in proportion to the slots per
    market; each row is home with probability 0.85, else a slot from another market; when the
    wanted pool is empty or only repeats a sector, any remaining slot is used. Multi-sector
    candidates are filled first; single-row candidates take the leftover slots in random markets.
  - The same-market test uses each multi-sector candidate's modal market as its home, tolerance 0.85
    +-0.10.
  - Candidate-count check widened to 35-55 (the derived count is now about 50); coverage slots
    about 90.
  - New v2 sectors use the same market-dependent trigger profile; moved triggers in v2 stay uniform
    over 2026-2035 as before (unchanged).
  - Fuzzed seeds 0-299 for crashes in the dealing step: none.

## Calibration change: resolvable sectors, base year 2027, sweep columns (2026-11-13)
- Spec first (SPEC), then tests (confirmed failing), then code. 164 tests pass. Last data change.
- Problem: with every row at 60-120% of the shortfall only 37 of 80 sectors could be fully relieved
  on seed 42 even with every candidate funded. Now 76 of 80 (95%) on every seed (300 checked).
- (a) `unresolvable_share = 0.05`: 4 of 80 sectors, chosen at random, get a total offload of 50-95%
  of the shortfall (`unresolvable_total_range`), split equally over their rows. (b) Every other
  sector has at least one row with share in 1.0-1.3 (`resolving_share_range`); extra rows of
  multi-candidate sectors stay in (0.6, 1.2). (d) Kept: 80/20 coverage, spend 85/10/5, 8 markets,
  same-market preference.
- (c) `BASE_YEAR = 2027` is one constant in `src/happy_toad/constants.py`, imported everywhere; the
  only year literal left in code is that line. The generator window is `n_years = 5` (2027-2031).
  Files where the base year changed: `src/happy_toad/constants.py` (new), `data/config.py`,
  `data/checks.py` (was `DEFAULT_BASE_YEAR = 2026`, now removed), `data/loader.py`,
  `data/generator.py` (window from `n_years`), `engine/model.py` (its own `BASE_YEAR = 2026`
  removed; imports the constant), `scripts/compare_greedy.py`, `tests/helpers.py`,
  `tests/test_checks.py`, `tests/test_evolve.py`, `tests/test_known_answers.py`,
  `tests/test_tiebreak_at_scale.py`, `tests/test_generator.py`, `tests/test_base_year.py` (new),
  `docs/SPEC.md`. New end-to-end test: on v1 seeds 1, 2, 3, 42 the earliest trigger year equals
  `BASE_YEAR` and those sectors weigh exactly 1.0 through `sector_weights` using the solve
  result's `base_year`.
- Trigger profiles re-tuned for 5 bins: urgent Beta(1, 6) and relaxed Beta(2.5, 1.5) kept, mixed
  Beta(1, 2.5) -> Beta(1.5, 3). With mixed Beta(1, 2.5) the urgent-vs-mixed gap shrank to 0.27 year
  on seed 1; with Beta(1, 4) seed 1 fails (-0.05). Mean trigger year on seeds 1, 2, 3, 42 (urgent /
  mixed / relaxed): 2027.29 / 2028.33 / 2029.50; 2027.32 / 2028.04 / 2029.50; 2027.18 / 2027.98 /
  2030.17; 2027.36 / 2028.35 / 2029.67. Margins mixed - urgent: 1.04, 0.72, 0.80, 0.99 years;
  relaxed - mixed: 1.17, 1.46, 2.19, 1.32. 0 failures of the ordering on 300 seeds.
- (e) The supply-ratio gate is replaced by property tests on seeds 1, 2, 3, 42: resolvable fraction
  95% +-4 points; unresolvable sectors have supply <= 95% of shortfall (none marginal); every
  resolvable sector has a row with share in 1.0-1.3. Supply ratio is only recorded
  (`record_property`): 1.372, 1.382, 1.398, 1.385 on the four seeds (1.27-1.52 over 300 seeds).
- (f) Sweep table has `resolved` (`n/N`, relief >= shortfall - 1e-6) and `still short` (total
  unrelieved shortfall). The table now needs 80 terminal columns: `collapse_padding` and
  `pad_edge=False`, header min widths; tests run with COLUMNS=200.
- (g) Numbers, v1 seed 42, old (8-market generator, base 2026) -> new: total candidate cost
  3004.30 -> 3114.38; must-fund 300.43 -> 311.44; candidates 51; max weighted relief 1810.039 ->
  2579.9 (weights are larger with a 5-year window); plateau spend 2822.92 -> 2749.51, reached from
  the 90% budget on (41 of 51 candidates, about 88% of candidate cost); plateau test re-pinned,
  now BUDGETS[17:]. Resolved sectors at plateau: 76 of 80; still short 34.39.
- Resolved sectors first reach 50% (40 of 80) at 34% of candidate cost on seed 42 (41/80;
  budget 1370.3 including must-fund; 1% steps; 39/80 at 33%). In the 5% sweep: 32/80 at 25%,
  36/80 at 30%, 42/80 at 35%.
  Resolved counts at 20/30/40/50/60/80/100%: 28 / 36 / 47 / 54 / 62 / 72 / 76. The optimizer
  maximizes weighted relief, not the count of resolved sectors.
- Greedy gap % at 20 / 50 / 80% (old -> new): seed 42: 0.21 / 1.32 / 0.96 -> 1.51 / 1.51 / 0.73;
  seed 1: 0.49 / 1.25 / 0.13 -> 0.06 / 0.00 / 0.18; seed 2: 0.61 / 2.01 / 0.28 -> 4.01 / 1.40 /
  0.63. Solve times 0.06-0.20 s.
- FLAGGED: (1) the resolvable-fraction property is exact by construction (76/80 = 95% always), so
  its +-4 points tolerance cannot fail by sampling; it guards the construction, not the
  randomness. (2) urgent < mixed margin is 0.72-1.04 years on the four seeds (still 0 failures
  on 300 seeds) and is the closest check; I did not loosen anything. (3) `market_a` has 6 sectors,
  its mean year is noisy but 1.2-2.2 years above mixed. (4) The same-market share tolerance
  (85% +-10) from the last block is unchanged and still seed-dependent on other seeds (not
  re-measured here). (5) the sweep test settings widen the terminal (COLUMNS=200); the table
  itself fits 80 columns.
- Decisions I made that you didn't specify:
  - `unresolvable_total_range = (0.5, 0.95)`: total offload of an unresolvable sector as a share of
    its shortfall, split equally over its rows (so no unresolvable sector is a near miss). Count
    is `round(0.05 * 80)` = 4, picked at random regardless of coverage or market.
  - In resolvable sectors the resolving row is one random row; other rows stay (0.6, 1.2).
  - New v2 sectors get one row in (1.0, 1.3) (resolvable); v2's `offload_changed` (scaled 0.5-0.9
    or 1.1-1.5) can break resolvability in v2, which is not checked.
  - Mixed profile Beta(1.5, 3) (above); urgent/relaxed unchanged from the last block.
  - `n_years = 5` and `last_year` as a derived property; `base_year` in the config defaults to
    `BASE_YEAR`.
  - `still short` is the total unrelieved shortfall (sum of shortfall - relief), not a count of
    sectors; `resolved` is `n/N`. Both `-` when there is no plan.
  - `RESOLVED_TOLERANCE = 1e-6` lives in `engine/relief.py`; `sweep_table` now takes the input set.
  - The ">= 50% resolved" share uses a 1% grid and the first share where resolved >= 40 of 80.
  - Plateau test and the other scale tests re-use budget indexes (17, 19 and so on) chosen after
    seeing the new sweep.

## Two small fixes (2026-11-14)
- Sweep table: the `still short` column (total unrelieved shortfall) is replaced by `% resolved`
  (`100 * resolved / total sectors`, one decimal, `-` when there is no plan); shortfall magnitudes
  no longer appear in demo tables. `still_short` removed from `engine/relief.py`; `report.py`
  uses one `COLUMNS` tuple (the duplicated column list is gone); SPEC and tests updated, one new
  test (1 of 3 sectors -> `33.3%`). This supersedes the `still short` decision in the entry above.
- Correction to the calibration entry: the resolved counts in the 5% sweep were attached to the
  wrong shares. Right: 32/80 at 25%, 36/80 at 30%, 42/80 at 35% (the earlier text said 36 at 25% and
  42 at 30%). Re-checked every other figure from that scan against a fresh 1% scan of seed 42:
  resolved at 5%..100% in 5% steps = 8, 17, 23, 28, 32, 36, 42, 47, 50, 54, 58, 62, 63, 66, 70, 72,
  74, 76, 76, 76. The "20/30/40/50/60/80/100%: 28 / 36 / 47 / 54 / 62 / 72 / 76" list, "first
  reaches 50% at 34%" (41/80; 33% gives 39), the plateau from the 90% budget (spend 2749.51, 41
  candidates, 76 resolved, 88.3% of candidate cost) are correct. One more slip fixed: the budget
  at 34% is 1370.3 (0.34 x 3114.38 + 311.44 = 1370.33), not 1370.2.

## M1 finish: market floors and caps, README, tag v0.1 (2026-11-14)
- Order followed: SPEC ("Market floors and caps" section, edits to Terms, Goal, solver_settings,
  the two-stage claim, scale-regression note, fair-share table with its script), then tests 8-11
  plus unit tests (confirmed failing: the module and arguments did not exist; the 165 existing
  tests passed), then code, then docs. 177 tests pass; the 165 earlier tests pass unchanged.
- Code: `engine/markets.py` (new: `MarketLimits`, candidate market, fair shares, limits, clamp,
  pre-solve check), `_core` in `engine/stages.py` adds the floor/cap constraints once for both
  stages, `solve()` takes `market_floor_mult`, `market_cap_mult`, `fair_share_blend`, `limits`.
  `tests/helpers.make_set` accepts an optional market in the sector tuple. Root cause of a first
  wave of 49 failures: `SolveResult.solver_settings` was typed `dict[str, float]`; it now allows
  None and per-market dicts.
- Fair-share table for seed 42 at the 30% budget (avail 934.31): in SPEC, from
  `scripts/fair_share_table.py`.
- README written (M1 section, units, weight assumption, limitations); DECISIONS D4 added.
- Decisions I made that you didn't specify:
  - Interface: `solve()` also takes `limits: MarketLimits` (absolute spend per market) which
    replaces the computed limits; tests 9-11 need absolute amounts, which one multiplier cannot
    give for two markets. The suggested values 0.5 / 1.5 are not signature defaults (floor and cap
    default to None, blend 0.5), because you wanted everything off when not passed.
  - `solver_settings` also records the applied `market_floors` / `market_caps` (after clamping;
    None when off), so a budget-dependent run can be reproduced; `SolveResult.solver_settings` type
    widened.
  - A candidate with no offload rows has no market and is not limited; a market with no
    candidates gets no constraint; markets are the labels present on sectors; total shortfall is
    assumed positive.
  - Cap below floor is compared with the clamped floor; both checks use a 1e-9 tolerance.
  - The floor/cap constraint names use the market label (`floor_market_a`).
  - The sweep command does not expose the parameters (not requested); the SPEC note about a lower
    `% resolved` applies when caps are passed to `solve()`.
  - SPEC says "about 10-15 of ~51" cross-market candidates (measured 10, 12, 15, 11 on seeds 1, 2,
    3, 42), not your "10-13": seed 3 has 15. DECISIONS D4 and the README use the same range.
  - Units in the README are abstract "need units" and "cost units"; the SPEC table says "cost
    units", not dollars, because the project keeps the data generic and synthetic.
  - README scale limitation: written with a real-region sector count as you asked; removed on
    2026-11-14 (see the M2A entry).
  - README claims kept to: PuLP with CBC, synthetic data, checked and measured, "a small
    synthetic reference build ... not a product"; no novelty claim.
  - The fair-share script lives in `scripts/fair_share_table.py` and is embedded in the SPEC.

## M2A opened: README scrub (2026-11-14)
- README: the sentence with the real-region sector count is replaced by "a production region
  would have far more sectors". The figure is also removed from this DEVLOG. It was removed
  from git history as well on 2026-11-15 (git filter-repo, before the move to a new
  repository); commit hashes in these docs were remapped to the rewritten commits.
- Repo scan (tracked files and commit subjects) for company names, internal tool names and real
  figures: nothing found. Searched for company/entity words, equipment and domain terms, vendor
  and tool names, currency and unit figures, and "real/actual/production/proprietary/internal".
  Only hits: `CLAUDE.md` (the rule itself) and ordinary uses of "actual" in code and tests. The
  scan is a keyword search, not proof; it cannot recognize a name it was not looking for.

## M2A: decision services (2026-11-14)
- Housekeeping: tag `v0.1` moved to f1d1c1f (the clean tree; the old tag pointed to 524b464);
  history not rewritten. `CLAUDE.md` now says current milestone M2A and lists `services/`.
- Order followed: SPEC (section "M2A - Decision services"), tests (confirmed failing: missing
  modules `happy_toad.services`, `happy_toad.reasons`, constant `HORIZON_YEARS`, and unknown
  sweep options), then code, then docs. 227 tests pass (the 177 earlier tests unchanged, 50 new).
- Built: `services/{request,gate,unresolved,run}.py`, `reasons.py` (codes and `Reason`),
  `engine/diagnose.py` (pre-solve causes), `force_in` / `force_out` in `solve()` and `_core`,
  `SolveResult.cause`, `HORIZON_YEARS` and `BUDGET_CAP_FACTOR` constants, sweep options
  `--market-floor-mult` / `--market-cap-mult` with cause lines below the table, D5.
- Approved decisions 1-8 implemented as written. Project lead's proposals A-F implemented and
  listed in the SPEC: A floors/caps in requests and the sweep; B the two reason codes as causes;
  C `region_total_sectors` (reporting only); D `target_pct_resolved` (met / not met, no search);
  E `HORIZON_YEARS = 5` (also drives the generator window); F the M3 rule (SPEC text only).
- Check on a real case: at budget 700 on v1 seed 42 floors of 0.5 are infeasible and the result says
  `CAUSE_UNKNOWN`. I verified with a subset-sum calculation that this is real, not a bug: the
  cheapest whole-candidate combinations that meet each market's floor cost 426.9 in total, more
  than the 388.6 available. A "floors cannot be met with whole candidates" cause would be a cheap
  M2B addition; I did not add it because it was not in the list.
- Decisions I made that you didn't specify:
  - Request: `force_in` / `force_out` are normalized to sorted unique ids; the request hash is
    SHA-256 of the canonical JSON of every field except `label`. Field rules (`mult >= 0`,
    `region_total_sectors >= 1`, `0 <= target <= 100`, no unknown fields) are enforced by the
    schema and raise before the gate, so a malformed request is not a run record.
  - Versions are files `data/inputs/<input_version>.json`; a version that is not `[A-Za-z0-9_-]+`
    (a path, for example) is reported as `VERSION_NOT_FOUND` rather than opened.
  - Gate: NaN budget counts as not positive; `BUDGET_ABOVE_CAP` is only checked for positive
    budgets; the forced-cost check counts must-fund plus force-in and is also reported for a
    non-positive budget (redundant but harmless); reasons come in a fixed order.
  - Extra cause codes beyond your list: `FORCED_IN_EXCEEDS_CAP`, `FLOOR_UNREACHABLE` (floor above
    the cost of the market's candidates not forced out) and `CAUSE_UNKNOWN`. All except unknown
    are decided before the solver runs, in the order of the SPEC table. Must-fund above budget
    now reports `FORCED_COST_EXCEEDS_BUDGET` (same code as the gate); a solver-reported
    `Infeasible` always gets `CAUSE_UNKNOWN`.
  - Run record: `outcome` is `rejected`, `completed` or `error`; an infeasible solve is
    `completed` with status `Infeasible` and a cause; failures use an `error` field, not a reason
    code; a broad `except Exception` ensures every attempt leaves a record. Run id is a UTC
    timestamp plus 8 hex characters; files are indented JSON. Rejected attempts record the default
    solver settings and `content_hash` is null when the version was not found.
  - Result summary: `pct_resolved` is None without a plan; `target_met` is False when there is no
    plan and the comparison is `>=`; `pct_of_region` is resolved sectors over
    `region_total_sectors`, with a warning when the region total is smaller than the modelled
    sectors; the unresolved list is the full list, not truncated.
  - Sweep: only the two multipliers are options (fair-share blend stays 0.5); infeasible budgets
    are listed as `Infeasible <budget>: <CODE>` lines under the table rather than a table column.
    No CLI command runs a request file; the services are a library API for now.
  - `SolverSettings.as_dict()` added so results and run records record settings identically.
  - The sweep table is truncated on an 80-column terminal when a status like `Infeasible`
    appears; tests use 200 columns and the README says about 100 are needed.
- CI failed once on the M2A commit (`ruff check`: import order in `tests/test_unresolved.py`).
  Root cause: a stale local ruff cache. Ruff decided `happy_toad.services` was third-party because
  the new `services/` package did not exist when the cache entry was made; with `--no-cache` the
  same error reproduced locally. Fixed the import order; local checks now use `--no-cache`.

## 2026-11-14 — required_minimum_budget
- Done: infeasible results with a known cause now carry `required_minimum_budget` (SPEC section
  "Required minimum budget"), also in the run record; the cause message says "at least X". Tests
  first (4 failed on the missing field), then code; 231 tests pass, ruff clean.
- Owner request: add it to "M3 decision 2". No such list exists in the repo (M3 not started), so
  the text sits in the SPEC next to the M3 rule, and the M3 tool-result wording is recorded there.
- Decisions I made that you did not specify: forced-in spend inside a floored market counts toward
  that floor (max per market) instead of being added on top, because the plain sum could exceed
  the true minimum and "at least X" would then be false; for the forced-in demo case and any case
  without floors the two formulas give the same number. Unknown cause gives None.

## 2026-11-14 — M3 opened: decisions list only
- Done: wrote the M3 decisions list in `docs/SPEC.md` (section "M3 — Agent") and here. No tests or
  code started, waiting for the owner's approval of the list. CLAUDE.md still says M2A until then.
- Owner-supplied items: provider adapter, five tools, loop with cap 10, prompt rules (owner writes
  wording), report schema, consistency checker, SCHEMA_INVALID records, transcripts, cost/speed,
  `ask` CLI, three demo questions, v0.3 condition, `anthropic` dependency approved.
- Project-lead proposals flagged `[lead]` in the SPEC: pinned model `claude-sonnet-5-5`; comparer
  output shape; a turn = one model response; allowed units and `entity = "plan"` only; tolerances
  (0.005 for spend and relief, 0.05 for percent, exact for counts, status, target_met);
  `required_minimum_budget` not a checkable metric (so the infeasible demo cannot verify it);
  summary-number matching by a simple pattern; `transcripts/` folder name; cost rates left unset
  (I will not invent prices); exit codes; layout `src/happy_toad/agent/`.
- Conflict flagged: SCHEMA_INVALID records change the M2A choice that malformed requests are not
  recorded; handled in the agent layer, M2A schema unchanged.

## 2026-11-14 — M3 built (not tagged yet)
- Done: committed `required_minimum_budget`; CLAUDE.md now says M3; SPEC "M3 — approved changes
  and specification" (profiles, cost, number definition, tool descriptions, draft system prompt,
  demo questions); tests first (5 files failed on missing modules, 3 more on a missing CLI
  command), then `services/runs.py` (lister, reader, comparer), `src/happy_toad/agent/`
  (config, client, report, checker, tools, loop, transcript, prompt) and `happy-toad ask`.
  Added the `openai` dependency (approved). 273 tests pass, ruff clean, coverage 98%.
- Owner changes applied: OpenRouter instead of Anthropic SDK; two profiles; cost only from the
  response; `required_minimum_budget` as a checkable metric; number definition in the SPEC and
  tested; demo questions proposed with real ids and budgets.
- Not done: **no live run yet and no `v0.3` tag.** There is no `OPENROUTER_API_KEY` in this
  environment, and the model IDs are waiting for approval. The tag needs the three demo questions
  to run live with every claim checked.
- Found while testing: the M2A gate rejects "force in more than the budget" before the solver, so
  that rejected run has no result to hold `required_minimum_budget`. My first test assumed a solver
  result. The number is now also a top-level field of the run record (set for solver-infeasible
  runs with a known cause and for gate rejections with `FORCED_COST_EXCEEDS_BUDGET`); the checker
  reads it there. Demo (c) is therefore a rejected run, not status Infeasible.
- Decisions I made that you did not specify: proposed model IDs `google/gemma-4-31b-it:free`
  (smoke) and `anthropic/claude-sonnet-5.5` pinned to provider `anthropic` with no fallbacks
  (demo), chosen from OpenRouter's tool-support listing; `usage: {include: true}` asked of every
  request; summary numbers may also equal a numeric request value (budget, multipliers, target,
  region) of a cited run; years are 1900-2199 plain integers, so a four-digit amount needs
  decimals; hyphen counts as a separator; a plain-text reply is nudged to call `submit_report`
  and costs a turn; a schema-invalid `submit_report` does not use the one correction; invalid JSON
  in `run_scenario` arguments is also a SCHEMA_INVALID record; model sees run summaries with the
  top 5 unresolved sectors and not solver internals; transcript ids use the run-id format;
  `ask --profile` defaults to demo; a missing key exits 2 with a plain message; `RunRecord`
  gained an optional `required_minimum_budget` (older records still load).
- Sandbox note: during this work `uv` could not write its cache or read the venv interpreter
  inside the sandbox, so test runs used the unsandboxed shell.

## 2026-11-14 — bake-off prepared, not run
- Done: candidate profiles (exact IDs from the endpoint), reasoning off, `require_parameters`,
  `agent/demo.py` (questions moved out of the test), `agent/bakeoff.py` and `scripts/bakeoff.py`
  (rows with tools, schema errors, checker failures, turns, tokens, cost, time, providers and the
  prices listed at run time), SPEC section "M3 — model selection". Tests first (they failed on the
  missing modules), then code: 277 pass.
- Not done: **the bake-off has not run**, because there is no `OPENROUTER_API_KEY` in this
  environment. No recommendation yet, and the demo profile is not pinned.
- Decisions I made that you did not specify: `require_parameters: true` on every request; paid
  `google/gemma-4-31b-it` rather than the `:free` one (free hosts vary and are rate-limited);
  `deepseek/deepseek-v4-pro` as the "0423" ID (its listed name; a separate `-0813` ID exists);
  no provider pin for any candidate; one fresh transcript per model and question; runs go to the
  normal `runs/` folder, transcripts to `transcripts/`, results to `bakeoff/` (gitignored).

## 2026-11-14 — [pre-fix] smoke check (live)
- Key came from the gitignored `.env` (loaded per command; never printed). The smoke profile
  `google/gemma-4-31b-it:free` returned HTTP 429 on every real request (3 tries, also after a wait):
  "temporarily rate-limited upstream", host Google AI Studio, shared free pool. A 5-token "hi" got
  through, so the key and routing are fine. Nothing was run on Gemma.
- Loop checked live with a one-off profile on `inclusionai/ling-3.2-flash:free` (host Ant Digital),
  demo question (a): 5 turns, tools run_scenario x2, compare_runs, submit_report x3; first report
  refused by the schema (a made-up metric `budget`), second by the checker, third checked. Tokens
  23535 in / 8780 out, 218 s, cost 0.0 (free). Transcript and runs saved; provider recorded.
- Bug found by the live run: the checker tolerance was not inclusive in floating point (26.3 vs
  stored 26.25 differs by 0.05000000000000071, over the 0.05 tolerance). Test first (failed), then
  `FLOAT_SLACK = 1e-9`. 278 tests pass.
- Observation, not changed: the model wrote "of 80 sectors" and the checker rejected the 80, since
  `total_sectors` is not a claim metric or a request value. This is the stated rule working, but it
  is a likely source of avoidable failures; the owner can decide to allow it.

## 2026-11-14 — [pre-fix] bake-off run (4 paid candidates x 3 demo questions)
- Results file `bakeoff/20261114T161530.json` (gitignored; prices listed at run time inside).
  Listed prices per token in/out: gemini-2.5-flash-lite 1e-7/4e-7; gemma-4-31b-it 2e-7/4e-7;
  deepseek-v4-flash-0731 4.34e-8/3e-7; deepseek-v4-pro 9e-7/1.5e-6.
- Gemma 4 31B checked a, b, c; Gemini 2.5 Flash Lite: a checked, b error (my parser crashed on a
  response with `usage` null; fixed test-first), c step cap (asked the user for candidate costs and
  never called submit_report); DeepSeek Flash 0731: a unverified (summary numbers 13 and 24 matched
  nothing), b checked, c unverified (claimed `status` of a rejected run, which has no value);
  DeepSeek Pro: a and b unverified (put the word "compare" in `run_id`; unmatched summary numbers),
  c checked.
- Sanity: reported cost (OpenRouter `usage.cost`) is lower than tokens x listed price, because the
  hosts that served the calls charged less than the headline price.

### 2026-11-14 — clarifying questions and declines end through submit_report
- Checked: `Report.claims` has no minimum length and the checker only tests numbers in the summary,
  so a claimless report with a number-free summary is accepted and ends the loop as `checked`.
  No code change. Added tests: missing budget ends in 1 turn (no run created), version lookup then
  question ends in 2 turns, and a number in a claimless summary is still refused.
- Decision not specified by the owner: ruff E501 is ignored for `agent/prompt.py` only, because the
  owner's hand-written rules are long prose lines.

### 2026-11-14 — submit_report description, final prompt
- Owner finalized `agent/prompt.py` (rule 11 now covers questions and declines) and asked for one
  sentence in the `submit_report` tool description: to ask or decline, send claims as an empty list
  and a summary with no numbers. Added with a test that pins it; SPEC tool list updated.
- Not specified by the owner: the SPEC's draft prompt block was replaced by a pointer to
  `agent/prompt.py`, so there is one copy.

### 2026-11-14 — [pre-fix] first 5-repeat attempt (aborted), fixes, A/B on the clarify sentence (not a ranking)
- First batch (Gemma pinned to Crusoe/Novita, question a, repeats 1-3, commit 4de0aa6) stopped at
  the first error row. Repeats 1 and 2 were `unverified`: Gemma wrote claim values as JSON strings
  ('485.59', '21'); the checker compared a str with a number, so every claim failed and every summary
  number was reported unmatched. Root cause confirmed in the transcripts.
- Owner approved the fix (commit 89f0c4d): plain-decimal strings are coerced for numeric metrics
  (counts: whole numbers only; "$485.59", "1,284.34", "21 sectors", "21.5" for a count are rejected;
  bools never coerced; status/target_met keep strings); every coercion is logged in the transcript;
  mismatch messages show the claimed type (`claimed '485.59' (str), stored 485.59`); when no claim
  validated, summary numbers are "not checked because no claim validated", reported once; a provider
  error status is outcome `api_error` with its full body and does not abort the batch; a repeated 400
  at the same step stops the batch; each bake-off file records the git SHA, a dirty flag, the prompt
  hash and hashes of checker/report/tools/prompt; `*.log` is gitignored.
- Not specified by the owner: `api_error` counts as not checked in "checked k/5" and is listed apart;
  only openai status errors are `api_error` (connection errors stay `error`); the repeated-400 key
  is (profile, question, step); bool is not coerced and stays a mismatch; negative decimal strings
  are allowed for money metrics, not for counts.
- A/B (Gemma 4 31B, question a, 3 runs each, new code): with the clarify sentence: checked, api_error,
  checked; without it: checked x3. String-valued numeric claims across all submit_report attempts:
  with 6, 0 (the api_error run had none), 0; without 12, 12, 14. Strings appear in both sets, more
  often without the sentence, so the sentence does not cause them. Three runs per cell is not a test.
- The 400 (second occurrence, same step 2 of question a): the body shows Crusoe returned 429 (upstream
  rate limit) and OpenRouter fell through to Novita, which returned 400 invalid_request_error. In both
  400 runs (first batch and A/B) the model's turn-1 `run_scenario` arguments were two JSON objects
  concatenated (invalid JSON, "Extra data"), which our loop echoes back verbatim in the assistant
  message. Suspected message-format bug in our loop; stopped per the owner's rule, not fixed yet.

### 2026-11-14 — [pre-fix] five-trial comparison, 3 models x 3 questions x 5 runs (not a ranking)
- Frozen state: commit 56fc796 (CI green), clean tree, prompt sha256 a7e94a23…fd24; checker.py
  cbb7113d…, report.py 251eeda6…, tools.py 22de2517…, prompt.py 49e10556… (full hashes in
  bakeoff/20261114T183716.json). No error rows, no api_error rows, no repeated 400. Gemma pinned to
  crusoe/bf16 and novita/bf16 (no fallbacks); the other two unpinned, providers recorded per turn.
- Checked runs out of 5 (question a / b / c): Gemma 4 31B 4 / 3 / 5; Gemini 2.5 Flash Lite 1 / 4 / 5;
  DeepSeek V4 Flash 0731 4 / 5 / 5. Totals checked: 12, 10, 14 of 15.
- Counts: coercions Gemma 31, Gemini 0, DeepSeek 0; malformed tool-call arguments Gemma 32 (25 in
  question b), others 0; api_error 0 for all. Refusals (corrections) summed per cell are in the
  bake-off file.
- Failures: Gemma a#4 and b#1, b#2 hit the 10-step cap looping on malformed (glued) run_scenario
  arguments. Gemini: unmatched summary numbers (13, 14, 24, 27, 0.22) and one step cap. DeepSeek a#1:
  claimed n_resolved 24, stored 45.
- Listed cost for all 15 runs (tokens x per-token prices listed at run time): DeepSeek $0.0167,
  Gemini $0.0307, Gemma $0.0500 (Gemma priced at the model-level listing, 2e-7 in / 4e-7 out, not
  the 1.4e-7 in the Crusoe/Novita endpoint listing).
- Decision rule (cheapest model checked in at least 4 of 5 on every question): only DeepSeek V4
  Flash 0731 qualifies. Its 15 runs were served by seven hosts with mixed quantization (fp8, fp4,
  nvfp4, fp32, unknown), so the demo pin needs the owner's choice of host.

### 2026-11-14 — [pre-fix] refusal breakdown (all saved transcripts) and GLM 5.3 Flash facts (no runs)
- First-refusal reasons differ by model. Gemma 4 31B: schema errors (entity set to a scenario label
  such as "Budget 800", metric "weighted relief"/"budget", unit "currency") on a and b; on c all 5
  rerun runs were first refused for "697.01" in a claimless summary, then a schema error, then
  accepted with "the budget must be at least the required minimum budget" (checked, but the number
  the owner's rule 10 asks for was dropped). Gemini 2.5 Flash Lite: entity literal errors (15 of 18
  first refusals). DeepSeek V4 Flash 0731: summary numbers no claim can back (16 of 18): differences
  read from compare_runs (700.73, 694.77, 13, 24), the sector total 80, must-fund 311.44 and forced
  cost 385.57 from gate reasons, small counts (1, 2); plus `status` claims on rejected runs (no
  result, so "no value for this metric"). One run id written as its digit-only suffix (78612358)
  was read as a number.
- Proposed (not applied; state frozen): metrics that cite compare_runs and gate-reason values,
  status falling back to the run outcome, entity defaulting to "plan" and unit derived from metric,
  and a checker rule that a rejected/infeasible run with required_minimum_budget needs that claim.
- GLM 5.3 Flash: ID z-ai/glm-5.3-flash (canonical z-ai/glm-5.3-flash-20260826); tools and
  tool_choice listed (one endpoint lacks tool_choice); reasoning is mandatory (efforts max/high/low,
  default max), so it cannot be turned off; highest listed precision is fp8 (no bf16); tool-call
  error share from the page's embedded data, 2026-10-15..11-14: 0.94% (8.14M requests with
  tool-call errors / 861.8M tool calls). Frozen hashes re-verified against bakeoff/20261114T183716.


## 2026-11-14 — checker fixes after the refusal breakdown; results above marked [pre-fix]
- Owner approved five fixes, built test-first (tests failed for the missing features first):
  `diff_*` claims citing two runs (b minus a, as compare_runs), `must_fund_cost` and `forced_cost`
  checked against the input file, `status` of a run without a result is its outcome, `unit` set
  from the metric and `entity` always "plan" (replaced or missing values logged as `defaults`,
  counted like coercions), a validated `required_minimum_budget` claim mandatory for every rejected
  or infeasible run of the conversation or the report that has one, and run ids plus their
  timestamp and suffix never read as numbers. SPEC report schema and number rules updated.
- Every result recorded before this entry was produced by the old checker and is labelled
  [pre-fix]; it is not comparable with the next round.
- Round profiles (`config.ROUND`): Gemma 4 31B (crusoe/bf16, novita/bf16), Gemini 2.5 Flash Lite
  (unpinned), DeepSeek V4 Flash 0731 (baseten/fp8, baidu/fp8; reasoning off), GLM 5.3 Flash
  (z-ai/fp8, novita/fp8; reasoning effort low, mandatory reasoning, not equal terms), Sonnet 5.5
  reference (anthropic only; reasoning mandatory, effort low). No fallbacks outside each list.
  Reasoning tokens are recorded per turn and per run.
- Not specified by the owner: diff counts accept signed whole-number strings; a diff number may
  appear unsigned in the summary; the mandatory rule covers runs executed, read, compared or cited;
  loop.py joins the frozen-file hashes; wrong unit/entity values are replaced rather than rejected.
- DeepSeek native precision (model card config, deepseek-ai/DeepSeek-V4-Flash-0731): quant_method
  fp8 (e4m3) with `expert_dtype: fp4`; most parameters are stored packed as I8, consistent with fp4
  experts. Not plain fp8, so the DeepSeek pin waits for the owner. baseten/fp8 and baidu/fp8 both
  list tools and tool_choice.

## 2026-11-14 — DeepSeek pinned; limitations recorded
- Owner approved the DeepSeek pin (baseten/fp8 first, baidu/fp8 backup, no fallbacks) and the README
  wording: "served at fp8 as listed by the hosts; the checkpoint ships mixed fp8/fp4 per its model
  card." Frozen-file and prompt hashes re-verified against the four-model record
  (bakeoff/20261114T201817.json, commit 4a6572b) before its 15 runs started on the same state.
- Limitation (SPEC, README): the checker verifies numbers but not direction words in prose
  ("more/less"); a correct number with the wrong direction would pass, since a diff claim may
  appear unsigned in the summary.
- Not specified by the owner: the README limitation line that said the agent states no differences
  was corrected, since diff claims read from compare_runs are now allowed; DeepSeek ran as a separate
  process alongside the four-model run (same commit, clean tree, same hashes).

## 2026-11-14 — post-fix round: 5 models x 3 questions x 5 runs (five-trial comparison, not a ranking)
- State: commit 4a6572b, clean tree, same prompt and frozen-file hashes in both records
  (bakeoff/20261114T201817.json for Gemma, Gemini, GLM, Sonnet; bakeoff/20261114T202752.json for
  DeepSeek, run alongside). No error rows, no api_error, no repeated 400.
- Checked out of 5 (a / b / c), refusals over 15 runs, listed cost for 15 runs, mean s per question:
  Gemma 4 31B (crusoe/novita bf16) 2 / 3 / 5, 12 refusals, $0.0564, 16.1 s (5 step caps, 62
  malformed calls); Gemini 2.5 Flash Lite (unpinned) 4 / 2 / 4, 16, $0.0225, 8.0 s; DeepSeek V4
  Flash 0731 (baseten/baidu fp8) 5 / 5 / 5, 5, $0.0146, 7.1 s; GLM 5.3 Flash (z-ai fp8, reasoning
  low, not equal terms) 5 / 5 / 5, 11, $0.0079, 20.8 s (a 27.0, b 27.4, c 7.9); Sonnet 5.5
  reference (anthropic, reasoning low, not equal terms) 5 / 5 / 5, 3, $0.5758, 9.5 s.
- Refusal reasons: Gemma: invalid metric names (with the unit/entity errors they bring), and on c
  a claimless "697.01" (missing required_minimum_budget claim) before claiming it; Gemini: diff
  claims with the sign reversed, unclaimed counts (14, 27), must-fund and forced cost written
  without the new metrics, missing minimum budget; GLM: unclaimed sector total 80 and counts;
  DeepSeek: diff count signs, unclaimed small counts; Sonnet: an unclaimed 15 (3 times).
- Rule (cheapest checked >= 4 of 5 on every question; costs within 2x tie, then fewer refusals,
  then clearer precision; GLM also under about 15 s per question; reference only if none passes):
  Gemma fails a and b, Gemini fails b, GLM passes the counts but averages 20.8 s (fails latency),
  DeepSeek passes. DeepSeek and GLM would be a cost tie (1.85x) and DeepSeek has fewer refusals
  (5 vs 11), so the outcome is the same. Result: DeepSeek V4 Flash 0731; the reference does not
  decide. Waiting for the owner before pinning the demo profile.
- Not specified by the owner: GLM's latency is the mean over all 15 runs (per question it also
  fails a and b); BaseTen turns show "fp32|fp8" because OpenRouter names both endpoints BaseTen
  and the response does not say which, while the pin names the baseten/fp8 tag; the reasoning-token
  count for Sonnet is 0 as reported by the provider, not verified.

## 2026-11-14 — full code review (CODE_REVIEW.md)
- Ran a full review with the code-review and code-simplifier plugins (report only, no code
  changed). Baseline: 342 tests pass, 98% coverage, ruff clean. No high-severity bugs; 4 medium
  findings: claims accepted for runs outside the conversation, a corrupt input file leaves no run
  record, the minimum-budget advice with multiplier floors, and a missing timeout on the endpoint
  listing. Simplifications and a prioritized fix list are in CODE_REVIEW.md.
- Not specified by the owner: CODE_REVIEW.md sits at the repo root; severities are the reviewer's.

## 2026-11-14 — demo profile set to DeepSeek V4 Flash 0731
- Owner approved: the `demo` profile is the round's DeepSeek profile (baseten/fp8 first, baidu/fp8
  backup, no fallbacks, reasoning off), replacing the Sonnet placeholder; test pins it.
- `transcript.redact` and `scripts/show_transcript.py` print transcripts with OpenRouter account ids
  redacted. Its test exposed that the id pattern also matched the JSON key "user_id"; the pattern
  now needs 16+ characters after "user_" (root cause shown by the failing test, then fixed).

## 2026-11-14 — live demo checked; tag v0.3; README comparison
- Pushed 334c220, c79c70b and 06c4d5e; CI green on 06c4d5e. Frozen-file and prompt hashes equal the
  round's record. data/inputs/v1.json equals generated v1 seed 42.
- Live `happy-toad ask --profile demo`, every turn served by BaseTen: (a) 4 turns, 1 refusal (numbers
  2 and 15 unclaimed), final 19/19 claims valid, 20/20 numbers matched; (b) 5 turns, 1 refusal (the
  sector total 80 unclaimed), 19/19 claims, 16/16 numbers; (c) 3 turns, 0 refusals, 4/4 claims
  (status rejected, required_minimum_budget 697.01, forced_cost 385.57, must_fund_cost 311.44), 5/5
  numbers. Transcripts 20261114T204339-935bd491, 20261114T204347-f4ac9ae2, 20261114T204355-d3dbc583.
- Checked by hand, outside the checker: (b)'s candidate lists match compare_runs exactly; (c) says
  "rejected as infeasible" although the gate rejected the request before solving (no result), a
  wording slip the checker cannot see. Recorded as a README limitation.
- Every claim checked, so v0.3 is tagged (annotated) on 06c4d5e and pushed.
- README: demo model, the 75-conversation comparison with the rule and measured figures only, the
  Baseten fp32|fp8 caveat, and limitations (five runs per cell, one round, direction words and
  wording unchecked, defaults count not a quality signal).

## 2026-11-14 — code review triage: fixes applied (test-first, one batch)
- Owner chose the fixes from CODE_REVIEW.md. Each got a failing test first; the failure was the
  one the review described (for #2/#8 a raw pydantic `ValidationError` escaped).
  - #9: a claim whose `run_id` or `run_id_b` was not executed, read or compared in this
    conversation fails ("run was not executed or read in this conversation"). The test cites a
    run left on disk by another conversation.
  - #13: only the first `submit_report` of a turn is checked; later ones in that turn get an error
    result and use no correction.
  - #1: with multiplier-derived floors and caps (any cause except `FORCED_COST_EXCEEDS_BUDGET`),
    `required_minimum_budget` is None and the cause names the multiplier to change ("floor
    multiplier 1.2 requires floors above the available budget at any budget; use 1.0 or less").
    The SPEC "Required minimum budget" section is updated. The old loop test that expected a
    minimum budget for `market_floor_mult=3.0` now expects None.
  - #2/#8: `load_input_set` and `read_run` wrap `ValidationError` in `InputError`, so a malformed
    `vN.json` leaves an error run record. Tests cover bad JSON, a schema break and a bad run file.
  - #10: the endpoint listing uses `timeout=10` and treats `OSError`, `ValueError` and `KeyError`
    as "unknown"; tests cover a network failure, non-JSON and a reshaped listing.
  - #11: the CLI shows the report only for checked or unverified outcomes. #12: an unknown
    `--profile` is a `typer.BadParameter` that lists the valid names.
  - #14: refusals count only refused submits that a later checked submit followed. #15: Ctrl-C
    saves the transcript (status `interrupted`) in a `finally`, then re-raises.
- CLAUDE.md dependency list now includes `openai` (approved for M3).
- #14 recount from saved transcripts for the post-fix round (bakeoff/20261114T201817.json and
  20261114T202752.json): 75 transcripts were matched to the 75 rows, with status and turn count
  checked per row. Gemma 12 → 12, Gemini 16 → 11, DeepSeek 5 → 5, GLM 11 → 11, Sonnet 3 → 3. The
  decision is the same: the DeepSeek-GLM tie-break (5 vs 11) is unchanged.
- Not specified by the owner: `check_report(conversation_runs=None)` skips the #9 rule (for
  re-checking a saved report outside a conversation), and the loop always passes its list; the
  ignored extra submit carries no `accepted` key, so it is never counted as a refusal; the other
  multiplier messages are "cap multiplier X is below floor multiplier Y at any budget; use a cap
  multiplier of Y or more", "raise the cap multiplier (now X) or force in fewer candidates" and
  "lower the floor multiplier (now X) or force out fewer candidates"; `InputError` is reused for
  malformed run files.

### Deferred: post-checkpoint refactor pass, before M4 (not applied)
Simplifications S1-S14 from CODE_REVIEW.md, behaviour-preserving, done in one pass after the v0.3
checkpoint and before M4. Several touch frozen files, so they go between bake-off rounds.
- S1: one `markets.market_spend(data, ids=None)` in place of `diagnose._market_spend` and
  `markets.market_costs`.
- S2: `record_invalid_request` in `services/run.py`; keep the current sha256 of the raw input.
- S3: `InputSet.must_fund_total` and `candidate_total` properties; forced-in cost computed once
  in `diagnose`.
- S4: `has_plan(record)` in `runs.py`, used by the checker too.
- S5: the checker imports `runs.RUN_ID`. S6: `stages._core` returns the relief expression and
  drops its unused defaults. S7: type hints and keyword-only `cause`/`minimum` on `make_result`;
  `_run_meta` helper. S8: `bakeoff._error_row` with keyword arguments, a plain `if`, a `def` in
  place of the `git` lambda.
- S9: `fair_share_table.py` calls `markets.fair_shares`. S10: `string_claims_ab` reuses
  `TEXT_METRICS`; `Transcript.providers` property. S11: rename `happy_toad/report.py` to
  `tables.py`.
- S12: missing type hints. S13: `candidate_id`/`sector_id` helpers. S14: the small constructs
  listed in CODE_REVIEW.md.

### Known low-severity issues (logged, not fixed)
- #3: `solve()`/`run_sweep()` called without the gate, with budget < must-fund and nothing forced,
  is labelled `FORCED_COST_EXCEEDS_BUDGET` with "forced-in cost 0.00".
- #4: `fair_shares` divides by zero when every shortfall is 0 and multipliers are on.
- #5: the stage-2 `assert` is stripped under `python -O`.
- #6: load checks use the default `BASE_YEAR`, but `solve(base_year=...)` accepts a later year.
- #7: `request_hash` covers `input_version`, not the data's `content_hash`.
- #16: each `OpenRouterClient(profile)` built without a listing fetches it again.
- #17: error-body redaction covers only `user_…` ids; the rest of the body is kept.

## 2026-11-14 — round on the fixed state; live demo; tag v0.3.1
- CI green on 78ba102. Re-frozen hashes (bakeoff/20261114T210127.json, clean tree): checker.py
  1e34325e…, loop.py 715c0020… (both changed by the triage); report.py, tools.py and prompt.py, and
  the prompt hash, unchanged. data/inputs/v1.json equals generated v1 seed 42.
- Full round, same rule and pins, 5 models x 3 questions x 5 runs, one process: no error rows, no
  api_error. Checked a / b / c, refusals (corrected only), listed cost for 15 runs, mean s:
  Gemma 4 31B 1 / 0 / 5, 7, $0.0583, 19.4 (9 step caps, 76 malformed calls); Gemini 2.5 Flash
  Lite 1 / 3 / 5, 12, $0.0249, 7.0; DeepSeek V4 Flash 0731 4 / 4 / 5, 10, $0.0170, 9.1 (all
  turns BaseTen); GLM 5.3 Flash 2 / 5 / 5, 11, $0.0075, 19.2 (a 24.0, b 24.1, c 9.5); Sonnet 5.5
  reference 5 / 5 / 5, 1, $0.5238, 8.5.
- Decision unchanged: DeepSeek V4 Flash 0731 is the only model at 4 of 5 or better on every
  question. It is closer to the bar than last round (5 / 5 / 5 then).
- Failure reasons: Gemma's step caps are glued JSON arguments (two run_scenario objects in one
  call, 6-10 schema-invalid calls per capped run), the same as before. DeepSeek a: unclaimed
  counts 15 and 2; DeepSeek b: `diff_n_selected` claimed as -2.0 (a float) while the stored count
  is the int -2. Counts are compared exactly, type included (unchanged rule). GLM a: unclaimed 15
  and 2. Gemini: unclaimed 14 and 27, a reversed diff sign, 2 step caps, and one claim citing the
  made-up run id 20220408T084943-70e93c2c (refused by the new #9 rule; the old checker would also
  have failed it as "run not found"). The new one-submit-per-turn rule never fired.
- Live demo on 78ba102 (`--profile demo`, every turn BaseTen): (a) 4 turns, 0 refusals, 19/19
  claims, 24/24 numbers; (b) 4 turns, 1 refusal (relief claimed truncated to 1 decimal), 17/17,
  13/13; (c) 3 turns, 1 refusal (297.57 and 311.44 unclaimed), 2/2, 2/2. Transcripts
  20261114T210145-c04c55d4, 20261114T210154-e11f5b1d, 20261114T210201-5276b834. Hand check: (c)
  says the budget must be at least 697.01 "for this scenario to be feasible". That overstates a
  lower bound, and the checker cannot see wording.
- v0.3 already existed on 06c4d5e (tagged before the fixes). Owner chose to leave it and tag
  v0.3.1 (annotated) on 78ba102, the demo-checked commit.
- README comparison replaced with this round's figures only.
- Not specified by the owner: the demo ran while the round was in progress (separate profile name,
  real data/inputs); the round ran as one process this time.

## 2026-11-14 — README additions; open items for the M4 fix pass
- Owner asked for: the checkpoint version (tag v0.3.1), two limitations, the earlier round's counts
  (4a6572b: DeepSeek 15, GLM 15, Gemini 10, Gemma 10 of 15) with "suggestive at five runs per
  cell", and the planned milestones (M2B diagnostics, M4 evaluations, M5 revision analysis, M6 MCP)
  marked as not done.
- Open for the M4 fix pass: (1) candidate ids in the summary are not checked against the runs;
  (2) a count claimed as a whole-valued float (2.0) is rejected (`values_match` requires the same
  type as the stored int; confirmed on the current tree).
- Not specified by the owner: the SPEC profile table still listed the Sonnet placeholder as `demo`;
  corrected to the approved DeepSeek pin.

## 2026-11-14 — README restructure
- Owner asked for a new top section (description, status, Why, Mermaid architecture, live demo
  excerpt of question c, How it was built, quick start), a headline above the model table, and the
  order Layout, M1, M2A, M3, comparison, What is next. Existing content moved, not rewritten; the
  limitations block is unchanged (checked by diff). The original intro paragraph moved to M1.
- Live demo on 78ba102 confirmed from the earlier DEVLOG entry and transcript times (21:01 UTC, after
  the 78ba102 commit); no code change between 78ba102 and HEAD. Not rerun. Transcripts and run
  records do not store a commit SHA, which is a provenance gap.
- Not specified by the owner: M3 and the comparison became level-2/3 headings; the diagram adds
  two edges that the code has (gate rejections also write a run record; the checker refuses back
  to the agent once); "Working rule:" phrasing for spec-first/tests-first; "about 30x" is the
  latest round (Sonnet $0.5238 vs DeepSeek $0.0170, 30.8x; the earlier round was 39x).

## 2026-11-14 — Compact `ask` output (presentation only)
- Owner asked for: a compact default renderer for `happy-toad ask` in cli.py only, the old output
  behind `--verbose`, a renderer test on a saved transcript, and no change to checker.py,
  report.py, tools.py, prompt.py or loop.py (frozen-file hashes unchanged; confirmed by git diff).
- Compact output: one line per tool call (name, key arguments, outcome, no JSON); a panel with the
  summary and a CHECKED / NOT CHECKED badge; "N claims, M numbers matched, K mismatches", with
  mismatches listed only when K > 0; a "First report refused, then corrected" line naming what was
  unmatched; a dim footer (model, provider, turns, cost, seconds). Exit codes unchanged.
- Test fixture: tests/fixtures/transcript_demo_c.json, a copy of live transcript
  20261114T210201-5276b834 (demo question c, 78ba102); it has no account id.
- Not specified by the owner: argument shown per tool (run_scenario: version, budget and every
  other set field except label; submit_report: claim count; others: argument values); run
  outcome shows status, spend and weighted relief to 2 decimals, or the rejection codes, plus the
  minimum budget and run id; compare_runs shows the spend and weighted-relief differences;
  K counts every checker error line (bad claims, missing minimum budgets, unmatched numbers);
  a schema-refused first report gets "did not fit the report schema"; runs without a report
  print "Status: <status>"; all compact lines pass through `redact`; long lines soft-wrap. The
  existing CLI tests now pass `--verbose`. Demo output shown from the three saved transcripts,
  not rerun live.

## 2026-11-15 — README honesty fixes, compact demo excerpt, Run it notes; tag v0.3.2
- Owner asked for: the "Why" sentence (a checker compares each summary number to the stored runs;
  an answer it cannot verify is shown as not checked); the headline softened to "suggestive, not
  conclusive"; cost as "roughly 30 to 40 times cheaper" with the two-round wording fixed; the M1
  sweep comment; the 1900-2199 year-skip limitation; the demo excerpt as compact output for
  question c; Run it with a clone step, uv and Python 3.12+, `.env` not read by the CLI, and the
  paid default with `--profile smoke` free; a made-up `region_total_sectors` in the README
  example; tag v0.3.2 and the status line.
- Year skip confirmed on the current checker: `find_numbers` drops "2000" and "2027" but keeps
  "2000.00", "1899" and "2200".
- Grep for 1500 in src, tests, scripts and docs: every hit is a budget (demo question a, SPEC
  expected values, two tests); the README example was the only region count. Now 12345.
- Correction to the earlier README report: the M1 sweep comment's range was right (defaults are
  must-fund plus 5% to 100% of candidate cost); it only omitted "plus must-fund", now added.
- Not specified by the owner: "cheaper" is attached to DeepSeek versus Sonnet (Sonnet is the
  expensive one), with both ratios given (30.8x, 39x); M3 now says a failing report is shown as
  NOT CHECKED (status `unverified` in the transcript and `--verbose`) to match the new Why; the
  checkpoint line names v0.3.2 and says the live demo ran on v0.3.1; the clone URL is the current
  repo and must change if the repo moves; not pushed (owner will push to a new repo).

## 2026-11-15 — Compact output: check-line wording, NO NUMBERS TO CHECK badge; v0.3.2 moved
- Owner asked for: the check line as "N claims, M numbers matched against stored runs, K
  mismatches"; a neutral NO NUMBERS TO CHECK badge with "This answer contains no figures" for an
  accepted report with zero claims and zero summary numbers (CHECKED only with at least one
  verified claim or number); tests; SPEC and DEVLOG entries; the unpushed local tag v0.3.2 moved
  to the new commit. checker.py, report.py, tools.py, prompt.py and loop.py unchanged.
- Tests: two new renderer tests (no figures; one verified claim keeps CHECKED); the existing
  compact CLI test (a clarifying question with no claims) now expects NO NUMBERS TO CHECK.
  370 pass (368 + 2).
- Not specified by the owner: the neutral badge is bold reverse with no colour; the no-figures
  line replaces the count line (the correction line still shows when the first report was
  refused); the badge decision reads only the last check (claims and numbers both empty) and the
  status; "1 claims" is kept as the owner's "N claims" pattern; the README demo excerpt's check
  line updated to the new wording (diffed against the renderer output).

## 2026-11-15 — Review fixes: one verdict for both outputs and the exit code
- From an automated review of the previous commit, owner chose: (1) work out the verdict once
  (`verdict(t)` in cli.py) and use it for the compact badge, a `Verdict: <label>` line in
  `--verbose`, and the exit code; NO NUMBERS TO CHECK gets its own exit code, 3 (unused before:
  0 checked, 1 not checked or no report, 2 bad option or missing key); (2) the no-figures line
  reworded to "No checkable figures in this answer", because the checker's number list skips
  whole numbers 1900-2199, list markers and run ids, so "contains no figures" could be false.
- Exit-code dependence checked: nothing in scripts/ or on the web-replay branch reads the CLI
  exit code (bakeoff and the web server call the loop directly). Two CLI tests relied on exit 0
  for a no-figures answer; one now expects 3 (compact), and the verbose one was split into a
  real CHECKED case (a created run, get_run, a status claim; exit 0) and a no-figures case
  (exit 3, same label). 372 pass.
- Not specified by the owner: `exit_code(t)` and `verdict(t)` are public for the tests; verbose
  prints the label as "Verdict: <label>" after the check lines and keeps the UNVERIFIED line;
  statuses without a report (step cap, API error, error) have no verdict and exit 1 as before.
- Open, not changed (other session's branch): web-replay `web/view.py:79` still labels a
  no-figures answer CHECKED; to settle when the branch is merged. Bake-off counts use transcript
  status, so a no-figures answer to a demo question would count as checked there.

## 2026-11-15 — web-replay branch: replay page, local live page (not merged)
- Built in web/ and scripts/ only, on branch web-replay, rebased on main (cd21748). One view
  dict (`web.view.build_view`, schema v2) feeds a self-contained replay (`web/replay.html`, two
  v0.3.1 demo runs: 800 vs 1500, and the forced-in request rejected at 600) and a local live page
  (`web/server.py`, 127.0.0.1 only, key kept server-side, 500-character cap, one request at a
  time, steps streamed through the loop's `on_event` hook). Frozen agent files unchanged.
- Owner asked: CLI verdicts and wording (CHECKED, NOT CHECKED, NO NUMBERS TO CHECK, "matched
  against stored runs"); NOT CHECKED greyed out under a warning banner; "1 mismatch"; unmatched
  numbers before the count line; wording copied into `web/format.py` so the view no longer
  imports cli.py (a test compares it with the CLI); refusals logged as JSON lines in the
  gitignored `web/refusals.log` (time, reason, question length, no text); a closed page ends the
  stream quietly and the transcript is still saved. Approved exceptions: this entry, and
  `web/tests` in `testpaths`. 393 pass.
- Not specified by the owner: the CLI keeps "1 mismatches" (only the web says "1 mismatch");
  a run with no report shows "No answer. Status: ..." (the CLI's status line) and no badge;
  a refused oversized body (over 4000 bytes, not read) logs question_length null; a body that
  is not JSON is refused and logged as "bad_request"; after a disconnect the answer runs to the
  end (10-step cap) holding the one-request lock, so the transcript is complete; the server
  replies before writing the refusal log and creates its folder; light theme only; Inter only
  if installed locally (no external requests).

## 2026-11-15 — web-replay merged into main; "1 mismatch" in the CLI; v0.3.2 moved
- Owner asked: fast-forward main to web-replay (bb7cab7); the CLI now says "1 mismatch" too, so
  the web wording test no longer has an exception (it asserts the two lines are equal for one
  mismatch); one README line pointing to `web/replay.html` and the local live page; tag v0.3.2
  moved to this commit; worktree `../happy_toad_web` removed, branch `web-replay` kept. Not
  pushed. 394 pass; frozen agent files unchanged.
- Not specified by the owner: a CLI test for the singular (`test_one_mismatch_is_singular`);
  SPEC M3 decision 10 notes "1 mismatch"; the README line sits under the demo excerpt.
- Follow-up (owner corrected the request): "1 problem" singular for a refused report, in the CLI
  and in `web/format.py`, with a test on each side (`test_one_refusal_problem_is_singular`,
  `test_one_problem_is_singular`, plus a one-error case in the web/CLI comparison list).
- Stored-runs table: measured at 1280 px it needed 1023 px in an 802 px box. It already had
  `overflow-x: auto`, but macOS hides scrollbars until you scroll, so the right columns looked
  cut off. Fix in `web/page.html`: header cells wrap, table font 12 px, cell padding 8 px. It
  now fits exactly (802/802) at 1280 and 900 px; at 400 px it scrolls inside its box and the
  page itself does not overflow. `web/replay.html` re-exported from the same two transcripts
  (only the CSS changed). 396 pass.
- Not specified by the owner: fitting by wrapping headers and a smaller font rather than a
  visible scrollbar.

## 2026-11-15 — Third replay example: a real run that failed the check
- Owner asked: add the web session's failed-check transcript (20261115T144300-0c18a8bc) to the
  replay, or, if gone, a real unverified run of question (a), preferring the demo model. It was
  gone: `git worktree remove` deleted the worktree's gitignored transcripts/ and runs/; not
  found by name anywhere on the volume, in Spotlight or in the Trash.
- Chosen instead: 20261114T210844-a403d428 (DeepSeek V4 Flash 0731 on Baseten, the demo model,
  same round as the other two replay runs). Its claims all matched; the summary numbers 15 and
  2 did not match any stored figure, so it is NOT CHECKED after two refused reports.
- Changed from the owner's wording: the owner's label said the number was one "no stored run
  supports". That is not true of this run: 15 and 2 are the candidates added and dropped
  between the two stored runs (14 - 2 + 15 = 27), correct but not a figure the checker can
  match. The other two demo-model unverified runs of (a) fail the same way. The label used is
  "Real run that failed the check: the model put numbers in its summary that the checker could
  not match to a stored figure (DeepSeek V4 Flash 0731)".
- Not specified by the owner: `scripts/export_replay.py --label N=TEXT` (tested in
  `web/tests/test_export.py`); README's web line now says three runs; web/README fixed (web
  tests are in the default run, schema_version 2, paths relative to the repo).

## 2026-11-15 — Guide for planners; change list no longer offered as a version
- Owner asked: `docs/GUIDE.md`, one page for planners who do not program (what it does, the
  data with definitions and counts, one example question per tool option, the steps from
  question to human decision, what it does not do, how to try it, with Download ZIP for the
  replay), linked from the top of README.md and from the replay page. Owner edits: definitions
  of sector, shortfall, trigger year, resolved and weighted relief; fair share as a share of
  the budget left after must-fund; "so the plan doesn't spend money that adds no relief";
  "Checked live with one model"; "(revision analysis is planned)".
- Found while writing the guide: `list_input_versions` offered `changes_v1_to_v2` as a version
  (the lister returned every `*.json` stem) and a run on it ended as an error ("malformed").
  Fix, owner approved: `data/files.is_change_list` (prefix `changes_`, the name the generator
  writes); the lister skips change lists and `load_version` treats one as no such version, so
  the gate rejects it with VERSION_NOT_FOUND. Two tests; SPEC M3 decision 2 updated. Frozen
  agent files unchanged; generator output byte-identical. 400 pass.
- Not specified by the owner: the guide's counts come from the seed-42 files (checked
  byte-identical with `generate --seed 42`); the replay link is shown in replay mode only (the
  live server does not serve docs/), and from a local copy it opens the Markdown as plain text;
  "Checked live with one model" keeps the five-model round with its caveat; `load_version`
  also refuses change lists (the owner asked only for the list); example budgets and the
  region size of 200 in the guide are made up.

## 2026-11-15 — "How an answer is made" panel on the web page
- Owner asked: show the process flowchart on the page so a new user understands it; option 1
  of 3 chosen (a static map with captions; per-run path highlight and live pulse deferred).
- `web/page.html`: a panel that opens and closes, above the controls in both replay and live
  mode, with eight numbered stops (Question, Agent, Gate, Optimizer, Run record, Report,
  Checker, You), each with a one-line caption taken from `docs/GUIDE.md` section 4. A row on
  desktop, a vertical line below 760px. `web/replay.html` rebuilt from `web/replay.json`. 400 pass.
- Not specified by the owner: HTML/CSS instead of Mermaid (Mermaid needs a script from a CDN,
  and the replay makes no external requests); the two branches (rejected at the gate, sent back
  once by the checker) are red notes under their stops, not drawn arrows; the last stop is
  "You" instead of "Summary to a human"; the panel starts open.

## 2026-11-15 — The flow panel follows the run (option 2)
- Owner asked: a gray-box highlight that moves through the stages, and in the replay the run
  should play when its button is clicked ("play when you hit ask").
- `web/page.html`: while a run is in progress, stages not yet reached are faded, passed stages
  are black, and the current stage sits in a gray box. Each tool call moves it: `run_scenario`
  rejected → Gate, Run record and the red "Rejected" note; any other `run_scenario` (not an
  error) → Gate, Optimizer, Run record; `submit_report` → Report, Checker, and the red
  "Mismatch" note when refused; other tools → Agent. The final view moves it to You. Live mode
  follows the streamed steps; replay buttons play the stored steps 0.9 s apart, with the
  trace filling in, then show the answer. No server or schema change. 400 pass.
- Not specified by the owner: on page load the replay shows the first run's final path without
  playing; clicking another button mid-play cancels the current one; reduced-motion users get
  no delay; the step interval (0.9 s); a `run_scenario` error counts as Agent only. No JS tests
  (the project has no JS test setup); checked with headless Chrome screenshots and DOM dumps.

## 2026-11-15 — Flaky refusal-log test; summary markdown on the page
- Owner asked: investigate the one-time failure of `test_refusals_are_logged_without_the_question`
  (hypothesis: the server replies before writing the log). 50 plain runs: 0 failures. With a
  50 ms delay put into `log_refusal` from a scratch plugin, it failed on order (`empty` logged
  before `too_long`): each request has its own thread and the reply comes first, so the next
  request could log first. `_settle` already covered a missing line. The test now polls for each
  line (2 s limit) before the next request; passes with the delay and 50/50 plain. Server order
  unchanged, as asked.
- Owner asked: render bold and bullet lists in the model summary, after escaping HTML.
  `web/markdown.py` escapes everything, then renders `**bold**` and `-`/`*` lists; the view
  carries `summary_html` and the page inserts it. Tests with `<script>` in a summary (renderer
  and `build_view`). Replay re-exported. Checked in headless Chrome.
- Not specified by the owner: rendering in Python (testable with pytest; the page has no JS tests)
  rather than in the page; `schema_version` 2 → 3 for the new field; single newlines become line
  breaks and blank lines new paragraphs (the old summary used `pre-wrap`); headings, italics and
  code stay literal.

## 2026-11-15 — v1 "plan of record", v2 "refreshed forecast"
- Owner asked: describe v1 as the plan of record (the data the plan was built on) and v2 as the
  refreshed forecast (a mid-year update with re-estimated costs, moved trigger years and new
  sectors) in the guide and the data descriptions; version ids unchanged.
- Changed: `docs/GUIDE.md` (table header and section 2 paragraph), `docs/SPEC.md` (generator
  section), docstrings of `data/generator.py` and `data/evolve.py`, the `generate` command help.
- Not specified by the owner: which places count as "data descriptions" (the input JSON files
  have no description field, and adding one would change their content hash, so they are
  untouched); the evolve docstring also names the changed offloads, which v2 has.

## 2026-11-15 — Glossary in the guide; definitions as claim-card tooltips
- Owner asked: a plain-English glossary at the end of `docs/GUIDE.md` (every report metric with
  the `diff_` direction, run outcomes, solver statuses, gate codes, infeasible causes, the three
  labels, the data terms, run id, transcript, claim); a test that fails when a metric or code in
  the code has no entry; if quick, definitions as hover tooltips on the claim cards.
- `docs/GUIDE.md` section 7. `web/glossary.py` reads the backtick entries from it;
  `render_page` adds them to the boot data and each claim card gets a `title` (dotted
  underline on the metric name). `web/tests/test_glossary.py` compares `Metric` and
  `ReasonCode` with the entries (checked to fail by name when an entry is removed). Replay
  re-exported.
- Not specified by the owner: each `diff_` metric has its own entry as well as the prefix entry
  (so each card has a tooltip); the guide is the single source (no copy in code), so the page
  reads it at render time; the test sits in `web/tests` to share the parser; tooltips use the
  native `title` attribute (no tap equivalent on phones).
- Owner review of the glossary: CHECKED now says words, candidate ids and year-like numbers
  are not checked; Optimal is "proved no better plan exists under the modeled objective and
  constraints"; Floor says floors above 1x fair share cannot all be met (the shares add up to
  the whole available budget). Asked to check region size: `pct_resolved` is always out of the
  version's sectors; `pct_of_region` is stored separately, is not a report metric and is not an
  allowed number, so a summary stating it fails the check (shown on a scratch run: v1, 800,
  region 200, "10.5%" unmatched). Recorded under `pct_resolved`. This conflicts with the guide's
  section 3 example "give the percent resolved out of 200 sectors"; raised with the owner, not
  changed.

## 2026-11-15 — Refactor before M2B (S1, S2, S3, S7, S11 from CODE_REVIEW.md)
- Owner asked: S1, S2, S3, S7 and S11, no behaviour change, one commit each, CI green after
  each; time box 3 hours. Skipped: S5, S6, S9, S12, S14. Moved: S8 and S10 to the start of M4,
  S4 and S13 to M5.
- **The bake-off file freeze is lifted.** S2 and S3 edit `agent/tools.py` and
  `agent/checker.py`, two of the `FROZEN_FILES` in `bakeoff.provenance()`, so their hashes
  change. Bake-off rounds before and after this work are not comparable by hash; a future
  comparison round records the new file hashes.
- Baseline before any change: the five engine requests behind demo questions a, b and c on v1
  (800; 1500; 1000; 1000 forcing C033, C024; 600 forcing C033, C034, C024), saved to compare
  after the last refactor.
- S1: `markets.market_spend(data, ids=None)` replaces `markets.market_costs` and
  `diagnose._market_spend` (same summation order). 409 pass, tests unchanged.
- S2: run records start from one `_base_fields` helper in `services/run.py`;
  `record_invalid_request(raw, message, runs_dir)` replaces `tools.record_schema_invalid` and
  keeps its sha256 of the sorted-key raw JSON (not `request_hash`), so stored hashes do not
  change. Edits `agent/tools.py` (frozen list). 409 pass, tests unchanged.
- S3: `InputSet.must_fund_total` and `InputSet.candidate_total` properties replace the 7
  must-fund and 4 candidate-cost sums (cli, model, diagnose, gate, checker, both scripts);
  properties are not dumped, so content hashes are unchanged (checked). `diagnose.forced_cost`
  replaces its two forced-in sums. The checker's forced-cost lookup (request order) is left as
  is, so its float sum cannot shift. `scripts/fair_share_table` output identical before/after.
  Edits `agent/checker.py` (frozen list). 409 pass, tests unchanged.
- S7: `engine/model.py`: `make_result` typed, with `cause` and `minimum` keyword-only; the
  meta/settings dict moved to `_run_meta(...)`; `solve` 96 → 80 lines. Not split further (the
  review asked only for this). 409 pass, tests unchanged.
- S11: `happy_toad/report.py` (the Rich tables for the CLI) renamed to `happy_toad/tables.py`;
  only `cli.py` imported it. `agent/report.py` and the `FROZEN_FILES` entry "report.py" (which
  means the agent's) are untouched. 409 pass, tests unchanged; `sweep` output checked.
- Verified after S11: no test file changed since before S1 (`git diff 52bb8e0..HEAD -- tests
  web/tests` is empty), 409 pass, and the engine results for the five demo requests (outcome,
  status, spend, weighted relief, resolved, percent, selected ids, minimum budget) are
  byte-identical to the baseline. Time used: about 15 minutes of the 3-hour box.

## 2026-11-15 — Region percent example replaced; failed-check image in the README
- Owner asked: replace the guide's "percent resolved out of 200 sectors" example with one that
  passes the checker; list the region percent as reported but not yet checkable (planned for
  M4); add it to the M4 fix list; move `docs/NotChecked.png` to `docs/images/not_checked.png` and
  show it in the README limitations as "what a failed check looks like".
- **Added to the open items for the M4 fix pass:** (3) the region percent (`pct_of_region`) is
  stored in the run but is not a report metric or an allowed number, so a summary that states
  it fails the check.
- Guide example is now "what percent of all sectors does the plan resolve?" (`pct_resolved`,
  checkable). Limitation added to guide section 5.
- Not specified by the owner: the README's existing "logged for the M4 fix pass" sentence also
  lists the region percent; the image sits under the M3 checker limitations with a one-line
  caption of what failed (the unclaimed "15"). The screenshot shows "refused (1 problems)", from
  before the singular fix.

## 2026-11-15 — M2B design: resolved count is not monotonic in budget
- Owner asked: which reading of "smallest budget that meets a target", whether resolved count is
  monotonic in budget on v1, and a proposed method. The SPEC had no M2B section (only "M2B:
  diagnostics, for example the smallest budget that meets a target").
- **Finding: resolved count is not monotonic in budget.** v1 seed 42, normal optimizer, budgets
  311.44 (must-fund) to 5138.73 (the gate's cap) in steps of 1, 4828 solves, all Optimal: **148
  budgets where one more unit resolves fewer sectors**, for example **981.44 → 982.44: 30 → 26**
  (also 434.44 → 435.44: 8 → 5); 1356 budgets resolve fewer than some smaller budget; the last
  drop is at 3019.44, and from 3061.44 on it is always 76 (the maximum). Weighted relief never
  decreases. Cause: the optimizer maximizes weighted relief and partial relief counts, so extra
  money can go to partial relief in urgent sectors instead of finishing a sector.
- A scratch minimum-cost model (not committed) gave the cheapest-plan budget per target; it is
  20-209 cost units below the budget at which the optimizer first reaches the same target (for
  50%: 1145.21 against about 1329.44), and at the cheapest-plan budget the optimizer resolves
  fewer sectors (33 instead of 40).
- **Owner decisions:** build only the cheapest-plan target-budget search, with the proposed
  answer wording plus "a higher budget does not guarantee more resolved sectors"; no
  optimizer-plan scan; no extra diagnostics. SPEC M2B section written for approval.
- **Moved to M7:** the optimizer-plan scan (smallest budget at which the normal optimizer's plan
  reaches a target); the whole-candidate floor cause (floors no combination of whole candidates
  can meet, now `CAUSE_UNKNOWN`); the per-sector cheapest fix in the unresolved report; the CLI
  table of target → cheapest budget.
- Not specified by the owner (in the SPEC draft, marked or listed): the proposed answer ended by
  offering the optimizer-plan scan, which is now out of scope, so it offers to run the optimizer
  at budgets the user names instead; `TimeLimit` gives no `target_budget`; the stage-2 tie-break
  (most weighted relief at the minimum cost); `compare_runs` accepts a search record; a
  `happy-toad target-budget` CLI command and the trace wording (both marked [lead]).

## 2026-11-15 — M2B SPEC approved with changes
- Owner approved the M2B section with three changes: (1) `target_budget` is stored rounded up to
  the cent, the follow-up run uses that same value, and a test checks that the cheapest plan's
  cost fits within it minus must-fund; (2) new claimable metrics `target_sectors` (exact) and
  `max_pct_resolvable` (percent tolerance), with glossary entries, and rule 12 states the target
  as "at least k of N sectors"; (3) the sweep's reference values for the v1-scale test are a
  committed fixture with a note on how they were produced.
- Owner answers: the answer wording is approved; keep the trace wording and the
  `happy-toad target-budget` command; the six unspecified behaviours are fine; CLAUDE.md now says
  current milestone M2B; the milestone tag will be v0.4.
- Not specified by the owner: rounding is `ceil(round(x * 100, 6)) / 100` (the inner round removes
  float noise); `max_resolvable` and `max_pct_resolvable` are set on every search record, not only
  unreachable ones.

## 2026-11-15 — M2B target-budget search: tests first, then code
- **Tests were written first and confirmed failing for the right reason before any code:** the
  three new test files stopped at collection with `No module named 'happy_toad.engine.target'`;
  `test_target_budget_wording` got the generic wording `"v1 50 ['C033']"`; the tool-list test
  lacked `find_target_budget`; everything else in the touched files passed. The fixture
  `tests/fixtures/v1_first_budget_per_target.json` comes from the step-1 sweep (its note says
  how; same content hash as `make_v1(seed=42)`).
- Code: `engine/target.py` (two-stage cheapest-plan model, `target_sectors`, `round_up_cent`,
  `max_resolvable`), `services/target.py` (request with the multiplier and budget messages,
  hash with the kind, gate, search record, follow-up run), `TARGET_UNREACHABLE`, record fields
  `kind`, `follow_up_run_id` and four result fields, four claimable metrics in the report and
  checker, the `find_target_budget` tool, follow-up tracking in the loop, rule 12, trace wording
  in the CLI and the web page, the `happy-toad target-budget` command, glossary, guide and README.
- Owner set the CLI exit codes after the tests were written (0 found or unreachable, 1 rejected,
  2 invalid request, 3 time limit), now in the SPEC. **Their four tests were written after the
  code**, so they were not seen failing first.
- Checks before commit: 457 pass, ruff clean, and the engine results of the five demo requests
  are byte-identical to the baseline taken before the refactor (so before M2B as well).
- Not specified by the owner: module and function names; the tool sits after `run_scenario`;
  scenario run views hide the four search fields (what the model sees of a scenario run does not
  change); the search record is written once and rewritten with `follow_up_run_id` after the
  follow-up run; a stage-1 optimum with no time left for stage 2 is `TimeLimit` with no budget;
  the web runs table gets a `target_budget` column for search runs; the CLI prints the cheapest
  plan's size, spend and resolved count as well; the guide's "no reverse budget search" limitation
  is replaced by the cheapest-plan caveat, and the guide gains a "budget for a target" example.
- Fix after commit (automated security review, then reproduced): with no must-fund and target 0
  the target budget is 0.00, the follow-up run is rejected (`BUDGET_NOT_POSITIVE`), and both the
  CLI and the trace formatter crashed on its missing result (`AttributeError`, `TypeError`).
  Tests first (seen failing with those errors), then the CLI and both formatters show the
  follow-up's own outcome ("optimizer at 0.00: rejected BUDGET_NOT_POSITIVE"). Not specified by
  the owner: `follow_up_run_id` is still recorded for a rejected follow-up (the run exists and
  can be cited) rather than dropped as the review suggested. Cannot happen on v1 (must-fund
  311.44).

## 2026-11-15 — M2B live check; flow panel for find_target_budget; M4 fix list; v0.4
- Live check, "On v1, what total budget reaches 50% of sectors resolved?" (demo model): the CLI
  (`happy-toad ask`) and the local web page both ended **CHECKED** (9 claims, 11 numbers, 0
  mismatches): target budget 1145.21 for at least 40 of 80 sectors; the optimizer at that budget
  resolves 33; maximum resolvable 76 of 80.
- Owner asked: the "How an answer is made" panel now lights Gate, Optimizer and Run record for
  `find_target_budget` (found or stopped on time: all three; unreachable: Gate and Run record;
  rejected: Gate, Run record and the red "Rejected" note). No automated test: the logic is
  browser JavaScript and the project has no JS test setup (adding one is outside the approved
  dependencies). Checked in a headless browser on a scratch replay of the live web transcript:
  before, gate/optimizer/record were not marked passed; after, they are. Replay re-exported.
- **Added to the open items for the M4 fix pass:** (4) rule 12 wording is not always followed:
  on the web run the model attached "a higher budget does not guarantee more resolved sectors"
  to a sentence it does not follow from ("spending 833.67 — showing that ...") and dropped the
  offer to run other budgets (the checker verifies numbers, not wording); (5) the CLI run wrote
  a percentage with two decimals ("41.25%") where rule 7 asks for one; the checker accepts it
  within tolerance.
- README status ("M1 to M3 and M2B complete (tag v0.4)") and the guide's section 3 example
  ("Budget for a target") were already in the M2B commit (710a353).

## 2026-11-15 — M4 design approved with changes; SPEC section drafted
- Owner approved the M4 proposal with changes: required phrases stay automatic, forbidden wording
  is only flagged for manual review; extra `run_scenario` calls are allowed unless a case forbids
  them; case 18 (units mistake, BUDGET_ABOVE_CAP) and case 19 (pressure to confirm a wrong spend)
  added; the candidate-id check joins checker group 1, last; grader and runner in
  `src/happy_toad/evals/`, `truth.py` and `truth.json` in a top-level `evals/` with an import-ban
  test; the SPEC states that independent truth catches coding bugs, not SPEC errors, and that with
  95 conversations a round differences under about 10 points are noise; official rounds need a
  clean working tree; 5 runs per case; fix order as proposed. CLAUDE.md set to M4.
- Found while writing case 19: the checker marks any summary number that is not a claim or a
  request value as unmatched, so "the spend is not 400 but 485.59" is NOT CHECKED exactly like
  "the spend is 400". Case 19 therefore fails only on a claimed 400 or on CHECKED with 400 in the
  summary, and otherwise flags 400 for manual review; recorded as a known limitation.
- Not specified by the owner (in the SPEC draft): case texts for the new rewording and off-script
  cases; allowed labels per case (two for 8, 9, 14, 17, 18, 19); which numbers each case must
  claim; `prompt_sha256` covers the tool definitions as well as the system prompt; error bodies cut
  at 500 characters; `report_accepted` as an explicit transcript field; the runner command and its
  `--unofficial` flag; round reports in `evals/rounds/`; fix letters a-j (the default version is
  j); tag v0.5 when done.

## 2026-11-15 — M4 part A: provenance, source, run-to-transcript link, accepted flag, redaction
- Tests first (`tests/test_provenance.py`, one web-server test): seen failing at collection with
  `No module named 'happy_toad.agent.provenance'` and on the missing `Transcript.source`.
- `agent/provenance.py`: `git_sha`, `git_dirty`, `prompt_sha256` (system prompt plus sorted-key
  JSON of the tool definitions); every transcript stores it with `source` (cli, web, eval,
  bakeoff) and `report_accepted`. Run records store `transcript_id` when an agent tool call made
  them (scenario, search, follow-up and schema-invalid records). `agent/redaction.py` holds the key
  and account-id patterns (moved from `web/redact.py` and `client.py`) and `redact_error`
  (redact, then cut to 500 characters), used for provider error bodies and unexpected-error text.
  S8 (`_error_row` with keywords, plain `if`, the git lambda replaced by the shared module) and S10
  (`Transcript.providers` in the CLI, bake-off, web view and script; the script reuses
  `TEXT_METRICS`). Stored transcripts and run records still load (tested).
- Changed existing tests: the bake-off provenance test now expects the new prompt hash (prompt
  plus tools); the provider-error test is renamed (the body is now cut at 500 characters).
- **Bake-off prompt hashes before and after this change are not comparable**: the hash now covers
  the tool definitions too. 475 pass, ruff clean.
- Not specified by the owner: `report_accepted` and `source` are `None` on transcripts saved before
  M4 (unknown) rather than guessed from `status`; `ask()` takes `source` as an optional argument
  (`None` in tests); the string-claims script now prints "unknown" instead of "?" for a turn with
  no provider.
- Fix after commit (automated security review, then reproduced): `provenance()` ran git before
  `ask()`'s save guard, so without git (`FileNotFoundError`) or outside a checkout
  (`CalledProcessError`) `ask()` raised and saved no transcript. Tests first (seen failing with
  those errors); now commit and dirty flag are `None` (unknown) and the transcript is saved.
  Declined: the review's suggestion to add `redaction.py`, `provenance.py` and `client.py` to the
  bake-off `FROZEN_FILES`; that list is for what the model sees and how it is checked, which
  these modules do not change.

## 2026-11-15 — M4 part B: cases, independent truth, cross-check
- Tests first (`tests/test_evals_truth.py`): seen failing at collection with `No module named
  'happy_toad.evals'`. Then `src/happy_toad/evals/cases.py` and `cases.json` (19 cases),
  `evals/truth.py` (own PuLP models and plain-Python metrics from the SPEC; reads JSON as data;
  the import-ban test passes), and `evals/truth.json` (note, input content hashes, commit).
- **Cross-check, shown to the owner before commit: no disagreement.** 20 runs and 1 follow-up
  (107 values, 20 differences, 14 selections) as shown; after case 11 moved to 1500, 21 runs and
  1 follow-up (113 values, 25 differences, 16 selections); outcome and reason codes of every run; the engine
  side read with the checker's `stored_value` and `difference`; an engine value missing from
  truth also counts. Shown to catch a planted 0.01 spend change and a dropped selected id. Every
  engine value in the SPEC table (485.59, 1284.34, 697.01, 1145.21, 76, ...) is reproduced.
- Owner changes after the cross-check: case 11 used 1000, where the unforced plan already
  contains the 800 plan (forcing changed nothing, so the numbers could not catch a missing
  force list); it now uses 1500, where the unforced plan drops C006 and C044, and its truth holds
  the unforced 1500 run and forced minus unforced (keeping them costs 11.51 weighted relief, at
  0.06 less spend and the same 45 resolved). SPEC: truth and the engine share PuLP with CBC, so
  a solver bug would make both agree.
- Not specified by the owner: `extra_pairs` in the case format for truth-only differences;
  `truth.py` treats a gap-limit stop with gaps 0 as optimal (as the SPEC says for the engine);
  truth does not re-derive infeasibility causes (case 14 grades the word "unknown"); the
  cross-check compares floats within 1e-6.

## 2026-11-16 — M4 part C: grader, runner, `happy-toad eval`
- Tests first (`tests/test_evals_grade.py`, 19 tests): seen failing at collection with `cannot
  import name 'runner' from 'happy_toad.evals'`.
- `evals/grade.py`: right runs (required calls with matching arguments, extra calls allowed,
  forbidden tools fail), right numbers (key numbers claimed on a run whose request matches the
  case's spec, every claim on such a run compared with truth.json at the checker's tolerances),
  right behaviour (label in the allowed set, required phrases; review phrases only listed);
  case 19's pushed value from a `pressure` field in the case. `evals/runner.py`: rounds (source
  "eval"), rates, manual-review list, noise statement, JSON and Markdown reports; refuses inputs
  whose content hash differs from truth.json and official rounds on a dirty tree or without git.
  `happy-toad eval --round NAME [--cases] [--repeats 5] [--unofficial]`; unofficial reports are
  gitignored (`*.unofficial.*`).
- Live smoke before commit (unofficial, cases 5 and 9 once): both passed, $0.0019.
- Not specified by the owner: key numbers are excused only when the label is NOT CHECKED and the
  case allows it (case 19); a claim on an extra run that matches no case run is ignored; the
  Markdown report lists failures with their problems; the eval command imports the runner inside
  the function (the grader uses the CLI's verdict); exit code 2 when a round is refused.

## 2026-11-16 — Baseline round; infrastructure rule; re-grade; fixes k and l added
- Baseline (official, commit 7414534, 95 conversations, $0.0942): pass 85%, checked 79%, first
  pass 65%. Failures read one by one: case 15 (5, the agent never passes `target_pct_resolved`),
  case 17 (5, "change list" not reachable from the tools), case 13 (an HTTP 429, and "50%"
  written for the 0.5 multiplier), case 18 (gate-message numbers 1.5 and 5,138.73 unclaimable),
  case 19 (one claimed spend 800).
- **Correction:** I told the owner one case 19 run ended CHECKED with "400" in its summary. Wrong:
  all three summaries that repeat 400 ended NOT CHECKED with 400 as the unmatched number; the two
  CHECKED runs contain no 400 (checked against the transcripts and the checker's last results).
  The checker never accepted 400; I had misread the case's 40% checked rate.
- Owner decisions: provider errors are tagged "infrastructure", excluded from every rate and
  counted separately, no retries; the baseline is re-graded from its transcripts (no new
  conversations) and committed with a note that case 17's required phrase was not reachable with
  the original gate message; fix (k) joins group 1 (numbers in request values and rejection
  messages of executed runs allowed; question-only numbers stay unallowed); fix (l) joins group 2
  (gate message for a change list). Tests first for the infrastructure rule and the re-grade
  (seen failing on the missing `Grade.infrastructure` and `regrade`).
- **Logged for later (not on the fix lists):** (1) reports that do not fit the schema on the first
  try: 7 first refusals in the baseline (null claim values, unknown metric names), in cases 12,
  14, 15 and 18; (2) case 13: the agent wrote the 0.5 floor multiplier as "50%", which the checker
  cannot match (0.5 is a request value, 50% is not).
- Not specified by the owner: infrastructure means transcript status `api_error` (provider
  refused); our own errors (`error`) still count as failures; the re-grade keeps the round's
  original header and adds `regraded` (date, provenance) and `notes`; the fix order puts (k)
  before the candidate-id check (e), which stays last.

## 2026-11-16 — M4 fix group 1 (checker): a, b, c, d, k, e
- Prediction before applying (e) as specified: in the baseline, all 5 case 9 declines name
  C033 and 1 case 8 answer names C099 while citing no run; under (e) those reports are refused,
  so case 9 (allowed NO NUMBERS TO CHECK or CHECKED) will likely fail because of the rule, not the
  agent. Applied as specified, to be measured in round 2.
- (a) Whole-valued counts: a count claimed as a whole float (2.0, -1.0) becomes the int in the
  claim schema; 21.5 stays a float and still fails. Tests first (4 seen failing on the type).
- (b) Added and dropped counts: `compare_runs` reports `n_only_in_a` / `n_only_in_b`; new pair
  metrics `n_added` (only in `run_id_b`) and `n_dropped` (only in `run_id`) need both run ids and
  are checked against the two selections (`checker.pair_value`); the compare_runs tool text names
  them; glossary entries; `evals/truth.py` computes them independently (truth.json regenerated;
  cross-check still clean; case 1: 15 added, 2 dropped). Tests first (4 seen failing).
- (c) Region percent: `pct_of_region` is a claimable metric (percent tolerance) read from the
  run; none for runs without a region size. Guide: the "not checkable yet" limitation removed,
  glossary entry added, `pct_resolved` points to it. Tests first (2 seen failing); the
  cross-check also requires truth to cover any region percent the engine reports.
- (d) Year skip: only the planning window (2027-2031, from BASE_YEAR and HORIZON_YEARS) is
  skipped as years; "a budget of 2000" is now a checked number. SPEC number rule 2 and the guide
  updated. Tests first (2 seen failing); the existing year tests use 2027-2031 and still pass.
- (k) Numbers from the conversation's runs: the request values and the numbers in rejection
  messages of every run in the conversation are allowed in the summary, cited or not; numbers
  only in the question stay unallowed (tested: "not 400" still fails). Tests first (3 seen
  failing; the question-only guard passed before and after). Not specified by the owner: "runs
  in the conversation" is the loop's existing list, which also holds runs the agent read
  (`get_run`) or compared, since their values were shown to it too; a request value that is not
  a number (a schema-invalid record's raw input) is skipped instead of raising.
- (e) Candidate ids: every candidate id (C plus three digits) in the summary must be in the
  selection or force lists of a run cited by a valid claim; otherwise the report is refused with
  "candidate C0xx in the summary is not in a cited run's selection or force lists". As specified,
  a claimless answer that names a candidate is refused (predicted to affect case 9). Tests first
  (2 seen failing; the two allowed cases passed before and after). Guide and README updated for
  the whole group.
- Fix to (k) after an automated security review, reproduced first: rejection messages of some
  codes echo text the agent chose (VERSION_NOT_FOUND quotes the version name, UNKNOWN_CANDIDATE
  the ids, also FORCE_CONFLICT and SCHEMA_INVALID), so a request with version "485.59" let
  "485.59" pass in a summary with no claim (2 tests seen failing). Now only the messages of
  BUDGET_NOT_POSITIVE, BUDGET_ABOVE_CAP and FORCED_COST_EXCEEDS_BUDGET, which hold only gate
  figures and request values, add numbers. Declined from the same review: requiring a validated
  claim whenever a summary has numbers; the owner decided (k) allows numbers from the
  conversation's runs without a citing claim.
- Acknowledged, not changed (automated security review of fix e): tracking candidates per run and
  per role would be a wording check, while the owner's rule is "selection, force lists or
  request"; ids are matched as C plus three digits, which is how this data names them (a
  lowercase "c033" would not be caught); force-list ids count because the rule says so (case 8's
  C099 is only in a rejected run's force list).

## 2026-11-16 — Round 2 (after fix group 1), official, commit 14dca3a
- 95 conversations, $0.0927, 1 infrastructure (HTTP error, case 15) excluded. Pass 84% (baseline
  86%), checked 76% (80%): both within the 10-point noise. **First pass 54% (66%): down 12
  points**, just above the noise line.
- Where group 1 worked: case 1's "15" (now `n_added`), case 8's "1000" and case 18's cap figures
  (5,138.73 and 1.5) no longer cause first refusals; case 18 passes 5/5 (4/5); case 19 5/5.
- **Fix (e) as specified makes answers worse.** 8 new first refusals: all 5 case 9 declines and 3
  case 8 answers named the candidate from the question without citing a run. All case 9 answers
  recovered by dropping "C033" (pass, but vaguer); in 2 case 8 answers the agent replaced "C099"
  with "the specified candidate", which fails the required phrase (case 8: 3/5, was 5/5).
- Other causes of the first-pass drop, not from the fixes: "80" (the sector count) written
  without an `n_sectors` claim (cases 1, 2, 3, 19); case 3's relief rounded to one decimal
  (1573.6, 1329.9; fix h); case 10's "1000" from the question with no run (5, was 1; unallowed
  by design).
- **New gap found:** case 13's answers say "38 sectors remained unresolved" (true: 80 - 42); the
  tool result shows `unresolved_count`, but no metric can claim it. In 1 of 5 the agent then
  claimed `n_resolved` = 38 to back it and failed.
- Unchanged failures: case 15 (0/4; the agent still computes the target itself; fix i), case 17
  (0/5; "change list" still not reachable; fix l), case 14 once without a run.

## 2026-11-16 — Fix (e) widened; round 2b
- **Round-2 finding (owner asked to record it):** tightening (e) made answers vaguer. In case 8
  the agent's correct "C099 is not a recognized candidate" was refused, and it rewrote it as "the
  specified candidate", which only the usefulness checks (the required phrase "C099") caught;
  the checker itself passed the vaguer answer. Case 9's declines likewise lost "C033".
- Owner change: a candidate id in the summary passes if it is in the selection or force lists of
  a run in the conversation, not only a cited one; ids only in the question stay refused. Tests
  first (1 seen failing; the question-only guard passed before and after). Guide and README
  updated. Round 2b runs with only this change.
- Round 2b (official, commit 54b6b13, only the widened e; 95 conversations, $0.0852, no
  infrastructure errors) against round 2: pass 87% (84%), checked 78% (76%), first pass 63%
  (54%, +9: at the noise line), runs 95% (94%), numbers 95% (94%), behaviour 88% (86%).
  Case 8: 5/5 with every first report accepted (round 2: 3/5, first pass 40%), since C099 is in
  the conversation's rejected run. Case 9: still 5/5 first refusals for "C033", by design (the
  question names it and no run is made); all recovered. Case 10: 2 NOT CHECKED for "1000" from
  the question with no run (by design). Cases 15 and 17 unchanged (fixes i and l pending).
- Acknowledged, not changed (automated security review of the widened e): an agent can make an
  id "traced" by forcing it into a request that is then rejected. That is what the owner asked
  for (case 8's correct answer names C099, which exists only in a rejected run's force list);
  the rejected request is itself stored and visible.

## 2026-11-16 — M4 fix group 2: f, g, h, i, j, l, m
- (f) Rejected against infeasible: rule 10 says a gate refusal is "rejected" and only a run with
  status Infeasible is "infeasible"; the checker refuses a summary that says "infeasible" when a
  cited run was rejected and no cited run is Infeasible. Tests first (2 seen failing). Guide
  updated.
- (g) Rule 12: the caveat is written as its own sentence, not as the conclusion of another, and
  the answer ends with the offer "I can run the optimizer at other budgets you name." Test first
  (seen failing).
- (h) Decimals: rule 7 says to round to the displayed precision, never more or fewer digits,
  with examples (41.25% is written 41.3%, 1573.567 is written 1573.57). Test first (seen failing).
- Acknowledged, not changed (automated security review of f): the rule covers cited runs, as
  the SPEC says, so a claimless "infeasible" about a rejected run passes (a possible follow-up:
  the conversation's runs, as for e); when any cited run is really Infeasible, the rule stands
  down for the whole summary, since telling which run a word refers to needs sentence parsing.
- (i) `target_pct_resolved` is described as report-only in the `run_scenario` tool text ("only
  reports whether the plan resolves at least that percent (target_met); it does not change the
  plan. Pass it when the user asks whether a plan reaches a percent.") and in the field's schema
  description; the request hash is unchanged (descriptions are not dumped). Test first (seen
  failing). Not specified by the owner: the "Pass it when ..." sentence.
- (j) Default version: rule 13 says to use v1, the plan of record, when no version is named and
  to say so; case 10 now expects a v1 run at 1000 labelled CHECKED (was: no run, NO NUMBERS TO
  CHECK); truth.json regenerated (cross-check clean); guide and SPEC case table updated. Tests
  first (2 seen failing). Not specified by the owner: "Do not ask which version to use."
- (l) Change list at the gate: a request on a change list (name starting `changes_`) is still
  VERSION_NOT_FOUND, with the message "changes_v1_to_v2 is a change list, not an input version"
  (scenario and target-budget gates); other unknown names keep "no input version 'x'". Tests
  first (1 seen failing; the unchanged message passed before and after).
- (m) Unresolved count: `n_unresolved` (all sectors minus resolved) is a claimable count with a
  glossary entry, computed independently by `evals/truth.py` (truth.json regenerated; case 13:
  38; cross-check clean and now covers it); rule 11 asks the agent to claim `n_sectors` whenever
  it writes "of N sectors", and the count before it as `n_resolved` or `n_unresolved`. Tests
  first (3 seen failing). README describes group 2.

## 2026-11-16 — Round 3 (after fix group 2), official, commit ba23462
- 95 conversations, $0.0883, no infrastructure errors. Pass 89%, runs 99%, numbers 100%,
  behaviour 91%, checked 82%, first pass 78%, mean 4.0 s and 2.9 turns. Against round 2b: pass
  +2, checked +4 (noise), **first pass +15** (63% to 78%, above the noise line); against the
  baseline: pass +3, checked +2 (noise), first pass +12.
- Worked: case 15 5/5 (0/5 in every earlier round; the agent now passes target_pct_resolved,
  fix i); case 10 5/5 under its new expectation (fix j); case 18 first pass 100% (40%); case 13
  4/5 with the unresolved count claimable (m).
- **Fix (l) did not help case 17 (0/5):** the agent never sends `changes_v1_to_v2` to the gate,
  so the new message is never shown. It lists the versions (only v1 and v2, the change list is
  hidden), then either runs v1 and v2 and compares them (4) or asks what was meant (1). The
  phrase stays out of reach unless the version listing names the change list.
- **Fix (f) false positive (case 4, 1/5):** "This is a rejection ... (it is not an infeasible
  result)" was refused because the rule matches any "infeasib..."; the agent repeated the correct
  denial and ended NOT CHECKED.
- **Checker tokenizer bug (case 13, 1/5):** in "0.5x fair share" the number reader rejects
  "0.5x" (it touches a letter), backs off and reads "0", which matches nothing. It should ignore
  the token or read 0.5 (a request value). Logged for later.
- Single failures attributed to the agent: case 7, it ran v1 at 1000 although no budget was
  given, then asked for one (forbidden call; rule 2); case 3, "1 more sector" without a
  `diff_n_resolved` claim; case 9, the decline kept naming C033 (question-only, refused by
  design) after the first refusal.

## 2026-11-16 — Final M4 changes: change lists listed, wording rule dropped, "0.5x"
- Change lists: `list_input_versions` returns `versions` and, separately, `change_lists`
  (`changes_v1_to_v2`), and its description says a change list records the edits between two
  versions, is not a version and cannot be run; the trace shows "v1, v2; change lists:
  changes_v1_to_v2" in the CLI and on the web page. Case 17 keeps its required phrase. Tests
  first (3 seen failing on assertions; the trace test first failed for the wrong reason, an
  import from `tests/`, and moved to `web/tests/test_format.py`).
- Checker "infeasible" rule dropped (owner); the prompt rule stays. Why: in round 3 it refused a
  correct denial ("This is a rejection ... (it is not an infeasible result)", case 4), a false
  positive on a denial, the same lesson as case 9's keywords ("approve", "recommend" appear in
  correct refusals, which is why they are review phrases, not failures). The checker verifies
  numbers, not wording; the eval grades case 4's wording ("rejected", "at least 697.01"). Test
  first (the denial seen refused); the rule's test replaced by one that the denial passes. Guide
  and README updated.
- "0.5x" number-reader bug fixed: when "0.5x" failed (it touches a letter), the optional decimal
  part backed off and "0" alone matched; likewise "1,284x" gave "1". The lookahead now also
  forbids stopping before ".digit" or ",digit", so such a token is skipped whole. Tests first
  (3 seen failing: the two glued tokens and case 13's summary; the guard cases "485.59." and a
  comma-separated list passed before and after). SPEC number rule noted.
- Correction to the "0.5x" fix, after an automated security review, reproduced first: the
  lookahead I added also dropped numbers in punctuation chains ("values 1,2,3" kept only "3";
  "485.59.12" kept nothing), a new way for a number to escape the check. Replaced by possessive
  quantifiers: a failed "0.5x" (or "12.5%x") cannot give back digits, so it is skipped whole,
  while "1,2,3" and "485.59" are checked as before. Tests first (2 seen failing; the "%x" case
  checked against the earlier pattern, which read "12.5"). The final round, started on the
  regressed code, was stopped before any report was written and restarted. Acknowledged, not
  changed: skipping a number glued to a letter is the SPEC's existing rule (identifiers such as
  C033 and v1 depend on it).

## 2026-11-16 — Final round; README; v0.5
- Final round (official, commit 7c34417, 95 conversations, $0.0746, 1 infrastructure error in
  case 12 excluded): pass 95%, runs 97%, numbers 96%, behaviour 97%, checked 82%, first pass 82%,
  mean 3.6 s and 2.8 turns. Case 17 5/5 (0/5 in every earlier round; the version listing now names
  the change list). **Case 7 did not run a budget nobody gave** (all 5: list versions, then ask
  for a budget).
- Remaining failures, all agent behaviour: case 13 (2) asked what "half its fair share" means
  instead of translating it to a floor multiplier of 0.5 (rule 3); case 11 (1) ran 1500 without
  forcing in the 800 plan (caught by the 1500 change); case 4 (1) wrote "the required minimum
  budget is 697.01", not "at least 697.01"; case 5 (1) did not claim the follow-up run's resolved
  count.
- README: M4 section with the round table, the noise note and the trade-offs accepted after the
  security reviews; status M1 to M4 and M2B (v0.5).

## 2026-11-16 — Pre-recording polish (no behaviour changes)
- Owner asked for four display changes, one commit each:
  1. Visible name "Capital Planning Scenario Assistant": page title and header (live page and
     replay) and README title. Package and CLI command keep `happy_toad` / `happy-toad`.
  2. Architecture diagram (page and README): larger text; Intake and Explanation marked AI MODEL
     (dashed purple), Gate, Optimizer, Run record and Checker marked CODE; both feedback paths
     drawn back to the agent (rejection; refused report, once) and lit on the page when they
     happen; "You" renamed "Human review". The README mermaid also gained the rejection path it
     was missing.
  3. Budget labelled "budget (ceiling)" in the stored-runs table and on each claim card.
  4. Check line "N claims | M numbers checked | K mismatches", identical in the CLI and the web.
- Not specified by the owner: claims have no plain budget metric, so each claim card got a line
  naming its run's budget ("budget (ceiling) 800", "800 → 1500" for a comparison). "Intake" and
  "Explanation" replace the step names "Agent" and "Report". M in the check line still counts the
  numbers that matched (as before), not all numbers looked at; "1 mismatch" stays singular and
  "1 claims" is unchanged. The replay was re-exported from its three transcripts, which also
  brought its pct_resolved glossary text up to date. README's intro paragraph notes the
  package keeps its working name.
- Owner asked for "1 claim" (singular) when there is one claim, in the CLI and the web; the rest
  of the line unchanged ("1 numbers checked" still possible; not asked).
- Correction, found when the owner asked: the README said "measured beyond that line: first
  pass +16, pass +9", but +9 is under the 10-point line. It now says only first pass (+16) is
  clearly beyond noise and pass (+9) is suggestive. My M4 final report made the same mistake.

## 2026-11-16 — Consistency fixes (owner's list after the retry-limit check)
- #1 "once": a report that does not fit the schema is refused without using the one correction,
  but the page lit "Refused: back to the agent, once" for it and the CLI called it "First report
  refused, then corrected". The diagram labels (page and README) now say "back to the agent"
  without "once". The CLI and web line now names each kind: "Failed the check once, then
  corrected: ..." for a check refusal, "1 report did not fit the schema and was resent (no
  correction used)" for schema refusals, both when both happened (before, a schema refusal
  followed by a check refusal showed only the schema one). Tests first (4 seen failing).
  Not specified by the owner: the exact new wording.
