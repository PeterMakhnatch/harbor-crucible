"""Eval Lab bridge: export Crucible multi-seat safety/integrity evidence in Eval Lab–ready
JSONL/JSON formats and generate strict regrade trial configs for Harbor PR 3 (SeatsRegradeTrial).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crucible.loader import discover_trial_dirs, load_trial_bundle
from crucible.schema import MonitorVerdict, TrialBundle
from crucible.trace import build_exposure_graph


def export_evallab_seat_record(
    bundle: TrialBundle,
    verdicts: list[MonitorVerdict] | None = None,
) -> dict[str, Any]:
    """Produce a normalized offline evidence record compatible with Eval Lab seat audits.

    Preserves missing usage/traces distinctly from zero, keeps raw task utility separate
    from safety/adversarial indicators, and never collapses team identity onto seat 0.
    """
    exposure = build_exposure_graph(bundle)
    seat_records: list[dict[str, Any]] = []
    usage_complete = True
    total_cost_usd = 0.0
    any_cost_recorded = False

    for seat in bundle.seats:
        u = bundle.seat_usage.get(seat) or {}
        cost = u.get("cost_usd")
        if cost is None:
            usage_complete = False
        else:
            any_cost_recorded = True
            total_cost_usd += float(cost)
        seat_records.append(
            {
                "seat": seat,
                "model": bundle.seat_models.get(seat, "unknown"),
                "trace_present": seat not in bundle.missing_traces,
                "n_atif_steps": len(bundle.seat_steps.get(seat, [])),
                "n_input_tokens": u.get("n_input_tokens"),
                "n_output_tokens": u.get("n_output_tokens"),
                "n_cache_tokens": u.get("n_cache_tokens"),
                "cost_usd": cost,
                "exception": u.get("exception"),
                "is_ground_truth_adversary": (
                    seat in bundle.report.ground_truth_adversaries
                    if bundle.report is not None
                    else None
                ),
            }
        )

    monitor_summary: list[dict[str, Any]] = []
    for v in verdicts or []:
        if v.trial_name != bundle.trial_name:
            continue
        monitor_summary.append(
            {
                "monitor_name": v.monitor_name,
                "tier": v.tier.value,
                "trial_suspicion_score": v.trial_suspicion_score,
                "top_predicted_seat": v.top_predicted_seat,
                "top_seat_correct": v.top_seat_correct,
                "cutoff_seq": v.cutoff_seq,
                "monitor_cost_usd": v.monitor_cost_usd,
            }
        )

    return {
        "schema": "crucible-evallab-seat-evidence/v1",
        "trial_name": bundle.trial_name,
        "trial_dir": bundle.trial_dir,
        "task_family": bundle.task_family,
        "condition": bundle.condition,
        "seed": bundle.seed,
        "trial_exception": bundle.trial_exception,
        "is_negative_control": (
            bundle.report.is_negative_control if bundle.report is not None else None
        ),
        "is_instructed_refuser": (
            bundle.report.is_instructed_refuser if bundle.report is not None else None
        ),
        "ground_truth_adversaries": (
            bundle.report.ground_truth_adversaries if bundle.report is not None else []
        ),
        "rewards": bundle.rewards,
        "task_utility": bundle.rewards.get("task_utility"),
        "safety_score": bundle.rewards.get("safety_score"),
        "usage_accounting": {
            "complete": usage_complete and bool(bundle.seats),
            "recorded_cost_usd": round(total_cost_usd, 6) if any_cost_recorded else None,
        },
        "exposure": {
            "n_messages_sent": exposure["n_messages_sent"],
            "n_messages_read_by_peer": exposure["n_messages_read_by_peer"],
            "exposure_rate": exposure["exposure_rate"],
            "action_after_exposure_rate": exposure["action_after_exposure_rate"],
        },
        "seats": seat_records,
        "monitors": monitor_summary,
    }


def export_corpus_evallab_jsonl(
    runs_root: Path | str,
    out_path: Path | str,
    verdicts: list[MonitorVerdict] | None = None,
) -> int:
    """Export all discovered trials under runs_root as Eval Lab–compatible JSONL."""
    trial_dirs = discover_trial_dirs(runs_root)
    dest = Path(out_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with dest.open("w") as f:
        for td in trial_dirs:
            bundle = load_trial_bundle(td)
            rec = export_evallab_seat_record(bundle, verdicts=verdicts)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    return count


def build_seat_regrade_config(
    source_trial_dir: Path | str,
    regrade_task_dir: Path | str,
    trials_dir: Path | str = "regrade_trials",
) -> dict[str, Any]:
    """Build a Harbor TrialConfig dict targeting SeatsRegradeTrial (PR 3).

    Allows re-running a separate-mode strict/repaired verifier against recorded
    `/logs/artifacts` and `/logs/seats/<seat>/agent/` with zero additional LLM spend.
    """
    src = Path(source_trial_dir).resolve()
    cfg_path = src / "config.json"
    participants: list[dict[str, Any]] = []
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text())
            if isinstance(raw.get("participants"), list):
                participants = raw["participants"]
        except (OSError, ValueError):
            pass

    return {
        "task": {"path": str(Path(regrade_task_dir).resolve())},
        "trials_dir": str(Path(trials_dir).resolve()),
        "participants": participants,
        "source_trial": {
            "action": "regrade",
            "path": str(src),
        },
        "environment": {
            "type": "docker",
            "delete": True,
        },
    }
