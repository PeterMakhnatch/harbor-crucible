# Fork merge plan

Merge **#36 → #37 → #38 → #10 → #12 → #21 → #11**. Do not merge the integration branch itself. It is a verified reference for the individual PRs.

- Fork base: `origin/main` at `6aeb609e31fd77e5f89ce3bcb018db8045520fb7`.
- Integration: [`crucible/stack-integration`](https://github.com/PeterMakhnatch/harbor-multiagent/tree/crucible/stack-integration) at `723e9bd4db14df170292e0ba5f980f531bce5a15`.
- This rebuild did not open or merge a PR, change a PR branch, or make model calls.

## Merge steps and changes to make

Use the pinned heads below to reproduce the integration. Check the PR head and base again before merging each PR. The merge commits on the reference branch show the conflict resolutions. The final commit shows the additional regression fixes and tests.

| Step | PR and fetched head | Reference merge | Result | Change after the preceding step lands |
| --- | --- | --- | --- | --- |
| 1 | [#36](https://github.com/PeterMakhnatch/harbor-multiagent/pull/36) `3d94df4b59d6f1cb28c255c6b89eaabad066e85f` | `4d71fa19` | Clean | No predecessor. Merge the timeout and scoring guidance as written. |
| 2 | [#37](https://github.com/PeterMakhnatch/harbor-multiagent/pull/37) `566e5b569ce2a216660a09a7646015a35d111bff` | `a290cd1d` | Clean | No manual edit. Keep both the timeout guidance and the image command guidance. |
| 3 | [#38](https://github.com/PeterMakhnatch/harbor-multiagent/pull/38) `21e07d9512b613626f7799d2383aa5dd58b96a72` | `e63e39b9` | Clean | No manual edit. Keep the retry in the shared verifier environment and keep late outputs out of regrade. |
| 4 | [#10](https://github.com/PeterMakhnatch/harbor-multiagent/pull/10) `86372e2e557743a819c53b401c0d3685dd593157` | `bfacea5f` | 1 conflicted file | In `src/harbor/trial/seats.py`, keep #10's seat collection order and #38's `pre_verifier` flag. Override `_should_verify` in `SeatsTrial` to check every recorded error. Use it for both collection phase and grading. |
| 5 | [#12](https://github.com/PeterMakhnatch/harbor-multiagent/pull/12) `e7aba94a84d5585eeffa1dbd4acd4deceaaad7f0` | `abfe6e6a` | 2 conflicted files | Keep the image command, trial hooks, and live log entries in `CHANGELOG.md`. In `src/harbor/trial/seats.py`, combine seat-tagged log contexts with policy-aware errors and #10's timeout conversion. Use `_finish_seats` without removing the pre-verifier flag. Emit `SEAT_END` after seat log collection. Update the seat test double to accept #38's `retry_artifacts_dir` keyword. |
| 6 | [#21](https://github.com/PeterMakhnatch/harbor-multiagent/pull/21) `d0e0bddc72118b2f4033421dd24d04edef98856b` | `30b7c5e7` | 1 conflicted file | In `docs-mintlify/tasks/multi-agent.mdx`, keep the live logs and seat stats sections. Keep the temporary regrade refusal until #11 lands. |
| 7 | [#11](https://github.com/PeterMakhnatch/harbor-multiagent/pull/11) `d8750cd5f98ea0e490e74048deecf240dbb06dd6` | `13f303c5` plus `723e9bd4` | 2 conflicted files | In `src/harbor/trial/regrade.py`, remove #21's blanket refusal. Keep the matching-seat check, `seat_results` copying, and #38's artifact rules. In `src/harbor/trial/seats.py`, keep both `deque` and `Sequence` imports. The `seats_dir` verifier argument merges cleanly. Apply the follow-up changes below. |

For #11, also apply these changes from `723e9bd4`:

- Compare participants by seat using the serialized JSON representation. Use `mode="json", exclude_none=True`, as the trial lock does.
- Apply the current regrade override for the exact exception type first. Use its persisted `policy_base_type` next. Then use the recorded override or source configuration.
- Update #21's single-agent target test. Assert the matching-seat error and that the verifier does not produce a reward.
- Keep the integrated seat stats, inherited policy, seat event ordering, and late artifact refusal and exclusion tests. Document the replay restriction.
- Merge rainy's [#15](https://github.com/PeterMakhnatch/harbor-multiagent/pull/15) before #11 for live `SeatResult.logs_downloaded` metadata. Do not add the field again in #11. This 7-PR branch does not include #15. It retains #11's refusal of `false` in a stored record and accepts legacy records with no status.

**OBSERVED:** The recommended order had 3 clean merges and 4 conflicted merges, with 6 file conflicts. The alternate order **#21 → #11 → #10 → #12 → #36 → #37 → #38** had 4 conflict stops in a `git merge-tree` preview. Those stops were #11 (`regrade.py`), #12 (`multi-agent.mdx`, `seats.py`), #37 (`CHANGELOG.md`), and #38 (`seats.py`). The preview used virtual commits with no manual resolutions, not the PR branches.

**INFERRED:** A new base or squash merges can change the exact conflict markers. Use the behavior in the reference branch to guide the resolution.

## Cross-PR findings

| Interaction | Evidence | Result |
| --- | --- | --- |
| #10 canonical participant order × #11 roster check × #21 seat stats | `test_regrade_stats_keep_seat_keys_for_reordered_participants` | **OBSERVED:** The original replay rejected equivalent settings when a `Path` in memory became a string in the source record. After the fix, a reverse-ordered legacy record regrades. The saved result retains both seat groups, roles, rewards, usage, and error counts. The generic reward does not enter either seat group. |
| #10 policy inheritance × #11 replay | `test_seat_regrade_applies_base_then_exact_error_override` | **OBSERVED:** Replay ignored a new no-grade override on the recorded base type and ran the verifier. After the fix, the base override prevents grading. An exact-type override still takes priority. |
| #10 seat grading gate × #38 collection phases | `test_all_seat_error_policies_gate_verification` | **OBSERVED:** The seat trial requests `pre_verifier` collection only when all recorded seat errors permit grading. Changing the order of the seat errors does not change the gate. |
| #12 `SEAT_END` × #38 collection phases | `test_record_shared_edit_task_and_regrade_in_fresh_environment` | **OBSERVED:** All seat-end callbacks completed before the first task artifact collection. The verifier ran next. The retry collected the late artifact as `post_verifier`. |
| #11 regrade × #38 `post_verifier` record | Same live-record replay test on `723e9bd4` | **OBSERVED:** The old integration seeded verifier-authored output into the fresh verifier. This was a defect (rainy's #38 review, P1). With #38 at `21e07d95`, regrade refuses a source when a declared input needs late bytes. Without that declaration, regrade succeeds and excludes the late file, its symlink alias, and its manifest entry. |
| #11 regrade × #15 log completion metadata | `test_seat_regrade_checks_raw_log_download_status` | **OBSERVED:** #11 rejects a stored `logs_downloaded: false` before verification and accepts `true` or `null`. #15 owns writing this field and is outside the 7-PR stack. |
| #21 temporary refusal × #11 seat regrade | `test_regrade_refuses_seat_source_even_if_target_is_single_agent` | **OBSERVED:** #21 expected the old blanket refusal. The revised regression test confirms that replay into a single-agent target still fails without a reward. |

**INFERRED:** A successful transfer does not prove that the source agent produced every expected log. Regrade does not restore original containers, services, or live state. Review the verifier's declared inputs before using a historical record.

## Verification

All local checks used the same existing fork virtual environment. The main SHA did not change, so this comparison uses the recorded main baseline. The default unit command was `PYTHONPATH="$PWD/src" <venv>/bin/python -m pytest -q -p no:cacheprovider tests/unit`. A second run added `--continue-on-collection-errors` on both trees.

| Check | Main | Integration | Comparison |
| --- | --- | --- | --- |
| Default unit command | 20 collection errors, 18 skips | 20 collection errors, 18 skips | Same 20 collection errors. Missing optional packages and the local Vercel import block a clean run. |
| Unit command with collection continuation | 13,942 passed; 473 skipped; 222 failed; 240 errors | 14,059 passed; 473 skipped; 222 failed; 240 errors | 117 more passing tests. The failed and errored test IDs match exactly. |
| Focused cross-PR unit tests | Not applicable | 652 passed; 4 skipped | All seat, regrade, stats, artifact, lock, and Docker unit regressions passed. |
| `uv tool run ty@0.0.49 check --python <venv> src` | 256 diagnostics | 256 diagnostics | No new or removed diagnostics after matching severity, rule, message and file. |
| Ruff `0.15.17`: `check .` and `format --check .` | Passed; 1,705 files formatted | Passed; 1,708 files formatted | Both checks passed on both trees. |
| `tests/runtime/test_verifier_artifacts_docker.py` | File not present | 3 passed | Shared single-agent, separate single-agent, and shared seat modes passed on Docker `29.8.0`. The run used `/tmp/crucible-docker-slot.sh`. |
