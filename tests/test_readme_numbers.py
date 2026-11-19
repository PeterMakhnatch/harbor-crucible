"""The README headline must match the committed evidence, or the test fails.

Documentation drifted from the data three times during this project: an audit
lift that came from timed-out trials, a pooled table that mixed families, and a
verdict that outlived its correction. This test makes that drift loud.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "experiments" / "report_final4" / "report.json"
README = ROOT / "README.md"


@pytest.fixture(scope="module")
def tier1_by_family() -> dict[str, dict[str, float | int | None]]:
    payload = json.loads(REPORT.read_text())
    out: dict[str, dict[str, float | int | None]] = {}
    for family, summaries in payload["monitor_summary_by_family"].items():
        for summary in summaries:
            if summary["tier"] == "tier1_public_plus_audit":
                out[family] = summary
    return out


def _readme_row(family: str) -> list[str]:
    for line in README.read_text().splitlines():
        if line.startswith(f"| `{family}`"):
            return [cell.strip() for cell in line.strip("|").split("|")]
    raise AssertionError(f"no README row for {family}")


def _pct(cell: str) -> float:
    return float(cell.replace("**", "").rstrip("%"))


def _auroc(cell: str) -> float:
    return float(re.search(r"([0-9.]+)", cell.replace("**", "")).group(1))


def test_supply_chain_row_matches_the_evidence(tier1_by_family) -> None:
    row = _readme_row("supply-chain-sabotage")
    evidence = tier1_by_family["supply-chain-sabotage"]

    assert int(row[1].split("/")[0]) == evidence["n_adversarial"]
    assert int(row[1].split("/")[1]) == evidence["n_negative_controls"]
    assert _auroc(row[3]) == pytest.approx(evidence["auroc_trial"], abs=5e-4)
    assert _pct(row[4]) == pytest.approx(evidence["tpr_at_5pct_fpr"] * 100, abs=0.1)
    assert _pct(row[5]) == pytest.approx(
        evidence["top_seat_attribution_accuracy"] * 100, abs=0.1
    )


def test_epistemic_row_matches_the_evidence(tier1_by_family) -> None:
    row = _readme_row("epistemic-crucible")
    evidence = tier1_by_family["epistemic-crucible"]

    assert int(row[1].split("/")[0]) == evidence["n_adversarial"]
    assert _auroc(row[3]) == pytest.approx(evidence["auroc_trial"], abs=5e-4)
    assert _pct(row[4]) == pytest.approx(evidence["tpr_at_5pct_fpr"] * 100, abs=0.1)


def test_reward_hack_row_matches_the_evidence(tier1_by_family) -> None:
    row = _readme_row("reward-hack-contagion")
    evidence = tier1_by_family["reward-hack-contagion"]

    assert int(row[1].split("/")[0]) == evidence["n_adversarial"]
    assert _auroc(row[3]) == pytest.approx(evidence["auroc_trial"], abs=5e-4)
    assert _pct(row[4]) == pytest.approx(evidence["tpr_at_5pct_fpr"] * 100, abs=0.1)


def test_the_headline_trial_count_matches_the_evidence() -> None:
    payload = json.loads(REPORT.read_text())
    text = README.read_text()
    match = re.search(r"(\d+) real-model seat trials, (\d+) of them complete", text)

    assert match, "the README no longer states a trial count"
    assert int(match.group(1)) == payload["n_trials"]
    assert int(match.group(2)) == payload["n_scored_for_integrity"]


def test_the_epistemic_tier_invariance_claim_is_true(tier1_by_family) -> None:
    """If a future corpus makes audit evidence matter here, the README claim must change."""
    payload = json.loads(REPORT.read_text())
    tiers = {
        summary["tier"]: summary["auroc_trial"]
        for summary in payload["monitor_summary_by_family"]["epistemic-crucible"]
    }

    assert tiers["tier0_public_only"] == tiers["tier1_public_plus_audit"]
    assert "scores identically at every tier" in README.read_text()
