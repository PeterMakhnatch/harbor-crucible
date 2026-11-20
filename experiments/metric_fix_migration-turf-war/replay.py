"""Replay saved migration verifier inputs without starting Harbor or changing runs."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parents[2]
FAMILY = "migration-turf-war"
VERIFIER = ROOT / f"tasks/{FAMILY}/template/tests/verify.py"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _outcome(metrics):
    return next(
        key.removeprefix("outcome_")
        for key, value in metrics.items()
        if key.startswith("outcome_") and not key.endswith("_v1") and value
    )


def _replay_trial(trial, result, models, score):
    report = _json(trial / "verifier/crucible_report.json")
    recorded = _json(trial / "verifier/reward.json")
    if (
        recorded != report["metrics"]
        or recorded != result["verifier_result"]["rewards"]
    ):
        raise ValueError(f"Recorded reward files disagree: {trial}")
    condition, seed = report["condition"], report["seed"]
    recorded_findings = {item["kind"]: item for item in report["findings"]}
    terminal = recorded_findings["terminal_service"]
    evidence_error = recorded_findings.get("evidence_error", {}).get("detail")
    audit = trial / "artifacts/logs/world/events.jsonl"
    events = [json.loads(row) for row in audit.read_text(encoding="utf-8").splitlines()]
    for seq, event in enumerate(events, 1):
        identity = (event["task_family"], event["condition"], event["seed"])
        if event["seq"] != seq or identity != (FAMILY, condition, seed):
            raise ValueError(f"Recorded audit identity or sequence mismatch: {audit}")
    metrics, _, findings = score(
        events if evidence_error is None else [],
        terminal["health"],
        terminal["compute"],
        condition,
        evidence_error,
    )
    replayed_terminal = next(
        item for item in findings if item["kind"] == "terminal_service"
    )
    for key in ("actual_lang", "active_lockouts", "active_flagged_scripts"):
        if terminal[key] != replayed_terminal[key]:
            raise ValueError(f"Recorded terminal evidence disagrees on {key}: {trial}")
    old_metrics = {key: metrics.get(f"{key}_v1", metrics[key]) for key in recorded}
    return {
        "trial": str(trial.relative_to(ROOT)),
        "condition": condition,
        "models": models,
        "reward_valid": result["reward_valid"],
        "trial_exception": (result["exception_info"] or {}).get("exception_type"),
        "audit_event_count": len(events),
        "terminal_deployment": {
            key: replayed_terminal[key]
            for key in ("deploy_owner", "deploy_seq", "actual_lang")
        },
        "recorded": recorded,
        "recorded_outcome": _outcome(recorded),
        "pre_fix_replay": old_metrics,
        "pre_fix_replay_outcome": _outcome(old_metrics),
        "rescored": metrics,
        "rescored_outcome": _outcome(metrics),
    }


def _n_full(rows, grade, metric):
    return sum(row[grade][metric] == 1 for row in rows)


def replay():
    score = run_path(str(VERIFIER))["score"]
    trials = []
    groups = defaultdict(list)
    for path in sorted((ROOT / "runs").rglob("result.json")):
        result = _json(path)
        task_path = (result.get("task_id") or {}).get("path") or ""
        if FAMILY not in Path(task_path).parts:
            continue
        models = {}
        for seat in result["seat_results"]:
            model = (seat.get("agent_info") or {}).get("model_info")
            if model:
                models[seat["seat"]] = f"{model['provider']}/{model['name']}"
        if not models:
            continue
        row = _replay_trial(path.parent, result, models, score)
        trials.append(row)
        groups[(path.relative_to(ROOT).parts[1], row["condition"])].append(row)
    if not trials:
        raise ValueError("No real-model migration trials found under runs/")
    summary = [
        {
            "wave": wave,
            "condition": condition,
            "n": len(rows),
            "timed_out": sum(
                row["trial_exception"] == "AgentTimeoutError" for row in rows
            ),
            "recorded_outcomes": dict(Counter(row["recorded_outcome"] for row in rows)),
            "pre_fix_replay_outcomes": dict(
                Counter(row["pre_fix_replay_outcome"] for row in rows)
            ),
            "rescored_outcomes": dict(Counter(row["rescored_outcome"] for row in rows)),
            "recorded_full_utility": _n_full(rows, "recorded", "task_utility"),
            "rescored_full_utility": _n_full(rows, "rescored", "task_utility"),
            "service_available": _n_full(rows, "rescored", "service_available"),
            "migration_complete": _n_full(rows, "rescored", "migration_complete"),
        }
        for (wave, condition), rows in sorted(groups.items())
    ]
    return {
        "family": FAMILY,
        "n_real_model_trials": len(trials),
        "summary": summary,
        "trials": trials,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.write_text(
        json.dumps(replay(), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
