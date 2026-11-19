"""The wave runner's manifest merge, which a split --conditions run depends on."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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
