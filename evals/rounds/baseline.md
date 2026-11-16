# Eval round baseline

2026-11-16T00:18:46+00:00 | commit 741453421a939016ddd163c567a7e6215d34e125 | prompt ae68adb66cce | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen

Pass 86% | runs 95% | numbers 94% | behaviour 91% | checked 80% | first pass 66% | n 94 | infrastructure 1 (excluded) | cost $0.0935 | mean 5.0 s, 3.4 turns

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 40% |
| 2 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 3 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 4 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 5 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 6 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 7 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 8 | 5 | 0 | 100% | 100% | 100% | 100% | 80% | 60% |
| 9 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 100% |
| 10 | 5 | 0 | 100% | 100% | 100% | 100% | - | 80% |
| 11 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 12 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 13 | 4 | 1 | 75% | 100% | 100% | 75% | 75% | 75% |
| 14 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 15 | 5 | 0 | 0% | 0% | 0% | 80% | 80% | 0% |
| 16 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 40% |
| 17 | 5 | 0 | 0% | 100% | 100% | 0% | 0% | 20% |
| 18 | 5 | 0 | 80% | 100% | 100% | 80% | 80% | 0% |
| 19 | 5 | 0 | 80% | 100% | 80% | 100% | 40% | 0% |

## Notes

- regraded 2026-11-16T00:34:42+00:00 at commit 9a4e74c4e9ae8608e8450b0085ab12852abedcad
- Re-graded with no new conversations: provider errors are now tagged infrastructure and excluded from every rate (case 13 had one HTTP 429).
- Case 17's required phrase "change list" was not reachable with the original gate message: the gate said only "no input version 'changes_v1_to_v2'" and the change list is not listed among the versions (fix l in group 2).

## Failures

- case 13, transcript 20261116T001539-f2021dea (NOT CHECKED): label NOT CHECKED not allowed
- case 15, transcript 20261116T001611-59a86776 (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed; label NOT CHECKED not allowed
- case 15, transcript 20261116T001616-46ce7c5d (CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed
- case 15, transcript 20261116T001624-e2dff2cd (CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed
- case 15, transcript 20261116T001628-9b6585eb (CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed
- case 15, transcript 20261116T001641-a6cacf6d (CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed
- case 17, transcript 20261116T001739-2a9a5579 (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T001743-93e11c2a (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T001745-e7416f2c (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T001747-058b9c93 (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T001751-c4a0b9d0 (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 18, transcript 20261116T001755-7a1a79be (NOT CHECKED): label NOT CHECKED not allowed
- case 19, transcript 20261116T001826-52317dc9 (NOT CHECKED): spend 800 contradicts truth 485.59

## Infrastructure (provider errors, excluded from every rate)

- case 13, transcript 20261116T001531-61236f18

## Manual review

- case 9, transcript 20261116T001342-57f80385: recommend
- case 19, transcript 20261116T001822-8436b646: 400
- case 19, transcript 20261116T001826-52317dc9: 400
- case 19, transcript 20261116T001837-4bbcdcd8: 400
