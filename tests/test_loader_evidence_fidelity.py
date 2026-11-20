"""Loader/export must keep missing, invalid, and conflicting evidence distinct.

Each case comes from the Eval Lab differential check
(experiments/evallab_differential/RESULT.md): before the fix crucible collapsed it into
a value that looks like real data.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_loader_trace_bridge_spend import _make_sample_trial

from crucible.bridge import export_evallab_seat_record
from crucible.loader import load_trial_bundle


def _seat(record: dict, name: str) -> dict:
    return next(s for s in record["seats"] if s["seat"] == name)


def _edit_result(trial: Path, **changes: object) -> None:
    path = trial / "result.json"
    data = json.loads(path.read_text())
    data.update(changes)
    path.write_text(json.dumps(data))


def test_missing_trajectory_reports_no_step_count(tmp_path: Path) -> None:
    """R1: scout_b has no trajectory.json, so its step count is unknown, not 0."""
    rec = export_evallab_seat_record(load_trial_bundle(_make_sample_trial(tmp_path)))

    scout_b = _seat(rec, "scout_b")
    assert scout_b["trace_present"] is False
    assert scout_b["trace_valid"] is None
    assert scout_b["n_atif_steps"] is None
    assert _seat(rec, "scout_a")["n_atif_steps"] == 1


def test_ungraded_trial_reports_no_rewards(tmp_path: Path) -> None:
    """R2: verifier_result null means the trial was never graded: None, not {}."""
    trial = _make_sample_trial(tmp_path)
    _edit_result(trial, verifier_result=None)
    (trial / "verifier" / "reward.json").unlink()

    bundle = load_trial_bundle(trial)
    rec = export_evallab_seat_record(bundle)

    assert bundle.rewards is None
    assert bundle.reward_source is None
    assert rec["rewards"] is None
    assert rec["task_utility"] is None
    assert rec["safety_score"] is None


def test_unparseable_trajectory_is_invalid_not_empty(tmp_path: Path) -> None:
    trial = _make_sample_trial(tmp_path)
    (trial / "seats" / "scout_a" / "agent" / "trajectory.json").write_text(
        '{"steps": ['
    )

    bundle = load_trial_bundle(trial)
    scout_a = _seat(export_evallab_seat_record(bundle), "scout_a")

    assert bundle.invalid_traces == ["scout_a"]
    assert bundle.seat_steps["scout_a"] == []
    assert scout_a["trace_present"] is True
    assert scout_a["trace_valid"] is False
    assert scout_a["n_atif_steps"] is None


def test_steps_not_a_list_is_invalid(tmp_path: Path) -> None:
    trial = _make_sample_trial(tmp_path)
    (trial / "seats" / "scout_a" / "agent" / "trajectory.json").write_text(
        json.dumps({"schema_version": "ATIF-v1.7", "steps": {"bad": 1}})
    )

    scout_a = _seat(export_evallab_seat_record(load_trial_bundle(trial)), "scout_a")

    assert (scout_a["trace_valid"], scout_a["n_atif_steps"]) == (False, None)


def test_valid_empty_trajectory_keeps_zero_steps(tmp_path: Path) -> None:
    """The positive control: a valid ATIF file with no steps really has 0 steps."""
    trial = _make_sample_trial(tmp_path)
    (trial / "seats" / "scout_a" / "agent" / "trajectory.json").write_text(
        json.dumps({"schema_version": "ATIF-v1.7", "steps": []})
    )

    scout_a = _seat(export_evallab_seat_record(load_trial_bundle(trial)), "scout_a")

    assert (scout_a["trace_present"], scout_a["trace_valid"]) == (True, True)
    assert scout_a["n_atif_steps"] == 0


def test_result_json_rewards_win_and_a_differing_file_is_flagged(
    tmp_path: Path,
) -> None:
    trial = _make_sample_trial(tmp_path)
    (trial / "verifier" / "reward.json").write_text(
        json.dumps({"task_utility": 0.0, "safety_score": 0.0})
    )

    bundle = load_trial_bundle(trial)
    rec = export_evallab_seat_record(bundle)

    assert bundle.rewards == {"task_utility": 0.3, "safety_score": 0.2}
    assert bundle.reward_source == "result_json"
    assert rec["reward_file_mismatch"] is True
    assert rec["task_utility"] == 0.3


def test_matching_reward_file_is_not_flagged(tmp_path: Path) -> None:
    trial = _make_sample_trial(tmp_path)
    (trial / "verifier" / "reward.json").write_text(
        json.dumps({"task_utility": 0.3, "safety_score": 0.2})
    )

    bundle = load_trial_bundle(trial)

    assert bundle.reward_file_mismatch is False
    assert bundle.reward_source == "result_json"


def test_reward_file_is_the_fallback_only_without_result_json(tmp_path: Path) -> None:
    trial = _make_sample_trial(tmp_path)
    (trial / "result.json").unlink()

    bundle = load_trial_bundle(trial)

    assert bundle.reward_source == "reward_json"
    assert bundle.rewards == {
        "task_utility": 0.3,
        "safety_score": 0.2,
        "sabotage_success": 1.0,
    }
    assert bundle.reward_file_mismatch is False


def test_stray_seat_dir_is_an_anomaly_not_a_seat(tmp_path: Path) -> None:
    trial = _make_sample_trial(tmp_path)
    (trial / "seats" / "intruder" / "agent").mkdir(parents=True)

    bundle = load_trial_bundle(trial)
    rec = export_evallab_seat_record(bundle)

    assert bundle.seats == ["scout_a", "scout_b"]
    assert bundle.seat_anomalies == ["undeclared_seat_dir:intruder"]
    assert rec["seat_anomalies"] == ["undeclared_seat_dir:intruder"]


def test_missing_seat_result_takes_model_from_participants(tmp_path: Path) -> None:
    trial = _make_sample_trial(tmp_path)
    participants = [
        {
            "seat": "scout_a",
            "name": "mini-swe-agent",
            "model_name": "deepseek/deepseek-chat",
        },
        {
            "seat": "scout_b",
            "name": "mini-swe-agent",
            "model_name": "deepseek/deepseek-chat",
        },
        {
            "seat": "builder",
            "name": "mini-swe-agent",
            "model_name": "qwen/qwen-2.5-72b",
        },
    ]
    _edit_result(trial, config={"participants": participants})

    bundle = load_trial_bundle(trial)
    builder = _seat(export_evallab_seat_record(bundle), "builder")

    assert bundle.seats == ["scout_a", "scout_b", "builder"]
    assert bundle.seat_models["builder"] == "qwen/qwen-2.5-72b"
    assert bundle.seat_anomalies == ["missing_seat_result:builder"]
    assert builder["model"] == "qwen/qwen-2.5-72b"
    assert builder["cost_usd"] is None


def test_seat_dirs_are_the_roster_only_when_nothing_is_declared(tmp_path: Path) -> None:
    trial = _make_sample_trial(tmp_path)
    (trial / "result.json").unlink()

    bundle = load_trial_bundle(trial)

    assert bundle.seats == ["scout_a", "scout_b"]
    assert bundle.seat_anomalies == [
        "seat_from_dir_only:scout_a",
        "seat_from_dir_only:scout_b",
    ]
