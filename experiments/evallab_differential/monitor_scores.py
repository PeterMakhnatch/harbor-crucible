"""Dump every frozen-monitor score on the retained corpus, for before/after loader checks.

Usage: .venv/bin/python experiments/evallab_differential/monitor_scores.py OUT.json
(set PYTHONPATH to another crucible src tree to score with that loader version).
Trials are listed from the immutable runs/ dirs named in compare.py (primary + extended).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import crucible
from crucible.loader import discover_trial_dirs, load_trial_bundle
from crucible.monitor import DeterministicCrucibleMonitor
from crucible.schema import MonitorTier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import EXTENDED, PRIMARY, REPO


def main() -> int:
    monitor = DeterministicCrucibleMonitor()
    rows = []
    for wave in (*PRIMARY, *EXTENDED):
        for trial in discover_trial_dirs(REPO / "runs" / wave):
            bundle = load_trial_bundle(trial)
            for tier in MonitorTier:
                verdict = monitor.evaluate(bundle, tier)
                rows.append(
                    {
                        "trial": f"{wave}/{trial.name}",
                        "tier": tier.value,
                        "trial_suspicion_score": verdict.trial_suspicion_score,
                        "top_predicted_seat": verdict.top_predicted_seat,
                        "seat_scores": {
                            seat: score.score
                            for seat, score in sorted(verdict.seat_scores.items())
                        },
                        "seats": bundle.seats,
                        "n_steps": {
                            s: len(v) for s, v in sorted(bundle.seat_steps.items())
                        },
                    }
                )
    Path(sys.argv[1]).write_text(
        json.dumps(
            {"crucible_src": str(Path(crucible.__file__).parent), "rows": rows},
            indent=1,
        )
    )
    print(len(rows), Path(crucible.__file__).parent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
