# Eval round m6_direct_revision

2026-11-18T22:19:54+00:00 | commit d2b7b3f9ec850672eb5813c3c1d82301caecf5e6 | prompt a46431581249 | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen | via direct

Pass - | runs - | numbers - | behaviour - | checked - | first pass - | n 0 | infrastructure 0 (excluded) | cost $0.0000 | mean - s, - turns

Revision group (M5, not in the headline; counts): passed 15 of 20 | runs 20 of 20 | numbers 16 of 20 | behaviour 17 of 20 | checked 12 of 15

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 101 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 102 | 5 | 0 | 20% | 100% | 20% | 60% | 60% | 40% |
| 103 | 5 | 0 | 80% | 100% | 100% | 80% | 80% | 40% |
| 104 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 60% |

## Notes

- Run at d2b7b3f, not 8ae5633: the commits between them change only tests and docs (no src changes); prompt hash a46431581249 is the same as m6_mcp_revision.

## Failures

- case 102, transcript 20261118T221657-6c10f37b (CHECKED): key number total_relief of run 0 not claimed
- case 102, transcript 20261118T221741-664949c8 (NOT CHECKED): key number effect_relief:costs of run 0 not claimed; key number effect_relief:offloads of run 0 not claimed; key number effect_relief:triggers of run 0 not claimed; key number effect_relief:sectors of run 0 not claimed; key number total_relief of run 0 not claimed; label NOT CHECKED not allowed
- case 102, transcript 20261118T221757-f9e5428e (NOT CHECKED): key number effect_relief:costs of run 0 not claimed; key number effect_relief:offloads of run 0 not claimed; key number effect_relief:triggers of run 0 not claimed; key number effect_relief:sectors of run 0 not claimed; key number total_relief of run 0 not claimed; label NOT CHECKED not allowed
- case 102, transcript 20261118T221815-2797b52d (CHECKED): key number total_relief of run 0 not claimed
- case 103, transcript 20261118T221841-d1b6b955 (NO NUMBERS TO CHECK): label NO NUMBERS TO CHECK not allowed

## Infrastructure (provider errors, excluded from every rate)

- none

## Manual review

- none
