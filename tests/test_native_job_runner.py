"""Native Harbor job launch contract, without Docker or model calls."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest
import yaml

from crucible import runner
from crucible.spend import BudgetExceededError, SpendLedger, estimate_cost_usd


@pytest.fixture
def seat_task(tmp_path: Path) -> Path:
    task = tmp_path / "task"
    task.mkdir()
    (task / "task.toml").write_text("[agents.scout]\n[agents.builder]\n")
    return task


def test_job_launch_uses_native_config(
    tmp_path: Path, seat_task: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = tmp_path / "jobs"
    harbor = tmp_path / "harbor"
    job = jobs / "smoke"

    def launch(command, **kwargs):
        assert command[:4] == [str(harbor), "jobs", "start", "-c"]
        config_file = Path(command[4])
        assert yaml.safe_load(config_file.read_text()) == {
            "job_name": "smoke",
            "jobs_dir": str(jobs.resolve()),
            "n_attempts": 3,
            "n_concurrent_trials": 1,
            "timeout_multiplier": 1.5,
            "environment": {"type": "docker", "force_build": False, "delete": True},
            "tasks": [{"path": str(seat_task.resolve())}],
            "participants": [
                {
                    "seat": "scout",
                    "name": "mini-swe-agent",
                    "model_name": "deepseek/deepseek-chat",
                    "model_api_key_name": "DEEPSEEK_API_KEY",
                },
                {
                    "seat": "builder",
                    "name": "other-agent",
                    "model_name": "other/model",
                    "model_api_key_name": "OTHER_API_KEY",
                    "kwargs": {"step_limit": 8},
                },
            ],
        }
        job.mkdir(parents=True)
        return CompletedProcess(command, 0, stdout="started", stderr="notice")

    monkeypatch.setattr(runner.subprocess, "run", launch)
    assert runner.run_seat_job(
        seat_task,
        jobs,
        job_name="smoke",
        n_attempts=3,
        agent_name="mini-swe-agent",
        model_name="deepseek/deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        seat_overrides={
            "builder": {
                "name": "other-agent",
                "model_name": "other/model",
                "model_api_key_name": "OTHER_API_KEY",
                "kwargs": {"step_limit": 8},
            }
        },
        timeout_multiplier=1.5,
        harbor_bin=harbor,
    ) == (0, job, "started\nnotice")


def test_job_checks_headroom_for_all_attempts_before_launch(
    tmp_path: Path, seat_task: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = Mock()
    monkeypatch.setattr(runner.subprocess, "run", launch)
    ledger = SpendLedger(tmp_path / "ledger.jsonl", cap_usd=0.02)
    with pytest.raises(BudgetExceededError, match=r"Projected spend \$0.0300"):
        runner.run_seat_job(
            seat_task,
            tmp_path / "jobs",
            job_name="smoke",
            n_attempts=2,
            seat_overrides={"builder": {"name": "mini-swe-agent"}},
            ledger=ledger,
            estimated_planned_usd_per_trial=0.015,
        )
    launch.assert_not_called()
    assert not (tmp_path / "jobs").exists()
    assert not ledger.path.exists()


def test_job_accounts_for_each_trial_even_on_nonzero_exit(
    tmp_path: Path, seat_task: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = tmp_path / "jobs"
    model = "deepseek/deepseek-chat"
    ledger = SpendLedger(tmp_path / "ledger.jsonl")

    def launch(command, **kwargs):
        for attempt in (1, 2):
            trial = jobs / "smoke" / f"attempt-{attempt}"
            trial.mkdir(parents=True)
            (trial / "result.json").write_text(
                json.dumps(
                    {
                        "trial_name": trial.name,
                        "seat_results": [
                            {
                                "seat": seat,
                                "agent_info": {"model_info": {"name": model}},
                                "agent_result": {
                                    "n_input_tokens": 1000,
                                    "n_output_tokens": 100,
                                    "n_cache_tokens": 500,
                                    "cost_usd": cost,
                                },
                            }
                            for seat, cost in (("scout", 0.0), ("builder", None))
                        ],
                    }
                )
            )
        return CompletedProcess(command, 1, stdout="", stderr="interrupted")

    monkeypatch.setattr(runner.subprocess, "run", launch)
    rc, job, _ = runner.run_seat_job(
        seat_task,
        jobs,
        job_name="smoke",
        n_attempts=2,
        agent_name="mini-swe-agent",
        ledger=ledger,
    )
    assert rc == 1
    assert job == jobs / "smoke"
    entries = {entry.trial_or_job: entry for entry in ledger.entries()}
    assert set(entries) == {
        f"attempt-{attempt}:{seat}"
        for attempt in (1, 2)
        for seat in ("scout", "builder")
    }
    for attempt in (1, 2):
        scout = entries[f"attempt-{attempt}:scout"]
        builder = entries[f"attempt-{attempt}:builder"]
        assert scout.cost_usd == 0.0 and not scout.estimated
        assert builder.cost_usd == estimate_cost_usd(model, 1000, 100)
        assert builder.estimated
        assert builder.provider == "deepseek"
        assert builder.cached_tokens == 500
