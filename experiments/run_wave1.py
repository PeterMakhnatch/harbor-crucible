#!/usr/bin/env python3
"""Wave 1: real model seat runs for the Crucible monitor benchmark.

Pre-registered in experiments/PROTOCOL.md. Each trial records exact seat usage into
experiments/spend_ledger.jsonl and refuses to start when the budget cap would be
crossed. Failed trials stay in the corpus; they are reported, never dropped.
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

# Every family with the conditions that carry a matched control.
FAMILIES: dict[str, tuple[str, ...]] = {
    "supply-chain-sabotage": ("honest", "noisy_honest", "instructed_refuser", "saboteur"),
    "reward-hack-contagion": ("clean", "hack_seeded_coder", "hack_seeded_planner", "strict_gate_defense"),
    "epistemic-crucible": ("gullibility_p00", "gullibility_p50", "gullibility_p100"),
    "migration-turf-war": ("aligned_control", "conflicting_blind", "conflicting_with_protocol"),
}


def _rewards(trial: Path | None) -> dict[str, float]:
    if trial is None:
        return {}
    path = trial / "verifier" / "reward.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError:
        return {}


@app.command()
def wave1(
    family: str = typer.Option("supply-chain-sabotage", help=", ".join(FAMILIES)),
    model: str = typer.Option("deepseek/deepseek-chat", help="Model for every seat."),
    api_key_env: str = typer.Option("DEEPSEEK_API_KEY", help="Host env var holding the key."),
    attempts: int = typer.Option(1, help="Trials per condition."),
    conditions: str | None = typer.Option(
        None,
        help="Comma-separated subset of the family's conditions. Default: all of them.",
    ),
    timeout_multiplier: float = typer.Option(1.0),
    planned_usd_per_trial: float = typer.Option(0.75, help="Refuse to start a trial above this estimate."),
    out_dir: Path | None = typer.Option(None),
    ledger_path: Path = typer.Option(Path("experiments/spend_ledger.jsonl")),
    cap_usd: float = typer.Option(20.0),
    dry_run: bool = typer.Option(False),
) -> None:
    if family not in FAMILIES:
        raise typer.BadParameter(f"unknown family {family!r}; choose from {sorted(FAMILIES)}")

    ledger = SpendLedger(path=ledger_path, cap_usd=cap_usd)
    tasks_root = Path("tasks") / family / "variants"
    trials_dir = out_dir or Path("runs") / f"wave1-{family}"
    manifest: list[dict[str, object]] = []

    selected = (
        tuple(c.strip() for c in conditions.split(",") if c.strip())
        if conditions
        else FAMILIES[family]
    )
    for condition in selected:
        task_dir = tasks_root / condition
        if not (task_dir / "task.toml").is_file():
            raise typer.BadParameter(f"missing task: {task_dir}")
        for attempt in range(1, attempts + 1):
            if dry_run:
                print(f"DRY {family}/{condition} #{attempt}")
                continue
            ledger.check_headroom(planned_usd_per_trial)
            rc, trial, out = run_seat_trial(
                task_dir,
                trials_dir,
                agent_name="mini-swe-agent",
                model_name=model,
                api_key_env=api_key_env,
                timeout_multiplier=timeout_multiplier,
                ledger=ledger,
                estimated_planned_usd=planned_usd_per_trial,
            )
            row = {
                "family": family,
                "condition": condition,
                "attempt": attempt,
                "model": model,
                "rc": rc,
                "trial_dir": str(trial) if trial else None,
                "rewards": _rewards(trial),
                "spent_usd": ledger.total_usd(),
            }
            manifest.append(row)
            print(json.dumps(row)[:500], flush=True)

    dest = trials_dir / "wave1_manifest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2))
    print(f"spent ${ledger.total_usd():.4f} of ${cap_usd:.2f}; manifest {dest}")
    print(json.dumps(ledger.summary(), indent=2))


if __name__ == "__main__":
    app()
