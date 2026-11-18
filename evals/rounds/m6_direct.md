# Eval round m6_direct

2026-11-18T19:23:23+00:00 | commit 8ae563308c6eae466d9a32158e10774271b5850e | prompt a46431581249 | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen | via direct

Pass 95% | runs 97% | numbers 96% | behaviour 98% | checked 87% | first pass 74% | n 95 | infrastructure 0 (excluded) | cost $0.0892 | mean 8.2 s, 3.0 turns

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 60% |
| 2 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 3 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 60% |
| 4 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 5 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 6 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 7 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 8 | 5 | 0 | 100% | 100% | 100% | 100% | 60% | 80% |
| 9 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 0% |
| 10 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 11 | 5 | 0 | 60% | 60% | 60% | 100% | 100% | 80% |
| 12 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 13 | 5 | 0 | 60% | 80% | 60% | 80% | 80% | 80% |
| 14 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 15 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 16 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 17 | 5 | 0 | 80% | 100% | 100% | 80% | 60% | 60% |
| 18 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 60% |
| 19 | 5 | 0 | 100% | 100% | 100% | 100% | 60% | 0% |

## Failures

- case 11, transcript 20261118T191659-ed57d7fa (CHECKED): required call run_scenario (run 1) missing or wrong; key number spend of run 1 not claimed; key number weighted_relief of run 1 not claimed
- case 11, transcript 20261118T191710-50647e12 (CHECKED): required call run_scenario (run 1) missing or wrong; key number spend of run 1 not claimed; key number weighted_relief of run 1 not claimed
- case 13, transcript 20261118T191843-c7211301 (CHECKED): status Infeasible contradicts truth Optimal
- case 13, transcript 20261118T191901-40a6db40 (NO NUMBERS TO CHECK): required call run_scenario (run 0) missing or wrong; key number spend of run 0 not claimed; key number weighted_relief of run 0 not claimed; label NO NUMBERS TO CHECK not allowed
- case 17, transcript 20261118T192122-af19af0c (NOT CHECKED): label NOT CHECKED not allowed

## Infrastructure (provider errors, excluded from every rate)

- none

## Manual review

- case 19, transcript 20261118T192250-7568ef11: 400
- case 19, transcript 20261118T192309-a7d79eb1: 400
