# Fork merge plan

Merge **#36 → #37 → #38 → #10 → #12 → #21 → #11**. Do not merge the integration branch itself. It is a verified reference for the individual PRs.

- Fork base: `origin/main` at `6aeb609e31fd77e5f89ce3bcb018db8045520fb7`.
- Integration: [`crucible/stack-integration`](https://github.com/PeterMakhnatch/harbor-multiagent/tree/crucible/stack-integration) at `9a87192293f22530b6ef7bf7c93b665b6c6b6da2`.
- No PR was opened or merged. No PR head or upstream branch changed. No model calls ran.

## Merge steps and changes to make

Use the pinned heads below to reproduce the integration. Check the PR head and base again before merging each PR. The merge commits on the reference branch show the conflict resolutions. The final commit shows the additional regression fixes and tests.

| Step | PR and fetched head | Reference merge | Result | Change after the preceding step lands |
| --- | --- | --- | --- | --- |
| 1 | [#36](https://github.com/PeterMakhnatch/harbor-multiagent/pull/36) `3d94df4b59d6f1cb28c255c6b89eaabad066e85f` | `7d451aa7` | Clean | No predecessor. Merge the timeout and scoring guidance as written. |
| 2 | [#37](https://github.com/PeterMakhnatch/harbor-multiagent/pull/37) `566e5b569ce2a216660a09a7646015a35d111bff` | `18bc3ddb` | Clean | No manual edit. Keep both the timeout guidance and the image command guidance in `docs-mintlify/tasks/multi-agent.mdx`. |
| 3 | [#38](https://github.com/PeterMakhnatch/harbor-multiagent/pull/38) `d017eae33d9bde35b37c17d8841fadb3a58bb5e8` | `82a78a05` | Clean | No manual edit. Keep collection in the live verifier environment before it stops. |
| 4 | [#10](https://github.com/PeterMakhnatch/harbor-multiagent/pull/10) `86372e2e557743a819c53b401c0d3685dd593157` | `61349174` | Clean | No manual edit. Preserve the canonical participant order and the grading decision across all recorded seat errors. |
| 5 | [#12](https://github.com/PeterMakhnatch/harbor-multiagent/pull/12) `5d77ccbc40901d8119c07f0a7c2d900859659ea7` | `9248e430` | 2 conflicted files | Keep both `CHANGELOG.md` entries. In `src/harbor/trial/seats.py`, combine seat-tagged setup and execution log contexts with #10's timeout conversion and policy-aware exception handling. Do not restore the separate nonzero-exit handler. Use `_finish_seats` in the normal and recovery paths. Record the diagnostic error before collection, and emit `SEAT_END` after collection. Keep #10's verifier gate. |
| 6 | [#21](https://github.com/PeterMakhnatch/harbor-multiagent/pull/21) `5f0f01253592b712ff5da429c2dbcceccf11198a` | `50f251ad` | 1 conflicted file | In `docs-mintlify/tasks/multi-agent.mdx`, keep **Live logs and Python hooks** followed by **Job seat statistics**. Keep the temporary regrade refusal until #11 lands. |
| 7 | [#11](https://github.com/PeterMakhnatch/harbor-multiagent/pull/11) `d8750cd5f98ea0e490e74048deecf240dbb06dd6` | `7c5b75e1` plus `9a87192293` | 2 conflicted files | In `src/harbor/trial/regrade.py`, remove #21's blanket refusal. Keep the check that rejects replay into a target without matching seats. Keep `SeatsRegradeTrial` copying the recorded `seat_results`. In `src/harbor/trial/trial.py`, keep both `retry_failed_artifacts` and `seats_dir` on the separate verifier. Then apply the follow-up changes below. |

For #11, also apply these changes from `9a87192293`:

- Compare participants by seat using the serialized JSON representation. Use `mode="json", exclude_none=True`, as the trial lock does.
- Apply a current regrade override for the exact exception type first. Use its persisted `policy_base_type` next. Then use the recorded override or source configuration.
- Add optional `SeatResult.logs_downloaded` metadata. Set it after the live seat log transfer attempt. Reject `false` on replay. Preserve support for legacy records that omit the field.
  **Owner note:** `SeatResult.logs_downloaded` is the field that rainy's PR #15 (`rainy/seat-log-completeness`) adds. Do not add it a second time: merge #15 before #11 and keep only #11's refusal of `false`, which already reads the raw record and works with or without #15.
- Update #21's test for replay into a single-agent task. Assert the matching-seat error and prove the verifier does not produce a reward.
- Keep the integrated tests for seat stats, inherited error policies, `SEAT_END` ordering and artifact phase replay. Document the log status and the replay of recorded `post_verifier` artifacts.

**OBSERVED:** The recommended order had 4 clean merges and 3 conflicted merges, with 5 conflicted files in total. The alternate order **#21 → #11 → #10 → #12 → #36 → #37 → #38** had 4 conflict stops in a `git merge-tree` preview. Those stops were #11 (`regrade.py`), #12 (`multi-agent.mdx`, `seats.py`), #37 (`CHANGELOG.md`), and #38 (`trial.py`). The preview used virtual commits, not the PR branches.

**INFERRED:** A new base or squash merges can change the exact conflict markers. Use the behavior in the reference branch to guide the resolution.

## Cross-PR findings

| Interaction | Evidence | Result |
| --- | --- | --- |
| #10 canonical participant order × #11 roster check × #21 seat stats | `test_regrade_stats_keep_seat_keys_for_reordered_participants` | **OBSERVED:** The original replay rejected equivalent settings when a `Path` in memory became a string in the source record. After the fix, a reverse-ordered legacy record regrades. The saved result retains both seat groups, roles, rewards, usage, and error counts. The generic reward does not enter either seat group. |
| #10 policy inheritance × #11 replay | `test_seat_regrade_applies_base_then_exact_error_override` | **OBSERVED:** Replay ignored a new no-grade override on the recorded base type and ran the verifier. After the fix, the base override prevents grading. An exact-type override still takes priority. |
| #12 `SEAT_END` × #38 collection phases | `test_record_shared_edit_task_and_regrade_in_fresh_environment` | **OBSERVED:** All seat-end callbacks completed before the first task artifact collection. The verifier ran next. The retry collected the late artifact as `post_verifier`. The callbacks did not wait for either artifact phase. |
| #11 regrade × #38 `post_verifier` record | Same live-record replay test | **OBSERVED:** The fresh verifier received the exact recorded late bytes before it ran. The new record preserved the original manifest entry and phase. No extra retry or phase change was needed. |
| #12 seat completion × #11 log integrity check | The failed-transfer case of the same test | **OBSERVED:** Before the fix, a failed transfer produced the same unknown status as a successful transfer. After the fix, `SEAT_END` records the failure and replay refuses that source before starting verification. |
| #21 temporary refusal × #11 seat regrade | `test_regrade_refuses_seat_source_even_if_target_is_single_agent` | **OBSERVED:** #21 expected the old blanket refusal. The revised regression test confirms that replay into a single-agent target still fails without a reward. |

**INFERRED:** A successful transfer does not prove that the source agent produced every expected log. Regrade does not restore original containers, services, or live state. Review the verifier's declared inputs before using a historical record.

## Verification

All local checks used the same existing fork virtual environment. The default unit command was `PYTHONPATH="$PWD/src" <venv>/bin/python -m pytest -q -p no:cacheprovider tests/unit`. A second run added `--continue-on-collection-errors` on both trees.

| Check | Main | Integration | Comparison |
| --- | --- | --- | --- |
| Default unit command | 20 collection errors, 18 skips | 20 collection errors, 18 skips | Same 20 collection errors. Missing optional packages and the local Vercel import block a clean run. |
| Unit command with collection continuation | 13,942 passed; 473 skipped; 222 failed; 240 errors | 14,039 passed; 473 skipped; 222 failed; 240 errors | 97 more passing tests. The failed and errored test IDs match exactly. |
| Focused cross-PR unit tests | Not applicable | 402 passed; 2 skipped | All 5 new interaction cases passed, plus the single-agent rejection regression. |
| `uv tool run ty@0.0.49 check --python <venv> src` | 256 diagnostics | 256 diagnostics | No new or removed diagnostics after matching severity, rule, message and file. |
| Ruff `0.15.17`: `check .` and `format --check .` | Passed; 1,705 files formatted | Passed; 1,708 files formatted | Both checks passed on both trees. |
| `tests/runtime/test_verifier_artifacts_docker.py` | File not present | 3 passed | Shared single-agent, separate single-agent and shared seat modes passed on Docker `29.8.0`. |
