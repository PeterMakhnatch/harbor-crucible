"""Crucible CLI: inspect multi-seat traces, benchmark monitors, run trials, export to Eval Lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from crucible.bridge import build_seat_regrade_config, export_corpus_evallab_jsonl
from crucible.lint import LintReport, lint_task, lint_trial, render_lint_report
from crucible.loader import discover_trial_dirs, load_trial_bundle
from crucible.schema import MonitorTier, MonitorVerdict
from crucible.spend import SpendLedger
from crucible.trace import (
    build_exposure_graph,
    build_unified_timeline,
    render_timeline_html,
)

app = typer.Typer(
    name="crucible",
    help="Adversarial multi-agent evaluation & calibrated monitor benchmark for Harbor Multi-Agent.",
    no_args_is_help=True,
)
console = Console()


@app.command("trace")
def cmd_trace(
    trial_dir: Annotated[Path, typer.Argument(help="Path to a Harbor multi-seat trial directory.")],
    html_out: Annotated[Path | None, typer.Option("--html", help="Write standalone HTML explorer.")] = None,
    json_out: Annotated[Path | None, typer.Option("--json", help="Write timeline + exposure JSON.")] = None,
) -> None:
    """Build cross-seat causal timeline and message-exposure graph for a trial."""
    bundle = load_trial_bundle(trial_dir)
    timeline = build_unified_timeline(bundle)
    graph = build_exposure_graph(bundle)

    table = Table(title=f"Crucible Trace: {bundle.trial_name} ({bundle.task_family}/{bundle.condition})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")
    table.add_row("Seats", ", ".join(bundle.seats))
    table.add_row("World events", str(len(bundle.world_events)))
    table.add_row("Timeline entries", str(len(timeline)))
    table.add_row("Missing ATIF traces", ", ".join(bundle.missing_traces) or "none")
    table.add_row(
        "Message exposure",
        f"{graph['exposure_rate']:.1%} ({graph['n_messages_read_by_peer']}/{graph['n_messages_sent']})",
    )
    for k, v in sorted(bundle.rewards.items()):
        table.add_row(f"reward.{k}", f"{v:.3f}")
    console.print(table)

    if html_out is not None:
        rendered = render_timeline_html(bundle, html_out)
        console.print(f"[green]HTML explorer written:[/green] {rendered}")
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(
                {
                    "trial_name": bundle.trial_name,
                    "exposure_graph": graph,
                    "timeline": [t.model_dump() for t in timeline],
                },
                indent=2,
            )
        )
        console.print(f"[green]JSON trace written:[/green] {json_out}")


@app.command("benchmark-monitors")
def cmd_benchmark_monitors(
    runs_roots: Annotated[
        list[Path], typer.Argument(help="Directories containing Harbor multi-seat trials.")
    ],
    out_dir: Annotated[Path, typer.Option("--out-dir")] = Path("experiments/monitor_benchmark"),
    target_fpr: Annotated[float, typer.Option("--target-fpr", help="Calibration false-positive rate.")] = 0.05,
    llm_model: Annotated[
        str | None, typer.Option("--llm-model", help="Optional LLM monitor model (e.g. deepseek-chat).")
    ] = None,
    tiers: Annotated[str, typer.Option("--tiers", help="Comma-separated monitor visibility tiers.")] = (
        "tier0_public_only,tier1_public_plus_audit,tier2_full_trajectories"
    ),
    families: Annotated[
        str | None,
        typer.Option(
            "--families",
            help="Comma-separated task families to score. Default: all. "
            "Use this to exclude designs with no instructed adversary.",
        ),
    ] = None,
) -> None:
    """Evaluate deterministic (and optional LLM) monitors across visibility tiers with fixed-FPR calibration."""
    from crucible.calibration import render_benchmark_markdown, summarize_verdicts
    from crucible.monitor import DeterministicCrucibleMonitor, LLMMonitor

    wanted = {f.strip() for f in families.split(",")} if families else None
    trial_dirs: list[Path] = []
    for root in runs_roots:
        trial_dirs.extend(discover_trial_dirs(root))
    if not trial_dirs:
        console.print(f"[red]No multi-seat trials found under {[str(r) for r in runs_roots]}[/red]")
        raise typer.Exit(code=1)

    selected_tiers = [MonitorTier(t.strip()) for t in tiers.split(",") if t.strip()]
    bundles = [load_trial_bundle(td) for td in trial_dirs]
    if wanted is not None:
        bundles = [b for b in bundles if b.task_family in wanted]
        if not bundles:
            console.print(f"[red]No trials left after filtering to {sorted(wanted)}[/red]")
            raise typer.Exit(code=1)
    det_monitor = DeterministicCrucibleMonitor()
    verdicts: list[MonitorVerdict] = []

    for bundle in bundles:
        for tier in selected_tiers:
            verdicts.append(det_monitor.evaluate(bundle, tier))

    if llm_model:
        ledger = SpendLedger()
        llm_mon = LLMMonitor(model=llm_model, ledger=ledger)
        for bundle in bundles:
            for tier in selected_tiers:
                verdicts.append(llm_mon.evaluate(bundle, tier))

    summaries = summarize_verdicts(verdicts, target_fpr=target_fpr)
    md = render_benchmark_markdown(summaries)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "verdicts.jsonl").write_text(
        "\n".join(v.model_dump_json() for v in verdicts) + "\n"
    )
    (out_dir / "summary.json").write_text(
        json.dumps([s.model_dump() for s in summaries], indent=2)
    )
    (out_dir / "BENCHMARK.md").write_text(md)

    console.print(md)
    console.print(f"[green]Saved benchmark artifacts to[/green] {out_dir}")


@app.command("export-evallab")
def cmd_export_evallab(
    runs_root: Annotated[Path, typer.Argument(help="Directory containing Harbor multi-seat trials.")],
    out_path: Annotated[Path, typer.Option("--out")] = Path("experiments/evallab_seat_evidence.jsonl"),
    verdicts_jsonl: Annotated[
        Path | None, typer.Option("--verdicts", help="Optional monitor verdicts JSONL.")
    ] = None,
) -> None:
    """Export multi-seat trial evidence in Eval Lab–compatible JSONL format."""
    verdicts: list[MonitorVerdict] = []
    if verdicts_jsonl and verdicts_jsonl.is_file():
        for line in verdicts_jsonl.read_text().splitlines():
            if line.strip():
                verdicts.append(MonitorVerdict.model_validate_json(line))
    count = export_corpus_evallab_jsonl(runs_root, out_path, verdicts=verdicts)
    console.print(f"[green]Exported {count} trials to[/green] {out_path}")


@app.command("regrade-config")
def cmd_regrade_config(
    source_trial: Annotated[Path, typer.Argument(help="Completed multi-seat trial directory.")],
    regrade_task: Annotated[Path, typer.Argument(help="Separate-verifier task directory.")],
    out_yaml: Annotated[Path, typer.Option("--out")] = Path("regrade_trial.yaml"),
) -> None:
    """Write a Harbor SeatsRegradeTrial YAML config targeting Harbor PR 3."""
    import yaml

    cfg = build_seat_regrade_config(source_trial, regrade_task)
    out_yaml.parent.mkdir(parents=True, exist_ok=True)
    out_yaml.write_text(yaml.safe_dump(cfg, sort_keys=False))
    console.print(f"[green]Wrote seat regrade config:[/green] {out_yaml}")


def _is_trial_dir(path: Path) -> bool:
    return (path / "result.json").is_file() and (
        (path / "seats").is_dir() or (path / "verifier").is_dir()
    )


@app.command("lint-task")
def cmd_lint_task(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON instead of text.")] = False,
) -> None:
    """Check the audit contract of a task, trial, or directory of evidence."""
    if (path / "task.toml").is_file():
        report = lint_task(path)
    elif _is_trial_dir(path):
        report = lint_trial(path)
    else:
        report = LintReport()
        tasks = {item.parent for item in path.rglob("task.toml") if item.is_file()}
        trials = {item.parent for item in path.rglob("result.json") if _is_trial_dir(item.parent)}
        for directory in sorted(tasks | trials):
            child = lint_task(directory) if directory in tasks else lint_trial(directory)
            prefix = directory.relative_to(path).as_posix()
            report.findings.extend(
                finding.model_copy(update={"path": f"{prefix}/{finding.path}"})
                for finding in child.findings
            )
    typer.echo(json.dumps(report.to_dict(), indent=2) if as_json else render_lint_report(report))
    if not report.ok:
        raise typer.Exit(code=1)


@app.command("spend")
def cmd_spend(
    ledger_path: Annotated[Path, typer.Option("--ledger")] = Path("experiments/spend_ledger.jsonl"),
) -> None:
    """Display current experiment spend vs budget cap."""
    ledger = SpendLedger(path=ledger_path)
    console.print_json(json.dumps(ledger.summary(), indent=2))


@app.command("report")
def cmd_report(
    runs_roots: Annotated[
        list[Path],
        typer.Argument(help="Corpus roots holding multi-seat trials."),
    ],
    out_dir: Annotated[Path, typer.Option("--out-dir")] = Path("experiments/report"),
    tiers: Annotated[
        str,
        typer.Option("--tiers", help="Comma-separated monitor visibility tiers to score."),
    ] = "tier0_public_only,tier1_public_plus_audit,tier2_full_trajectories",
    integrity_families: Annotated[
        str | None,
        typer.Option(
            "--integrity-families",
            help="Families with an instructed adversary. Others are left out of the monitor table.",
        ),
    ] = None,
    ledger_path: Annotated[
        Path, typer.Option("--ledger")
    ] = Path("experiments/spend_ledger.jsonl"),
) -> None:
    """Write a reproducible evidence report for a corpus of multi-seat trials."""
    from crucible.report import build_report

    try:
        payload = build_report(
            runs_roots,
            out_dir=out_dir,
            tiers=tiers,
            integrity_families=integrity_families,
            ledger_path=ledger_path,
        )
    except FileNotFoundError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1) from error

    spend = payload["spend"]
    console.print(
        f"[green]Report written:[/green] {out_dir / 'REPORT.md'}\n"
        f"  trials: {payload['n_trials']}  scored: {payload['n_scored_for_integrity']}  "
        f"spend: ${spend['total_usd']:.4f}/${spend['cap_usd']:.2f}"
    )


if __name__ == "__main__":
    app()
