# Eval round m5_revision

2026-11-17T02:43:56+00:00 | commit 6fbb32a1c6a643808d7d569787b54b3693621a54 | prompt a46431581249 | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen

Pass - | runs - | numbers - | behaviour - | checked - | first pass - | n 0 | infrastructure 0 (excluded) | cost $0.0000 | mean - s, - turns

Revision group (M5, not in the headline; counts): passed 10 of 20 | runs 20 of 20 | numbers 16 of 20 | behaviour 13 of 20 | checked 8 of 15

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 101 | 5 | 0 | 100% | 100% | 100% | 100% | - | 100% |
| 102 | 5 | 0 | 0% | 100% | 20% | 60% | 60% | 40% |
| 103 | 5 | 0 | 40% | 100% | 100% | 40% | 40% | 20% |
| 104 | 5 | 0 | 60% | 100% | 100% | 60% | 60% | 0% |

## Notes

- regraded 2026-11-17T03:18:35+00:00 at commit e678a12c1360b9e0d7e8895d84667f60970c5f1a
- Offline regrade of m5_revision with the arrow-tolerant phrase check ("→" counts as "->"), a grader change made after seeing the round's results; no new conversations; same transcripts and runs.

## Failures

- case 102, transcript 20261117T024158-6dc3ce1d (CHECKED): key number total_relief of run 0 not claimed
- case 102, transcript 20261117T024205-e93090cf (NOT CHECKED): key number effect_relief:costs of run 0 not claimed; key number effect_relief:offloads of run 0 not claimed; key number effect_relief:triggers of run 0 not claimed; key number effect_relief:sectors of run 0 not claimed; key number total_relief of run 0 not claimed; label NOT CHECKED not allowed
- case 102, transcript 20261117T024213-71e5698e (CHECKED): key number effect_relief:costs of run 0 not claimed; key number effect_relief:offloads of run 0 not claimed; key number effect_relief:triggers of run 0 not claimed; key number effect_relief:sectors of run 0 not claimed; key number total_relief of run 0 not claimed
- case 102, transcript 20261117T024219-33542b7c (CHECKED): key number effect_relief:costs of run 0 not claimed; key number effect_relief:offloads of run 0 not claimed; key number effect_relief:triggers of run 0 not claimed; key number effect_relief:sectors of run 0 not claimed; key number total_relief of run 0 not claimed
- case 102, transcript 20261117T024225-c6feaa2e (NOT CHECKED): label NOT CHECKED not allowed
- case 103, transcript 20261117T024236-26fcc19a (NOT CHECKED): label NOT CHECKED not allowed
- case 103, transcript 20261117T024257-e87d8964 (NOT CHECKED): label NOT CHECKED not allowed
- case 103, transcript 20261117T024308-4d492fda (NOT CHECKED): label NOT CHECKED not allowed
- case 104, transcript 20261117T024327-985373f7 (NOT CHECKED): label NOT CHECKED not allowed
- case 104, transcript 20261117T024350-c778d705 (NOT CHECKED): label NOT CHECKED not allowed

## Infrastructure (provider errors, excluded from every rate)

- none

## Manual review

- none
