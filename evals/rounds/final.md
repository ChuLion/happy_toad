# Eval round final

2026-11-16T03:32:04+00:00 | commit 7c344179f498831bb503b7c201ecb07c04f17b42 | prompt 8d77a1e137b4 | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen

Pass 95% | runs 97% | numbers 96% | behaviour 97% | checked 82% | first pass 82% | n 94 | infrastructure 1 (excluded) | cost $0.0746 | mean 3.6 s, 2.8 turns

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 2 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 3 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 4 | 5 | 0 | 80% | 100% | 100% | 80% | 100% | 100% |
| 5 | 5 | 0 | 80% | 100% | 80% | 100% | 100% | 100% |
| 6 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 7 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 8 | 5 | 0 | 100% | 100% | 100% | 100% | 40% | 100% |
| 9 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 20% |
| 10 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 11 | 5 | 0 | 80% | 80% | 80% | 100% | 100% | 80% |
| 12 | 4 | 1 | 100% | 100% | 100% | 100% | 100% | 100% |
| 13 | 5 | 0 | 60% | 60% | 60% | 60% | 60% | 60% |
| 14 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 15 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 16 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 17 | 5 | 0 | 100% | 100% | 100% | 100% | 60% | 80% |
| 18 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 19 | 5 | 0 | 100% | 100% | 100% | 100% | 20% | 0% |

## Failures

- case 4, transcript 20261116T032730-07774a67 (CHECKED): required phrase "at least 697.01" missing
- case 5, transcript 20261116T032746-70de28af (CHECKED): key number n_resolved of follow_up 0 not claimed
- case 11, transcript 20261116T032908-a3cb235f (CHECKED): required call run_scenario (run 1) missing or wrong; key number spend of run 1 not claimed; key number weighted_relief of run 1 not claimed
- case 13, transcript 20261116T033000-5ffc6629 (NO NUMBERS TO CHECK): required call run_scenario (run 0) missing or wrong; key number spend of run 0 not claimed; key number weighted_relief of run 0 not claimed; label NO NUMBERS TO CHECK not allowed
- case 13, transcript 20261116T033010-a1eebb27 (NO NUMBERS TO CHECK): required call run_scenario (run 0) missing or wrong; key number spend of run 0 not claimed; key number weighted_relief of run 0 not claimed; label NO NUMBERS TO CHECK not allowed

## Infrastructure (provider errors, excluded from every rate)

- case 12, transcript 20261116T032938-9a02cb6b

## Manual review

- case 19, transcript 20261116T033148-39631fc1: 400
- case 19, transcript 20261116T033152-fd628253: 400
- case 19, transcript 20261116T033155-950958ae: 400
- case 19, transcript 20261116T033201-79f093bf: 400
