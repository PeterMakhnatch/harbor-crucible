# Adversarial review: PR crucible/seat-regrade — "regrade recorded multi-seat trials without rerunning agents"

Checkout: `/Users/petermakhnatch/Developer/crucible-wt/seat-regrade`
Commit: `b2cb29ec` on base `main` (`6aeb609e`). One commit, 7 files, +465/−20.
Core change: `src/harbor/trial/regrade.py:908-1015` (new `SeatsRegradeTrial`), dispatch at
`src/harbor/trial/trial.py:507-512`, seats upload at `src/harbor/trial/trial.py:1088-1092`,
`participants` carried by CLI/job (`src/harbor/cli/trials.py:1444-1465`, `src/harbor/job.py:607-639`).

Method: full diff read against live seat trial (`src/harbor/trial/seats.py`) and base regrade
machinery; PR tests run (30 passed: `test_regrade_seats.py` + `test_seats.py`); five adversarial
probes run from `/tmp/probe_pr11/test_probe.py` (all 5 passed, i.e. every bad case grades
reward 1.0 instead of failing). No files in the worktree were edited (`git status` clean).

Verdict: **Do not merge as is.** The symlink/artifact plumbing is careful, but the PR lifts the
stock refusal (`Trial.create` raised "Regrade does not support seat tasks") without replacing
the two guarantees that refusal protected: (1) the verifier grades the world the agents left
behind, and (2) the record being graded is the roster that ran. A regrade can produce a fresh,
valid-looking reward against an initial-state environment, an unverified roster, and
incomplete seat logs.

Why stock Harbor refused: a live seat verifier must run in `main`, shared mode, with every
container still up (`src/harbor/trial/seats.py:8-10`, enforced at `seats.py:73-74`), after
uploading `trial/seats/` to `/logs/seats` (`seats.py:282-286`). It may read live world state:
main's filesystem, shared volumes, and the still-running seat services over the network.

---

## F1 — BLOCKER — Fresh separate environment is graded as if it were the recorded final world

- `src/harbor/trial/regrade.py:937-957` (`_validate_regradable`) + `:432-444`
  (`_validate_source_record` → `check_task_regradable`, `:116-123`): the only mode gate is that
  the *new* task resolves to separate-mode. Nothing checks that the verifier actually grades
  from restored inputs only.
- Every real recorded seat task ran shared (`seats.py:73-74` refuses anything else), so the
  operator must edit `task.toml` after the run — flip `[verifier] environment_mode` (or add a
  verifier environment) — before this code will regrade at all. That edit is undetectable:
  `_validate_source_record` checks task *name* only (`regrade.py:445-450`); `task_checksum`
  in the source `result.json` is never compared.
- With no `[verifier.environment]`, the separate verifier env is "a fresh deep copy of
  task.environment" (`src/harbor/models/task/verifier_mode.py:48-69`, definition at `:89-140`),
  started from scratch (`trial.py:1155-1158`). For a seat task that means the whole Compose
  project — main plus every seat service — at *initial* state. A verifier written for live
  `main` (reads files the agents wrote in main, queries a seat service, inspects a shared
  volume) now silently executes against that fresh world. The reward is stored as a grade of
  the agents' recorded work. Fresh state presented as final state.
- Only two input classes are restored: declared artifacts (`regrade.py:453-475` coverage) and
  `seats/` (`trial.py:1088-1092`). Seat-container state outside `/logs/agent` and declared
  artifacts was never recorded (collection: `seats.py:347-386` logs, `:280` artifacts), so any
  verifier dependence on it has *no* coverage signal — unlike artifacts, there is no manifest
  to fail against. The guidance in `check_task_regradable` (`regrade.py:120-122`) still only
  tells authors to read `/logs/artifacts`; it never mentions `/logs/seats` or warns that the
  services come back fresh. The separate-verifier runtime even drops
  `extra_docker_compose` (`trial.py:1131-1133`), so the regrade world differs from the live
  world again.

Fix direction: treat "separate-mode seat verifier" as a new, explicit task contract — require
the mode flip to be visible (compare source `task_checksum`/lock task digest and warn or
require an opt-in flag when the verifier definition changed), update the regradable guidance
to name `/logs/seats` + fresh services, and record in the result that world state was fresh.

## F2 — BLOCKER — No roster cross-check: participants, task seats, seat_results and seats/ dirs are never compared

- `src/harbor/trial/regrade.py:937-957`: validation never compares
  `config.participants` ↔ `task.config.agents` ↔ `source_result.seat_results[].seat` ↔
  `seats/` subdirectories ↔ source config participants. Live trials enforce exactly this in
  `check_launch` (`seats.py:59-89`, roster at `:62-70`); the regrade dispatch never calls it
  (`trial.py:488-519`), and `Trial.create` only checks the converse direction
  (participants require a seat task, `trial.py:483-487`).
- Contrast in the same file: multi-step regrade requires the exact ordered step names
  "so verifier results remain attributable" (`regrade.py:788-797`) and mandatory
  `step_results` (`:782-786`). Seats get no analogous check.
- CLI/job entry points do carry source participants (`cli/trials.py:1444-1465`,
  `job.py:607-639`) — good — but the core trial accepts anything, including nothing.
- Probe evidence (mocked verifier returning reward 1.0, same harness as the PR tests):
  - participants = `[eve]` against a maya/raj record → reward 1.0, `exception_info=None`,
    `seat_results` still `['maya','raj']` while config says `eve`. Internally inconsistent
    result, graded anyway.
  - participants = `[]` → reward 1.0; `_init_result` (`regrade.py:919-923`) then keeps the
    default `agent` in `config.json`, so the fork does not even present as a seat trial.
- Task-side drift is equally open: a new task with different `[agents.*]` seats or flipped
  `under_test` flags regrades old logs under the new roster (name-only check, F1).

Fix direction: in `_validate_regradable`, require
`{p.seat for p in participants} == set(task.config.agents) == {sr.seat for sr in seat_results}`
and one `seats/<seat>/` per seat (with `under_test` agreement), mirroring the multi-step
exact-match rule.

## F3 — HIGH — OR-gate record check lets missing/incomplete seat evidence grade as complete

- `src/harbor/trial/regrade.py:949-956`: source passes if `seat_results` **or** `seats/`
  exists. Either half of the record may be absent.
  - `seat_results` present, `seats/` missing: `_seed_from_source` skips the copy
    (`:965` `if source_seats_dir.is_dir()`), `TrialPaths.mkdir` never creates `seats/`
    (`src/harbor/models/trial/paths.py:150-153`), and `_run` passes the nonexistent dir to
    the verifier (`regrade.py:982-988` → `trial.py:1088-1092`). Probe: target `seats/`
    `exists() == False` at upload time, reward 1.0 with the mock. With a real Docker env,
    `upload_dir` on a missing dir fails as a compose-cp/tar error
    (`src/harbor/environments/docker/docker_unix.py:178-198`) — an environment error, not a
    `RegradeError` naming the missing record; providers that tolerate empty uploads grade an
    empty `/logs/seats` instead. Provider-dependent silent-vs-cryptic failure.
  - `seats/` present, `seat_results` absent: verifier grades whatever directories exist;
    all seat exceptions vanish. Probe: `seat_results=None`, `recorded_exceptions() == []`,
    `reward_valid == True`, reward 1.0.
- No provenance or completeness check on the logs that are uploaded:
  `regrade.py:959-975` copies `seats/` verbatim after symlink containment only
  (`_validate_recorded_outputs`, `:638-671`). Artifacts get a manifest with
  status/exclude/destination checks (`:453-581`); seat logs have no manifest at all. So the
  regrade cannot distinguish a complete record from: logs filtered by participant
  `include_logs`/`exclude_logs` at collection (`seats.py:362-368`), a seat whose log
  download failed and was only logged (`seats.py:373-377`), a non-under-test seat cancelled
  mid-run (`seats.py:310-322`), an empty `seats/` dir, or logs edited in the trial directory
  after the run. All present as "the recorded seats."

Fix direction: require both `seat_results` and per-seat `seats/<seat>/agent` dirs (F2), fail
with `RegradeError` when the seats dir is absent/empty before any verifier starts, and say in
the result/docs that seat logs carry no integrity record.

## F4 — HIGH — An exceptioned seat can come out trial-level clean; validity rests on one untested thread

- Trial-level `exception_info` is taken only from the source trial-level field via the base
  timing heuristic (`regrade.py:992-995` → `:738-762`). It is never reconstructed from
  `seat_results`, although the live trial derives it exactly that way
  (`seats.py:388-406`, `_record_seat_errors`).
- The PR's own fixture shows the hole: source seat `maya` has `AgentTimeoutError`, source
  trial-level `exception_info` is `None` (`tests/unit/trial/test_regrade_seats.py:103-140`),
  and the happy-path test (`:164-232`) asserts the seat exception but never
  `result.exception_info` or `result.reward_valid`. Probe on that fixture:
  regrade `exception_info=None`, reward 1.0, **`reward_valid == True`** — because the default
  policy for `AgentTimeoutError` is `has_valid_reward=True`
  (`src/harbor/models/trial/error_policy.py:99-109`; unknown types also default valid,
  `:33-35`). Consumers keyed on the trial-level field misreport: the CLI regrade command
  exits 1 or prints green "Regrade completed!" on `result.exception_info` alone
  (`cli/trials.py:1491` onward).
- Credit where due: seat exceptions *are* deep-copied (`regrade.py:931-935`, `997-1015`) and
  `TrialResult.reward_valid` does fold seat exceptions in
  (`src/harbor/models/trial/result.py:142-164`), so with an explicit
  `has_valid_reward=False` override the reward is correctly invalid — the PR test asserts that
  override lands on the seat (`test_regrade_seats.py:213-220`).
- But the override thread is fragile: neither CLI nor job regrade carries the *source*
  config's `override_error_policy` into the fork (`cli/trials.py:1458-1470` builds a fresh
  `TrialConfig`; `job.py:626-645` uses the new job's), and the seat branch rewrites
  `policy_override` to the new config's lookup-or-None (`regrade.py:1007-1014`), erasing any
  recorded override. Forget to re-specify the override and a timed-out seat silently becomes
  valid-reward. The seat branch also skips the base class's stale-verifier-error timing test
  while claiming to exclude stale verifier errors (`:1002`) — harmless for today's writers
  (seats only record agent/setup errors) but the docstring overstates the code.
- `_run` grades unconditionally (`regrade.py:978-995`): seat errors whose policy says
  `should_grade=False` (e.g. `AgentSetupTimeoutError`, `error_policy.py:38-51`) still get a
  verifier run and a stored reward; only downstream `reward_valid` keeps it from counting.

Fix direction: rebuild trial-level `exception_info` from seat results when the source
trial-level field is absent (mirror `_record_seat_errors`), carry source
`override_error_policy` in CLI/job forks, and assert `exception_info` + `reward_valid` in tests.

## F5 — MEDIUM — Fork relabels the copied record under the new task's identity

- The new `result.json` takes `task_checksum` and `started_at` from the regrade run
  (`trial.py:1219-1237`), `verifier_environment_mode=separate`, while `agent_info`,
  `agent_result` (`regrade.py:388-392`) and full seat timings/results (`:926-929`) are copied
  from the source. Read without following `config.source_trial`, it looks like an ordinary
  trial of the edited task. The trial lock does copy the source task lock verbatim
  (`src/harbor/models/job/lock.py:468-490`) — credit — but nothing compares or warns when
  lock (recorded task) and result checksum (regrade task) disagree, which for seat tasks is
  *always*, per F1.

## F6 — MEDIUM-LOW — Source overwrite is guarded only by the default trial name (inherited, widened)

- Normal path is safe and tested: new trial dir, source bytes asserted unchanged
  (`test_regrade_seats.py:164-232`). Trial names auto-generate when empty
  (`src/harbor/models/trial/config.py:647-649`).
- But there is no explicit `new trial_dir != source trial_dir` guard anywhere in
  `regrade.py`/`cli/trials.py`/`job.py`. An explicit `--trial-name` + `--trials-dir` pointing
  at the source makes `_init_result` overwrite the source `config.json` before any regrade
  validation runs (`trial.py:1220-1221`), the seats `copytree` copy onto itself
  (`regrade.py:969-974`), and the final `result.json` replace the original reward — the one
  case where "reward overwriting original result" is literal. Inherited from base regrade;
  this PR adds the seats copy to the blast radius. (By design, the fork's `result.json` also
  drops the source reward entirely; only the CLI prints old-vs-new to the console,
  `cli/trials.py:1500-1512`.)

Fix direction: one `RegradeError` if `self.paths.trial_dir.resolve() ==
self._source_paths.trial_dir.resolve()` in `RegradeTrial.__init__` (covers all regrades).

## F7 — LOW — Regrade secret scrub covers none of the participants

- End-of-trial scrub runs for regrades (`trial.py:651`, `:692`) but the inherited
  `_secrets_to_scrub` (`trial.py:1270` onward) knows only the nop/default agent and verifier
  env. The live seat trial unions every seat agent + participant
  (`seats.py:408-421`), and `Participant` is an `AgentConfig` that can carry env secrets
  (`src/harbor/models/trial/config.py:213`). Copied seat logs in the fork rely entirely on
  the source run's scrub having happened; legacy or hub-downloaded sources are not
  re-scrubbed for participant env values.

## F8 — LOW — Tests do not cover the real workflow or the failure lanes

- The fixture task is a *separate-mode* seat task (`test_regrade_seats.py:46-61`), which
  `check_launch` would refuse to run live (`seats.py:73-74`). No test covers the actual
  workflow: record shared → edit task → regrade (F1).
- `_write_seat_source` knobs `include_seats` / `include_seat_results`
  (`test_regrade_seats.py:75-76`) are never passed `False` — both OR-gate lanes (F3) are
  untested, as are roster drift (F2), checksum drift (F1/F5), missing per-seat dirs, and
  `result.exception_info`/`reward_valid` (F4).
- The verifier is mocked at `_run_separate_verifier`, so the real `upload_dir` of `seats/`
  into a fresh multi-service verifier env (`trial.py:1088-1092`) is asserted only as kwargs.
- Test file style: `import shutil` before `import json` (`test_regrade_seats.py:3-4`) will
  trip the repo linter's import sort.

## Checked and OK (no finding)

- Shared-mode *new* tasks are refused with a clear message (`regrade.py:116-123`, tested).
- Artifact coverage machinery is fully reused, including failed/skipped/empty manifest
  semantics (`regrade.py:453-581`, tested via the coverage case).
- Symlink escape from `seats/` is validated and tested (`regrade.py:963`,
  `test_regrade_seats.py:234-258`); copies dereference links (`symlinks=False`).
- Multi-step sources are refused (`regrade.py:941-948`); agents+steps tasks cannot exist
  (`src/harbor/models/task/config.py:917`), so dispatch precedence (`trial.py:507-512`) is safe.
- Source trial is not modified on the normal path (byte-compare test); CLI and job forks
  carry participants from result-embedded config when `config.json` is unreadable
  (`cli/trials.py:1444-1457`, `job.py:607-622`).
- The removed stock refusal test was replaced, not deleted
  (`tests/unit/trial/test_seats.py` diff): create now routes and fails cleanly with
  `RegradeError` on an unreadable source.

## Minimum bar to merge

1. Exact roster/record cross-check (F2+F3): participants = task seats = seat_results =
   seats/ dirs; both record halves required; `RegradeError` before verifier start.
2. Task-drift visibility (F1+F5): compare source checksum/lock digest, require explicit
   acknowledgement when the verifier definition or mode changed, fix the guidance text.
3. Rebuild trial-level exception from seats when absent; carry source error-policy
   overrides (F4). Add the five probe cases as tests.
