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
- Report against a region size: "On v1 at 800, give the percent resolved out of 200 sectors."
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
- **No reverse budget search yet.** It cannot find the smallest budget that meets a target
  (planned). It reports whether a target is met at the budget you give.
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
