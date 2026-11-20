"""The wave runner's manifest merge, which a split --conditions run depends on."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

RUNNER_PATH = Path(__file__).resolve().parents[1] / "experiments" / "run_wave1.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_wave1_under_test", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_merging_keeps_both_halves_of_a_split_run() -> None:
    runner = _load()

    merged = runner.merge_manifest(
        [{"trial_dir": "runs/a", "condition": "honest"}],
        [{"trial_dir": "runs/b", "condition": "saboteur"}],
    )

    assert [row["trial_dir"] for row in merged] == ["runs/a", "runs/b"]


def test_merging_replaces_a_rerun_of_the_same_trial() -> None:
    runner = _load()

    merged = runner.merge_manifest(
        [{"trial_dir": "runs/a", "attempt": 1}],
        [{"trial_dir": "runs/a", "attempt": 1, "rerun": True}],
    )

    assert len(merged) == 1
    assert merged[0]["rerun"] is True


def test_merging_drops_rows_without_a_trial_directory() -> None:
    runner = _load()

    merged = runner.merge_manifest([{"trial_dir": ""}, {"attempt": 2}], [])

    assert merged == []


def test_merging_an_empty_manifest_returns_the_existing_rows_sorted() -> None:
    runner = _load()

    merged = runner.merge_manifest([{"trial_dir": "b"}, {"trial_dir": "a"}], [])

    assert [row["trial_dir"] for row in merged] == ["a", "b"]


@pytest.mark.parametrize("as_job", [False, True])
def test_wave_dispatches_trials_unless_job_mode_is_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_job: bool
) -> None:
    runner = _load()
    monkeypatch.chdir(tmp_path)
    task_dir = Path("tasks/epistemic-crucible/variants/gullibility_p50")
    task_dir.mkdir(parents=True)
    (task_dir / "task.toml").touch()
    out_dir = tmp_path / "runs"
    job_dir = out_dir / "gullibility_p50"
    if as_job:
        # Names sort in reverse execution order.
        for name, day in (("z-first", 1), ("a-second", 2)):
            trial = job_dir / name
            (trial / "seats").mkdir(parents=True)
            (trial / "result.json").write_text(
                json.dumps({"started_at": f"2026-01-0{day}T00:00:00"})
            )

    launch_trial = Mock(
        side_effect=[(0, out_dir / "trial-1", ""), (0, out_dir / "trial-2", "")]
    )
    launch_job = Mock(return_value=(0, job_dir, ""))
    monkeypatch.setattr(runner, "run_seat_trial", launch_trial)
    monkeypatch.setattr(runner, "run_seat_job", launch_job)
    args = [
        "--family",
        "epistemic-crucible",
        "--conditions",
        "gullibility_p50",
        "--attempts",
        "2",
        "--out-dir",
        str(out_dir),
    ]
    result = CliRunner().invoke(runner.app, [*args, "--as-job"] if as_job else args)
    assert result.exit_code == 0, (result.output, result.exception)

    manifest = json.loads((out_dir / "wave1_manifest.json").read_text())
    assert [row["attempt"] for row in manifest] == ([2, 1] if as_job else [1, 2])
    if as_job:
        launch_trial.assert_not_called()
        launch_job.assert_called_once()
        assert launch_job.call_args.args == (task_dir, out_dir)
        assert launch_job.call_args.kwargs["job_name"] == "gullibility_p50"
        assert launch_job.call_args.kwargs["n_attempts"] == 2
        assert [Path(row["trial_dir"]).name for row in manifest] == [
            "a-second",
            "z-first",
        ]
    else:
        launch_job.assert_not_called()
        assert [call.args for call in launch_trial.call_args_list] == [
            (task_dir, out_dir),
            (task_dir, out_dir),
        ]
        assert [Path(row["trial_dir"]).name for row in manifest] == [
            "trial-1",
            "trial-2",
        ]
