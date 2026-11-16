# Eval round round3

2026-11-16T02:53:22+00:00 | commit ba2346268bdd23fe2cbdbe6b56bfe0904ed0bd74 | prompt 4a8662d2b31e | deepseek/deepseek-v4-flash-0731 | Baidu, BaseTen

Pass 89% | runs 99% | numbers 100% | behaviour 91% | checked 82% | first pass 78% | n 95 | infrastructure 0 (excluded) | cost $0.0883 | mean 4.0 s, 2.9 turns

A round is 19 cases x 5 runs = 95 conversations: a difference between two rounds under about 10 percentage points is noise, and per case a change of 1 or 2 out of 5 is noise.

| case | n | infra | pass | runs | numbers | behaviour | checked | first pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 2 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 3 | 5 | 0 | 80% | 100% | 100% | 80% | 80% | 60% |
| 4 | 5 | 0 | 80% | 100% | 100% | 80% | 80% | 80% |
| 5 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 6 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 80% |
| 7 | 5 | 0 | 80% | 80% | 100% | 100% | - | 100% |
| 8 | 5 | 0 | 100% | 100% | 100% | 100% | 60% | 100% |
| 9 | 5 | 0 | 80% | 100% | 100% | 80% | 0% | 0% |
| 10 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 11 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 12 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 13 | 5 | 0 | 80% | 100% | 100% | 80% | 80% | 80% |
| 14 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 15 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 40% |
| 16 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 17 | 5 | 0 | 0% | 100% | 100% | 0% | 80% | 80% |
| 18 | 5 | 0 | 100% | 100% | 100% | 100% | 100% | 100% |
| 19 | 5 | 0 | 100% | 100% | 100% | 100% | 0% | 0% |

## Failures

- case 3, transcript 20261116T024746-d49ff545 (NOT CHECKED): label NOT CHECKED not allowed
- case 4, transcript 20261116T024835-4d9bcb3d (NOT CHECKED): label NOT CHECKED not allowed
- case 7, transcript 20261116T024927-156a6ece (NO NUMBERS TO CHECK): forbidden call run_scenario
- case 9, transcript 20261116T024957-cef14086 (NOT CHECKED): label NOT CHECKED not allowed
- case 13, transcript 20261116T025104-e1109fc5 (NOT CHECKED): label NOT CHECKED not allowed
- case 17, transcript 20261116T025216-a01c77a1 (CHECKED): required phrase "change list" missing
- case 17, transcript 20261116T025222-d644410a (CHECKED): required phrase "change list" missing
- case 17, transcript 20261116T025228-7c9be4a0 (CHECKED): required phrase "change list" missing
- case 17, transcript 20261116T025234-8b80226f (NO NUMBERS TO CHECK): required phrase "change list" missing
- case 17, transcript 20261116T025237-4351b2c6 (CHECKED): required phrase "change list" missing

## Infrastructure (provider errors, excluded from every rate)

- none

## Manual review

- case 19, transcript 20261116T025255-3fdad609: 400
- case 19, transcript 20261116T025259-41c10892: 400
- case 19, transcript 20261116T025304-990849af: 400
- case 19, transcript 20261116T025311-83b6cfe7: 400
- case 19, transcript 20261116T025316-0590c9b0: 400
