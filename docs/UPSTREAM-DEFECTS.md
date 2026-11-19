# Upstream defects in `olamlabs/harbor-multiagent`

Each item below was observed while building a four-seat adversarial suite on top of the fork. Every one cost real debugging time on day one, and each has a minimal repair direction. Line references are against `6aeb609e31fd77e5f89ce3bcb018db8045520fb7`.

Nothing here is a style preference. Each item either produces a wrong measurement, a silent no-op, or an error message that names the wrong cause.

---

## 1. Harbor's build overlay replaces `main`'s command, so a world declared only in the Dockerfile never starts

**Severity: high. Silent false negative on every seat task that follows the docs.**

`src/harbor/environments/docker/docker.py` `_maybe_override_compose()` writes `docker-compose-build.yaml` whose `main` service sets

```yaml
command: [ "sh", "-c", "sleep infinity" ]
```

`docker-compose-prebuilt.yaml` sets the same thing, so this is not limited to the build path: a prebuilt image loses its `CMD` too.

Compose merges `command` as a scalar, so the overlay wins over the task's own `docker-compose.yaml` and over the Dockerfile `CMD`. The service then runs `sleep infinity` forever.

**Repro.** Take `examples/tasks/hello-seats` (which declares `command` in its own compose file, so it works) and remove the `command:` line, leaving the same entrypoint only in `environment/player/Dockerfile` as `CMD ["python3","..."]`. Run a trial. Result:

```
service "main" is unhealthy
```

The container is running. `docker top` shows `sh -c sleep infinity`. The healthcheck cannot pass, because the world never started. The error names "unhealthy", so a reader looks at the healthcheck, not at the command.

**Repair options.** Either copy the resolved `command`/`entrypoint` from the task's compose file into the overlay instead of substituting one, or keep `command` out of the overlay entirely and let Compose fall through to the image. A startup warning when a seat task's `main` has no resolved command would have caught this in one second.

**Workaround for task authors.** Always declare `command` explicitly in the task's `environment/docker-compose.yaml` for `main`. The fork's own example does this, which is why the defect is not visible from the example.

---

## 2. Declaring a verifier output as an artifact records it as `failed`

**Severity: high. It silently discards the evidence a regrade needs.**

The documented artifact contract invites a task to declare every file the trial produces:

```yaml
artifacts:
  - /logs/world/events.jsonl
  - /logs/verifier/crucible_report.json
```

Harbor collects and uploads artifacts **before** the verifier runs, so a file that only the verifier creates is always missing at collection time. It is recorded in the trial's artifact manifest as `"status": "failed"`, and `SeatsRegradeTrial` then refuses the trial because a declared artifact has no collected counterpart.

**Observed.** With `crucible_report.json` declared, the trial's `artifacts/manifest.json` records the entry with `"status": "failed"`, and a regrade against that trial then refuses:

```
/logs/verifier/crucible_report.json: collection failed in the source trial;
the record does not contain it
```

The coverage check itself is correct and well written. The problem is the contract: it documents artifacts as "everything the trial produces", while collection runs before the producer runs.

**Repair.** Either collect artifacts a second time after verification, or document that verifier outputs must not be declared, or (best) let a task declare the phase of each artifact so the contract matches the implementation.

---

## 3. Harbor pre-creates declared artifact paths, so exclusive-create in a world always fails

**Severity: medium. It breaks a natural, safe file-writing pattern.**

Harbor stages the destination for every declared artifact before the trial starts. A world that refuses to clobber another writer's file with `open(path, "x")` therefore fails on its own declared log:

```
FileExistsError: [Errno 17] File exists: '/logs/world/events.jsonl'
```

**Repair options.** Do not pre-create files (create the parent directory only), or honour the `"user"/"exclusive"` flag. In the meantime, task authors must use append mode on paths they declare as artifacts, which silently removes the overwrite protection they wanted.

---

## 4. A seat that runs as a different uid breaks every `/proc/<pid>/exe` integrity check

**Severity: medium. This one fails closed, which is the good direction, but it fails for the wrong reason.**

A cross-uid `/proc/<pid>/exe` comparison raises `PermissionError` under a non-root seat (`os.geteuid() != 0`). Code that treats "cannot read" as "not the expected binary" marks a healthy world unhealthy. Code that treats it as "skip" opens a tamper window, because a seat can then swap its interpreter and the check never fires.

**Repair.** Record the executable digest at spawn time (in the spawning process, before privilege drops) and compare the digest later, or accept `PermissionError` explicitly as `unverified` rather than as pass or fail. A four-line helper in the fork's environment module would keep every seat task from re-solving this.

**Note.** `waitid(WNOWAIT)` cannot be used to inspect a live child here: it reaps the child on return, so the probe kills the service it is inspecting.

---

## 5. Job statistics attribute a whole team to the first tested seat

**Severity: high for anyone reporting per-model numbers from a seat job.**

`src/harbor/models/job/result.py` `JobStats.increment()` builds one group key from `trial_result.agent_info`. For a seat trial that is `next(seat.agent for seat in seats if seat.under_test)`, so:

- every reward key lands in that one group;
- the other seats' models never appear in `stats.evals`;
- the trial's whole token and cost total is attributed to one group.

A four-seat job with four different models reports one model's statistics. `result.json` already carries `seat_results` with per-seat `agent_info`, usage and exceptions, so the truth is present and unused. A fix is open as PR #21 on the fork (additive `seat_stats`, existing key format untouched).

---

## 6. Seat exceptions ignored the error-policy override (fixed in a PR)

`Trial._setup_seat()` caught seat setup exceptions and always built the default `SetupTimeoutError`, so a suite that customised `override_error_policy` for a seat still rewarded it the default way. `TrialLock` also compared participants in list order, so two runs with the same roster in a different order produced different lock identities and could run concurrently.

Repro and fix: PR #10 on the fork.

---

## 7. Regrade refused seat tasks (fixed in a PR)

An episode could not be re-scored against a stricter verifier without paying for the agents again, which makes a "does a stronger verifier catch more" study cost a full rerun per variant. Fixed by PR #11; verified by regrading a recorded four-seat trial with identical rewards and zero agent re-execution.

---

## 8. Nothing in a live log or a lifecycle hook names the seat (fixed in a PR)

`LogEntry` carried no seat, so a live monitor could not attribute a line to an agent, and `TrialHookEvent` fired without a roster identity. Live multi-seat oversight is impossible without it. PR #12 adds an optional `seat` field plus `SEAT_START`/`SEAT_END`, backwards compatible.

---

## 9. A timeout multiplier below 1 makes mission outcomes unmeasurable, not faster

**Severity: high as a research hazard, not a code bug.** Worth documenting in the multipagent guide.

`harbor trials start` accepts `--timeout-multiplier`. At `0.5`, a 180 s seat task gets 90 s. In a 42-trial corpus we hit `AgentTimeoutError` in 8 trials, including all three `sabotage` trials and all three protocol-conflict trials. The adversarial act was still measured (`sabotage_success=1.0`), but `task_utility` was truncated, and the truncated number reads like model failure.

**Recommendation.** Document that `--timeout-multiplier` is a cost knob only for tasks whose successful run finishes well inside the base timeout. For seat tasks, report the timeout count next to any completion rate, or the rate is a floor presented as a measurement.
