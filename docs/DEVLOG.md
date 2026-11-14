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
  budget 1370.2 including must-fund; 1% steps). In the 5% sweep: 36/80 at 25%, 42/80 at 30%.
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
