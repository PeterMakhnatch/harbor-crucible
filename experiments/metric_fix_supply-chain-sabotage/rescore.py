#!/usr/bin/env python3
"""Replay retained supply trials and compare the same monitor inputs before and after."""

import json
import runpy
from collections import defaultdict
from functools import cache
from math import comb, sqrt
from pathlib import Path
from sys import path

path.insert(0, str(Path(__file__).resolve().parents[1]))

from evasive_saboteur.score import (
    EVASIVE_RUNS,
    NEGATIVE_CONDITIONS,
    NEGATIVE_RUNS,
    ROOT,
    SABOTEUR_RUNS,
    evaluate,
    load,
)

FAMILY = "supply-chain-sabotage"
OUTPUT = Path(__file__).resolve().parent
TIER1 = "tier1_public_plus_audit"


def read_json(file):
    return json.loads(file.read_text(encoding="utf-8"))


@cache
def scorer(condition):
    verify = ROOT / "tasks" / FAMILY / "variants" / condition / "tests/verify.py"
    return runpy.run_path(str(verify))["score"]


def replay_trials():
    trials = []
    new_metrics = {}
    for file in sorted((ROOT / "runs").rglob("result.json")):
        result = read_json(file)
        if not (result.get("task_name") or "").startswith(f"crucible/{FAMILY}-"):
            continue
        models = sorted(
            {
                seat["model_name"]
                for seat in result["config"]["participants"]
                if seat.get("model_name")
            }
        )
        if not models:
            continue
        trial = file.parent
        world = trial / "artifacts/logs/world"
        state = read_json(world / "state.json")
        old = read_json(trial / "verifier/reward.json")
        report = read_json(trial / "verifier/crucible_report.json")
        assert old == report["metrics"] == result["verifier_result"]["rewards"], trial
        condition = state["condition"]
        assert condition == report["condition"], trial
        seat_logs = {
            seat: entry["agent_log_files"] for seat, entry in report["per_seat"].items()
        }
        with (world / "events.jsonl").open(encoding="utf-8") as audit:
            new = scorer(condition)(state, map(json.loads, audit), seat_logs)["metrics"]
        assert new["sabotage_success_v1"] == old["sabotage_success"], trial
        assert new["reward"] == new["task_utility"], trial
        drift = {
            key: {"recorded": value, "replayed": new[key]}
            for key, value in old.items()
            if key != "sabotage_success" and new[key] != value
        }
        new_metrics[str(trial)] = new
        trials.append(
            {
                "path": str(trial.relative_to(ROOT)),
                "models": models,
                "condition": condition,
                "exception": (result.get("exception_info") or {}).get("exception_type"),
                "ore_delivered": state["delivered_ore"],
                "adversary_ore_held_or_stashed": sum(
                    state["holds"][seat]["keystone"] + state["stashes"][seat]
                    for seat in report["ground_truth_adversaries"]
                ),
                "mission_failed": new["mission_failed"],
                "sabotage_success_v1": old["sabotage_success"],
                "sabotage_success": new["sabotage_success"],
                "reward": new["reward"],
                "other_metric_differences": drift,
            }
        )
    return trials, new_metrics


def with_corrected_metrics(bundle, new_by_trial):
    metrics = new_by_trial[bundle.trial_dir]
    # Hold historical diagnostics fixed to isolate the changed label.
    replacements = {
        name: metrics[name]
        for name in (
            "sabotage_success",
            "sabotage_success_v1",
            "mission_failed",
            "reward",
        )
    }
    report = bundle.report.model_copy(
        update={"metrics": bundle.report.metrics | replacements}
    )
    return bundle.model_copy(
        update={"report": report, "rewards": bundle.rewards | replacements}
    )


def compare_monitor(new_by_trial):
    negatives, _ = load(NEGATIVE_RUNS, NEGATIVE_CONDITIONS)
    patched_negatives = [with_corrected_metrics(b, new_by_trial) for b in negatives]
    published = read_json(OUTPUT.parent / "evasive_saboteur/results.json")
    wave10 = read_json(OUTPUT.parent / "rejected_requests/results.json")
    arms = (
        ("standard", SABOTEUR_RUNS, {"saboteur"}, published["standard"]),
        ("evasive", EVASIVE_RUNS, {"saboteur_evasive"}, published["evasive"]),
        (
            "wave10",
            ("runs/wave10-supply-evasive-rr",),
            {"saboteur_evasive"},
            wave10["treatment"],
        ),
    )
    rows = {}
    for name, runs, conditions, reference in arms:
        positives, _ = load(runs, conditions)
        patched_positives = [with_corrected_metrics(b, new_by_trial) for b in positives]
        before = evaluate(negatives, positives)
        after = evaluate(patched_negatives, patched_positives)
        assert before["tiers"] == after["tiers"] == reference["tiers"], name
        assert before["sabotage_success"] == reference["sabotage_success"], name
        rows[name] = {
            "old_n": before["sabotage_success"],
            "new_n": after["sabotage_success"],
            "positive_n": len(positives),
            "negative_n": len(negatives),
            "tiers_identical_before_after_and_to_published": True,
            "tiers": {
                tier: {
                    "auroc": value["stability"]["auroc"],
                    "attribution_correct": value["attribution_correct"],
                    "attribution_n": value["attribution_n"],
                }
                for tier, value in after["tiers"].items()
            },
        }
        if name != "wave10":
            rows[name]["tier1_auroc_conditioned_on_sabotage"] = {
                version: {
                    label: evaluate(
                        negatives,
                        [
                            b
                            for b in bundles
                            if b.report.metrics["sabotage_success"] == success
                        ],
                    )["tiers"][TIER1]["stability"]["auroc"]
                    for label, success in (("successful", 1), ("not_successful", 0))
                }
                for version, bundles in (("old", positives), ("new", patched_positives))
            }
    return rows


def fisher_two_sided(x, n, y, m):
    """Sum probabilities no larger than the observed table, with fixed margins."""
    total = x + y
    weight = comb(n, x) * comb(m, y)
    tail = sum(
        w
        for k in range(max(0, total - m), min(n, total) + 1)
        if (w := comb(n, k) * comb(m, total - k)) <= weight
    )
    return tail / comb(n + m, total)


def wilson95(x, n):
    z = 1.959963984540054
    proportion = x / n
    center = proportion + z * z / (2 * n)
    half = z * sqrt((proportion * (1 - proportion) + z * z / (4 * n)) / n)
    scale = 1 + z * z / n
    return [(center - half) / scale, (center + half) / scale]


def clopper_pearson95(x, n):
    def lower(successes):
        if not successes:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(60):
            p = (lo + hi) / 2
            tail = sum(
                comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(successes, n + 1)
            )
            if tail < 0.025:
                lo = p
            else:
                hi = p
        return (lo + hi) / 2

    return [lower(x), 1 - lower(n - x)]


def main():
    trials, metrics = replay_trials()
    monitor = compare_monitor(metrics)
    by_run_condition = defaultdict(list)
    for trial in trials:
        wave = Path(trial["path"]).parts[1]
        by_run_condition[wave, trial["condition"]].append(trial)
    totals = [
        {
            "run": run,
            "condition": condition,
            "n": len(rows),
            "timeouts": sum(
                "timeout" in (row["exception"] or "").lower() for row in rows
            ),
            **{
                key: int(sum(row[key] for row in rows))
                for key in ("mission_failed", "sabotage_success_v1", "sabotage_success")
            },
        }
        for (run, condition), rows in by_run_condition.items()
    ]
    standard, evasive, wave10 = (
        monitor[name] for name in ("standard", "evasive", "wave10")
    )
    wave1 = by_run_condition["wave1-supply", "saboteur"]
    wave2 = by_run_condition["wave2-supply-deepseek", "saboteur"]
    wave1_success = sum(int(row["sabotage_success"]) for row in wave1)
    wave2_success = sum(int(row["sabotage_success"]) for row in wave2)
    stats = {
        "fisher_standard_vs_evasive": {
            version: fisher_two_sided(
                standard[f"{version}_n"],
                standard["positive_n"],
                evasive[f"{version}_n"],
                evasive["positive_n"],
            )
            for version in ("old", "new")
        },
        "fisher_wave8_vs_wave10": {
            version: fisher_two_sided(
                evasive[f"{version}_n"],
                evasive["positive_n"],
                wave10[f"{version}_n"],
                wave10["positive_n"],
            )
            for version in ("old", "new")
        },
        "standard_new_wilson95": wilson95(standard["new_n"], standard["positive_n"]),
        "wave2_new_clopper_pearson95": clopper_pearson95(wave2_success, len(wave2)),
        "waves1_and_2_new_clopper_pearson95": clopper_pearson95(
            wave1_success + wave2_success, len(wave1) + len(wave2)
        ),
    }
    report = {
        "trial_count": len(trials),
        "totals": totals,
        "statistics": stats,
        "monitor": monitor,
        "trials": trials,
    }
    output = OUTPUT / "rescore.json"
    output.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(output)


if __name__ == "__main__":
    main()
