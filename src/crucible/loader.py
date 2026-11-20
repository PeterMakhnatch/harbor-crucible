"""Offline loader for native Harbor multi-seat trial directories and Crucible evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crucible.schema import (
    CrucibleReport,
    SeatTrajectoryStep,
    TrialBundle,
    WorldEvent,
)


def _read_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _parse_world_events(trial_dir: Path) -> list[WorldEvent]:
    candidates = [
        trial_dir / "artifacts" / "logs" / "world" / "events.jsonl",
        trial_dir / "artifacts" / "world" / "events.jsonl",
        trial_dir / "world" / "events.jsonl",
    ]
    for path in candidates:
        if path.is_file():
            events: list[WorldEvent] = []
            for raw_line in path.read_text().splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    events.append(WorldEvent.model_validate_json(raw_line))
                except ValueError:
                    continue
            events.sort(key=lambda e: (e.seq, e.ts))
            return events
    return []


def _parse_atif_steps(
    seat: str, trajectory_path: Path
) -> list[SeatTrajectoryStep] | None:
    """Return the seat's steps, or None when the file is not a usable ATIF document.

    None (unparseable JSON, ``steps`` not a list of objects, malformed step ids) is
    distinct from ``[]``: a valid trajectory that recorded no steps.
    """
    data = _read_json(trajectory_path)
    if not isinstance(data, dict):
        return None
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not all(
        isinstance(s, dict) for s in raw_steps
    ):
        return None
    try:
        return [
            _atif_step(seat, idx, raw) for idx, raw in enumerate(raw_steps, start=1)
        ]
    except (TypeError, ValueError):
        return None


def _atif_step(seat: str, idx: int, raw: dict[str, Any]) -> SeatTrajectoryStep:
    obs = raw.get("observation")
    obs_parts: list[str] = []
    if isinstance(obs, dict):
        for res in obs.get("results") or []:
            if isinstance(res, dict) and res.get("content") is not None:
                obs_parts.append(str(res["content"]))
    elif isinstance(obs, str):
        obs_parts.append(obs)
    metrics = raw.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    msg = raw.get("message")
    if isinstance(msg, list):
        msg_str = "\n".join(
            str(p.get("text", p)) if isinstance(p, dict) else str(p) for p in msg
        )
    else:
        msg_str = "" if msg is None else str(msg)
    return SeatTrajectoryStep(
        seat=seat,
        step_id=int(raw.get("step_id", idx)),
        source=str(raw.get("source", "unknown")),
        timestamp=raw.get("timestamp"),
        message=msg_str,
        reasoning_content=raw.get("reasoning_content"),
        tool_calls=raw.get("tool_calls")
        if isinstance(raw.get("tool_calls"), list)
        else [],
        observation_text="\n".join(obs_parts),
        prompt_tokens=metrics.get("prompt_tokens"),
        completion_tokens=metrics.get("completion_tokens"),
        cost_usd=metrics.get("cost_usd"),
    )


def _numeric_rewards(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    return {
        str(k): float(v)
        for k, v in raw.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def _load_rewards(
    trial_dir: Path, result_data: dict[str, Any] | None
) -> tuple[dict[str, float] | None, str | None, bool]:
    """Return (rewards, source, file_mismatch).

    ``result.json`` is Harbor's record of the verifier verdict, so it wins whenever it
    exists; ``verifier_result: null`` there means the trial was never graded (None, not
    ``{}``). ``verifier/reward.json`` is a mutable copy: it is used only when no
    ``result.json`` exists, and any difference from the record is flagged, never
    silently preferred.
    """
    file_rewards = _numeric_rewards(_read_json(trial_dir / "verifier" / "reward.json"))
    if isinstance(result_data, dict):
        verifier_result = result_data.get("verifier_result")
        recorded = (
            _numeric_rewards(verifier_result.get("rewards"))
            if isinstance(verifier_result, dict)
            else None
        )
        mismatch = file_rewards is not None and file_rewards != recorded
        return recorded, ("result_json" if recorded is not None else None), mismatch
    if file_rewards is not None:
        return file_rewards, "reward_json", False
    return None, None, False


def _participants(
    result_data: dict[str, Any] | None, config_data: dict[str, Any] | None
) -> list[dict[str, Any]]:
    for source in (
        (result_data or {}).get("config") if isinstance(result_data, dict) else None,
        config_data,
    ):
        if isinstance(source, dict) and isinstance(source.get("participants"), list):
            return [
                p
                for p in source["participants"]
                if isinstance(p, dict) and p.get("seat")
            ]
    return []


def load_trial_bundle(trial_dir: Path | str) -> TrialBundle:
    """Load one completed multi-seat Harbor trial directory into a TrialBundle."""
    root = Path(trial_dir).resolve()
    result_data = _read_json(root / "result.json")
    config_data = _read_json(root / "config.json")
    report_data = _read_json(root / "verifier" / "crucible_report.json")
    report = (
        CrucibleReport.model_validate(report_data)
        if isinstance(report_data, dict)
        else None
    )
    world_events = _parse_world_events(root)

    trial_name = root.name
    if isinstance(result_data, dict) and result_data.get("trial_name"):
        trial_name = str(result_data["trial_name"])

    task_family = "unknown"
    condition = "unknown"
    seed = 42
    if report is not None:
        task_family = report.task_family
        condition = report.condition
        seed = report.seed
    elif world_events:
        task_family = world_events[0].task_family
        condition = world_events[0].condition
        seed = world_events[0].seed

    seats: list[str] = []
    seat_models: dict[str, str] = {}
    seat_usage: dict[str, dict[str, Any]] = {}
    seat_anomalies: list[str] = []

    has_seat_results = isinstance(result_data, dict) and isinstance(
        result_data.get("seat_results"), list
    )
    if has_seat_results:
        for sr in result_data["seat_results"]:
            if not isinstance(sr, dict) or not sr.get("seat"):
                continue
            seat = str(sr["seat"])
            if seat not in seats:
                seats.append(seat)
            ai = sr.get("agent_info") or {}
            model_info = ai.get("model_info") or {}
            model_name = model_info.get("name") or ai.get("name") or "unknown"
            seat_models[seat] = str(model_name)
            ar = sr.get("agent_result") or {}
            seat_usage[seat] = {
                "n_input_tokens": ar.get("n_input_tokens"),
                "n_output_tokens": ar.get("n_output_tokens"),
                "n_cache_tokens": ar.get("n_cache_tokens"),
                "cost_usd": ar.get("cost_usd"),
                "exception": (sr.get("exception_info") or {}).get("exception_type"),
            }

    # Declared roster: participants recorded in result.json's config, else config.json.
    # A declared seat with no seat result is still a seat (its model comes from the
    # declaration), but the missing result is flagged.
    for p in _participants(result_data, config_data):
        seat = str(p["seat"])
        if seat in seats:
            continue
        seats.append(seat)
        seat_models[seat] = str(p.get("model_name") or p.get("name") or "unknown")
        if has_seat_results:
            seat_anomalies.append(f"missing_seat_result:{seat}")

    # seats/<name> dirs never add a seat when a roster exists; a stray dir is an anomaly.
    # Only a trial with no recorded roster at all falls back to the directory names.
    seats_dir = root / "seats"
    if seats_dir.is_dir():
        has_roster = bool(seats)
        for child in sorted(seats_dir.iterdir()):
            if not child.is_dir() or child.name in seats:
                continue
            if has_roster:
                seat_anomalies.append(f"undeclared_seat_dir:{child.name}")
            else:
                seats.append(child.name)
                seat_anomalies.append(f"seat_from_dir_only:{child.name}")

    seat_steps: dict[str, list[SeatTrajectoryStep]] = {}
    missing_traces: list[str] = []
    invalid_traces: list[str] = []
    for seat in seats:
        traj_path = seats_dir / seat / "agent" / "trajectory.json"
        if not traj_path.is_file():
            seat_steps[seat] = []
            missing_traces.append(seat)
            continue
        parsed = _parse_atif_steps(seat, traj_path)
        if parsed is None:
            seat_steps[seat] = []
            invalid_traces.append(seat)
        else:
            seat_steps[seat] = parsed

    trial_exc: str | None = None
    if isinstance(result_data, dict) and isinstance(
        result_data.get("exception_info"), dict
    ):
        trial_exc = str(result_data["exception_info"].get("exception_type") or "")

    rewards, reward_source, reward_file_mismatch = _load_rewards(root, result_data)
    return TrialBundle(
        trial_dir=str(root),
        trial_name=trial_name,
        task_family=task_family,
        condition=condition,
        seed=seed,
        seats=seats,
        seat_models=seat_models,
        seat_usage=seat_usage,
        rewards=rewards,
        reward_source=reward_source,
        reward_file_mismatch=reward_file_mismatch,
        report=report,
        world_events=world_events,
        seat_steps=seat_steps,
        missing_traces=missing_traces,
        invalid_traces=invalid_traces,
        seat_anomalies=seat_anomalies,
        trial_exception=trial_exc,
    )


def discover_trial_dirs(root: Path | str) -> list[Path]:
    """Find every Harbor trial directory under root (single trial or job directory)."""
    base = Path(root).resolve()
    if (base / "result.json").is_file() and (
        (base / "seats").is_dir() or (base / "verifier").is_dir()
    ):
        return [base]
    found: list[Path] = []
    for res in sorted(base.rglob("result.json")):
        parent = res.parent
        if (parent / "seats").is_dir() or (
            parent / "verifier" / "crucible_report.json"
        ).is_file():
            found.append(parent)
    return found
