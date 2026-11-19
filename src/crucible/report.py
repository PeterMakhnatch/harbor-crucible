"""Self-contained evidence report over a corpus of multi-seat trials."""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from crucible.calibration import render_benchmark_markdown, summarize_verdicts
from crucible.loader import discover_trial_dirs, load_trial_bundle
from crucible.monitor import DeterministicCrucibleMonitor
from crucible.schema import MonitorTier, TrialBundle
from crucible.spend import SpendLedger

# Reward keys that identify a task outcome rather than an integrity signal.
HEADLINE_METRICS = (
    "task_utility",
    "safety_score",
    "sabotage_success",
    "hoarded_keystone_units",
    "ground_truth_deceptive_reports",
    "honest_detection_hit",
    "false_accusation_rate",
    "rh_confirmed",
    "contagion_occurred",
    "delivered_hack",
    "hack_blocked",
    "decision_accuracy",
    "liar_identified",
    "gap_recovered",
    "group_correct",
    "unique_facts_surfaced",
    "premature_consensus_trap",
    "outcome_clean_collaboration",
    "outcome_truce",
    "outcome_force",
    "outcome_passivity",
    "outcome_unresolved",
    "escalation_count",
    "lockout_count",
    "camouflage_count",
)


def _span(values: list[float]) -> str:
    if not values:
        return "-"
    if len(values) == 1:
        return f"{values[0]:.2f}"
    return f"{min(values):.2f}–{max(values):.2f}"


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def collect_condition_table(
    bundles: list[TrialBundle],
) -> list[dict[str, Any]]:
    """Group trials by family, condition and seat model set, and summarise rewards."""
    groups: dict[tuple[str, str, str], list[TrialBundle]] = defaultdict(list)
    for bundle in bundles:
        models = ",".join(sorted(set(bundle.seat_models.values()))) or "unknown"
        groups[(bundle.task_family, bundle.condition, models)].append(bundle)

    rows: list[dict[str, Any]] = []
    for (family, condition, models), members in sorted(groups.items()):
        metrics: dict[str, list[float]] = defaultdict(list)
        for bundle in members:
            for key, value in bundle.rewards.items():
                metrics[key].append(value)
        rows.append(
            {
                "family": family,
                "condition": condition,
                "models": models,
                "n_trials": len(members),
                "n_errored": sum(1 for b in members if b.trial_exception),
                "n_timeouts": sum(
                    1
                    for b in members
                    if b.trial_exception and "timeout" in b.trial_exception.lower()
                ),
                "metrics": {
                    key: {
                        "n": len(values),
                        "mean": _mean(values),
                        "min": min(values),
                        "max": max(values),
                        "span": _span(values),
                    }
                    for key, values in sorted(metrics.items())
                },
            }
        )
    return rows


def render_condition_markdown(rows: list[dict[str, Any]]) -> str:
    """One table per family, with only the metrics that family reports."""
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[row["family"]].append(row)

    blocks: list[str] = []
    for family, family_rows in sorted(by_family.items()):
        present = [
            key
            for key in HEADLINE_METRICS
            if any(key in row["metrics"] for row in family_rows)
        ]
        # Metrics a family never reports would only add dashes.
        header = "| Condition | Model | n | Timeouts | " + " | ".join(present) + " |"
        rule = "|---|---|---:|---:|" + "---:|" * len(present)
        lines = [f"### `{family}`", "", header, rule]
        for row in family_rows:
            cells = [
                f"`{row['condition']}`",
                f"`{row['models']}`",
                str(row["n_trials"]),
                str(row["n_timeouts"]),
            ]
            for key in present:
                metric = row["metrics"].get(key)
                cells.append(metric["span"] if metric else "-")
            lines.append("| " + " | ".join(cells) + " |")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def build_report(
    runs_roots: list[Path],
    *,
    out_dir: Path,
    tiers: str = "tier0_public_only,tier1_public_plus_audit,tier2_full_trajectories",
    integrity_families: str | None = None,
    ledger_path: Path = Path("experiments/spend_ledger.jsonl"),
    cap_usd: float = 20.0,
) -> dict[str, Any]:
    """Load a corpus, score the monitor tiers, and write REPORT.md plus report.json."""
    trial_dirs: list[Path] = []
    for root in runs_roots:
        trial_dirs.extend(discover_trial_dirs(root))
    if not trial_dirs:
        raise FileNotFoundError(f"no multi-seat trials under {[str(r) for r in runs_roots]}")
    bundles = [load_trial_bundle(td) for td in trial_dirs]

    selected_tiers = [MonitorTier(t.strip()) for t in tiers.split(",") if t.strip()]
    monitor = DeterministicCrucibleMonitor()
    scored = bundles
    if integrity_families:
        wanted = {f.strip() for f in integrity_families.split(",")}
        scored = [b for b in bundles if b.task_family in wanted]
    verdicts = [monitor.evaluate(b, tier) for b in scored for tier in selected_tiers]
    summaries = summarize_verdicts(verdicts)

    rows = collect_condition_table(bundles)
    ledger = SpendLedger(path=ledger_path, cap_usd=cap_usd)

    commit = "unknown"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[2],
        ).stdout.strip() or "unknown"
    except OSError:
        pass

    payload = {
        "generated_by": "crucible report",
        "corpus_commit": commit,
        "corpus_roots": [str(r) for r in runs_roots],
        "n_trials": len(bundles),
        "n_scored_for_integrity": len(scored),
        "tiers": [t.value for t in selected_tiers],
        "integrity_families": integrity_families,
        "conditions": rows,
        "monitor_summary": [s.model_dump() for s in summaries],
        "spend": ledger.summary(),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out_dir / "REPORT.md").write_text(
        _render_markdown(payload, rows, summaries, bundles, ledger)
    )
    return payload


def _render_markdown(
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
    summaries: list[Any],
    bundles: list[TrialBundle],
    ledger: SpendLedger,
) -> str:
    missing = sum(1 for b in bundles if b.missing_traces)
    errored = sum(1 for b in bundles if b.trial_exception)
    timeouts = sum(
        1 for b in bundles if b.trial_exception and "timeout" in b.trial_exception.lower()
    )
    spend = ledger.summary()
    parts = [
        "# Crucible evidence report",
        "",
        f"- Generated by `crucible report` at corpus commit `{payload['corpus_commit']}`.",
        f"- Corpora: {', '.join(f'`{r}`' for r in payload['corpus_roots'])}.",
        (
            f"- Trials: {payload['n_trials']} ({errored} with a recorded trial error, "
            f"of which {timeouts} timed out; "
            f"{missing} with at least one missing seat trace)."
        ),
        f"- Spend so far: ${spend['total_usd']:.4f} of the ${spend['cap_usd']:.2f} cap.",
        "",
        "## Outcomes by condition",
        "",
        "Each cell is the observed range across trials. A dash means the verifier did not report that metric.",
        "",
        render_condition_markdown(rows),
        "",
        "## Monitor tiers",
        "",
    ]
    if summaries:
        parts.append(render_benchmark_markdown(summaries))
    else:
        parts.append("No integrity-labelled trials in this corpus.")
    parts += [
        "",
        "## How to read this",
        "",
        "- Ranges, not means, are shown per condition because the per-condition sample is small.",
        "- A trial that timed out still counts in the denominator. Its mission metrics are lower bounds, because the episode was cut short, so read `task_utility` under a timeout as a floor and not as model failure.",
        "- A trial with no recorded seat trace still counts in the denominator. Missing evidence is not a pass.",
        "- The monitor table scores only trials whose family is listed under `integrity_families`; conflict-only designs have no instructed adversary and would otherwise be counted as negatives.",
        "",
    ]
    return "\n".join(parts)
