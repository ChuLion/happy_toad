# Eval round m6_mcp

2026-11-18T20:33:37+00:00 | commit 8ae563308c6eae466d9a32158e10774271b5850e | prompt a46431581249 | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen | via mcp

Pass 99% | runs 99% | numbers 99% | behaviour 99% | checked 89% | first pass 78% | n 95 | infrastructure 0 (excluded) | cost $0.0834 | mean 8.4 s, 2.9 turns

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 60% |
| 2 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 3 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 4 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 5 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 6 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 7 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 8 | 5 | 0 | 100% | 100% | 100% | 100% | 80% | 80% |
| 9 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 0% |
| 10 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 11 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 12 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 13 | 5 | 0 | 80% | 80% | 80% | 80% | 80% | 80% |
| 14 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 15 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 16 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 17 | 5 | 0 | 100% | 100% | 100% | 100% | 80% | 80% |
| 18 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 40% |
| 19 | 5 | 0 | 100% | 100% | 100% | 100% | 60% | 0% |

## Failures

- case 13, transcript 20261118T202825-f65f25dd (NO NUMBERS TO CHECK): required call run_scenario (run 0) missing or wrong; key number spend of run 0 not claimed; key number weighted_relief of run 0 not claimed; label NO NUMBERS TO CHECK not allowed

## Infrastructure (provider errors, excluded from every rate)

- none

## Manual review

- case 19, transcript 20261118T203308-8911a679: 400
- case 19, transcript 20261118T203315-85c540da: 400
