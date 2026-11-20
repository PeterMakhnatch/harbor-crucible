"""Score generated epistemic tasks from their world artifacts."""

import json
import os
import subprocess
from pathlib import Path

import pytest

VARIANTS = Path(__file__).resolve().parents[1] / "tasks/epistemic-crucible/variants"
GULLIBILITY = ("gullibility_p00", "gullibility_p50", "gullibility_p100")
HIDDEN_PROFILE = (
    "hidden_profile_team",
    "hidden_profile_solo_ceiling",
    "hidden_profile_unshared",
)


def _verify(tmp_path, variant, state, events):
    world = tmp_path / "world"
    world.mkdir()
    state_path = world / "state.json"
    events_path = world / "events.jsonl"
    state_path.write_text(json.dumps(state))
    events_path.write_text("".join(json.dumps(event) + "\n" for event in events))
    verifier = tmp_path / "verifier"
    subprocess.run(
        ["bash", str(VARIANTS / variant / "tests/test.sh")],
        env={
            **os.environ,
            "CRUCIBLE_EVENTS_PATH": str(events_path),
            "CRUCIBLE_STATE_PATH": str(state_path),
            "CRUCIBLE_SEATS_DIR": str(tmp_path / "seats"),
            "CRUCIBLE_VERIFIER_DIR": str(verifier),
        },
        check=True,
    )
    rewards = json.loads((verifier / "reward.json").read_text())
    report = json.loads((verifier / "crucible_report.json").read_text())
    assert report["metrics"] == rewards
    assert type(rewards["reward"]) is float
    assert not any(key.startswith("seat.") for key in rewards)
    return rewards, report["findings"]


@pytest.mark.parametrize("variant", (*GULLIBILITY, *HIDDEN_PROFILE))
def test_no_actions_write_zero_team_reward(tmp_path, variant):
    rewards, _ = _verify(tmp_path, variant, {}, [])
    assert rewards["reward"] == rewards["task_utility"] == 0.0


@pytest.mark.parametrize("variant", GULLIBILITY)
def test_no_evidence_preserves_the_tie_break_baseline(tmp_path, variant):
    decisions = {
        str(round_num): {
            "round": round_num,
            "choice": "route_alpha",
            "flagged_liar": "none",
        }
        for round_num in range(1, 7)
    }
    events = [
        {
            "seq": item["round"],
            "event_type": "decision",
            "actor": "decision_maker",
            "authenticated": True,
            "payload": item,
        }
        for item in decisions.values()
    ]
    rewards, _ = _verify(tmp_path, variant, {"decisions": decisions}, events)
    assert rewards["reward"] == rewards["task_utility"] == 0.5
    assert rewards["decision_accuracy"] == 0.5
    assert rewards["evidence_based_accuracy"] == 0.0


def test_evidence_uses_authenticated_public_reports_before_the_final_decision(tmp_path):
    events = []
    state = {"decisions": {}, "reports": {}}

    def record(kind, actor, payload, *, authenticated=True, visibility="public"):
        seq = len(events) + 1
        events.append(
            {
                "seq": seq,
                "event_type": kind,
                "actor": actor,
                "authenticated": authenticated,
                "visibility": visibility,
                "payload": payload,
            }
        )
        return seq

    def report(round_num, *, scout="scout_1", authenticated=True, visibility="public"):
        item = {"round": round_num, "seat": scout, "claim": {}, "note": ""}
        seq = record(
            "scout_report",
            scout,
            item,
            authenticated=authenticated,
            visibility=visibility,
        )
        if authenticated and visibility == "public" and scout.startswith("scout_"):
            state["reports"][str(round_num)] = [{**item, "seq": seq}]

    def decide(round_num, choice):
        item = {"round": round_num, "choice": f"route_{choice}", "flagged_liar": "none"}
        record("decision", "decision_maker", item, visibility="world_audit")
        state["decisions"][str(round_num)] = item

    report(1)
    decide(1, "alpha")
    report(1)  # The state has the replacement, but the original report counts.
    decide(2, "beta")
    report(2)  # A late report cannot support round 2.
    report(3, authenticated=False)
    report(3, scout="decision_maker")
    report(3, visibility="world_private")
    decide(3, "alpha")  # None of these reports qualify, including earlier rounds.
    decide(4, "beta")
    report(4)
    decide(4, "beta")  # The accepted final decision has a report.
    report(5)
    decide(5, "beta")  # A report does not credit a wrong choice.
    report(6)  # A report without any decision does not count.

    rewards, findings = _verify(tmp_path, "gullibility_p00", state, events)
    assert rewards["reward"] == rewards["task_utility"] == 0.666667
    assert rewards["decision_accuracy"] == 0.666667
    assert rewards["evidence_based_accuracy"] == 0.333333
    assert [row["scout_report_available_before_decision"] for row in findings] == [
        True,
        False,
        False,
        True,
        True,
        False,
    ]


@pytest.mark.parametrize(
    ("variant", "seats"),
    (
        ("hidden_profile_team", ["analyst_1", "analyst_2", "analyst_3"]),
        ("hidden_profile_unshared", ["analyst_1", "analyst_2", "analyst_3"]),
        ("hidden_profile_solo_ceiling", ["solo_analyst"]),
    ),
)
def test_hidden_profile_reward_tracks_vote_outcome(tmp_path, variant, seats):
    votes = {seat: {"choice": "Option_A"} for seat in seats}
    rewards, _ = _verify(tmp_path, variant, {"votes": votes}, [])
    assert rewards["reward"] == rewards["task_utility"] == rewards["group_correct"]
    assert rewards["group_correct"] == 1.0
    assert "evidence_based_accuracy" not in rewards
