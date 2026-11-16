# Eval round round2b

2026-11-16T01:28:58+00:00 | commit 54b6b1322879e12d8579f11930f3008c3044e4c3 | prompt 27a044b445ce | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen

Pass 87% | runs 95% | numbers 95% | behaviour 88% | checked 78% | first pass 63% | n 95 | infrastructure 0 (excluded) | cost $0.0852 | mean 3.9 s, 3.5 turns

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 2 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 3 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 4 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 5 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 6 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 60% |
| 7 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 8 | 5 | 0 | 100% | 100% | 100% | 100% | 40% | 100% |
| 9 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 0% |
| 10 | 5 | 0 | 60% | 100% | 100% | 60% | - | 0% |
| 11 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 12 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 13 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 40% |
| 14 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 15 | 5 | 0 | 0% | 0% | 0% | 20% | 20% | 0% |
| 16 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 17 | 5 | 0 | 0% | 100% | 100% | 0% | 60% | 60% |
| 18 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 40% |
| 19 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 0% |

## Failures

- case 10, transcript 20261116T012517-c9c330d0 (NOT CHECKED): label NOT CHECKED not allowed
- case 10, transcript 20261116T012526-449331d2 (NOT CHECKED): label NOT CHECKED not allowed
- case 15, transcript 20261116T012703-f1b8e512 (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed; label NOT CHECKED not allowed
- case 15, transcript 20261116T012707-12ee59d4 (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed; label NOT CHECKED not allowed
- case 15, transcript 20261116T012712-8e49840d (CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed
- case 15, transcript 20261116T012718-51137217 (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed; label NOT CHECKED not allowed
- case 15, transcript 20261116T012724-366896ff (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed; label NOT CHECKED not allowed
- case 17, transcript 20261116T012757-0bfe1548 (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T012800-6ecb24af (CHECKED): required phrase "change list" missing
- case 17, transcript 20261116T012805-4508c794 (CHECKED): required phrase "change list" missing
- case 17, transcript 20261116T012814-dca3d525 (CHECKED): required phrase "change list" missing
- case 17, transcript 20261116T012819-88173b98 (NO NUMBERS TO CHECK): required phrase "change list" missing

## Infrastructure (provider errors, excluded from every rate)

- none

## Manual review

- case 19, transcript 20261116T012842-85647663: 400
- case 19, transcript 20261116T012846-9db06e66: 400
- case 19, transcript 20261116T012849-d7269467: 400
- case 19, transcript 20261116T012852-6f9d1b0b: 400
- case 19, transcript 20261116T012855-a1e4c27c: 400
