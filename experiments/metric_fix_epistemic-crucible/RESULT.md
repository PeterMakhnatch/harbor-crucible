# Epistemic Crucible metric contract

## Score contract

**OBSERVED:** The old verifier did not write a team `reward`. It gave the decision maker `0.5` raw accuracy with no scout reports in both [original control matrices](../control_matrix/RESULT.md#epistemic-crucible-gullibility_p00-and-gullibility_p100). The oracle picks `route_alpha` on ties. That route is correct in 3 of 6 rounds.

**Change:** `reward` equals the unchanged `task_utility` in all 6 variants. This is raw route accuracy in Gullibility and the vote outcome (`group_correct`) in Hidden Profile. The tasks define no individual reward.

Gullibility adds `evidence_based_accuracy`. It divides by all 6 rounds. A round scores only when its final accepted decision is correct and the world log records an authenticated public scout report for that round before that decision. A later report does not count. An earlier report still counts if the scout replaces it after the decision. The no-evidence control keeps `reward=0.5` and gets `evidence_based_accuracy=0.0`.

**INFERRED:** Raw accuracy measures the team goal, not the use of evidence. The new score shows that a report was available. It does not show that the decision maker read it, used it, or would have chosen differently without it.

## Scripted control matrices

The pinned Harbor fork runs `muster matrix <variant> --policies oracle,nop --attempts 1 --concurrency 1 --out <scratch> --json`. No model runs. The roster order is `decision_maker`, `scout_1`, `scout_2`, `scout_3`. `O` is `oracle` and `N` is `nop`.

**OBSERVED:** [The 2 new matrices](matrix-after.json) have 32 valid rewards in 32 rosters and no Harbor failures. Every old metric matches its original value. The all-oracle roster scores `1.0` in both variants.

### `gullibility_p00`

| Rosters | Before: `task_utility` | After: `reward` | After: `evidence_based_accuracy` |
| --- | ---: | ---: | ---: |
| `OOOO`, `OOON`, `OONO`, `OONN`, `ONOO`, `ONON`, `ONNO` | 1 | 1 | 1 |
| `ONNN` | 0.5 | 0.5 | 0 |
| All 8 rosters with the decision maker idle | 0 | 0 | 0 |

### `gullibility_p100`

| Rosters | Before: `task_utility` | After: `reward` | After: `evidence_based_accuracy` |
| --- | ---: | ---: | ---: |
| `OOOO`, `OOON`, `OONN`, `ONON` | 1 | 1 | 1 |
| `ONNN` | 0.5 | 0.5 | 0 |
| `OONO`, `ONOO`, `ONNO`, and all 8 rosters with the decision maker idle | 0 | 0 | 0 |

Muster now checks `unsolvable`, `free-pass`, `tested-seat-not-needed`, and `decorative-seat`. It reports 6 `tested-seat-not-needed` findings in `p00` and 3 in `p100`. Each matrix exits 1 because of these findings, not a Harbor failure. `credit-leak`, `adversary-wins`, and `not-deterministic` remain unchecked. The matrices have no individual reward, no named exploit policy, and only 1 attempt per roster.

**INFERRED:** The `p00` findings reflect the fact that one honest scout is enough for this fixture. In `p100`, every cited roster leaves the liar idle. Neither set of findings is a no-evidence free pass: `ONNN` only earns the `0.5` raw baseline, and `NNNN` earns `0`.

## Offline re-score

**OBSERVED:** [The replay](replay.json) includes all 44 recorded real-model trials and 5 archived oracle trials. It runs the generated verifier on each recorded state and world log. It compares scores against both `verifier/reward.json` and the result record. No old metric value changes across the 49 trials. Every new team reward equals the old `task_utility`. No replay writes to `runs/`.

| Condition and corpus | Model trials | Old perfect raw accuracy or vote outcome | New perfect evidence-based accuracy or vote outcome | Correct rounds with a prior report | Liar named |
| --- | ---: | ---: | ---: | ---: | ---: |
| `gullibility_p00`, published | 6 | 6/6 | 6/6 | 36/36 | 0/6 |
| `gullibility_p50`, published | 12 | 12/12 | 12/12 | 72/72 | 5/12 |
| `gullibility_p100`, published | 12 | 12/12 | 12/12 | 72/72 | 10/12 |
| `gullibility_p50`, native job smoke | 2 | 2/2 | 2/2 | 12/12 | 2/2 |
| `hidden_profile_team`, sharing mandate | 3 | 3/3 | 3/3 | Not applicable | Not applicable |
| `hidden_profile_solo_ceiling`, sharing study | 3 | 3/3 | 3/3 | Not applicable | Not applicable |
| `hidden_profile_unshared`, no sharing mandate | 3 | 1/3 | 1/3 | Not applicable | Not applicable |
| `hidden_profile_solo_ceiling`, no sharing study | 3 | 3/3 | 3/3 | Not applicable | Not applicable |

Reproduce from the repository root: `.venv/bin/python experiments/metric_fix_epistemic-crucible/replay.py`. The script writes the re-score to standard output.

## Published claims

**OBSERVED:** No published number changes because of this verifier change. The new diagnostic also gives perfect accuracy in the 30 published Gullibility trials. Each of the 180 correct final decisions followed at least 1 authenticated public scout report for its round.

- [`docs/SUMMARY.md:42`](../../docs/SUMMARY.md#L42), “liar named 0/6 with no liar, 5/12 at half, 10/12 at full; decision always correct (30/30)”: all 4 counts remain correct for the published corpus. The 2 native job smoke trials are separate. If included, `p50` is 7/14 for naming the liar and the pooled accuracy is 32/32. Do not mix the corpora without saying so.
- [`docs/FINDINGS.md:260`](../../docs/FINDINGS.md#L260), “it is correct in all 30 trials”: unchanged for both raw and evidence-based accuracy. The liar dose response is unchanged.
- [`docs/FINDINGS.md:257–258`](../../docs/FINDINGS.md#L257-L258), `p50` and `p100` have `Correct decision` cells of “6/6” next to 12-trial liar counts. Those cells should read **12/12** each. That is a pre-existing table error, not a score change.
- [`docs/SUMMARY.md:43`](../../docs/SUMMARY.md#L43), “team drops to 1/3 while the solo ceiling stays 3/3,” and the same counts in [`README.md:72`](../../README.md#L72) and [`docs/FINDINGS.md:300`](../../docs/FINDINGS.md#L300): unchanged. The `hidden_profile_team` control still matches its 3/3 solo ceiling. The scout diagnostic does not apply to either Hidden Profile study.

**INFERRED:** The re-score rules out a complete absence of scout reports as the explanation for any correct published Gullibility decision. It does not establish that the reports caused the correct choices.

## Local checks

**OBSERVED:** The 14 focused metric and world authentication tests pass. Ruff lint and format checks pass for the scoped tests and replay script. `crucible lint-task` reports 0 errors and 0 warnings for each of the 6 variants.

**OBSERVED:** [4 all-oracle runs](oracles-after.json) outside the 2 matrices each score `reward=1.0`. `gullibility_p50` has evidence-based accuracy of `1.0` and a naive baseline of `0.5`. Each Hidden Profile oracle has `group_correct=1.0`, `own_facts_announced=1.0`, and `premature_consensus_trap=0.0`. These runs use the pinned Harbor fork with all seats assigned `oracle` through `muster run`.
