# Guide for planners

## 1. What it does
You ask a budget question in plain English, and an agent runs the scenarios on an optimizer that
picks which candidate solutions to fund so that weighted shortfall relief is as large as possible
within the budget. A checker compares each number in the agent's summary to the stored runs, and
an answer it cannot verify is shown as not checked. A human decides; the agent approves nothing.

## 2. The data
All data is synthetic and generated from a seed (seed 42); the numbers carry no real-world
meaning. Costs and budgets are in an abstract cost unit, shortfalls in an abstract need unit.

A **version** is one complete data set: sectors (each with a market, a shortfall and a trigger
year), candidate solutions (each with a cost), offloads (how much of a sector's shortfall a
candidate relieves if funded), and must-fund projects that are always paid for first.

- **Sector:** an area with an unmet need; each belongs to one market.
- **Shortfall:** how much need a sector has that is not yet covered.
- **Trigger year:** the year a sector's shortfall starts to bite, from 2027 to 2031.
- **Resolved:** a sector is resolved when the funded candidates relieve its whole shortfall.
  Partial relief still counts toward weighted relief, but not toward resolved.
- **Weighted relief:** relief for sectors that hit their shortfall sooner counts more. A sector
  that triggers in 2027 weighs 1, in 2028 one half, in 2029 one third, and so on. This weighting
  is a modelling assumption.

| | v1 (plan of record) | v2 (refreshed forecast) |
|---|---|---|
| Sectors (in 8 markets) | 80 | 83 |
| Candidate solutions | 51 | 51 |
| Offloads | 104 | 107 |
| Must-fund projects | 5 (cost 311.44) | 5 (cost 311.44) |
| Total candidate cost | 3,114.38 | 3,052.34 |

**v1 is the plan of record**: the data the plan was built on. **v2 is the refreshed forecast**: a
mid-year update with re-estimated costs, moved trigger years and new sectors. The version ids
stay v1 and v2. **changes_v1_to_v2 is a change list, not a version**: it lists the 27 edits
that turn v1 into v2 (10 candidate costs re-estimated, 8 offloads changed, 6 trigger years
moved, 3 sectors added). You cannot run a scenario on it.

## 3. What you can ask
Budgets are always the total, including must-fund projects.
- Which data sets exist? "Which input versions are there?"
- One budget: "On v1, what does a total budget of 1000 fund?"
- Force a candidate in: "On v1 at a total budget of 1000, what happens if we force in C033?"
- Leave a candidate out: "On v2 at a total budget of 1200, what if C001 is left out?"
- Spend floor per market: "On v1 at 1400, make each market get at least half its fair share."
- Spend cap per market: "On v1 at 1400, cap each market at 1.5 times its fair share."
- Report a target: "On v1 at 1400, does the plan resolve at least 50% of sectors?"
- Budget for a target: "On v1, what total budget reaches 50% of sectors resolved?"
- Percent resolved: "On v1 at 800, what percent of all sectors does the plan resolve?"
- Compare two runs: "On v1, compare a total budget of 800 with a total budget of 1500."
- Look up an earlier run: "Show me run <run id from an earlier answer> again."

A market's fair share is a share of the budget left after must-fund projects; it mixes the
market's share of the total shortfall with an equal split between markets.
A target or region size changes only what is reported, not the plan.

## 4. From question to decision
1. **You ask a question.** The planner states the scenario in their own words.
2. **The agent turns it into scenario requests.** The optimizer needs exact inputs, not prose.
3. **A gate accepts or rejects each request, listing every problem.** An impossible request is
   refused with its reasons instead of being turned into a misleading plan.
4. **The optimizer solves it in two stages.** First the most weighted relief, then the lowest
   spend that delivers it, so the plan doesn't spend money that adds no relief.
5. **Every attempt is stored as a run record.** Each number can be traced to a run id.
6. **The agent writes a summary and lists its numbers as claims.** The numbers become data that
   can be checked, not just sentences.
7. **The checker compares the claims and every number in the summary with the stored runs.**
   A mismatch goes back to the agent once; if it still fails, you see the answer as NOT CHECKED.
8. **You see CHECKED, NOT CHECKED or NO NUMBERS TO CHECK.** The label tells you how far the
   numbers can be trusted.
9. **A human decides.** The agent approves nothing.

## 5. What it does not do
- **No approvals.** It runs scenarios and reports; it never approves or funds anything.
- **No wording check.** The checker verifies numbers against stored runs, not whether the words
  are a fair reading of them. It does not check direction words such as "more" or "less", or
  wording such as "rejected" versus "infeasible". Candidate ids named in the summary are not
  checked, and whole numbers from 1900 to 2199 are skipped as possible years.
- **A target budget is for the cheapest plan, not the optimizer's plan.** "What budget reaches
  50%?" gives the total budget of the cheapest plan that resolves at least that many sectors. The
  optimizer's usual plan at that budget maximizes weighted relief and can resolve fewer, and a
  higher budget does not guarantee more resolved sectors (on v1 there are 148 budgets where one
  more unit resolves fewer). Market floors and caps cannot be combined with this search.
- **Synthetic data only.** 80 sectors is small; the weights by trigger year are a modelling
  assumption, not a calibrated value.
- **Checked live with one model.** The demo answers were checked live with one model (DeepSeek V4
  Flash 0731). One small round compared five models; with five runs per cell the differences
  are suggestive, not conclusive.
- **It cannot read the change list** (revision analysis is planned). Ask about v1 or v2, not
  about what changed between them.

## 6. How to try it
**Replay page first** (no key, no network, nothing to install): on the project's GitHub page,
click **Code**, then **Download ZIP**. Unzip the file, open the folder, then open
`web/replay.html` in your browser. It replays three real runs: two that passed the check and one
that failed it.

**Then the live page** (needs [uv](https://docs.astral.sh/uv/), Python 3.12 or later and an
OpenRouter key; the demo questions cost $0.0010 to $0.0019 each in the live runs):
```
git clone https://github.com/ChuLion/happy_toad.git && cd happy_toad
uv sync
uv run happy-toad generate --seed 42
OPENROUTER_API_KEY=your-key uv run python -m web.server
```
Then open http://127.0.0.1:8765 and ask one question at a time.

## 7. Glossary

### Report metrics
A claim in a report names one of these metrics, its value and the run it comes from.
- **`spend`:** what the plan spends on candidate solutions, in cost units. Must-fund projects
  are not included, though the budget you give does include them.
- **`weighted_relief`:** the shortfall the plan relieves, with each sector's relief multiplied
  by its weight, in need units. Relief in a sector counts only up to its shortfall. The
  optimizer makes this as large as the budget allows.
- **`n_selected`:** how many candidate solutions the plan funds.
- **`n_resolved`:** how many sectors the plan resolves (whole shortfall relieved).
- **`pct_resolved`:** resolved sectors as a percent of all sectors in the version. A region
  size does not change it; the percent of the region is `pct_of_region`.
- **`pct_of_region`:** resolved sectors as a percent of the region size you gave
  (`region_total_sectors`). Only for runs with a region size.
- **`n_sectors`:** how many sectors the run's version has. Read from the data, not the plan.
- **`status`:** the solver status of a run with a plan (Optimal, Infeasible, TimeLimit, Error),
  or the run outcome (rejected, error) when the run has none.
- **`target_met`:** true when `pct_resolved` reaches the target percent you asked for, false
  when it does not. Present only when a target was asked.
- **`required_minimum_budget`:** for a rejected or infeasible run with a known cause, the total
  budget below which the scenario cannot work: must-fund cost plus forced-in cost plus market
  floors. A budget this size is necessary, not a promise that the scenario then works.
- **`must_fund_cost`:** the total cost of the must-fund projects in the run's version.
- **`forced_cost`:** the total cost of the candidates the run forced in.
- **`target_budget`:** the total budget, including must-fund projects, of the cheapest plan that
  resolves at least the target percent of sectors, rounded up to the cent. The optimizer's usual
  plan at that budget can resolve fewer, because it maximizes weighted relief.
- **`target_sectors`:** the target as a number of sectors: the target percent of all sectors,
  rounded up (50% of 80 is 40).
- **`max_resolvable`:** the most sectors any plan can resolve with the candidates that are not
  forced out. Given with every target-budget search; when the target needs more, it is
  unreachable.
- **`max_pct_resolvable`:** `max_resolvable` as a percent of all sectors in the version.
- **`n_added`:** how many candidates the second run (`run_id_b`) funds that the first does not.
- **`n_dropped`:** how many candidates the first run (`run_id`) funds that the second does not.
- **`diff_` prefix:** a difference between two runs: the value in the second run (`run_id_b`)
  minus the value in the first (`run_id`), in the same unit as the metric without the prefix.
  Positive means the second run is higher, negative means it is lower.
- **`diff_spend`:** the second run's `spend` minus the first run's.
- **`diff_weighted_relief`:** the second run's `weighted_relief` minus the first run's.
- **`diff_n_selected`:** the second run's `n_selected` minus the first run's.
- **`diff_n_resolved`:** the second run's `n_resolved` minus the first run's.
- **`diff_pct_resolved`:** the second run's `pct_resolved` minus the first run's, in
  percentage points.

### Run outcomes
- **completed:** the gate accepted the request and the optimizer ran; the run has a solver
  status.
- **rejected:** the gate refused the request, so nothing was solved. The run lists every
  reason (gate codes below).
- **error:** something failed while running, for example an input file that fails its checks.
  The run stores the error message.

### Solver statuses
- **Optimal:** the solver proved no better plan exists under the modeled objective and
  constraints: the most weighted relief, then the lowest spend that keeps it.
- **Infeasible:** no plan can meet the scenario's rules. The run names the cause when it can
  (infeasible causes below).
- **TimeLimit:** the solver ran out of time. Any plan shown is the best found so far, not a
  proven best.
- **Error:** the solver stopped for another reason. Any plan shown is not a proven best.

### Gate codes
The gate checks a request before anything is solved and lists every problem it finds.
- **`VERSION_NOT_FOUND`:** there is no input version with that id.
- **`BUDGET_NOT_POSITIVE`:** the budget is zero or less.
- **`BUDGET_ABOVE_CAP`:** the budget is more than 1.5 times the cost of all candidates and
  must-fund projects together; usually a units mistake.
- **`UNKNOWN_CANDIDATE`:** a candidate id to force in or out does not exist in the version.
- **`FORCE_CONFLICT`:** the same candidate is both forced in and forced out.
- **`FORCED_COST_EXCEEDS_BUDGET`:** must-fund cost plus forced-in cost is more than the budget.
- **`SCHEMA_INVALID`:** the agent's request did not fit the request format (a missing or
  misspelled field, or a value of the wrong type).

### Infeasible causes
Checked before solving, in this order; the first one found is reported.
- **`FLOORS_EXCEED_BUDGET`:** the market floors add up to more than the budget left after
  must-fund projects.
- **`CAP_BELOW_FLOOR`:** a market's cap is lower than its floor.
- **`FORCED_IN_EXCEEDS_CAP`:** the forced-in candidates in a market cost more than that
  market's cap.
- **`FLOOR_UNREACHABLE`:** a market's floor is more than its candidates that are not forced out
  cost together.
- **`TARGET_UNREACHABLE`:** (target-budget search) no plan can resolve the target number of
  sectors, even with every candidate that is not forced out funded; the run gives
  `max_resolvable` and `max_pct_resolvable` instead of a budget.
- **`CAUSE_UNKNOWN`:** the solver proved no plan exists, but none of the checks above found why.

`FORCED_COST_EXCEEDS_BUDGET` is checked here too, but the gate normally catches it first.

### Labels
- **CHECKED:** every claim and every number in the summary matched a stored run, and there was
  at least one. Words, candidate ids and numbers that look like years (1900 to 2199) are not
  checked.
- **NOT CHECKED:** some number could not be matched, even after the agent was sent back once
  to correct it. Do not rely on the numbers.
- **NO NUMBERS TO CHECK:** the answer was accepted but contains no claims or numbers, so there
  was nothing to verify.

### Data terms
- **Version:** one complete data set you can run scenarios on, named by an id: v1 (plan of
  record) or v2 (refreshed forecast).
- **Change list:** the list of edits that turns one version into the next
  (`changes_v1_to_v2`). It is not a version and cannot be run.
- **Sector:** an area with an unmet need. Each belongs to one market.
- **Shortfall:** how much need a sector has that is not yet covered, in need units.
- **Trigger year:** the year a sector's shortfall starts to bite, from 2027 to 2031.
- **Candidate:** a candidate solution: something that can be funded, whole or not at all, for
  its cost. Funding it relieves one or more sectors through its offloads.
- **Offload:** how much of one sector's shortfall one candidate relieves if it is funded.
- **Must-fund project:** a project that is always paid for first, out of the budget. The
  optimizer does not choose it.
- **Market:** a group of sectors. A candidate belongs to the market of its largest offload.
- **Fair share:** a market's share of the budget left after must-fund projects: half by its
  share of total shortfall, half split equally across markets.
- **Floor:** the least the plan must spend in a market, as a multiple of its fair share. Only
  when you ask for one. Floors above 1 times fair share can't all be met at once: the fair
  shares already add up to the whole budget left after must-fund projects.
- **Cap:** the most the plan may spend in a market, as a multiple of its fair share. Only when
  you ask for one.
- **Weight:** how much a sector's relief counts: 1 for trigger year 2027, one half for 2028,
  one third for 2029, and so on.

### Records
- **Run id:** the id of one stored run, such as `20261114T210148-4c3b03e4`: the UTC time it was
  made, plus 8 random characters.
- **Transcript:** the full record of one question: every model turn, every tool call and its
  result, the report and the checker's results.
- **Claim:** one number from a report, given as data: a metric, its value and the run id it
  comes from (two run ids for a `diff_` metric). The checker compares each claim with the
  stored run.
