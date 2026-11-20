# Adversarial review — PR #21 `crucible/seat-job-stats` (PeterMakhnatch/harbor-multiagent)

**Verdict: do not merge as-is.** The common case works: one homogeneous seat job, all seats report full
usage, verifier uses seat-name reward keys, and models shared across seats are now separated.
Every invariant the PR body states without qualification ("totals equal the sum of its seats",
"retries stay symmetric", "shows `unknown` rather than `0`") breaks on reachable inputs.
Two defects silently destroy or mislabel data (F1, F3); the rest misreport it.

Method: `gh pr diff 21` (head `b7e99d1`), PR branch extracted read-only via `git archive` to
`/tmp/pr21src`, live `main` code in `harbor-multiagent/`, and 10 executed probes
([probe_pr21.py](/tmp/probe_pr21.py)) run against the PR code — all findings below marked
*probe* were observed, not inferred. Line numbers are PR-branch lines unless the path says `(main)`.

## Ranked findings

### F1 [P0] `_remove_seat_stats` can delete a live seat's whole entry, discarding other trials' usage
[src/harbor/models/job/result.py:386](/tmp/pr21src/src/harbor/models/job/result.py:386) (pop condition),
[:331](/tmp/pr21src/src/harbor/models/job/result.py:331) (`n_trials` gated on `reward_valid`)

The entry is dropped when `n_trials == 0 and n_errors == 0` after a removal, but `n_trials`
only counts reward-valid trials. A seat whose trials are reward-invalid with no seat exception
— verifier disabled ([src/harbor/trial/seats.py:281 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/trial/seats.py:281),
`reward_valid` is `False` when rewards are empty at
[src/harbor/models/trial/result.py:159 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/models/trial/result.py:159))
— accumulates real token/cost totals under `n_trials=0, n_errors=0`. Removing any one such
trial (the retry path, `update_trial` at [:389](/tmp/pr21src/src/harbor/models/job/result.py:389))
pops the entire seat entry. *Probe 6:* two no-verifier trials, job tokens 200, seat tokens 200;
after `remove_trial(t2)` job tokens are 100 but `seat_stats` is empty — seat sum 0, one live
trial's spend gone from `seat_stats` while job totals still count it.

### F2 [P0] Bare seat name as global key collides across datasets, tasks, and resumed jobs
[src/harbor/models/job/result.py:66](/tmp/pr21src/src/harbor/models/job/result.py:66),
[:217](/tmp/pr21src/src/harbor/models/job/result.py:217),
[:223](/tmp/pr21src/src/harbor/models/job/result.py:223)

`evals` is keyed `agent__model__dataset` ([:89](/tmp/pr21src/src/harbor/models/job/result.py:89));
`seat_stats` is keyed by seat string alone. A job spans multiple datasets/tasks
([src/harbor/job_plan.py:128 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/job_plan.py:128)),
participants are one fixed list per job ([src/harbor/models/job/config.py:453 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/models/job/config.py:453)),
but `under_test` comes from each task's `[agents.<seat>]`
([src/harbor/trial/seats.py:161 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/trial/seats.py:161)),
and a resumed job folds stored trial results into fresh stats
([src/harbor/job.py:385 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/job.py:385)).
So the same seat name can arrive with a different model (edited participants on resume,
runtime-reported `agent_info`), a different `source`, or flipped `under_test`.
All merge into one entry: `agent_name`/`model_name` are last-write-wins,
`under_test` is first-write-wins (`setdefault` at
[:217](/tmp/pr21src/src/harbor/models/job/result.py:217) never updates it), and tokens sum
across both assignments. *Probe 2:* seat `main` as `gpt-A`/under-test/`dsA`, then
`claude-B`/supporting/`dsB` → one entry labelled `claude-B`, `under_test=True`,
`n_trials=2`, 200 tokens — a model that never ran under test gets the under-test row.
Note what is *not* broken: sharing one model/agent across different seats in one trial
works, because the key is the seat. The collision is across trials, which no test covers.
Fix direction: key by `(seat, source)` at minimum, or record the eval key per seat entry.

### F3 [P0] `usage_complete` is wrong in both directions and sticky across trials
[src/harbor/models/job/result.py:250](/tmp/pr21src/src/harbor/models/job/result.py:250),
[src/harbor/cli/jobs.py:412](/tmp/pr21src/src/harbor/cli/jobs.py:412)

Only `cost_usd` decides completeness; token fields are skipped per-field
([:254](/tmp/pr21src/src/harbor/models/job/result.py:254)).

- Cost present, tokens `None` → `usage_complete=True` over a partial sum. *Probe 3/10:*
  2 trials, one token-less → seat shows 100 input tokens as complete truth for `n_trials=2`.
  The PR claim "shows `unknown` rather than `0`" is false for tokens.
- Tokens present, cost `None` → `usage_complete=False`, and the CLI masks *every* column,
  including the known tokens, as `unknown`
  ([src/harbor/cli/jobs.py:443](/tmp/pr21src/src/harbor/cli/jobs.py:443)). *Probe 3b.*
- Sticky poison: `usage_complete` is never set back to `True`, and `_remove_seat_stats`
  never restores it (nor `agent_name`/`model_name`). Seat results are pre-created for
  every seat before any agent runs
  ([src/harbor/trial/seats.py:198 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/trial/seats.py:198)),
  so one setup-failed trial leaves every seat's `agent_result=None` and flips every seat
  to incomplete for the whole job. *Probe 5:* after one such trial, both seats are
  `usage_complete=False`; after `remove_trial` retracts it, still `False` — the CLI then
  prints `unknown` for a job whose remaining data is complete. This also breaks the
  stated increment/remove symmetry outside the tested path.

### F4 [P1] Seat sum ≠ job totals whenever `compute_token_cost_totals` takes its other branches
[src/harbor/models/job/result.py:205](/tmp/pr21src/src/harbor/models/job/result.py:205) vs
[src/harbor/models/trial/result.py:178 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/models/trial/result.py:178)

Job totals come from `compute_token_cost_totals`: if trial-level `agent_result` is set it
wins and seat contexts are ignored; else `step_results` *and* `seat_results` are summed
together. The seat loop ignores both rules and always sums seats only. *Probe 4:*
`agent_result` set → job reports 999 input tokens, seat sum is 200, unflagged.
Live `SeatsTrial` never sets trial `agent_result` today, so the homogeneous case holds;
the invariant is still unstated and unguarded for regraded/deserialized/hybrid results,
and for mixed jobs (seat tasks + single-agent tasks in one dataset list) where job totals
include non-seat trials with no marker that `seat_stats` covers only part of the job.
Regrade is a concrete gap: `src/harbor/trial/regrade.py` (main) contains no seat handling
at all and copies only `agent_info`/`agent_result`
([regrade.py:391 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/trial/regrade.py:391)),
so a regraded seat trial reaches `JobStats` with `seat_results=None` and `seat_stats`
silently stays empty while `evals` fills.

### F5 [P1] Supporting seats and reward-less seats are counted in `n_trials`
[src/harbor/models/job/result.py:227](/tmp/pr21src/src/harbor/models/job/result.py:227)

Every seat gets `n_trials += 1` when the *trial* is reward-valid — supporting seats
(`under_test=False`) and seats with no matching reward key included. *Probe 1:* supporting
seat `lee` has `n_trials=1`, empty `reward_stats`; seat `n_trials` sums to 2 for 1 completed
trial. Any consumer that sums seat `n_trials`, or divides reward mass by it, silently
over-counts. The new test ([test_job_stats_seats.py:182](/tmp/pr21-test.py:182)) loops over
the non-rewarded seats and asserts only `reward_stats == {}`, never their `n_trials` —
the defect sits exactly in the unasserted field. Either count a seat trial only when its
reward key is present, or rename/document the denominator before a viewer consumes it.

### F6 [P1] `exception_stats` attribution: dead branch, double- and zero-counting vs job errors
[src/harbor/models/job/result.py:235](/tmp/pr21src/src/harbor/models/job/result.py:235),
[:343](/tmp/pr21src/src/harbor/models/job/result.py:343)

- `hasattr(seat_result, "recorded_exceptions")` is always `False`:
  `SeatResult` has no such method (that is `TrialResult`
  [src/harbor/models/trial/result.py:142 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/models/trial/result.py:142);
  probe confirms). Dead code in both increment and remove, copied from the trial level.
- Trial-level exceptions are attributed to no seat. *Probe 7b:* trial-only `EnvError` →
  `n_errored_trials=1`, sum of seat `n_errors=0`. Seat sums undercount job errors silently.
- Two seats failing with the same type in one trial: `evals` dedupes by type (one entry),
  seat stats count both. *Probe 7:* `n_errored_trials=1`, sum of seat `n_errors=2`.
  Seat `n_errors` therefore neither equals nor bounds the job count in either direction,
  and nothing documents that. `CancelledError` also has no seat-level split, unlike the
  job-level `n_cancelled_trials` ([:192](/tmp/pr21src/src/harbor/models/job/result.py:192)).

### F7 [P1] Reward attribution by exact seat name misfires both ways
[src/harbor/models/job/result.py:229](/tmp/pr21src/src/harbor/models/job/result.py:229)

A verifier key equal to a seat name is credited to that seat — including generic/team keys
that collide with seat names such as `main` or `reward`. Verifiers using metric keys
(`accuracy`, `team`) credit no seat at all, yet F5 still counts the trial in every seat,
producing rows of scored-but-empty seats. `reward_stats` in a seat entry can only ever hold
the single key equal to the seat name ([:231](/tmp/pr21src/src/harbor/models/job/result.py:231)),
which a future viewer reading keys as metric names will misread. This convention needs to be
stated where task authors will see it, not only in the PR body.

## Compatibility of `result.json` consumers

- **Holds:** the eval-key format is untouched, so metrics and pass@k
  ([src/harbor/job.py:774 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/job.py:774),
  [src/harbor/utils/pass_at_k.py:13 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/utils/pass_at_k.py:13)),
  the folder viewer ([src/harbor/viewer/server.py:1345 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/viewer/server.py:1345)),
  and the DB compare grid, which rebuilds eval keys from rollout rows
  ([src/harbor/viewer/queries.py:58 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/viewer/queries.py:58)),
  keep working unchanged. Single-agent jobs gain only `seat_stats: {}`; the test at
  [test_job_stats_seats.py:119](/tmp/pr21-test.py:119) pins that.
- **Old jobs never gain seat stats.** New code reading an old `result.json` defaults
  `seat_stats` to `{}` with no backfill from the stored `trial_results[].seat_results`
  (*probe 9*). `schema_version` stays `Literal[1]`
  ([:413](/tmp/pr21src/src/harbor/models/job/result.py:413)), so consumers cannot distinguish
  "single-agent job" from "multi-seat job written before this PR". Only a resumed job
  rebuilds stats (`from_trial_results`, job.py:385 above).
- **Old binary, new file:** `JobStats` sets no `model_config`, so pydantic ignores the
  unknown `seat_stats` key and any old-binary rewrite of `result.json` drops it silently.
  Acceptable, but it is silent data loss in mixed-version fleets.
- **Compare defect remains:** two jobs that differ only in a supporting seat's model still
  produce the identical eval key (first under-test seat wins,
  [src/harbor/trial/seats.py:175 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/trial/seats.py:175)),
  so viewer/compare still cannot tell them apart — and keying the follow-up viewer change
  by bare seat name would repeat F2 across jobs.
- `SeatDatasetStats.seat`/`under_test` are required with no defaults
  ([:35](/tmp/pr21src/src/harbor/models/job/result.py:35)), unlike every `AgentDatasetStats`
  field; any partial/hand-written `seat_stats` entry now fails the whole `JobResult` load.
- `AgentContext.model_usage` (per-model subagent breakdown,
  [src/harbor/models/agent/context.py:34 (main)](/Users/petermakhnatch/Developer/harbor-multiagent/src/harbor/models/agent/context.py:34))
  is ignored: a seat's full spend, subagents included, is labelled with the seat's primary
  `model_name`. Same as job totals today, but it undercuts this PR's stated purpose.

## Test gaps (new file: tests/unit/models/test_job_stats_seats.py)

1. No second trial with the same seat name under a different model/source/`under_test` (F2).
2. No non-rewarded seat's `n_trials` asserted (F5); no trial-level-only exception (F6).
3. `usage_complete` tested only for missing cost on increment — not missing tokens,
   not stickiness, not remove (F3).
4. Remove test ([test_job_stats_seats.py:226](/tmp/pr21-test.py:226)) removes a second trial
   whose seat already has a surviving first trial; never the F1 reward-invalid seat,
   never a sole-trial seat's residue (`0` vs `None`: job tokens end at `0`, probe 8 —
   pre-existing `evals` behaviour, inherited).
5. Totals-equality test uses fully populated contexts and `agent_result=None` only (F4).

## Minor

- CLI seats table order is first-seen insertion order, unsorted
  ([src/harbor/cli/jobs.py:438](/tmp/pr21src/src/harbor/cli/jobs.py:438));
  `_format_usage` is typed `float | None` but receives ints
  ([src/harbor/cli/jobs.py:412](/tmp/pr21src/src/harbor/cli/jobs.py:412)).
- `sorted()` over a set built from a single `exception_info` is noise
  ([:243](/tmp/pr21src/src/harbor/models/job/result.py:243)).

Evidence: probes in [probe_pr21.py](/tmp/probe_pr21.py), PR source snapshot in
[/tmp/pr21src](/tmp/pr21src). No repository files were edited.
