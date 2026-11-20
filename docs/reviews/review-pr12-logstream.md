# Adversarial review — Peter fork draft PR #12 `crucible/seat-log-streaming`
Commit `1bbc2e6b` "attribute live logs and lifecycle hooks to each seat".
Checkout reviewed: `/Users/petermakhnatch/Developer/crucible-wt/seat-log-streaming` (read-only, no edits).
Diff scope: `src/harbor/trial/hooks.py` (+6), `seats.py` (+6/−), `trial.py` (+6/−), `tests/unit/trial/test_seats.py` (+146).

Evidence method: full diff + `trial/hooks.py`, `trial/trial.py` (`_log_context`/`_emit`/`run`), `trial/seats.py`,
`environments/base.py`+`seat.py`+`docker/docker.py`+`compose_service_ops.py`+`dind_compose.py`,
consumers `trial/queue.py`, `job.py`, `server/executor.py`. PR tests run: **31 passed**
(`test_seats.py`+`test_hooks.py`+`test_log_streaming.py`, harbor-multiagent venv + PYTHONPATH).
Findings marked PROBE were reproduced with throwaway scripts in `/tmp/probe_pr12.py`, `/tmp/probe_pr12b.py`
(reusing the PR's own fake-Compose harness); quoted outputs are observed, not inferred.

Verdict: the per-seat `LogEntry.seat` attribution core is sound on local Docker (see #11), and
event ordering on a single cancel is correct (see #14). The breaks are around it: hook/log-callback
failures become fake seat crashes, hook latency eats the agent timeout, the feature silently never
streams on the cloud seat backends, and `SEAT_END` fires before a seat is actually finished.

---

## CRITICAL

### 1. A raising hook or log callback kills the trial and is recorded as a seat-agent crash — `src/harbor/trial/seats.py:332`, `seats.py:340-347`, `src/harbor/trial/trial.py:624-625`, `trial.py:610-611`
`Trial._emit` awaits hooks with no isolation (`for hook in self._hooks[event]: await hook(hook_event)`),
and `SEAT_START` is emitted *inside* `_play_seat`'s `try:` whose `except Exception` writes
`seat.result.exception_info = ExceptionInfo.from_exception(exc)` and re-raises. Consequences, all PROBE-verified:
- P1: `SEAT_START` hook raising `RuntimeError("hook db down")` → **no agent ever runs**, all 3 seats record
  `exc=RuntimeError msg=hook db down`, trial `exception_type=RuntimeError`, never verified. An observer
  outage is indistinguishable in `result.json` from agent crashes, and the TaskGroup (`_seat_tasks`,
  `seats.py:93-104`) cancels every sibling seat: one hook bug has N-seat blast radius.
- P3: `SEAT_END` hook raising in the `finally:` (`seats.py:345-347`) replaces the seat's real outcome.
  Seat exited non-zero (`NonZeroAgentExitCodeError`, normally recorded + graded, `seats.py:340-341`),
  hook raised `ValueError` → trial exception became `ValueError: metrics sink broken`, `verifier_result=None`,
  grading bypassed. A raising `finally` also masks an in-flight non-zero/crash exception entirely,
  and preempts remaining hooks for the same event (sequential loop, `trial.py:624-625`).
- P4: a raising *log callback* is worse — it raises inside the environment's exec output path
  (`trial.py:601-611` emit → Docker `on_output`), so the exec itself fails: all seats recorded
  `exc=ConnectionError ("log websocket closed")`, trial failed, never verified. Closing a log viewer
  mid-trial fails the trial and blames the agents.
Pre-existing `_emit` fragility for START/END, but the PR multiplies call sites by 2·N and puts them
inside a TaskGroup and a `finally:`. Fix direction: isolate hook/log exceptions (log + continue, like
`harbor_hub`'s own callback already does defensively at `cli/plugins/harbor_hub.py:118-124`), and emit
`SEAT_START` outside the agent-exception `try:`.

### 2. Hook latency is charged to the agent timeout; finished agents get marked `AgentTimeoutError`; a hung hook blocks shutdown — `seats.py:303-322` vs `seats.py:347`
`_play` starts the timeout clock at task creation (`asyncio.wait(under_test, timeout=timeout_sec)`)
and marks **every not-done task** timed out, but a seat task is not done until its `SEAT_END` hooks return.
PROBE P8: all three agents finished instantly, `SEAT_END` hook hung → at the 0.2 s timeout every seat was
cancelled mid-hook and the trial recorded `Seat 'maya': Agent execution timed out after 0.2 seconds`
for agents that had completed their work. Any slow-but-legit hook (DB write, upload) near the timeout
converts successes into timeouts. `SEAT_START` has the symmetric problem: hook await precedes
`agent.run` inside the same budget (`seats.py:332-335`), so observers steal agent time.
PROBE P7: with the default 30 s timeout, a suspended `SEAT_END` hook blocked whole-trial cancellation —
repeated `run.cancel()` did not make `trial.run()` return within 1 s (TaskGroup joins children stuck in
`finally:` hooks; hooks are neither shielded-with-deadline nor time-bounded anywhere). A dead hook
consumer can hang trial teardown indefinitely. Fix direction: bound `_emit` (timeout/shield policy at
least in `finally:`), and set `execution.finished_at`/task-done semantics so hook time is not agent time.

### 3. On every non-Docker seat backend the "live logs" silently never stream — `src/harbor/environments/compose_service_ops.py:108-131`, `dind_compose.py:88-122`, `dind_compose.py:297-313`; only `docker/docker.py:1516` consults the callback
Attribution rides on `SeatEnvironment.exec` bridging `self._output_callback()` into
`project.scoped_output_callback(...)` (`environments/seat.py:76`), which only helps if the project's
`service_exec` actually reads `project._output_callback()`. Local Docker does
(`docker/docker.py:1512-1517`). The DinD cloud backends that `seat.py:19-23` advertises ("the docker
environment and the cloud environments that run Compose") do not: `ComposeServiceOpsMixin.service_exec`
routes non-main services straight to `transport.service_exec` (`compose_service_ops.py:125-131`), and
`DinDComposeOps.exec` is fully buffered via `_compose_exec` with zero `_output_callback` references in
the file. Same for `langsmith.py:651-676` and `runta/environment.py:462-480` (buffered `_compose`).
Mixins affected include modal/daytona/gke-style DinD providers (`prime.py`, `kernel.py`, `novita.py`,
`sail.py`, `islo.py`, `cwsandbox.py`, `ec2.py`, `vercel/`, …): for a seat service (never `main`, except a
seat literally named `main`) the bridged callback is dropped on the floor. Result: register a log
callback, run seats on Modal/GKE, receive **zero** `LogEntry`s forever, no error, no warning. The PR's
only streaming test fakes Docker (`tests/unit/trial/test_seats.py:166-171`), so nothing catches this.
(SBX may stream: it passes `self._output_callback` into its sandboxes, `sbx/environment.py:73-86` —
unverified for the per-service path.) Fix direction: thread `on_output` through
`ComposeServiceTransport.service_exec`, or have `SeatsTrial`/log registration warn when the backend
cannot stream; at minimum scope the PR description to Docker.

### 4. `SEAT_END` ≠ seat finished: collection, post-run context, and trial error recording all happen after it — `seats.py:345-347` vs `seats.py:278-279`, `seats.py:349-388`, `seats.py:390-408`
`SEAT_END` fires at the end of `agent.run`, but `_collect_seats` runs later in `_run` and mutates the
seat's record: downloads logs, `populate_context_post_run(context)`, fills `model_usage` from the
trajectory (`seats.py:380-388`). `_record_seat_errors` (sets the *trial-level* `exception_info` from the
first seat error) also runs after collection. A consumer that does the natural thing — snapshot/persist
the seat on `SEAT_END` — gets empty model usage/cost for agents that populate post-run, misses
downloaded logs, and sees `result.exception_info=None` even for a crashed-under-policy seat whose
trial-level error is only recorded minutes later. The name promises a lifecycle boundary the code
doesn't provide; either emit after `_collect_seat` per seat, or document/rename as agent-run-end.
(Single-agent `AGENT_END` has the same shape vs `_sync_agent_output`, `trial.py:811-815` — inherited,
but the PR creates the per-seat expectation.)

### 5. Hook payload has no per-seat state; all seat events alias one live, mutating `TrialResult` — `trial.py:616-623`, `hooks.py:31-50`, `server/executor.py:60-64`
`TrialHookEvent` gains `seat: str` but **no `SeatResult`**; `result` is the trial aggregate, passed by
reference and mutated concurrently by all seat tasks. PROBE P9: 6 seat events, 1 distinct result object
(`is trial.result`); a stored `SEAT_START` event read after the trial shows `agent_execution.finished_at`
set — point-in-time snapshots are impossible, and at `SEAT_START(maya)` the payload's
`seat_results[raj]` may already be finished. Consumers must fish `result.seat_results` by name
(undocumented) and still race. This hits real in-repo consumers immediately: `server/executor.py:63-64`
registers `report_result` for **every** `TrialEvent`, so seat trials now fire `on_result(partial_result)`
2·N extra times mid-play with the same mutable object — any downstream that persists on callback
overwrites state with partial results (and if it raises, see #1). Fix direction: include the seat's
`SeatResult` (or a copy) in the payload for seat events.

---

## HIGH

### 6. No lifecycle events for setup or collection; setup logs arrive before any `SEAT_START`; parts of setup never stream — `seats.py:200-262`
The PR tags setup *logs* (`agent_setup`, `seats.py:261`) but emits no seat hook around `_setup_seat`.
PROBE P6 (`install_only=True`): log entries `[('agent_setup','maya'),('agent_setup','raj'),('agent_setup','lee'),...]`
with hooks only `[start, environment-start, end]` — a log consumer cannot open/close a per-seat view,
and an `install_only` trial produces seat logs with zero seat lifecycle. Worse, when one seat's setup
fails, `_seat_tasks` cancels the other setups mid-flight; they emitted attributed logs and then vanish —
no `SEAT_END` will ever come (`_run` never reached). Additionally the first two seat execs in
`_install_seat` — `id -u` (`seats.py:249`) and `ensure_dirs` (`seats.py:255`) — run *before*
`_log_context` is entered, so their output never reaches log callbacks at all (the PR test's exact
2-entries-per-phase expectation now encodes this invisibility). Fix direction: seat setup hooks
(`SEAT_SETUP_*` or widen `SEAT_START` to cover setup→collect) and enter `_log_context` before the
`id -u` probe.

### 7. Collection/artifact/upload output is invisible to log streaming — `seats.py:358-388`, `seats.py:278-287`, `environments/seat.py:86-108`
`_collect_seat` downloads, `_collect_artifacts`, and the `trial/seats → main:/logs/seats` upload all run
with no `_log_context`, and `SeatEnvironment.upload_*/download_*` delegate to
`project.service_*` **without** the output-callback bridge that `exec` has (`seat.py:76` vs `86-108`),
so even execs inside transfers (tar/cp) can't stream. A "live view" goes dark from `SEAT_END` through
verification except the verifier itself; download failures surface only via `seat.logger.error`
(`seats.py:375-379`), never as `LogEntry`s. Missing-phase fix: wrap collection in
`_log_context(..., seat=...)` (needs a phase value — `LogPhase` at `hooks.py:14` has only
`agent_setup|agent|verification`) and bridge the transfer methods.

### 8. Feature unreachable from `Job`/`TrialQueue`; no seat helpers; concurrency permits still keyed to the phantom single agent — `trial/queue.py:55-102`, `job.py:231-262`, `server/executor.py:57-58`
Neither `TrialQueue` nor `Job` forwards log callbacks (`_setup_hooks` wires only hooks,
`queue.py:90-102`; `add_log_callback` exists only on `Trial`, `trial.py:577-582`), so the headline
"live logs" feature cannot be used through the normal job API at all. `Job`/`TrialQueue` gain no
`on_seat_started/on_seat_ended` beside the existing seven helpers — discoverable only via raw
`add_hook(TrialEvent.SEAT_START, ...)`. And the agent-concurrency machinery ignores seats:
`_uses_agent_concurrency` checks `config.agent` (the default-empty agent on seat trials,
`queue.py:104-105`; `check_launch` even forbids setting it, `seats.py:69-70`), and permits
acquire/release once on trial-level `AGENT_START/AGENT_END` (`queue.py:93-94`, `executor.py:57-58`)
while N agents actually run. The new per-seat events were the place to wire this; as shipped, seat
trials bypass `n_concurrent` accounting. (Accounting gap pre-exists seats; PR adds the events and
doesn't connect them.)

### 9. Typed-payload compatibility: `seat` field is safe, the two new enum members are the break — `hooks.py:24-25`, `hooks.py:50`, `hooks.py:80`
Checked the "seat field breaks consumers" hypothesis: construction stays compatible (both fields are
trailing with `None` defaults; old serialized JSON re-validates), so in-repo typed consumers do not
break on the field. `model_dump()` output does gain `"seat": null` (snapshot/strict-schema consumers
downstream will see a diff). The real compatibility hazard is `TrialEvent` growth: every
`for event in TrialEvent` subscriber silently opts into seat events — concretely
`server/executor.py:63-64` (see #5) and `TrialQueue.__init__` (`queue.py:36-39`); any external
exhaustive `match`/`assert_never` on `TrialEvent` breaks the first time a seat trial runs. No in-repo
exhaustive match exists (grep over `src`+`apps`), so in-repo blast radius is the executor behavior
change; flag it in release notes for SDK users.

### 10. The new streaming test encodes a backend that doesn't exist (stderr, global stream order) — `tests/unit/trial/test_seats.py:151-163`, `test_seats.py:706-745`
The fake `compose` emits `on_output(cmd,"stdout"); sleep(0); on_output(cmd,"stderr")` and the test
asserts per phase `streams == ["stdout"]*3 + ["stderr"]*3` plus verification `[(None,"stdout"),(None,"stderr")]`.
Real Docker merges stderr into stdout at the subprocess level (`stderr=asyncio.subprocess.STDOUT`,
`docker/docker.py:790`), labels every streamed line `"stdout"` (`docker.py:907`), and returns
`stderr=None` (`docker.py:936`) — so no real backend path in the PR can ever produce a `"stderr"`
`LogEntry`, and the all-stdouts-then-all-stderrs order is a scheduling artifact of the fake's
`sleep(0)`, not a guarantee. The test will keep passing while real behavior differs, and will fail
spuriously if someone makes the fake honest. Assert attributed *sets* per phase/stream against a fake
that mirrors Docker's merged-stream contract instead.

---

## MEDIUM / verified non-issues

### 11. Wrong-seat attribution under concurrency: core mechanism is correct on Docker — `trial.py:597-613`, `environments/base.py:692-750`, `environments/seat.py:76-84`
The attacked hypothesis does **not** break for exec output: `seat` is captured by value in the emit
closure (`trial.py:601-609`), callbacks travel in per-instance `ContextVar`s set inside each seat task
(TaskGroup copies context at `create_task`; `_log_context` is entered after, `seats.py:213-215`,
`304-307`), and `_output_callback()` snapshots the tuple at exec time (`base.py:741-750`), so even
callbacks invoked later/from helper tasks carry the right seat. Residual edges:
(a) an agent that spawns its own background task inherits the context snapshot and can emit
correctly-attributed-but-late entries **after** `SEAT_END`/phase exit (stale attribution, breaks
ordering assumptions; pre-existing for `step_name`/phase too);
(b) `callbacks = list(self._log_callbacks)` is snapshotted at `_log_context` entry (`trial.py:597`) —
subscribers added mid-play silently miss in-flight seat phases, while hooks are read live at emit
time (`trial.py:624`): inconsistent subscription semantics, undocumented;
(c) nested `_log_context` on one environment would double-emit under both closures (`base.py:746-748`
loops the stack) — not reachable from current call sites, worth a comment if collection wraps execs (#7).

### 12. Ordering vs play end/cancel: correct on the single-cancel paths — `seats.py:332-347`, `seats.py:264-287`, `trial.py:627-656`
PROBE P5 (whole-trial cancel, suspending hooks): `seat-end(raj) → seat-end(lee) → seat-end(maya) →
agent-end → cancel → end`, all hook bodies completed; PROBE P2 (agent-timeout cancel) likewise
completed all `SEAT_END`s. `SEAT_START` strictly precedes `agent.run`, `SEAT_END` follows
`ended/stopped` (PR's `_assert_seat_hooks`, `test_seats.py:208-221`). Credit due. The ordering holes
are the boundary cases, not the spine: timeout error info is written by `_play` *before* cancel so
`SEAT_END` sees it (`seats.py:313-322`, good), but on trial-level cancel `SEAT_END` fires before
`Trial.run` records the `CancelledError` (`trial.py:636-639`), and a raising `SEAT_END` hook during
cancel is only rescued into `CancelledError` by `_seat_tasks`' cancelling-check (`seats.py:101-103`) —
in the timeout path the same raise becomes the trial error instead of the timeout (#1).

### 13. `seat` contract is convention-only, not enforced — `hooks.py:39-50`, `hooks.py:71-80`, `trial.py:615`
Docstrings say seat is "for seat lifecycle events only", but nothing stops `_emit(START, seat="maya")`
or a `SEAT_START` with `seat=None`, and `LogEntry.seat` on `verification` entries type-checks fine.
Today exactly two call sites set it (`seats.py:332,347` for hooks; `seats.py:261,334` for logs), so
the invariant holds by discipline. A Pydantic model validator (seat set ⇔ event in {SEAT_START,
SEAT_END}; seat log ⇒ phase in {agent_setup, agent}) would make the typed payload mean what the docs
claim, and catch the next caller that gets it wrong.

### 14. Test coverage gaps behind the green suite — `tests/unit/trial/test_seats.py:199-221`, `:488-492`, `:520-527`
`_assert_seat_hooks` is wired into only 2 of the lifecycle tests (agent timeout; exit/auth failure) —
not the happy path, **not the seat-crash test** (`test_a_seat_crash_fails_the_trial_and_ends_play`,
the TaskGroup-cancels-siblings case), not whole-trial cancel, not setup failure. The recording hook
never suspends and never raises, which is precisely why #1/#2 are invisible to the suite. No test:
hook raises, log callback raises, slow hook vs timeout, seat events vs `AGENT_END/CANCEL/END`
ordering, `install_only` seat silence, or a non-Docker backend (#3). The `_seats_trial` helper also
quietly changed what *all* seat tests exercise — verifier mock moved from `_run_shared_verifier` to
`_verify_with_timeout` (`test_seats.py:182-188`), so the real `_run_shared_verifier` +
`VerifierFactory` now run in every seat test just to produce verification log entries; works, but it
widens the fake's surface without a comment.

### 15. First-tested-seat fallback does not leak into log attribution or non-seat trials (adjacent pre-existing quirks noted) — `seats.py:175`, `trial.py:780,1043,1115,1947,1965`
Attacked hypothesis falsified for this PR: every non-seat `_log_context`/`_emit` site defaults
`seat=None`, `SeatsTrial` never calls the single-agent `_setup_agent`/`_run_agent_phase`, and the new
ordinary-trial test (`test_seats.py:240-296`) proves 4 unattributed entries + 5 unattributed events
and no `SEAT_*` leakage. Adjacent, pre-existing (not introduced here, flagged because the review was
asked to look): trial-level `agent_info` and `_network_plan` inference-host detection still consult
only `self.agent` = first under-test seat (`seats.py:175,220`; `trial.py:314-322`), so other seats'
inference hosts are invisible to allowlisting; and `Trial.create`'s seat branch drops `_trial_id`
(`seats.py:112-123` has no such parameter vs `single_step.py:18-33`), so for server-executor rollouts
`LogEntry.trial_id`/`result.id` won't equal the requested rollout id on seat tasks.

### 16. Verification output during seat trials is unattributed by design — acceptable, but say so — `trial.py:1043-1046`
Shared verifier runs in `main` with `seat=None` entries (PR test asserts this). That's coherent,
but a verifier script that execs into seat services (via compose from inside `main`) produces output
labelled phase=`verification`, seat=`None` — consumers filtering by seat will miss seat-generated
grading output. One-line doc note on `LogEntry.seat` would close the expectation gap.

---

## Suggested minimum bar before merge
1. Isolate hook + log-callback exceptions (log & continue); move `SEAT_START` emit outside the
   agent-failure `try:`; bound `SEAT_END` in `finally:` so it can't mask outcomes or eat the timeout (#1, #2).
2. Either thread streaming through `ComposeServiceTransport`/DinD or warn/disable explicitly when the
   backend can't stream (#3); fix the streaming test to Docker's merged-stdout contract (#10).
3. Put the seat's `SeatResult` (copy) in the hook payload and fire `SEAT_END` after per-seat
   collection — or rename/document it as run-end (#4, #5).
4. Seat setup lifecycle + `Job`/`TrialQueue` plumbing (log-callback forwarding, `on_seat_*`) (#6, #8).
5. Tests: raising/suspending hooks, crash + cancel hook ordering, slow-hook-vs-timeout (#14).

## Verification performed
- `pytest tests/unit/trial/test_seats.py tests/unit/trial/test_hooks.py tests/unit/trial/test_log_streaming.py -q`
  → 31 passed (venv `/Users/petermakhnatch/Developer/harbor-multiagent/.venv`, `PYTHONPATH=<checkout>/src`).
- Probes `/tmp/probe_pr12.py` (P1–P6) and `/tmp/probe_pr12b.py` (P7–P9) against the checkout's own
  fake-Compose harness — outputs quoted in #1, #2, #5, #6, #12. No files in the checkout were modified
  (`git status` clean after review).
