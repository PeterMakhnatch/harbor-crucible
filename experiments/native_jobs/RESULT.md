# Native Harbor jobs for Crucible

Both smoke jobs produced Harbor `config.json`, `result.json`, `lock.json`, and 2 trial directories. Crucible and Eval Lab read those directories directly. Neither job needs a synthetic record.

## What changed

- `run_seat_job` launches `harbor jobs start -c <config>` with 1 local task and 1 participant per declared seat. The job runs 1 trial at a time by default.
- The launcher checks the full job estimate before it starts. It records reported seat costs and estimates missing costs from tokens, as the single-trial launcher does.
- `run_wave1.py --as-job` runs 1 job per condition at `<out-dir>/<condition>/`. Use a new `--out-dir` to repeat a condition. The wave manifest stays at `<out-dir>/wave1_manifest.json`. Each row has the job exit status and the cumulative ledger spend after the job.
- Without `--as-job`, the wave still launches and accounts for trials individually. `run_seat_trial`, the loader, the report, and the export did not change.

## Smoke jobs and spend

Run these commands from the Crucible checkout. The DeepSeek command uses `DEEPSEEK_API_KEY` from the environment. These are compatibility checks, not new data for the monitor benchmark.

```bash
.venv/bin/python -c 'from pathlib import Path; from crucible.runner import run_seat_job; rc, job, output = run_seat_job(Path("tasks/supply-chain-sabotage/variants/saboteur"), Path("runs"), job_name="job-oracle-smoke", n_attempts=2); print(job, output, sep="\n"); raise SystemExit(rc)'
.venv/bin/python experiments/run_wave1.py --as-job --family epistemic-crucible \
  --conditions gullibility_p50 --attempts 2 --planned-usd-per-trial 0.02 \
  --out-dir runs/job-model-smoke
```

| Job directory | Harbor exit | Completed / planned | Native `stats.evals` key | Model spend |
|---|---:|---:|---|---:|
| `runs/job-oracle-smoke` | 0 | 2 / 2 | `oracle__adhoc` | $0 |
| `runs/job-model-smoke/gullibility_p50` | 0 | 2 / 2 | `mini-swe-agent__deepseek-chat__adhoc` | $0.010064352 |

The model job checked $0.04 of headroom against the shared ledger. It added 8 entries to `experiments/spend_ledger.jsonl`. The entries match the exact seat costs in the trial results; none are estimates.

| Model trial | Seat entries | Cost |
|---|---:|---:|
| `gullibility_p50__2Sqv5xa` | 4 | $0.004697064 |
| `gullibility_p50__AgjPSjt` | 4 | $0.005367288 |

## Reader checks

Each invocation takes an original Harbor job directory. Eval Lab runs from `/tmp` with its own virtual environment and source extracted from the specified commit. These commands do not write to Eval Lab or the Harbor job directories.

```bash
repo=$PWD
base=$(mktemp -d /tmp/crucible-native-jobs.XXXXXX)
for rev in 3ee6a0ef3 11c8b53bc; do
  mkdir "$base/$rev"
  git -C ../eval-lab archive "$rev" src sql pyproject.toml | tar -x -C "$base/$rev"
done

eval_snapshot() (
  rev=$1; shift
  cd /tmp
  PYTHONPATH="$base/$rev/src" PYTHONDONTWRITEBYTECODE=1 \
    "$repo/../eval-lab/.venv/bin/python" -W ignore -c \
    "import sys;from evallab.entry import main;sys.argv[0]='evallab';sys.exit(main())" "$@"
)

for root in "$repo/runs/job-oracle-smoke" "$repo/runs/job-model-smoke/gullibility_p50"; do
  name=$(basename "$root")
  .venv/bin/python -c 'from crucible.loader import discover_trial_dirs; import sys; print(*discover_trial_dirs(sys.argv[1]), sep="\n")' "$root"
  .venv/bin/crucible report "$root" --out-dir "$base/$name-report" --stability-draws 0
  .venv/bin/crucible export-evallab "$root" --out "$base/$name-crucible.jsonl"
  eval_snapshot 3ee6a0ef3 jobs verify "$root" --json > "$base/$name-verify.json"
  eval_snapshot 11c8b53bc seat inspect "$root" > "$base/$name-inspect.json"
  for trial in "$root"/*/; do
    eval_snapshot 11c8b53bc seat inspect "$trial" > "$base/$(basename "$trial")-inspect.json"
  done
  eval_snapshot 11c8b53bc seat summary "$root" --json > "$base/$name-summary.json"
  eval_snapshot 11c8b53bc seat export "$root" --format jsonl > "$base/$name-seats.jsonl"
done
```

| Command | Oracle job | DeepSeek job |
|---|---|---|
| `discover_trial_dirs` | 2 immediate trial directories | 2 immediate trial directories |
| `crucible report` | Exit 0; 2 trials, 2 scored | Exit 0; 2 trials, 2 scored |
| `crucible export-evallab` | Exit 0; 2 trial rows, 8 seats | Exit 0; 2 trial rows, 8 seats |
| `jobs verify --json` (`3ee6a0ef3`) | Exit 1; 2 / 2 indexed, 1 false block, 0 warnings | Exit 0; 2 / 2 indexed, 0 blocks, 0 warnings |
| `seat inspect` on the job and each trial (`11c8b53bc`) | All 3 exit 0; no issues | All 3 exit 0; no issues |
| `seat summary --json` (`11c8b53bc`) | Exit 0; 2 valid reward trials, 0 errors | Exit 0; 2 valid reward trials, 0 errors |
| `seat export --format jsonl` (`11c8b53bc`) | Exit 0; 8 seat rows, 8 absent trajectories | Exit 0; 8 seat rows, 8 valid trajectories |

The oracle does not report model costs or trajectories. Eval Lab leaves its cost unknown. The model job reports complete costs of $0.010064352. Both summaries show a peak of 1 concurrent trial.

## Before and after

The [previous differential](../evallab_differential/RESULT.md#layout-adapter-job-level-commands-only) reported `missing result.json` on raw wave directories. The synthetic records removed that error but caused `block:job_stats_missing_evals` because they had no `stats.evals`. Neither finding occurs on either native job.

The remaining oracle block, `job_stats_reward_desync`, is a false positive in the pinned Eval Lab verifier:

- Harbor stores the integer reward keys `"1"` (`ground_truth_deceptive_reports`) and `"2"` (`hoarded_keystone_units`).
- Eval Lab converts trial rewards to `float` in `_check_trial`. It compares `"1.0"` and `"2.0"` to Harbor's original strings in `_check_job_stats`.
- An independent comparison used `Decimal` for each reward value and compared the trial names in each bucket. All 7 oracle buckets and all 9 model buckets match the native job stats. No artifact changed.

Both jobs have 2 informational findings. `task_digest_namespace` notes that lock digests and trial checksums use different namespaces. `pass_at_k_empty` is expected because both jobs have multiple reward metrics. Neither is a warning or a block.

## Local checks

- `.venv/bin/pytest -q -p no:cacheprovider`: 133 passed. The pytest-asyncio configuration deprecation warning does not affect the result.
- `.venv/bin/ruff check src tests experiments`: passed.
- `.venv/bin/ruff format --check src tests experiments`: passed.

## Follow-up: the Eval Lab false block is fixed (2026-11-20)

Eval Lab PR [#2268](https://github.com/PeterMakhnatch/eval-lab/pull/2268), merged as `232d69c869`, compares Harbor reward buckets by numeric value, so `"1"`, `"1.0"` and `1` are one bucket; different values or trial lists still block. Re-run on merged `main`: `job-oracle-smoke` now exits 0 with 0 blocks and 0 warnings (was exit 1 with `job_stats_reward_desync`); `job-model-smoke` is unchanged at 0 blocks. The bug affected any Harbor job with an integer-valued reward, not only seat tasks.
