# Adversarial review (crucible lane): Harbor fork PR #15

**Verdict: merge after fixes. Overall correctness: incorrect. Confidence: 0.99.**

[PR #15](https://github.com/PeterMakhnatch/harbor-multiagent/pull/15) adds a useful record for errors that the copy operation raises. The new field does not reliably say whether the files arrived. It can report `true` for incomplete data, `false` for a complete copy, and `null` after a cancelled copy.

Reviewed head: `5a4fbfc26609cfc978110271ac419f2118ce8c94`. Base: `6aeb609e31fd77e5f89ce3bcb018db8045520fb7`. The review did not change a PR branch. Cross-PR probes apply only the PR #15 source changes to scratch copies of the other PR heads, separately.

## Findings

### 1. [P2, confidence 0.99] Report incomplete copies separately from completed downloads

Anchor: `src/harbor/trial/seats.py:373`. The collector sets `true` whenever the download call returns. The filtered copy returns without a transfer if no files match (`src/harbor/environments/base.py:1374–1380`). It also accepts GNU tar's `file changed as we read it` status, which warns that the archive may be incomplete (`base.py:1403–1422`; `src/harbor/environments/tar_transfer.py:33–62`). A probe lists 2 selected files and supplies a tar stream cut after the first member. Extraction returns normally and the result says `true` with only 1 file. A second probe supplies the documented changed-file warning and a shortened file. The result still says `true`. Eval Lab's matching reader only warns on `false`, so neither result raises its evidence warning. Keep intentional filters and successful empty copies legal. Distinguish no selection or a known degraded copy from a complete transfer, and check that all selected members arrived before publishing a positive result.

Probes: `/tmp/probe_pr15/test_collection.py::test_real_filtered_archive_handler` (`missing_member`, `changed_member`), `::test_filtered_no_transfer`, and `/tmp/probe_pr15/test_freeze_consumer.py::test_real_docker_freeze_copies_logs_but_marks_no_transfer_true`. The archive probes inject the archive bytes and command results; they use Harbor's actual filtering and extraction code. The Docker probe exercises a real empty copy, a no-match filter, and a successful remote file copy.

### 2. [P2, confidence 0.99] Record cancelled downloads before propagating cancellation

Anchor: `src/harbor/trial/seats.py:373–375`. `asyncio.CancelledError` bypasses `except Exception`. If a child's pending download future is cancelled, `TaskGroup` accepts the cancelled child. The collector then sets its overall collection flag (`seats.py:347–354`), uploads the remaining files, and grades. The probe writes a partial file, cancels the future, and observes `logs_downloaded: null`, no trial exception, and `reward_valid: true`. A second external cancellation during recovery also saves `null` for an attempted copy. That is the same value the model assigns to an older result with no field (`src/harbor/models/trial/result.py:101–105`). Record a failed or interrupted attempt before re-raising cancellation. Keep cancellation of the parent visible and let a verified recovery replace the interrupted status.

Probes: `/tmp/probe_pr15/test_collection.py::test_child_cancelled_from_a_cancelled_future` and `::test_external_cancel_and_recovery[True]`. Controls: a single parent cancellation can recover the files and correctly records `true`, but does not grade. The outer `asyncio.timeout` probe shows that recovery can continue after the deadline; the caller receives `TimeoutError` after recovery. A backend exception that is a `TimeoutError` follows the normal `false` path.

### 3. [P2, confidence 0.99] Separate remote cleanup errors from transfer failure

Anchor: `src/harbor/trial/seats.py:375`. The filtered helper extracts the archive first, then awaits remote `rm` in `finally` (`src/harbor/environments/base.py:1420–1435`). A nonzero cleanup exit logs a warning, but an exception from cleanup escapes. Docker's timed command wrapper raises `RuntimeError` when a command times out (`src/harbor/environments/docker/docker.py:826–834`). If cleanup raises after successful extraction, the PR records `false` even when every selected byte reached the trial directory. The merged Eval Lab reader reports that the trajectory is unavailable even though the probe reads it byte for byte. Report cleanup failure independently. Keep the transfer result if the copy and extraction succeeded.

Probes: `/tmp/probe_pr15/test_collection.py::test_real_filtered_archive_handler[cleanup_timeout]` and `/tmp/probe_pr15/test_warning_consumer.py::test_complete_trajectory_warns_as_missing_after_cleanup_exception`. The second probe runs the actual seat-check function from [Eval Lab PR #2267](https://github.com/PeterMakhnatch/eval-lab/pull/2267), merge `3ee6a0ef3512fdc13b5f7d9a5a5bc43d20b2edca`, on the saved Harbor result.

## Verified non-issues and limits

- Ordinary exceptions set `false`. Probes cover permission denial, backend `TimeoutError`, and a truncated archive that raises during extraction. A partial file can remain on disk. `false` must not mean that no files are present.
- The seat adapter routes per-service downloads correctly. A probe drives the real `SeatEnvironment` → `ComposeServiceOpsMixin` → `DinDComposeOps` dispatch, with stubbed provider I/O. A remote copy permission error and a copy timeout both record `false`. A backend with no sidecar support raises the base `ServiceOperationsUnsupportedError`, which also records `false` in collection. This does not make that backend support seat tasks. No cloud service ran.
- Live verification and reward validity do not change. The trial uploads `seats/` and runs the shared verifier after a caught download error (`src/harbor/trial/seats.py:278–286`). `TrialResult.reward_valid` checks verifier rewards and recorded exceptions, not the download field (`src/harbor/models/trial/result.py:147–169`). `src/harbor/job.py:372–377` uses that validity when selecting rewards. The probe observes `false` and `reward_valid: true` together. This matches the PR's stated intent. A verifier that needs these files can still return a different reward.
- Legacy results still parse. A new `install_only` run also saves `null` because collection never starts. Document that distinction from an interrupted attempt. A genuinely empty log directory is allowed; not every agent writes a trajectory. An explicit filter that selects nothing is not itself a backend error.
- PR #15 adds no collection deadline. Local Docker's unfiltered `compose cp` passes no timeout (`src/harbor/environments/docker/docker_unix.py:298–320`). DinD bounds its Compose copy stage (`src/harbor/environments/dind_compose.py:45,269–283`). `Trial.run()` recovers after an outer cancellation before it re-raises (`src/harbor/trial/trial.py:632–638`). These behaviors predate PR #15; they do not make a hung copy set `false`.

## PR interactions

- **[PR #11: regrade](https://github.com/PeterMakhnatch/harbor-multiagent/pull/11), `0005331cdcb4f6f169543d814edc94366dc21d4a`.** `src/harbor/trial/regrade.py:968–975` carries the new field into the regrade result. The validator checks the roster, `seat_results`, and each `seats/<seat>/agent/` directory (`:978–1038`). It never checks the download flag. The live trial creates those directories before any copy (`src/harbor/trial/seats.py:137`). The combined probe shows that a source with `false` and an empty or partial directory reaches the verifier and can save a valid reward. It also shows that deleting the directory prevents grading, as intended. Legacy and successful empty directories still grade. The current regrade branch explicitly warns that seat logs have no integrity manifest. Before shipping these features together, make known-failed capture a separate regrade admission decision. Reject it or require an explicit override. Do not treat `true` as proof of integrity, or treat a legacy `null` as a known failure. Probe: `/tmp/probe_pr15/test_regrade_consumer.py::test_regrade_seat_download_flag_dispatch`.
- **[PR #35: freeze](https://github.com/PeterMakhnatch/harbor-multiagent/pull/35), `bfbfe127e1e40b4dbddf503b8ca3f4914b0f40be`.** The current head freezes seats before collection on both normal and recovery paths (`src/harbor/trial/seats.py:290–304`). A failed freeze records `SeatFreezeError`, which still permits verification but makes the reward invalid by default (`src/harbor/models/trial/result.py:160–185`, `src/harbor/models/trial/error_policy.py:80–85`). This differs from the earlier review comment on #15. The combined probes show failed freeze / successful copy → `true`, invalid reward; successful freeze / failed copy → `false`, valid reward. Real Docker confirms that a frozen seat's remote log can still reach the verifier. It also confirms that successful freeze does not prevent the no-match case from returning `true`. Freeze helps prevent after-play writes; it does not check the transfer. Probes: `/tmp/probe_pr15/test_freeze_consumer.py`.

## Minimum bar to merge

1. Make the recorded state distinguish failed or interrupted transfers from no files selected and successful transfers. Do not publish a positive completeness signal for a known partial copy. Keep the safety filters intact.
2. Keep cleanup errors separate from transfer status. Add regressions for cancellation, partial archive results, and a cleanup timeout after extraction. Update the field contract and the Eval Lab warning so they state what the record proves.
3. Keep live grading independent of the capture status, as this PR intends. Before enabling seat regrade on these results, make PR #11 handle a known failed transfer explicitly. Keep freeze policy separate.

## Checks executed

- Exact PR #15 head: **54 passed** across `tests/unit/trial/test_seats.py`, `tests/unit/models/test_trial_participants.py`, and `tests/unit/environments/test_seat.py`.
- PR #15 collection probes: **18 cases passed**, including the separate outer timeout run. These probes assert the observed behavior, including the defects above.
- Combined scratch branches: **5 regrade cases passed**, **3 freeze policy cases passed**, and **1 local Docker oracle/nop case passed**. The regrade uses a stub verifier and runs the actual validation, copy and result code.
- Merged Eval Lab warning consumer: **1 case passed**. No model calls, paid runs, or remote container execution.

Probe sources and output: `/tmp/probe_pr15/`.

Posted review: https://github.com/PeterMakhnatch/harbor-multiagent/pull/15#issuecomment-7031459296
