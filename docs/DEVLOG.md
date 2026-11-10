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
