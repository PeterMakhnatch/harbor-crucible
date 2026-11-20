"""Harbor Multi-Agent trial launcher with spend enforcement and seat-config helpers."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from crucible.loader import load_trial_bundle
from crucible.spend import SpendEntry, SpendLedger, estimate_cost_usd

DEFAULT_HARBOR_BIN = Path(
    os.environ.get(
        "CRUCIBLE_HARBOR_BIN",
        "/Users/petermakhnatch/Developer/harbor-multiagent-crucible/.venv/bin/harbor",
    )
)


def parse_task_seats(task_dir: Path) -> list[str]:
    """Read declared `[agents.<seat>]` names from task.toml in declaration order."""
    import tomllib

    data = tomllib.loads((task_dir / "task.toml").read_text())
    agents = data.get("agents") or {}
    return list(agents.keys())


def build_trial_config(
    task_dir: Path,
    trials_dir: Path,
    agent_name: str = "oracle",
    model_name: str | None = None,
    api_key_env: str | None = None,
    seat_overrides: dict[str, dict[str, Any]] | None = None,
    agent_kwargs: dict[str, Any] | None = None,
    timeout_multiplier: float = 1.0,
    force_build: bool = False,
    delete: bool = True,
) -> dict[str, Any]:
    """Construct a native Harbor multi-seat TrialConfig dict for any Crucible task."""
    seats = parse_task_seats(task_dir)
    participants: list[dict[str, Any]] = []
    overrides = seat_overrides or {}

    for seat in seats:
        ov = overrides.get(seat, {})
        entry: dict[str, Any] = {
            "seat": seat,
            "name": ov.get("name", agent_name),
        }
        effective_model = ov.get("model_name", model_name)
        if effective_model:
            entry["model_name"] = effective_model
        effective_key = ov.get("model_api_key_name", api_key_env)
        if effective_key:
            entry["model_api_key_name"] = effective_key
        kw = dict(agent_kwargs or {})
        kw.update(ov.get("kwargs") or {})
        if kw:
            entry["kwargs"] = kw
        participants.append(entry)

    return {
        "task": {"path": str(task_dir.resolve())},
        "trials_dir": str(trials_dir.resolve()),
        "timeout_multiplier": timeout_multiplier,
        "environment": {
            "type": "docker",
            "force_build": force_build,
            "delete": delete,
        },
        "participants": participants,
    }


def run_seat_trial(
    task_dir: Path,
    trials_dir: Path,
    *,
    agent_name: str = "oracle",
    model_name: str | None = None,
    api_key_env: str | None = None,
    seat_overrides: dict[str, dict[str, Any]] | None = None,
    agent_kwargs: dict[str, Any] | None = None,
    timeout_multiplier: float = 1.0,
    force_build: bool = False,
    trial_name: str | None = None,
    harbor_bin: Path = DEFAULT_HARBOR_BIN,
    ledger: SpendLedger | None = None,
    estimated_planned_usd: float = 0.0,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, Path | None, str]:
    """Run one native multi-seat trial via isolated harbor CLI and record spend.

    The trial name is chosen here and passed to Harbor, so the resulting directory
    is identified by construction. Never infer a trial from the newest directory:
    another concurrent job can create one at the same moment.
    """
    if ledger is not None and agent_name not in ("oracle", "nop"):
        ledger.check_headroom(estimated_planned_usd)

    trials_dir.mkdir(parents=True, exist_ok=True)
    resolved_name = trial_name or (
        f"{task_dir.parent.name}-{task_dir.name}-{uuid4().hex[:10]}"
    )
    if (trials_dir / resolved_name).exists():
        raise FileExistsError(f"trial already exists: {trials_dir / resolved_name}")

    cfg = build_trial_config(
        task_dir=task_dir,
        trials_dir=trials_dir,
        agent_name=agent_name,
        model_name=model_name,
        api_key_env=api_key_env,
        seat_overrides=seat_overrides,
        agent_kwargs=agent_kwargs,
        timeout_multiplier=timeout_multiplier,
        force_build=force_build,
    )
    cfg["trial_name"] = resolved_name

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(cfg, tf, sort_keys=False)
        cfg_path = Path(tf.name)

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    try:
        proc = subprocess.run(
            [
                str(harbor_bin),
                "trials",
                "start",
                "-c",
                str(cfg_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        cfg_path.unlink(missing_ok=True)

    created_trial = trials_dir / resolved_name
    if not created_trial.is_dir():
        created_trial = next(
            (
                p
                for p in trials_dir.iterdir()
                if p.is_dir() and p.name.startswith(resolved_name)
            ),
            None,
        )

    if (
        ledger is not None
        and created_trial is not None
        and agent_name not in ("oracle", "nop")
    ):
        bundle = load_trial_bundle(created_trial)
        for seat, usage in bundle.seat_usage.items():
            in_tok = int(usage.get("n_input_tokens") or 0)
            out_tok = int(usage.get("n_output_tokens") or 0)
            cache_tok = int(usage.get("n_cache_tokens") or 0)
            raw_cost = usage.get("cost_usd")
            seat_model = bundle.seat_models.get(seat, model_name or "unknown")
            if raw_cost is not None:
                cost = float(raw_cost)
                est = False
            else:
                cost = estimate_cost_usd(seat_model, in_tok, out_tok)
                est = True
            ledger.record(
                SpendEntry(
                    category="trial_run",
                    provider=seat_model.split("/")[0]
                    if "/" in seat_model
                    else "unknown",
                    model=seat_model,
                    trial_or_job=f"{bundle.trial_name}:{seat}",
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cached_tokens=cache_tok,
                    cost_usd=cost,
                    estimated=est,
                )
            )

    combined_out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, created_trial, combined_out


def _build_job_config(
    task_dir: Path,
    jobs_dir: Path,
    *,
    job_name: str,
    n_attempts: int,
    agent_name: str,
    model_name: str | None,
    api_key_env: str | None,
    seat_overrides: dict[str, dict[str, Any]] | None,
    timeout_multiplier: float,
    n_concurrent: int,
) -> dict[str, Any]:
    trial = build_trial_config(
        task_dir,
        jobs_dir,
        agent_name=agent_name,
        model_name=model_name,
        api_key_env=api_key_env,
        seat_overrides=seat_overrides,
        timeout_multiplier=timeout_multiplier,
    )
    if not trial["participants"]:
        raise ValueError(f"task declares no seats: {task_dir}")

    return {
        "job_name": job_name,
        "jobs_dir": trial["trials_dir"],
        "n_attempts": n_attempts,
        "n_concurrent_trials": n_concurrent,
        "timeout_multiplier": trial["timeout_multiplier"],
        "environment": trial["environment"],
        "tasks": [trial["task"]],
        "participants": trial["participants"],
    }


def _record_job_trial_spend(
    trial_dir: Path, ledger: SpendLedger, model_name: str | None
) -> None:
    # Match run_seat_trial: use recorded cost, including zero, or estimate from tokens.
    bundle = load_trial_bundle(trial_dir)
    for seat, usage in bundle.seat_usage.items():
        in_tok = int(usage.get("n_input_tokens") or 0)
        out_tok = int(usage.get("n_output_tokens") or 0)
        cache_tok = int(usage.get("n_cache_tokens") or 0)
        raw_cost = usage.get("cost_usd")
        seat_model = bundle.seat_models.get(seat, model_name or "unknown")
        ledger.record(
            SpendEntry(
                category="trial_run",
                provider=seat_model.split("/")[0] if "/" in seat_model else "unknown",
                model=seat_model,
                trial_or_job=f"{bundle.trial_name}:{seat}",
                input_tokens=in_tok,
                output_tokens=out_tok,
                cached_tokens=cache_tok,
                cost_usd=(
                    float(raw_cost)
                    if raw_cost is not None
                    else estimate_cost_usd(seat_model, in_tok, out_tok)
                ),
                estimated=raw_cost is None,
            )
        )


def run_seat_job(
    task_dir: Path,
    jobs_dir: Path,
    *,
    job_name: str,
    n_attempts: int = 1,
    agent_name: str = "oracle",
    model_name: str | None = None,
    api_key_env: str | None = None,
    seat_overrides: dict[str, dict[str, Any]] | None = None,
    timeout_multiplier: float = 1.0,
    harbor_bin: Path = DEFAULT_HARBOR_BIN,
    ledger: SpendLedger | None = None,
    estimated_planned_usd_per_trial: float = 0.0,
    n_concurrent: int = 1,
) -> tuple[int, Path | None, str]:
    """Run one native Harbor job for a task; return CLI status, job path, and output."""
    if not job_name or job_name in (".", "..") or Path(job_name).name != job_name:
        raise ValueError("job_name must be a single directory name")
    if n_attempts < 1 or n_concurrent < 1:
        raise ValueError("n_attempts and n_concurrent must be positive")

    cfg = _build_job_config(
        task_dir,
        jobs_dir,
        job_name=job_name,
        n_attempts=n_attempts,
        agent_name=agent_name,
        model_name=model_name,
        api_key_env=api_key_env,
        seat_overrides=seat_overrides,
        timeout_multiplier=timeout_multiplier,
        n_concurrent=n_concurrent,
    )
    billable = any(p["name"] not in ("oracle", "nop") for p in cfg["participants"])
    if ledger is not None and billable:
        ledger.check_headroom(n_attempts * estimated_planned_usd_per_trial)

    job_dir = jobs_dir / job_name
    if job_dir.exists() or job_dir.is_symlink():
        raise FileExistsError(f"job already exists: {job_dir}")

    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / "job.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        proc = subprocess.run(
            [str(harbor_bin), "jobs", "start", "-c", str(cfg_path)],
            check=False,
            capture_output=True,
            text=True,
        )

    created_job = job_dir if job_dir.is_dir() else None
    if ledger is not None and billable and created_job is not None:
        for result_path in sorted(created_job.glob("*/result.json")):
            _record_job_trial_spend(result_path.parent, ledger, model_name)

    combined_out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, created_job, combined_out
