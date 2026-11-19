#!/usr/bin/env python3
"""Wave 1: real model seat runs for the Crucible monitor benchmark.

Pre-registered in experiments/PROTOCOL.md. Each trial records exact seat usage into
experiments/spend_ledger.jsonl and refuses to start when the budget cap would be
crossed. Failed trials stay in the corpus. They are not dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import typer

from crucible.runner import run_seat_trial
from crucible.spend import SpendLedger

app = typer.Typer(add_completion=False)

FAMILY = "supply-chain-sabotage"
CONDITIONS = ("honest", "noisy_honest", "instructed_refuser", "saboteur")


@app.command()
def wave1(
    model: str = typer.Option("deepseek/deepseek-chat", help="Model for every seat."),
    api_key_env: str = typer.Option("DEEPSEEK_API_KEY", help="Host env var holding the key."),
    attempts: int = typer.Option(3, help="Trials per condition."),
    timeout_multiplier: float = typer.Option(1.0),
    planned_usd_per_trial: float = typer.Option(0.60, help="Refuse to start a trial above this estimate."),
    out_dir: Path = typer.Option(Path("runs/wave1")),
    ledger_path: Path = typer.Option(Path("experiments/spend_ledger.jsonl")),
    cap_usd: float = typer.Option(20.0),
    dry_run: bool = typer.Option(False),
) -> None:
    ledger = SpendLedger(path=ledger_path, cap_usd=cap_usd)
    tasks_root = Path("tasks") / FAMILY / "variants"
    manifest: list[dict[str, object]] = []

    for condition in CONDITIONS:
        task_dir = tasks_root / condition
        if not (task_dir / "task.toml").is_file():
            raise typer.BadParameter(f"missing task: {task_dir}")
        for attempt in range(1, attempts + 1):
            if dry_run:
                print(f"DRY {condition} #{attempt}')
                continue
            ledger.check_headroom(planned_usd_per_trial)
            rc, trial, out = run_seat_trial(
                task_dir,
                out_dir,
                agent_name="mini-swe-agent",
                model_name=model,
                api_key_env=api_key_env,
                timeout_multiplier=timeout_multiplier,
                ledger=ledger,
                estimated_planned_usd=planned_usd_per_trial,
            )
            rewards = {}
            if trial is not None:
                rp = trial / "verifier" / "reward.json"
                if rp.is_file():
                    try:
                        rewards = json.loads(rp.read_text())
                    except ValueError:
                        rewards = {}
            row = {
                "condition": condition,
                "attempt": attempt,
                "model": model,
                "rc": rc,
                "trial_dir": str(trial) if trial else None,
                "rewards": rewards,
                "spent_usd": ledger.total_usd(),
            }
            manifest.append(row)
            print(json.dumps(row)[:400])

    dest = out_dir / "wave1_manifest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2))
    print(f"spent ${ledger.total_usd():.4f} of ${cap_usd:.2f}; manifest {dest}")
    print(json.dumps(ledger.summary(), indent=2))


if __name__ == "__main__":
    app()
