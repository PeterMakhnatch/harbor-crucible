"""Unit tests for the verifier reward contract checked by the control smoke."""

from pathlib import Path
from runpy import run_path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "control_smoke.py"
assert_rewards = run_path(str(SCRIPT))["assert_rewards"]


def test_accepts_numeric_rewards_and_allows_extra_metrics():
    assert_rewards(
        {"reward": 0.0, "sabotage_success": 0, "other": 1},
        {"reward": 0, "sabotage_success": 0},
    )
    assert_rewards({"reward": 0.6}, {"reward": 0.6})


def test_rejects_non_object_reward():
    with pytest.raises(TypeError, match="must contain a JSON object"):
        assert_rewards([], {"reward": 0})


@pytest.mark.parametrize(
    ("recorded", "message"),
    [
        ({"reward": 0}, "missing sabotage_success"),
        (
            {"reward": 0, "sabotage_success": 1.0},
            "sabotage_success: expected 0, got 1.0",
        ),
        ({"reward": False}, "reward: expected 0, got False"),
        ({"reward": "0"}, "reward: expected 0, got '0'"),
    ],
)
def test_rejects_missing_or_incorrect_rewards(recorded, message):
    with pytest.raises(ValueError, match=message):
        assert_rewards(recorded, {"reward": 0, "sabotage_success": 0})
