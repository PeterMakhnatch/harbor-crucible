# Eval Lab seat evidence vs crucible loader: differential check

Status: complete. Spend: **$0** (no model calls, no Harbor launches, no Docker, no database).
No PREREG.md: this slice runs no billable trial.

## Answer

On the 4 assigned waves (44 trials, 164 seats), Eval Lab's seat commands and crucible's
`export-evallab` / `load_trial_bundle` agree on **every compared field (2364/2364 rows, 0
disagreements)**. That includes seat set, model, tokens, cost, trial and seat exception
type, timeout status, reward keys and values, trajectory presence and validity, and step
count.

The 4 assigned waves contain no missing usage, no missing trajectories and no unscored
trials, so they cannot test missing-vs-zero handling. I added 2 more inputs:

- **Extended real data**: the 20 other retained `runs/` dirs (154 trials, 530 seats).
  These hold null `agent_result`, null cost, missing trajectories, `RuntimeError` and
  `AgentTimeoutError`. Result: 108 disagreements in 2 groups. Both are **crucible
  defects** (missing collapsed to `0` or `{}`). Eval Lab reads the raw files correctly.
- **Perturbations**: 9 labeled mutations of 1 primary trial, under /tmp only. They show
  4 more crucible behaviours where crucible silently diverges from the raw record. Eval
  Lab either reports the right value or fails closed.

I found **no Eval Lab defect** in parsed values. I found 2 **layout incompatibilities**:

- The seat commands are not on eval-lab `main`.
- Crucible runs have no job-level `result.json`, and Eval Lab needs one for its job-level
  commands.

## What ran

Eval Lab is read-only. `git -C eval-lab status --porcelain` showed the same single
pre-existing untracked file before and after
(`?? research/inbox/rh-agents-validity-result-and-proposal-20261016.md`). HEAD stayed
`b9dd19245`. The `.worktrees/harbor-seat-evidence` worktree status stayed empty. Nothing
under eval-lab was written.

Eval Lab code is pinned:

- `evallab seat {inspect,trajectories,export,summary}` exist only on branch
  `pm/harbor-seat-evidence` @ `11c8b53bc`. The primary checkout `main` (`b9dd19245`) and
  `origin/main` (`3ee6a0ef3`) do not have them, so `eval-lab/.venv/bin/evallab seat`
  fails on main.
- The seat-aware `evallab jobs verify` (#2267) is on `origin/main` @ `3ee6a0ef3`. It is
  not on that branch.
- `compare.py` exports each commit's `src/` with `git archive` into
  `/tmp/evallab-seat-11c8b53bc` and `/tmp/evallab-main-3ee6a0ef3`. It runs the real CLI
  entry point with the eval-lab venv interpreter:
  `PYTHONPATH=<snapshot>/src PYTHONDONTWRITEBYTECODE=1 eval-lab/.venv/bin/python -c "from evallab.entry import main; ..." <args>`,
  with cwd `/tmp`.
- I read `job_verify.py`, `jobs_parser.py` and the `harbor_seat*.py` modules first. They
  contain no file writes and no database connection.

Commands per input dir:

| Side | Command | Input |
|---|---|---|
| Eval Lab | `seat inspect <trial>` | each original trial dir (read in place) |
| Eval Lab | `seat trajectories <trial>` | each original trial dir |
| Eval Lab | `seat export <job> --format jsonl`, `seat summary <job> --json` | /tmp job layout (see below) |
| Eval Lab | `jobs verify <job> --json` (origin/main snapshot) | /tmp job layout |
| Eval Lab | `seat inspect runs/<wave>` | original trials-dir, to record the layout failure |
| crucible | `.venv/bin/crucible export-evallab runs/<wave> --out out/crucible_export_<wave>.jsonl` | original trials-dir |
| crucible | `crucible.loader.load_trial_bundle(trial)` | each trial dir, to cross-check the export |
| raw | `compare.py:raw_trial` reads `result.json`, `config.participants`, `seats/*/agent/trajectory.json`, `verifier/reward.json` directly | each trial dir |

Rerun: `.venv/bin/python experiments/evallab_differential/compare.py`. The run takes
about 45 s. 2 consecutive runs produced byte-identical `out/` trees (77 files, shasum
diff empty). The extended cohort is a fixed list, so new waves that other lanes write
(`wave8-*`) do not change the result.

### Layout adapter (job-level commands only)

Each `runs/<wave>/` is a Harbor `--trials-dir`. It holds trial subdirs plus
`wave1_manifest.json`, and has **no job `result.json`**.

- `evallab seat inspect runs/wave4-supply-saboteur` exits 1 with
  `harbor seat evidence: missing result.json`. The same happens in all 24 dirs.
- A symlinked job layout does not work. `harbor_seats._directories` uses `lstat` and
  skips symlinked trial dirs.
- `compare.py` builds `/tmp/crucible-evallab-jobs/<wave>/` from APFS clones
  (`cp -cR`) of each trial dir. It adds a synthetic job `result.json` with `id`,
  `started_at`/`finished_at` (min/max of the trials), `n_total_trials`,
  `stats.n_completed_trials` and the marker `"_synthetic_layout_adapter"`.
- The originals are never written. Per-trial commands read the originals in place.

The synthetic job record has no `stats.evals`. Because of this, `jobs verify` returns
`block:job_stats_missing_evals` on every job. That finding comes from the adapter. It is
not a property of the runs. All other `jobs verify` findings are per trial and stay valid.

## Coverage

| Cohort | Dirs | Trials | Eval Lab `seat inspect` ok | Eval Lab `trajectories` ok | Eval Lab export rows | crucible trials | crucible seats |
|---|---:|---:|---:|---:|---:|---:|---:|
| primary (assigned 4 waves) | 4 | 44 | 44 | 44 | 164 | 44 | 164 |
| extended (20 other retained dirs) | 20 | 154 | 154 | 154 | 530 | 154 | 530 |
| perturbation (/tmp, synthetic) | 1 | 9 | 8 (1 fails closed, intended) | 8 | n/a | 9 | 37 |

Both sides parsed every real trial. The Eval Lab job-level export rows match the
per-trial `seat inspect` and `trajectories` output on all 694 real seats (field
`evallab_export_vs_inspect`). The crucible export matches `load_trial_bundle` on all 198
real trials (field `crucible_export_vs_loader`).

## Agreement per field

Source: `out/TABLE.md`. The real-data rate covers primary + extended only.

| Field | Primary | Extended | Real-data rate | Perturbation |
|---|---:|---:|---:|---:|
| parsed | 44/44 | 154/154 | 1.000 | 8/9 |
| seat_set | 44/44 | 154/154 | 1.000 | 8/9 |
| seat_present | 164/164 | 530/530 | 1.000 | 36/37 |
| agent_model | 164/164 | 530/530 | 1.000 | 35/36 |
| n_input_tokens | 164/164 | 530/530 | 1.000 | 36/36 |
| n_output_tokens | 164/164 | 530/530 | 1.000 | 36/36 |
| n_cache_tokens | 164/164 | 530/530 | 1.000 | 36/36 |
| cost_usd (seat) | 164/164 | 530/530 | 1.000 | 36/36 |
| cost_total_usd (trial, ±5e-7) | 44/44 | 154/154 | 1.000 | 9/9 |
| cost_complete | 44/44 | 154/154 | 1.000 | 8/9 |
| exception_type (trial) | 44/44 | 154/154 | 1.000 | 8/9 |
| is_timeout | 44/44 | 154/154 | 1.000 | 8/9 |
| seat_exception_type | 164/164 | 530/530 | 1.000 | 36/36 |
| reward_keys | 44/44 | 147/154 | 0.965 | 8/9 |
| reward_values | 44/44 | 147/154 | 0.965 | 8/9 |
| trajectory_present | 164/164 | 530/530 | 1.000 | 32/36 |
| trajectory_valid | 164/164 | 530/530 | 1.000 | 30/36 |
| n_steps | 164/164 | 436/530 | 0.865 | 29/36 |
| evallab_usage_mismatch_vs_atif | 164/164 | 530/530 | 1.000 | 35/36 |

Comparison rules:

- Usage counts as "absent" when Eval Lab omits the key or crucible writes `null`. Both
  mean "not recorded". A recorded `0` is a number, so missing-vs-zero stays a
  disagreement.
- Real data has 94 seats with absent cost (null `agent_result` or `cost_usd: null`).
  Both sides keep all 94 absent and not zero.
- Trial cost: crucible rounds `recorded_cost_usd` to 6 decimals. The largest observed
  difference from Eval Lab's `known_sum` is 4.98e-7, so the tolerance is 5e-7. This
  precision loss is crucible's documented behaviour, not a disagreement.
- Rewards are compared numerically. Crucible converts integer rewards to float (`2` →
  `2.0`). Eval Lab keeps the JSON type. The values are equal.
- Timeouts: 24 real trials have a trial-level `AgentTimeoutError` and 7 have a
  `RuntimeError`. Both sides report all 31.
- Every seat-level exception in real data (23 trials) occurs together with a trial-level
  `AgentTimeoutError`. Crucible's "exclude trials whose `trial_exception` contains
  timeout" rule therefore covers every seat timeout. Eval Lab `jobs verify` emits
  `warn:seat_exception_beside_reward` for the same trials:
  - smoke-openrouter: 3
  - smoke-openrouter-qwen: 1
  - wave1-migration: 4
  - wave1-migration2: 5
  - wave1-supply: 14
  - wave2-reward-qwen: 12
  - wave6-supply-qwen: 5
  - wave7-supply-qwen-long: 2
- No real trial gets a seat roster finding (`seat_results_missing`,
  `seat_participant_mismatch`, `seat_duplicate`).

## Disagreements on real data (108 rows; full list in `out/disagreements.csv`)

### R1. Missing trajectory reported as `n_atif_steps: 0` (94 seat rows): crucible defect

- **Where.** 94 seats with no `trajectory.json`:
  - `runs/oracle`: 23 trials, 75 seats
  - `runs/oracle3`: 12 seats
  - `runs/probe-id`: 4 seats
  - `runs/smoke-openrouter/variants-clean-99a0bbec61`: 3 seats
- **Eval Lab.** Trajectory `status: "absent"` with no step count.
- **crucible.** `trace_present: false` and `n_atif_steps: 0`.
- **Raw.** `runs/oracle/aligned_control__E33SNsk/seats/migrator_c/agent/` is empty.
  `runs/smoke-openrouter/variants-clean-99a0bbec61/seats/planner/agent/` holds only
  `setup/` and `mini-swe-agent.txt`. No trajectory exists, so the step count is unknown,
  not zero.
- **Verdict.** Eval Lab is correct. Crucible `bridge.export_evallab_seat_record` writes
  `len(bundle.seat_steps.get(seat, []))`, and the loader stores `[]` for a missing file.
  This merges "missing" with "zero steps". The `trace_present` field in the same record
  separates the cases here. Perturbation P2 shows a case where it does not.
- **Repro.**
  `.venv/bin/python -c "from crucible.loader import load_trial_bundle as L; from crucible.bridge import export_evallab_seat_record as E; r=E(L('runs/oracle/aligned_control__E33SNsk')); print([(s['seat'],s['trace_present'],s['n_atif_steps']) for s in r['seats']])"`
  - Expected: `n_atif_steps` is `None`.
  - Actual (observed): `[('migrator_c', False, 0), ('migrator_ruby', False, 0), ('migrator_ts', False, 0)]`.
  - Eval Lab on the same trial: `seat trajectories` gives `('migrator_c','absent',None)` and the same for the other 2 seats.

### R2. Unscored trial reported as `rewards: {}` (7 trials × 2 fields = 14 rows): crucible defect

- **Where.** `runs/oracle/{aligned_control__E33SNsk, aligned_control__cuP28HL, aligned_control__mWifieT, conflicting_blind__7H7DBGA, conflicting_blind__MN9aZKZ, conflicting_with_protocol__M5AhdwH, conflicting_with_protocol__tyx2Hkm}`.
- **Eval Lab.** `rewards: null`, `reward_valid: false`.
- **crucible.** `rewards: {}`. `task_utility` and `safety_score` are `null`.
- **Raw.** Each `result.json` has `"verifier_result": null`, `"reward_valid": false` and
  `exception_info.exception_type: "RuntimeError"`. The `verifier/` dir is empty, and
  there is no `reward.json` or `reward.txt`. No reward was recorded.
- **Verdict.** Eval Lab is correct. Crucible `loader._load_rewards` returns an empty dict
  for "no verifier result", so "not graded" and "graded with no metrics" look the same.
  Crucible also has no `reward_valid` field.
- **Impact.** [INFERENCE] The impact is low today. These are oracle dirs that I believe
  are not in any monitor benchmark. Crucible's exclusion filter matches only "timeout",
  so a `RuntimeError` trial with `{}` rewards would pass that filter.
- **Repro.** Use the same command as R1, but print `r['rewards']`.
  - Expected: `None`.
  - Actual (observed): `{}`.
  - Eval Lab `seat inspect` on the same trial: `rewards= None reward_valid= False issues= []`.

## Perturbation findings (synthetic; /tmp only; not counted in real-data rates)

`compare.py` copies `runs/wave4-supply-saboteur/variants-saboteur-dc962bb8fd` (APFS
clone) into `/tmp/crucible-evallab-perturb/<case>/`. It gives each copy a unique
`id`/`trial_name` and applies 1 mutation. Run `compare.py` first, then use the repro
commands below. Crucible output comes from `export_evallab_seat_record(load_trial_bundle(<dir>))`.
Eval Lab output comes from the pinned `seat` CLI.

| Case | Eval Lab | crucible | Raw truth | Verdict |
|---|---|---|---|---|
| P1 `zero_usage` (builder tokens/cost set to 0) | 0 kept; also flags `usage_mismatch` on 4 fields against ATIF `final_metrics` | 0 kept; no cross-check | result.json says 0; trajectory `final_metrics` says 78716/3707/73216/$0.003268848 | Both keep zero distinct from missing (positive control). Only Eval Lab detects the result/ATIF inconsistency. Crucible has no equivalent check (gap, not a wrong value). |
| P2 `trajectory_invalid_json` (truncated JSON) | `status: invalid`, `issues: [invalid_json]` | `trace_present: true`, `n_atif_steps: 0` | file exists, does not parse | **crucible defect**: an unparseable trajectory looks the same as a valid empty one. Observed: `('builder', True, 0, ...)`. |
| P3 `trajectory_steps_not_list` (`steps` is an object) | `status: invalid`, `issues: [invalid_steps]` | `trace_present: true`, `n_atif_steps: 0` | ATIF invalid | **crucible defect**, same as P2. |
| P4 `trajectory_missing` | `absent` | `trace_present: false`, `n_atif_steps: 0` | no file | Same as R1. |
| P5 `reward_json_differs` (`verifier/reward.json` rewritten after the run) | result.json rewards (7 keys, `task_utility 0.6`); `jobs verify`: `block:reward_mismatch_result_vs_file` | reward.json rewards (`{task_utility: 0.0, safety_score: 0.0}`), no warning | Harbor's verifier parses reward.json once, at grading (`harbor/verifier/verifier.py`), into `result.json.verifier_result.rewards`. That record is the harness verdict. | **crucible latent defect**: `_load_rewards` prefers the mutable `verifier/reward.json` over `result.json` and does not compare them. 0/198 real trials have a difference (checked over all retained `runs/`). Eval Lab reads the recorded verdict and blocks on the mismatch. |
| P6 `undeclared_seat_dir` (empty `seats/intruder/agent/`) | ignores it; seat set = 4 declared seats | seat set = 5 (`intruder`, model `unknown`); `usage_accounting.complete` changes to `false` | `config.participants` and `seat_results` list 4 seats | **crucible defect**: a stray directory changes the seat roster and cost completeness. Eval Lab is correct by its contract ("immediate trial results are authoritative"), but it does not report the stray dir (minor Eval Lab gap, no wrong value). |
| P7 `seat_result_dropped` (builder removed from `seat_results`) | `seat inspect` exits 1 with `issues: [missing_seat]`; `trajectories` refuses; `jobs verify`: `block:seat_participant_mismatch` | parses with no warning; builder recovered from `seats/` dir with model `unknown`, usage null, `complete: false` | config declares builder (`deepseek-chat`); its seat run is not recorded | Eval Lab is correct to fail closed. **crucible defect**: it does not flag the roster mismatch, and it reports model `unknown` although `config.participants` names the model (the loader reads participants only when `seat_results` is missing entirely). |
| P8 `exception_info_without_type` | `exception_type: null` | `trial_exception: ""` | `exception_info` present without a type | Representation difference only. Harbor's `ExceptionInfo.exception_type: str` is required (`harbor/models/trial/result.py:31`), so valid Harbor output cannot contain this. No defect. |
| P9 `null_agent_result` | usage keys omitted, cost null | usage null | `agent_result: null` | Agree. Both keep it absent, not zero. |

Repro for P2, P5, P6 and P7 (after `compare.py` has built `/tmp/crucible-evallab-perturb`):

```bash
.venv/bin/python -c "import sys; from crucible.loader import load_trial_bundle as L; from crucible.bridge import export_evallab_seat_record as E; r=E(L(sys.argv[1])); print([(s['seat'],s['trace_present'],s['n_atif_steps'],s['model']) for s in r['seats']], r['rewards'], r['usage_accounting'])" /tmp/crucible-evallab-perturb/<case>
```

Observed crucible output:

- `trajectory_invalid_json`: `('builder', True, 0, 'deepseek-chat')`.
- `reward_json_differs`: rewards `{'task_utility': 0.0, 'safety_score': 0.0}`.
- `undeclared_seat_dir`: adds `('intruder', False, 0, 'unknown')` and `complete=False`.
- `seat_result_dropped`: `('builder', True, 17, 'unknown')` and `complete=False`.

Eval Lab counterpart for the same cases:

- `seat trajectories /tmp/crucible-evallab-perturb/trajectory_invalid_json` gives `('builder','invalid',['invalid_json'])`.
- `seat inspect /tmp/crucible-evallab-perturb/seat_result_dropped` gives `issues ['missing_seat']` and exits 1.

## Defect list

### crucible (owner: harbor-crucible; I did not change any of it)

1. **R1/P4**: `bridge.export_evallab_seat_record` writes `n_atif_steps: 0` for a missing
   trajectory. Write `null` when `seat in bundle.missing_traces`. Observed on 94 real
   seats.
2. **P2/P3**: an unparseable or schema-invalid trajectory gives `trace_present: true,
   n_atif_steps: 0`. The loader drops the parse error. Add a `trajectory_valid` field
   or put these seats in `missing_traces`. Not seen in real data.
3. **R2**: `loader._load_rewards` returns `{}` when the trial was not graded. Return
   `None` and export `reward_valid`. Observed on 7 real trials.
4. **P5**: rewards come from `verifier/reward.json` before `result.json`, without a
   consistency check. Prefer `result.json.verifier_result.rewards` and report a
   mismatch. Real data: 0/198 trials have a difference.
5. **P6/P7**: the seat roster is the union of `seat_results` and `seats/*` dirs. A
   roster mismatch with `config.participants` is not flagged, and a recovered seat gets
   model `unknown`. Not seen in real data.

### Eval Lab

None found in parsed values. The only gaps are in visibility:

- An undeclared `seats/<x>` dir is not reported (P6).
- `seat inspect` reports a missing seat's model as `null`, although `config.participants`
  names it. It already flags `missing_seat`, so this is minor.

### Layout incompatibilities (neither side is wrong)

1. Eval Lab job-level commands (`seat export/summary/batch/pair/gate`, `jobs verify`)
   need a Harbor *job* dir with a job `result.json`. Crucible runs use `--trials-dir`
   without a job. Workaround: the /tmp clone plus synthetic job record above.
   - Symlinks do not work.
   - `jobs verify` then always reports `block:job_stats_missing_evals`, because of the
     adapter.
   - A native fix is either for crucible's `run_wave1.py` to launch through a Harbor job
     (`harbor run` with a job dir), or for Eval Lab to accept a trials-dir.
2. The `evallab seat …` commands are on branch `pm/harbor-seat-evidence` (`11c8b53bc`).
   They are not on eval-lab `main` (`b9dd19245`) or `origin/main` (`3ee6a0ef3`). The
   seat-aware `jobs verify` is on `origin/main` only. To use both, you need 2 snapshots.

## Caveats

- **Primary cohort.** The 4 assigned waves are clean: no missing usage, no missing
  trajectory, 1 timeout trial. 100% agreement there shows only that the common path
  matches. It does not test edge-case handling.
- **Extended cohort.** These are real retained runs, pinned as a fixed list. They include
  smoke and oracle dirs, which are not part of crucible's headline results.
- **Perturbations.** They are synthetic. They show what each tool does with malformed
  input. They do not show that such input occurs. I verified the occurrence rate only
  for P5 (0/198 trials).
- **Not compared.** Eval Lab `seat timing`, `seat retries`, `seat pair/batch/gate`.
  There is no crucible counterpart, and pair/gate need 2 locked jobs.
- **Single run.** I ran the comparison on 1 machine state. Determinism holds for the
  pinned inputs: 2 runs gave identical shasums.

## Files

- `experiments/evallab_differential/compare.py`: the differential script.
  `ruff check` and `ruff format --check` pass.
- `experiments/evallab_differential/out/`: generated output. Every rerun replaces it.
  - `comparison.csv`: 10588 rows, every field × trial/seat.
  - `disagreements.csv`: now 17 rows (0 real + 17 perturbation). Before the fixes it
    had 135 rows (108 real + 27 perturbation).
  - `TABLE.md`
  - `summary.json`: coverage, per-cohort agreement, `jobs verify` findings, command
    errors.
  - `crucible_export_<wave>.jsonl` (absolute `trial_dir` reduced to the dir name)
  - `evallab_export_<wave>.jsonl`
  - `evallab_summary_<wave>.json`
- /tmp only:
  - `/tmp/evallab-seat-11c8b53bc`
  - `/tmp/evallab-main-3ee6a0ef3`
  - `/tmp/crucible-evallab-jobs/`
  - `/tmp/crucible-evallab-perturb/`
  - `/tmp/crucible-evallab-seat-status.{before,after}`
- `experiments/evallab_differential/monitor_scores.py`: dumps every frozen-monitor
  score (198 trials × 5 tiers) with the current or another crucible `src/` (set
  `PYTHONPATH`). It proves that the loader fixes leave monitor inputs unchanged.

## After the fixes

All sections above describe the crucible code before the fixes. Main asked for 6
crucible-side fixes. I made them in `src/crucible/{loader,bridge,schema,cli,report,trace}.py`.
`monitor.py`, README, docs, `run_wave1.py` and `tasks/` are not changed. Nothing is
committed.

### What changed

| # | Defect | Fix |
|---|---|---|
| 1 | R1: a missing trajectory reported as `n_atif_steps: 0` | The export writes `n_atif_steps: null` when the seat has no trajectory. `trace_present: false` stays. A new seat field `trace_valid` is `null` when there is no file. |
| 2 | R2: an ungraded trial reported as `rewards: {}` | `TrialBundle.rewards` is now `dict \| None`. `verifier_result: null` gives `None`. The export writes `rewards`, `task_utility` and `safety_score` as `null`. `cli.py`, `report.py` and `trace.py` treat `None` as no rewards. |
| 3 | An invalid trajectory looked like a valid empty one | `_parse_atif_steps` returns `None` for unparseable JSON, for `steps` that is not a list of objects, and for malformed steps. The new `TrialBundle.invalid_traces` lists those seats. The export writes `trace_valid: false, n_atif_steps: null`. A valid empty trajectory stays `trace_valid: true, n_atif_steps: 0`. `seat_steps` keeps `[]` for invalid seats, so the monitor input type does not change. |
| 4 | `verifier/reward.json` was silently preferred | Rewards come from `result.json` (Harbor's record) whenever it exists. `reward.json` is used only when there is no `result.json`. New bundle and export fields: `reward_source` (`result_json` / `reward_json` / `null`) and `reward_file_mismatch` (`true` when the file differs from the record). |
| 5 | A stray `seats/<x>` dir became a seat | A dir with no matching seat result or participant is not a seat. It is recorded in the new `seat_anomalies` as `undeclared_seat_dir:<x>`. If no roster is recorded at all, the dir names are the only seat evidence. They are still used, and flagged `seat_from_dir_only:<x>`. |
| 6 | A missing seat result lost the model | A participant in `config.participants` (from `result.json`, else `config.json`) with no seat result is still a seat. Its model comes from `model_name`. It is flagged `missing_seat_result:<seat>`. Its usage stays `null`, so `usage_accounting.complete` is `false`. |

The export schema id stays `crucible-evallab-seat-evidence/v1`. The record gets 3 new
top-level keys (`reward_source`, `reward_file_mismatch`, `seat_anomalies`) and 1 new
seat key (`trace_valid`). `n_atif_steps` and `rewards` can now be `null`. Seat order
on real data does not change: seat results come first, then declared seats that have
no result.

### Tests

`tests/test_loader_evidence_fidelity.py` adds 11 tests, 1 or more per fix. All 11 fail
on the code before the fixes and pass after. I checked this by running them against
`git archive HEAD src` in `/tmp/crucible_head`.

| Fix | Tests |
|---|---|
| 1 | `test_missing_trajectory_reports_no_step_count` |
| 2 | `test_ungraded_trial_reports_no_rewards` |
| 3 | `test_unparseable_trajectory_is_invalid_not_empty`, `test_steps_not_a_list_is_invalid`, `test_valid_empty_trajectory_keeps_zero_steps` |
| 4 | `test_result_json_rewards_win_and_a_differing_file_is_flagged`, `test_matching_reward_file_is_not_flagged`, `test_reward_file_is_the_fallback_only_without_result_json` |
| 5 | `test_stray_seat_dir_is_an_anomaly_not_a_seat`, `test_seat_dirs_are_the_roster_only_when_nothing_is_declared` |
| 6 | `test_missing_seat_result_takes_model_from_participants` |

I changed 2 existing assertions in `tests/test_loader_trace_bridge_spend.py`. Both
changes follow from the new contract:

- The sample fixture's `reward.json` has an extra `sabotage_success` key that
  `result.json` does not have. The test now expects the `result.json` rewards plus
  `reward_file_mismatch is True`.
- The consumer-contract key sets now include the new keys.

Checks run:

- `.venv/bin/pytest -q -p no:cacheprovider`: **111 passed**.
- `.venv/bin/ruff check src tests experiments`: all checks passed.
- `.venv/bin/ruff format --check src tests experiments`: 59 files already formatted.

### Monitor scores do not change on real data

1. **Canonical report.** The command was
   `crucible report <14 corpus_roots of report_final5> --exclude-timeouts --integrity-families supply-chain-sabotage,reward-hack-contagion,epistemic-crucible --out-dir /tmp/report_check --stability-draws 1000`.
   - `monitor_summary_by_family` is identical to `experiments/report_final5/report.json`.
     A sorted-JSON `diff` is empty.
   - `monitor_summary`, `stability`, `conditions`, `n_trials` (130),
     `n_scored_for_integrity` (122) and `n_excluded_timeouts` (8) are also identical.
   - Only `corpus_commit` and `spend` differ. They read the current git HEAD and the
     shared spend ledger, which other lanes keep appending to.
   - I ran the same command before any code change (`/tmp/report_check_before`). It
     matched in the same way.
2. **Every trial, every tier.** `monitor_scores.py` scored all 198 trials in the
   primary and extended dirs at all 5 tiers: 990 verdicts. It ran once with the code
   before the fixes (`PYTHONPATH=/tmp/crucible_head/src`) and once with the fixed code.
   Score, top seat, per-seat scores, seat list and per-seat step counts are identical
   in all 990 rows.
3. **Waves still being written.** I ran the same old/new comparison on the 18 trials
   that existed in `runs/wave8-reward-instructed` and `runs/wave8-supply-evasive` at
   check time (90 verdicts). It found 0 differences.

Why real data cannot move:

- On all 211 retained trials, `reward.json` equals the `result.json` rewards.
- No trial has a stray seat dir or a declared seat without a result.
- Eval Lab finds every real trajectory valid ATIF, so no real seat changes from
  "parsed" to "invalid".
- The frozen monitor reads `seats` and `seat_steps` only. Neither changes.

### Before / after (compare.py rerun)

| Cohort | Disagreements before | After |
|---|---:|---:|
| primary (44 trials) | 0 | 0 |
| extended (154 trials) | 108 | **0** |
| perturbation (9 synthetic trials) | 27 | 17 |

After the fixes, every real-data field agrees at 1.000. `n_steps` was 0.865 and is
now 1.000. `reward_keys` and `reward_values` were 0.965 and are now 1.000.

The 17 remaining perturbation rows are below. None of them is a crucible value that
contradicts the raw files:

| Case | Rows | Why it remains |
|---|---:|---|
| `seat_result_dropped` | 12 (`n_steps`, `trajectory_present`, `trajectory_valid` × 4 seats) | Eval Lab fails closed (`issues: [missing_seat]`). `seat trajectories` then refuses the whole trial, so Eval Lab reports nothing. Crucible reports the real trajectories: 17/19/18/20 steps, which match the files. It also flags `missing_seat_result:builder`. This is Eval Lab's design, not a defect on either side. |
| `seat_result_dropped` | 1 (`agent_model`) | Crucible now reports `deepseek/deepseek-chat` from `config.participants` (fix 6). Eval Lab reports `null` for a declared seat with no seat result. My raw helper reads only `seat_results`, so the table's `matches_raw` says "evallab". The config does declare the model, so crucible is correct here. This is a minor Eval Lab gap. |
| `undeclared_seat_dir` | 1 (`parsed`) | Crucible now flags `undeclared_seat_dir:intruder` (fix 5). Eval Lab ignores stray dirs and reports no issue. Both report the same seat set. Crucible is stricter here, and Eval Lab has a visibility gap. |
| `exception_info_without_type` | 2 (`exception_type`, `is_timeout`) | Crucible keeps `""` to show that an exception record exists without a type. Eval Lab reports `null`. Harbor requires `ExceptionInfo.exception_type`, so real output cannot contain this case. I did not change it. |
| `zero_usage` | 1 (`evallab_usage_mismatch_vs_atif`) | Eval Lab cross-checks `result.json` usage against the ATIF `final_metrics`. Crucible has no such check. It still reports the recorded 0 correctly. This is a missing feature, not a wrong value, and it was not in scope. |

Eval Lab `jobs verify` on the perturbation job still reports
`block:reward_mismatch_result_vs_file` and `block:seat_participant_mismatch`. Crucible
now reports both cases too, as `reward_file_mismatch: true` and
`seat_anomalies: ["missing_seat_result:builder"]`.

### Impact on other code

`experiments/instructed_hacker/score.py` (another lane's file, which I did not change)
calls `b.rewards.get(...)`. That call raises an error for an ungraded trial, where
`rewards` is now `None`, unless that trial is excluded as a timeout. No retained trial
in its input dirs is ungraded. I sent the owner (`InstructedHacker`) the fix:
`(b.rewards or {}).get(...)`. `run_wave1.py` reads reward files itself and does not use
`TrialBundle`, so these changes do not affect it.

