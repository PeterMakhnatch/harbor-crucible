"""Combine two stored monitor benchmarks by maximum score, and compare all three.

Reads two verdicts.jsonl files (one per monitor), aligns them by trial, rescales the
LLM judge's scores so its maximum is 100, and reports the ensemble against each
member. Defined in experiments/PROTOCOL.md before the first measurement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from crucible.calibration import render_benchmark_markdown, summarize_verdicts
from crucible.schema import MonitorTier, MonitorVerdict

DOCTOR = "ensemble_max"


def _load(path: Path, tier: MonitorTier, name_prefix: str) -> dict[str, MonitorVerdict]:
    out: dict[str, MonitorVerdict] = {}
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            verdict = MonitorVerdict.model_validate(json.loads(line))
            if verdict.tier != tier or not verdict.monitor_name.startswith(name_prefix):
                continue
            out[verdict.trial_name] = verdict
    return out


def main(
    rules: Annotated[Path, typer.Option(help="Rules monitor verdicts.jsonl.")] = Path(
        "experiments/monitor_benchmark_wave1/verdicts.jsonl"
    ),
    llm: Annotated[Path, typer.Option(help="LLM judge verdicts.jsonl.")] = Path(
        "experiments/monitor_benchmark_wave1_llm/verdicts.jsonl"
    ),
    tier: Annotated[str, typer.Option(help="Visibility tier to compare.")] = (
        "tier1_public_plus_audit"
    ),
    rules_prefix: Annotated[str, typer.Option(help="Monitor name prefix to keep.")] = (
        "deterministic"
    ),
    llm_prefix: Annotated[
        str, typer.Option(help="Monitor name prefix to keep.")
    ] = "llm_",
    out_json: Annotated[Path, typer.Option(help="Where to write the summary.")] = Path(
        "experiments/monitor_ensemble/summary.json"
    ),
) -> None:
    monitor_tier = MonitorTier(tier)
    rule_map = _load(rules, monitor_tier, rules_prefix)
    llm_map = _load(llm, monitor_tier, llm_prefix)

    shared = sorted(set(rule_map) & set(llm_map))
    missing = sorted(set(rule_map) ^ set(llm_map))
    if not shared:
        raise typer.BadParameter("no trials shared between the two verdict files")

    llm_max = max((v.trial_suspicion_score for v in llm_map.values()), default=0.0)
    if llm_max <= 0.0:
        raise typer.BadParameter(
            "LLM judge scored zero on every trial; nothing to combine"
        )
    scale = 100.0 / llm_max

    ensemble: list[MonitorVerdict] = []
    for trial in shared:
        rule_v = rule_map[trial]
        llm_v = llm_map[trial]
        llm_scaled = llm_v.trial_suspicion_score * scale
        winner = rule_v if rule_v.trial_suspicion_score >= llm_scaled else llm_v
        ensemble.append(
            rule_v.model_copy(
                update={
                    "monitor_name": DOCTOR,
                    "trial_suspicion_score": min(
                        100.0, max(rule_v.trial_suspicion_score, llm_scaled)
                    ),
                    "seat_scores": winner.seat_scores,
                    "top_predicted_seat": winner.top_predicted_seat,
                    "top_seat_correct": None,
                    "monitor_cost_usd": llm_v.monitor_cost_usd,
                    "latency_ms": rule_v.latency_ms + llm_v.latency_ms,
                }
            )
        )

    summaries = summarize_verdicts(
        [rule_map[t] for t in shared] + [llm_map[t] for t in shared] + ensemble
    )
    markdown = render_benchmark_markdown(summaries)
    typer.echo(markdown)
    typer.echo(
        f"\nTrials paired: {len(shared)}. LLM score rescaled by {scale:.3f} "
        f"(raw maximum {llm_max:.2f}). Unpaired trials: {len(missing)}."
    )

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(
            {
                "tier": tier,
                "n_paired": len(shared),
                "llm_scale": scale,
                "unpaired_trials": missing,
                "summaries": [s.model_dump() for s in summaries],
            },
            indent=2,
        )
        + "\n"
    )
    (out_json.parent / "BENCHMARK.md").write_text(markdown + "\n")


if __name__ == "__main__":
    typer.run(main)
