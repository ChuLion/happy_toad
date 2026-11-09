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
