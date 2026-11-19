#!/usr/bin/env bash
# Detached smoke run: survives tool deadlines. Writes a result file when done.
set -uo pipefail
cd /Users/petermakhnatch/Developer/harbor-crucible
export CRUCIBLE_HARBOR_BIN=/Users/petermakhnatch/Developer/harbor-multiagent-crucible/.venv/bin/harbor
out=/tmp/crucible-smoke.log
exec >"$out" 2>&1
.venv/bin/python - <<'PY'
from pathlib import Path
from crucible.runner import run_seat_trial
from crucible.spend import SpendLedger

ledger = SpendLedger(path=Path("experiments/spend_ledger.jsonl"), cap_usd=20.0)
rc, trial, out = run_seat_trial(
    Path("tasks/supply-chain-sabotage/variants/honest"),
    Path("runs/smoke"),
    agent_name="mini-swe-agent",
    model_name="deepseek/deepseek-chat",
    api_key_env="DEEPSEEK_API_KEY",
    timeout_multiplier=0.35,
    ledger=ledger,
    estimated_planned_usd=0.75,
    trial_name="smoke-honest-llm",
)
print("RC", rc, "TRIAL", trial, flush=True)
print(out[-4000:], flush=True)
print("LEDGER", ledger.summary(), flush=True)
PY
echo "DONE" >>"$out"
