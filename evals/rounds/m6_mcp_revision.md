# Eval round m6_mcp_revision

2026-11-18T20:41:21+00:00 | commit 8ae563308c6eae466d9a32158e10774271b5850e | prompt a46431581249 | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen | via mcp

Pass - | runs - | numbers - | behaviour - | checked - | first pass - | n 0 | infrastructure 0 (excluded) | cost $0.0000 | mean - s, - turns

Revision group (M5, not in the headline; counts): passed 18 of 20 | runs 20 of 20 | numbers 18 of 20 | behaviour 19 of 20 | checked 15 of 15

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 101 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 102 | 5 | 0 | 80% | 100% | 80% | 100% | 100% | 20% |
| 103 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 104 | 5 | 0 | 80% | 100% | 80% | 80% | 100% | 60% |

## Failures

- case 102, transcript 20261118T203900-ae71a48c (CHECKED): key number total_relief of run 0 not claimed
- case 104, transcript 20261118T204106-53b58609 (CHECKED): key number n_sectors_removed of run 0 not claimed; required phrase "added" missing

## Infrastructure (provider errors, excluded from every rate)

- none

## Manual review

- none
