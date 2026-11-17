# Eval round m5_revision_round2

2026-11-17T03:20:47+00:00 | commit 9cbeb0832d3b25ad84a90fdbe188abaf813a36b8 | prompt a46431581249 | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen

Pass - | runs - | numbers - | behaviour - | checked - | first pass - | n 0 | infrastructure 0 (excluded) | cost $0.0000 | mean - s, - turns

Revision group (M5, not in the headline; counts): passed 13 of 19 | runs 19 of 19 | numbers 16 of 19 | behaviour 16 of 19 | checked 13 of 15

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 101 | 4 | 1 | 100% | 100% | 100% | 100% | - | 100% |
| 102 | 5 | 0 | 60% | 100% | 60% | 100% | 100% | 80% |
| 103 | 5 | 0 | 60% | 100% | 100% | 60% | 60% | 40% |
| 104 | 5 | 0 | 60% | 100% | 80% | 80% | 100% | 60% |

## Notes

- Post-fix measurement on commit 9cbeb08 (fix pass 66a0507: end runs known, changed-input candidates traced; arrow-tolerant phrase check; counts line). Compare with m5_revision and m5_revision_arrows. Same four cases, no case, prompt or tool changes.

## Failures

- case 102, transcript 20261117T031947-402d8cfa (CHECKED): key number effect_relief:costs of run 0 not claimed; key number effect_relief:offloads of run 0 not claimed; key number effect_relief:triggers of run 0 not claimed; key number effect_relief:sectors of run 0 not claimed; key number total_relief of run 0 not claimed
- case 102, transcript 20261117T031956-8a8d6799 (CHECKED): key number effect_relief:costs of run 0 not claimed; key number effect_relief:offloads of run 0 not claimed; key number effect_relief:triggers of run 0 not claimed; key number effect_relief:sectors of run 0 not claimed
- case 103, transcript 20261117T032000-99b8d8a9 (NOT CHECKED): label NOT CHECKED not allowed
- case 103, transcript 20261117T032009-d07eeebc (NOT CHECKED): label NOT CHECKED not allowed
- case 104, transcript 20261117T032033-ac642c12 (CHECKED): required phrase "added" missing
- case 104, transcript 20261117T032035-88a07a97 (CHECKED): key number n_sectors_removed of run 0 not claimed

## Infrastructure (provider errors, excluded from every rate)

- case 101, transcript 20261117T031854-05599fac

## Manual review

- none
