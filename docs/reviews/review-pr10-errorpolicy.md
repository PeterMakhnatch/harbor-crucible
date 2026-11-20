# PR #10 adversarial review — crucible/seat-error-policy-and-lock-order

Checkout: /Users/petermakhnatch/Developer/crucible-wt/seat-error-policy-and-lock-order
Commit: 081258b0 "fix(seats): honor error-policy overrides and ignore participant order"
Base: 6aeb609e. Diff: lock.py +5, seats.py +19, tests +75. Read-only; no checkout edits.
Paths below are relative to the worktree root.

Observed (ran): 156 tests pass (tests/unit/test_trial_lock.py, tests/unit/trial/test_seats.py, tests/unit/models/test_trial_result_policy.py, 12.54s, venv python with PYTHONPATH=worktree/src; import verified from the worktree).
Probes (mine, re-runnable): /tmp/probe_pr10.py (lock + policy), /tmp/probe_pr10_seats.py (live SeatsTrial runs A1/A2/B/C/C2/D).
Observed good behavior first, so the breaks below are calibrated: reordered roster IS equal; swapped models per seat, kwargs drift, env drift, override_setup_timeout_sec drift, import_path drift are all NOT equal; serialized participant order is unchanged; all five seat ExceptionInfo creation sites now pass the override, the trial copy keeps it via model_copy (seats.py:411), and propagated errors get it via Trial._record_exception (trial/trial.py:701, pre-existing).

## Ranked findings

### 1. [High] "Ignore participant order" is half-wired: resume still rejects a reordered roster
- src/harbor/models/job/lock.py:223-226 — TrialLock now sorts participants by seat.
- src/harbor/models/trial/config.py:611-618 — TrialConfig.__eq__ still compares model_dump, which is participant-order-SENSITIVE.
- src/harbor/job.py:397-427 — _init_remaining_trial_configs matches planned vs existing trial configs with TrialConfig.__eq__ and raises ValueError ("Existing trial config does not match planned job config") when counts do not reconcile.
- Probe: TrialLock reordered == True, TrialConfig reordered == False (same two Participant objects).
- Effect: resuming a partially completed job with a reordered participants list passes the lock gate (job.py lock comparison near line 987) but crashes in config reconciliation. The only consumer where the PR fully delivers is job_diff _same_non_task_inputs (job_diff.py:369-370, lock ==). Fix at source: make TrialConfig.__eq__ participant-order-insensitive too, or sort participants in validate_participants (config.py:246-250) so one canonical order exists everywhere.

### 2. [High] should_grade is first-seat-wins; the three policy fields aggregate three different ways
- src/harbor/trial/seats.py:399-417 — _record_seat_errors copies the FIRST seat error (task.toml seat order) onto the trial and returns.
- src/harbor/trial/single_step.py (_run_verifier gate, policy.should_grade) — grading looks only at that one copied exception.
- src/harbor/models/trial/result.py:158-164 — reward_valid uses all() over recorded_exceptions (trial copy plus every seat, duplicates included).
- src/harbor/trial/queue.py:188-191 — retry uses all() over recorded exception TYPE NAMES.
- Probe A1 vs A2 (identical error set {NonZeroAgentExitCodeError, AgentTimeoutError}, override AgentTimeoutError.should_grade=False): A1 (exit seat first) verified=True; A2 (timeout seat first) verified=False. The override is silently ignored or silently supreme depending only on seat position in task.toml. The PR test parametrizes single-error trials only, so it cannot see this. Suggested rule: grade iff all recorded exceptions' policies should_grade (matches reward_valid and retry), implemented at _record_seat_errors/_run_verifier for seats.

### 3. [High] Propagated seat errors never grade, whatever should_grade says — diverges from single-agent
- src/harbor/trial/seats.py:240-244 (setup generic) and seats.py:350-354 (play generic) record then re-raise; src/harbor/trial/seats.py:277-291 _run aborts before _record_seat_errors/_run_verifier; src/harbor/trial/trial.py run() (lines 630-648 in this checkout) catches, records, recovers output, never verifies.
- Single-agent reference: SingleStepTrial._run_agent catches every Exception, records it, and _run_verifier then decides by policy.should_grade (single_step.py). Same config, different outcome by trial kind.
- Probe B: seat RuntimeError crash with override should_grade=True, has_valid_reward=True → verified=False. The PR's own crash/setup-crash test cases have effective should_grade=True (UNKNOWN_ERROR_POLICY default, error_policy.py:33-35; their override sets only should_retry and has_valid_reward) yet assert verified=False — the test bakes the divergence in under a parameter named `verified` that really encodes handled-vs-propagated. For the main custom-policy use case (an agent-specific exception type), should_grade override is dead in seat trials. Either catch-and-grade like single-step, or state the limit in the policy docs/commit message.

### 4. [Medium] "Custom retry policies apply" is not delivered by this diff; policy.should_retry has no consumer
- No src consumer of ExceptionInfo.policy.should_retry (grep: only should_grade in trial.py/single_step.py and has_valid_reward in result.py:162).
- Retry is decided by RetryConfig.is_retryable(exception_type) (models/job/config.py:331-334) in trial/queue.py:189. Translation of overrides into exclude_exceptions happens only in JobConfig._apply_retry_policy_overrides (models/job/config.py:503-518), pre-existing, and is skipped entirely when retry.exclude_exceptions was explicitly set (lines 506-510) — silent no-op.
- Probe D: seat crash, TrialConfig override RuntimeError.should_retry=False → recorded policy.should_retry=False, but RetryConfig().is_retryable('RuntimeError')=True; a queue built around a bare TrialConfig retries anyway. Before the PR, seat trials already recorded correct type names, so job-level retry behavior is byte-identical before/after; the commit message overclaims. The PR test asserts info.policy.should_retry, a field nothing acts on.

### 5. [Medium] A not-under-test seat controls trial grading and reward validity; overrides cannot be scoped per seat
- src/harbor/trial/seats.py:399-417 iterates all seats regardless of under_test; src/harbor/models/trial/result.py:142-154 recorded_exceptions includes every seat; src/harbor/trial/seats.py:314-329 stamps AgentTimeoutError on every still-running seat, under test or not.
- Probe C: only lee (under_test=false) fails auth, both under-test seats succeed → verified=False, whole run ungraded. Probe C2: only lee exits nonzero + has_valid_reward=False override → reward_valid=False for the agents under test.
- No per-seat remedy exists: override_error_policy is one trial-level dict keyed by exception type (models/trial/config.py:574). The same type from two seats is indistinguishable, and a "RuntimeError" override also matches Harbor's own infrastructure RuntimeErrors raised in _install_seat (seats.py:256 uid resolution, seats.py:261 log dir) — wrong-seat/wrong-layer application by construction. For Crucible-style helper/adversary seats this is the sharpest footgun in the change. At minimum needs a test pinning intended semantics; arguably trial-level policy should consider only under-test seats, with helper-seat errors recorded but not gating.

### 6. [Medium] Name-keyed policy: subclass exits escape the override and unknown types default to a valid reward
- src/harbor/models/trial/error_policy.py:33-35 — UNKNOWN_ERROR_POLICY = retry True, grade True, has_valid_reward True.
- src/harbor/models/trial/result.py:47,51 — from_exception keys on type(e).__name__ exactly.
- src/harbor/trial/seats.py:346 — the except clause is isinstance-based (NonZeroAgentExitCodeError), so it HANDLES subclasses whose names the policy then treats separately.
- Probes: a custom NonZeroAgentExitCodeError subclass (MyExit) → policy_override=None, UNKNOWN policy (retry+grade+valid) even with a NonZeroAgentExitCodeError override present; built-in subclasses ApiError and AgentAuthenticationError (agents/installed/base.py:40,145) likewise ignore a NonZeroAgentExitCodeError override. A user overriding "agent exited nonzero" reasonably expects all of these. Pre-existing table design, but the PR extends it to seats without a subclass test; handled-exit is exactly the path where unknown=valid turns a failed agent into a countable reward.

### 7. [Low-Medium] Duplicate seats: unvalidated in TrialLock, and order still matters for them
- src/harbor/models/job/lock.py:189-191 — participants field has no validator; validate_participants (models/trial/config.py:246-250) is wired only into TrialConfig/JobConfig.
- src/harbor/models/job/lock.py:225 — sort key is seat alone; Python sort is stable.
- Probes: TrialLock with two maya participants constructs fine and survives a JSON round-trip (lock.json is read back via model_validate_json in job.py and job_diff.py, so a hand-edited/corrupt lock can carry duplicates); the two duplicate orders compare NOT equal. The build path from a valid TrialConfig cannot produce duplicates, which caps severity. Cheap hardening: reuse validate_participants on TrialLock and sort by (seat, repr(_frozen_value(p))).

### 8. [Low] Lock equality false negatives on disk round-trip; secret masking inside the fingerprint
- src/harbor/models/job/lock.py:316-327 — _frozen_value dumps with mode="python". Probe: participant kwargs containing a Path → fresh lock != same lock after model_dump_json/model_validate_json (Path becomes str). job.py compares a freshly built lock against the lock read from disk, so such kwargs brick resume with FileExistsError. (1 vs 1.0 in kwargs compare equal; seat names are case-sensitive — both fine.)
- Probe: Participant env dumps mask the sensitive value only partially (sk-AAAA → '****', longer secret → 'sk-B****unt'). Short distinct secrets collide to '****' and compare equal; long ones leak a prefix/suffix into the equality fingerprint and the written lock.json. Pre-existing serializer behavior shared with AgentConfig, now also on the participant path the PR touches.

### 9. [Low] Concurrency and diagnostics residue
- src/harbor/trial/seats.py:92-104 — _seat_tasks re-raises errors.exceptions[0]; with several seats failing at once, trial-level policy follows TaskGroup listing order, and a seat cancelled before it records its own error never appears in recorded_exceptions, so queue.py's all() retry test runs over an incomplete set.
- Probe: setup-timeout ExceptionInfo carries the inner TimeoutError traceback ("TimeoutError: inner") because result.py:49 uses traceback.format_exc() for a different, freshly built exception; propagated setup crashes reach the trial record without a seat-name prefix (only the timeout branch seats.py:232-235 and _record_seat_errors seats.py:410 name the seat).

### 10. [Test gaps in the PR itself]
- tests/unit/trial/test_seats.py new parametrized test sets has_valid_reward = not verified (circular with the outcome it names), never asserts effective should_grade/has_valid_reward, and its assert reward_valid is False is vacuous for setup/setup-crash/crash because result.py:159-160 returns False whenever verifier_result is None. No multi-error trial, no not-under-test-only failure, no subclass, no should_grade flip test.
- tests/unit/test_trial_lock.py new test changes only seat name and agent name. My probes confirm model_name/kwargs/env/import_path/setup-timeout drift all compare unequal (good), but none of that is pinned; no duplicate-seat case; equality is model_copy vs model_copy, never fresh-built vs JSON-restored; no TrialConfig/job-resume leg for finding 1.

## Verdict
The narrow diff is correct as far as it goes (all seat sites pass the override; per-seat identity survives sorting — swapped models per seat do NOT compare equal). It is not merge-ready under its own title: finding 1 means participant order is still load-bearing on resume, finding 2 means multi-error grading is seat-position roulette, finding 3 means should_grade overrides do nothing for propagated/custom errors in seat trials, and finding 4 means the retry half of the commit message describes pre-existing JobConfig behavior, not this diff. Minimum before merge: fix 1 (canonical order at validation is the smallest change), decide and test the aggregation rule for 2 and the under-test scoping for 5, and either implement or explicitly document 3. Inferred (not observed): end-to-end job resume crash in finding 1 — shown at the equality layer plus the job.py:425 raise, not driven through a full Job resume run.
