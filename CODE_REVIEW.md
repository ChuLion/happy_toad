# Code Review — happy_toad

Date: 2026-11-14 · Commit reviewed: `334c220` (main, clean tree)

How it was done: a full review of the code base, not a diff review. Two code-review agents read it,
one for `data/engine/services` and one for `agent/cli/scripts`. A code-simplifier agent went over
all of `src/` and `scripts/` in report-only mode. The lead reviewer re-read the code behind every
medium finding and spot-checked the simplifier's duplication claims. No code was changed.

## Baseline

| Check | Result |
|---|---|
| `uv run pytest` | 342 passed (18.5 s) |
| Coverage | 98% overall; gaps in `agent/client.py` 89%, `cli.py` 86%, `agent/tools.py` 95% |
| `uv run ruff check .` | clean |
| `uv run ruff format --check .` | clean (74 files) |

Overall: the code base is in good shape. Modules are short, functions are small, and names are
clear. The two-stage MILP, the relief and status mapping, hashing, load checks, the request gate,
the tool loop and the checker all match the SPEC. No high-severity bugs were found, and no API-key
leak was found. Severity in the tables below: **M** = medium, **L** = low.

---

## Part 1 — Correctness findings (code-review)

### Engine, data and services

| # | Sev | Location | Finding |
|---|---|---|---|
| 1 | M | `engine/model.py:93-97`, `engine/diagnose.py:75-91` | **The "budget must be at least X" advice can be impossible to follow when the limits come from multipliers.** `fair_share_limits` sets floors to `floor_mult × share × avail`, and the shares sum to 1, so total floors = `floor_mult × (budget − must_fund)`. This grows with the budget. With `market_floor_mult = 1.2`, no budget is ever feasible (unless clamping kicks in), yet the agent is told to state "at least X". `CAP_BELOW_FLOOR` with `cap_mult < floor_mult` does not depend on the budget at all, but still reports a minimum budget. The SPEC already says the minimum is "a lower bound, not a promise", but in these cases it is actively misleading. |
| 2 | M | `services/run.py:145-148` | **A corrupt input file leaves no run record.** Only `InputError` is caught around `load_version`. Malformed JSON or a schema violation in `data/inputs/vN.json` raises pydantic `ValidationError`, which is not an `InputError`. It escapes `run_request`, which breaks the rule that "every attempt leaves a record". No test covers this. |
| 3 | L | `engine/diagnose.py:36-41` | If `solve()` or `run_sweep()` is called directly (skipping the gate) with budget < must-fund and nothing forced in, `avail` is negative. The result is mislabelled `FORCED_COST_EXCEEDS_BUDGET`, with the message "forced-in cost 0.00 exceeds … (−X)". |
| 4 | L | `engine/markets.py:36` | `fair_shares` divides by total shortfall. Data where every shortfall is 0 passes the load checks (`shortfall >= 0`) and then raises `ZeroDivisionError` once multipliers are on. Only degenerate data triggers it. |
| 5 | L | `engine/model.py:125` | `assert status2 != "Infeasible"` is the only guard against a CBC tolerance edge case. It is stripped under `python -O`; otherwise it becomes an `"error"` run. Acceptable as is. |
| 6 | L | `data/checks.py:73`, `engine/model.py` | Load checks validate trigger years against the default `BASE_YEAR`, but `solve(base_year=...)` accepts any year. If `base_year > trigger_year`, the weights can be negative or divide by zero. |
| 7 | L | `services/request.py:30-33` | `request_hash` covers `input_version` but not the data's `content_hash`. If a version file is regenerated, the same request gets the same hash. This only matters if the hash is ever used as a cache or identity key; `content_hash` is stored separately. |
| 8 | L | `services/runs.py:46` | `read_run` on a corrupt record file raises `ValidationError` straight to the caller (the same pattern as #2). |

### Agent, CLI and scripts

| # | Sev | Location | Finding |
|---|---|---|---|
| 9 | M | `agent/checker.py:231-256`, `agent/loop.py:79` | **Claims are checked against any run on disk, not only runs from this conversation.** The tool description (`tools.py:70`) and SPEC:756 say a claim must come from "a run you executed or read". `conversation_runs` is used only for the minimum-budget rule and for removing run ids from the summary. A model can cite a run id from an earlier conversation without calling a tool, and the claim is accepted as "checked". |
| 10 | M | `agent/client.py:90-96` | **`fetch_quantizations` has no timeout and catches only `OSError`.** A stalled connection hangs `happy-toad ask` or the bake-off with no end. A non-JSON or reshaped reply raises `ValueError`/`KeyError`, which `cli.ask` does not catch (it catches `RuntimeError` only). The user gets a traceback before any transcript exists. |
| 11 | L | `cli.py:95-96` | `_show_outcome` prints "Report:" whenever `t.report` is set, and a draft that failed its check also sets it (`loop.py:81`). A run that ends as `step_cap`, `error` or `api_error` therefore shows a rejected draft with no UNVERIFIED banner. |
| 12 | L | `cli.py:124` | `PROFILES[profile]` raises a raw `KeyError` for an unknown name. The help text says "smoke or demo", but about 10 profiles exist. |
| 13 | L | `agent/loop.py:70-89` | Two `submit_report` calls in one assistant turn both run the checker. If the first fails, the second uses up the one correction before the model has seen the first errors, which goes against the SPEC's "failures go back to the model once" flow. |
| 14 | L | `agent/bakeoff.py:79-83` | `_refusals` counts the final failing report of an unverified run as a "refusal the model had to correct". The model never corrected it, so the counts in the bake-off tables come out a little high. |
| 15 | L | `agent/loop.py:163` | Ctrl-C (`KeyboardInterrupt`) skips the `except Exception`, so a paid run that is interrupted saves no transcript. |
| 16 | L | `agent/client.py:90` / `cli.make_client` | Every `OpenRouterClient(profile)` built without a listing calls the endpoint-listing API again. A per-model `functools.cache` would avoid the repeat calls. |
| 17 | L | `agent/client.py:37-46` | Error-body redaction covers only `user_…` ids. The rest of the body goes into transcripts and bake-off JSON. The risk is low and the behaviour is documented; you could truncate the body. |

### Convention notes
- `openai` is a dependency that is not on the CLAUDE.md allowed list. The owner approved it
  (DEVLOG:480, SPEC:649), so it is fine, but the list in CLAUDE.md is out of date.
- `scripts/bakeoff.py` and `scripts/string_claims_ab.py` generate inputs in a temporary directory
  but write run records to the real `runs/`. Re-checking those runs later depends on
  `data/inputs/` matching. Worth one line in each docstring.

---

## Part 2 — Simplification recommendations (code-simplifier)

Every item keeps behaviour the same unless it says otherwise. The duplication claims in S1, S3
and S5 were spot-checked with grep.

### High value
- **S1 — Per-market spend is computed twice.** `diagnose._market_spend(data, ids)` and
  `markets.market_costs(data)` do the same thing. Keep one function,
  `markets.market_spend(data, ids=None)`, and use it in `clamp_floors` and `diagnose`.
- **S2 — Run records are built in two places.** `tools.record_schema_invalid` repeats the
  `RunRecord` field list from `services/run.py` and builds its own sha256. Move it to
  `services/run.py` as `record_invalid_request(...)`. *Risk:* keep
  `json.dumps(raw, sort_keys=True, default=str)` as the hash, and do not switch to `request_hash`,
  or stored hashes will change.
- **S3 — The must-fund total is summed in 7 places.** `sum(m.cost for m in data.must_fund)`
  appears in cli, model, diagnose, gate (twice), checker and compare_greedy. The candidate total
  is summed in 4 places. Add `InputSet.must_fund_total` and `InputSet.candidate_total` properties;
  pydantic does not serialize properties, so the hash does not change. Compute the forced-in cost
  once in `diagnose.py`.
- **S4 — The "has a plan" check is written twice** (`runs.py:65`, `checker.py:146`). Add
  `has_plan(record)` in `runs.py` and use it in both.

### Medium value
- **S5** — `checker.RUN_ID_TEXT` is the same regex as `runs.RUN_ID`. Import it instead.
- **S6** — `stages.py`: both stages build the weighted-relief expression. Have `_core` return it.
  `_core`'s default arguments are never used; drop them (keep the ones on `build_stage1`, which
  tests rely on).
- **S7** — `model.make_result` takes 8 untyped positional parameters and `solve` is about 80
  lines. Add type hints, make `cause` and `minimum` keyword-only, and move the meta/settings dict
  into `_run_meta(...)`.
- **S8** — `bakeoff.py`:
  - `_error_row` builds `Row` from 16 positional arguments under `# fmt: skip`; use keyword
    arguments.
  - The `if (\n … == 400\n):` block is a formatter artifact; write a plain `if`.
  - The `git` lambda under `# noqa: E731` should be a `def`.
- **S9** — `scripts/fair_share_table.py` re-implements `markets.fair_shares`; call it instead.
  Floats may differ in the last bit, which the printed output does not show.
- **S10** — `string_claims_ab.TEXT` repeats `agent/report.TEXT_METRICS`. The provider-list
  expression appears 3 times; it could be a `Transcript.providers` property.
- **S11** — There are two modules named `report.py`. Rename `happy_toad/report.py` (the Rich
  tables) to `tables.py`.

### Low value (tidy-ups)
- **S12 — Missing type hints:**
  - `cli.make_client`, `_show_outcome`
  - several helpers in `generator.py` and `evolve.py` (`rng`/`cfg`)
  - `run.summarize(result)`, which should be `SolveResult`
  - `Conversation.__init__`
  - `Change = dict` adds little.
- **S13** — The ID formats `C{:03d}` and `S{:03d}` are written out in several places. Add
  `candidate_id(k)` and `sector_id(n)` helpers.
- **S14 — Small constructs with simpler equivalents:**
  - `sweep.py:15-17` has an inner generator; use a plain list comprehension.
  - `cli.py:73` builds `options` only to unpack it; pass the arguments directly.
  - `t.checks[-1:]` loop → `if t.checks:`.
  - `checker.py:203` has a conditional iterable; use an early `continue`.
  - `tools.py:166` builds a list but uses only its first element; use a plain loop.
  - `tools.py:84-92` has an `else` that a default value can replace.
  - In `client.__init__`, fetch quantizations only where they are needed.
  - `parse_completion` tests `usage` three times; one branch would do.
  - `evolve.py:71/77` builds the same key twice.
  - Move the `BUDGET_CAP_FACTOR` comment out of the formatter-made parentheses.
  - Move `RESOLVED_TOLERANCE` to the top of `relief.py`, and name it in the `unresolved.py`
    docstring instead of writing "1e-6".
  - The `_reason` wrapper is defined in both `diagnose.py` and `gate.py`.
  - `Conversation` receives `runs_dir` and `inputs_dir`, which `runner` already holds.
  - `bakeoff.py:112` uses a defensive `.get("reasoning", 0)`; index the key directly.
  - `coercions` and `defaults` each parse the same JSON.

### Risk note
Changes to `checker.py`, `report.py`, `tools.py`, `prompt.py` or `loop.py` change the
`FROZEN_FILES` hashes in `bakeoff.provenance()`. Bake-off results from before and after such a
change are then no longer comparable. Make those edits between bake-off rounds, not during one.

---

## Recommendations (in priority order)

1. **#9 Run provenance in the checker.** Fail any claim whose `run_id`/`run_id_b` is not in
   `conversation_runs` ("run was not executed or read in this conversation"), and add a test.
   This is the biggest gap in what the checker promises. It touches a frozen file, so do it
   between rounds.
2. **#2 / #8 Corrupt files.** Have `load_input_set` wrap `ValidationError` in `InputError` so that
   `run_request` always writes a record. Add a test with a malformed `vN.json`.
3. **#1 Minimum budget with multipliers.** Set `required_minimum_budget` only when the floors do
   not depend on the budget (explicit limits) or the cause is `FORCED_COST_EXCEEDS_BUDGET`.
   Otherwise leave it as None and name the multiplier to change. Update SPEC "Required minimum
   budget" and add a test that uses multipliers. *Owner decision:* this changes SPEC behaviour.
4. **#10 Network robustness.** Use `urlopen(..., timeout=10)` and catch
   `(OSError, ValueError, KeyError)` in `fetch_quantizations`; add a test for each failure.
5. **#11, #12 CLI polish.** Show the report only when the status is checked or unverified, and
   raise `typer.BadParameter` with the valid profile names.
6. **Simplifications S1–S4.** These remove real duplication at low risk. S3 and S4 also make the
   checker and gate easier to read.
7. **The low-severity items and S5–S14**, as time allows.
8. Update the CLAUDE.md dependency list to include `openai`, which was approved.

Suggested test additions:
- a claim that cites a run from outside the conversation (#9)
- a malformed input file (#2)
- a run with multiplier-derived floors and its minimum budget (#1)
- a failure of `fetch_quantizations` (#10)
- an unknown `--profile` (#12)
- two `submit_report` calls in one turn (#13)
