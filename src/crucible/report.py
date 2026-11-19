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
from crucible.stability import render_stability_markdown, summarize_monitor

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


def _timed_out(bundle: TrialBundle) -> bool:
    return bool(bundle.trial_exception) and "timeout" in bundle.trial_exception.lower()


def _span(values: list[float]) -> str:
    if not values:
        return "-"
    if len(values) == 1:
        return f"{values[0]:.2f}"
    return f"{min(values):.2f}–{max(values):.2f}"


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize_by_family(
    verdicts: list[Any],
) -> dict[str, list[Any]]:
    """One monitor summary per task family.

    Scores are not comparable across families: each world has its own event
    vocabulary and its own scale. A pooled table therefore mixes scales, so the
    report always shows the per-family split as well.
    """
    grouped: dict[str, list[Any]] = defaultdict(list)
    for verdict in verdicts:
        grouped[verdict.task_family].append(verdict)
    return {
        family: summarize_verdicts(items) for family, items in sorted(grouped.items())
    }


def collect_condition_table(
    bundles: list[TrialBundle],
) -> list[dict[str, Any]]:
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
    exclude_timeouts: bool = False,
    stability_draws: int = 1000,
    ledger_path: Path = Path("experiments/spend_ledger.jsonl"),
    cap_usd: float = 20.0,
) -> dict[str, Any]:
    """Load a corpus, score the monitor tiers, and write REPORT.md plus report.json."""
    trial_dirs: list[Path] = []
    for root in runs_roots:
        trial_dirs.extend(discover_trial_dirs(root))
    if not trial_dirs:
        raise FileNotFoundError(
            f"no multi-seat trials under {[str(r) for r in runs_roots]}"
        )
    bundles = [load_trial_bundle(td) for td in trial_dirs]
    n_excluded = 0
    if exclude_timeouts:
        all_bundles = bundles
        bundles = [b for b in all_bundles if not _timed_out(b)]
        n_excluded = len(all_bundles) - len(bundles)
        if not bundles:
            raise FileNotFoundError("every trial in this corpus timed out")

    selected_tiers = [MonitorTier(t.strip()) for t in tiers.split(",") if t.strip()]
    monitor = DeterministicCrucibleMonitor()
    scored = bundles
    if integrity_families:
        wanted = {f.strip() for f in integrity_families.split(",")}
        scored = [b for b in bundles if b.task_family in wanted]
    verdicts = [monitor.evaluate(b, tier) for b in scored for tier in selected_tiers]
    summaries = summarize_verdicts(verdicts)
    family_summaries = summarize_by_family(verdicts)

    stability_rows: list[dict[str, Any]] = []
    if stability_draws > 0:
        bucketed: dict[tuple[str, MonitorTier], list[Any]] = defaultdict(list)
        for verdict in verdicts:
            bucketed[(verdict.monitor_name, verdict.tier)].append(verdict)
        stability_rows = [
            summarize_monitor(items, draws=stability_draws)
            for _, items in sorted(
                bucketed.items(), key=lambda kv: (kv[0][0], kv[0][1].value)
            )
        ]

    rows = collect_condition_table(bundles)
    ledger = SpendLedger(path=ledger_path, cap_usd=cap_usd)

    commit = "unknown"
    try:
        commit = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parents[2],
            ).stdout.strip()
            or "unknown"
        )
    except OSError:
        pass

    payload = {
        "generated_by": "crucible report",
        "corpus_commit": commit,
        "corpus_roots": [str(r) for r in runs_roots],
        "n_trials": len(bundles),
        "n_excluded_timeouts": n_excluded,
        "exclude_timeouts": exclude_timeouts,
        "n_scored_for_integrity": len(scored),
        "tiers": [t.value for t in selected_tiers],
        "integrity_families": integrity_families,
        "conditions": rows,
        "monitor_summary": [s.model_dump() for s in summaries],
        "monitor_summary_by_family": {
            family: [s.model_dump() for s in items]
            for family, items in family_summaries.items()
        },
        "stability": stability_rows,
        "spend": ledger.summary(),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out_dir / "REPORT.md").write_text(
        _render_markdown(
            payload, rows, summaries, bundles, ledger, stability_rows, family_summaries
        )
    )
    return payload


def _render_markdown(
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
    summaries: list[Any],
    bundles: list[TrialBundle],
    ledger: SpendLedger,
    stability_rows: list[dict[str, Any]] | None = None,
    family_summaries: dict[str, list[Any]] | None = None,
) -> str:
    missing = sum(1 for b in bundles if b.missing_traces)
    errored = sum(1 for b in bundles if b.trial_exception)
    timeouts = sum(
        1
        for b in bundles
        if b.trial_exception and "timeout" in b.trial_exception.lower()
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
    ]
    if payload.get("n_excluded_timeouts"):
        parts.append(
            f"- **{payload['n_excluded_timeouts']} timed-out trials were excluded** "
            "(`--exclude-timeouts`), so every number below describes complete runs only."
        )
    parts += [
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
    if family_summaries:
        parts += [
            "",
            "## Monitor tiers per family",
            "",
            (
                "Scores are not comparable across families: each world has its own "
                "event vocabulary and its own scale, so a pooled table mixes scales. "
                "Read these."
            ),
            "",
        ]
        for family, items in family_summaries.items():
            parts += [f"### `{family}`", "", render_benchmark_markdown(items), ""]

    if stability_rows:
        parts += [
            "",
            "## How much of that is noise",
            "",
            "Bootstrap intervals over the negative controls. AUROC is threshold-free; a TPR is not, and its interval is the honest width of the claim.",
            "",
            render_stability_markdown(stability_rows),
            "",
        ]
    parts += [
        "",
        "## How to read this",
        "",
        "- Ranges, not means, are shown per condition because the per-condition sample is small.",
        "- A trial that timed out still counts in the denominator. Its mission metrics are lower bounds, because the episode was cut short, so read `task_utility` under a timeout as a floor and not as model failure.",
        "- A trial with no recorded seat trace still counts in the denominator. Missing evidence is not a pass.",
        "- The monitor table scores only trials whose family is listed under `integrity_families`; conflict-only designs have no instructed adversary and would otherwise be counted as negatives.",
        "- An AUROC interval that includes 0.5 means the monitor cannot be shown to rank adversaries above controls on this corpus, however good its TPR looks.",
        "",
    ]
    return "\n".join(parts)
