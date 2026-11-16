# Eval round round2

2026-11-16T01:07:30+00:00 | commit 14dca3a5b506a615e8e6aa4ce73525e49c614587 | prompt 27a044b445ce | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen

Pass 84% | runs 94% | numbers 94% | behaviour 86% | checked 76% | first pass 54% | n 94 | infrastructure 1 (excluded) | cost $0.0927 | mean 5.0 s, 3.5 turns

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 2 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 3 | 5 | 0 | 80% | 100% | 100% | 80% | 80% | 60% |
| 4 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 5 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 6 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 7 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 8 | 5 | 0 | 60% | 100% | 100% | 60% | 80% | 40% |
| 9 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 0% |
| 10 | 5 | 0 | 100% | 100% | 100% | 100% | - | 0% |
| 11 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 12 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 13 | 5 | 0 | 60% | 80% | 60% | 60% | 60% | 0% |
| 14 | 5 | 0 | 80% | 80% | 100% | 80% | 80% | 60% |
| 15 | 4 | 1 | 0% | 0% | 0% | 50% | 50% | 0% |
| 16 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 17 | 5 | 0 | 0% | 100% | 100% | 0% | 20% | 60% |
| 18 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 20% |
| 19 | 5 | 0 | 100% | 100% | 100% | 100% | 20% | 0% |

## Failures

- case 3, transcript 20261116T010031-ebf959c3 (NOT CHECKED): label NOT CHECKED not allowed
- case 8, transcript 20261116T010206-c5069629 (CHECKED): required phrase "C099" missing
- case 8, transcript 20261116T010221-ebf27210 (NO NUMBERS TO CHECK): required phrase "C099" missing
- case 13, transcript 20261116T010358-02b1092c (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number spend of run 0 not claimed; key number weighted_relief of run 0 not claimed; label NOT CHECKED not allowed
- case 13, transcript 20261116T010434-4d1f9afe (NOT CHECKED): n_resolved 38 contradicts truth 42; label NOT CHECKED not allowed
- case 14, transcript 20261116T010459-70b5f1ad (NO NUMBERS TO CHECK): required call run_scenario (run 0) missing or wrong; required phrase "unknown" missing
- case 15, transcript 20261116T010504-d4a75755 (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed; label NOT CHECKED not allowed
- case 15, transcript 20261116T010512-cdb15301 (CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed
- case 15, transcript 20261116T010518-0cc9e214 (NOT CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed; label NOT CHECKED not allowed
- case 15, transcript 20261116T010528-cbc20ca1 (CHECKED): required call run_scenario (run 0) missing or wrong; key number target_met of run 0 not claimed; key number pct_resolved of run 0 not claimed
- case 17, transcript 20261116T010630-bc12327c (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T010633-de8fa7b3 (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T010638-f7b83f9c (CHECKED): required phrase "change list" missing
- case 17, transcript 20261116T010646-23b7c352 (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T010651-0bbcc18e (NO NUMBERS TO CHECK): required phrase "change list" missing

## Infrastructure (provider errors, excluded from every rate)

- case 15, transcript 20261116T010535-7e7c93cd

## Manual review

- case 19, transcript 20261116T010712-e54180b9: 400
- case 19, transcript 20261116T010715-a71341fe: 400
- case 19, transcript 20261116T010723-6872acd1: 400
- case 19, transcript 20261116T010727-a92e5f17: 400
