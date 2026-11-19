"""Offline tests for task and trial audit-contract checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from crucible.cli import app
from crucible.lint import lint_bundle, lint_events, lint_task, render_lint_report
from crucible.loader import load_trial_bundle
from crucible.schema import WorldEvent

_TASK_TOML = '''\
artifacts = ["/logs/world/events.jsonl"]

[agents.scout_a]
[agents.scout_b]
'''
_COMPOSE = """\
services:
  main:
    environment:
      TOKEN_SCOUT_A: &scout_a unique-a
  scout_a:
    environment:
      SEAT_TOKEN: *scout_a
  scout_b:
    environment:
      - TOKEN_SCOUT_B=unique-b
  cache:
    image: cache
"""
_WORLD = '''\
def record(event_type, actor, *, visibility="world_private"):
    return {"event_type": event_type, "actor": actor, "visibility": visibility}

record("scan", "scout_a", visibility="world_audit")
record("hidden_yield", "world")
record("message_read", "scout_b", visibility="world_audit")
'''
_VERIFIER = '''\
import json
from pathlib import Path

output = Path("/logs/verifier")
reward_path = output / "reward.json"
metrics = {"score": 1.0, "safety": 0}
reward_path.write_text(json.dumps(metrics) + "\\n")
(output / "crucible_report.json").write_text(json.dumps({"is_negative_control": True}))
'''


@pytest.fixture

def task(tmp_path: Path) -> Path:
    root = tmp_path / "task"
    for folder in ("environment", "instructions", "tests"):
        (root / folder).mkdir(parents=True)
    files = {
        "task.toml": _TASK_TOML,
        "environment/docker-compose.yaml": _COMPOSE,
        "environment/world.py": _WORLD,
        "instructions/scout_a.md": "Instructions for scout_a.",
        "instructions/scout_b.md": "Instructions for scout_b.",
        "tests/test.sh": 'exec python3 "$(dirname "$0")/verify.py"\n',
        "tests/verify.py": _VERIFIER,
    }
    for path, content in files.items():
        (root / path).write_text(content)
    return root


def _event(seq: int, event_type: str, visibility: str = "public", actor: str = "scout_a") -> WorldEvent:
    return WorldEvent(seq=seq, ts=f"2026-01-01T00:00:{seq:02d}Z", task_family="supply-chain-sabotage",
                      condition="saboteur", event_type=event_type, visibility=visibility, actor=actor)


def _trial(root: Path, events: list[WorldEvent]) -> Path:
    trial = root / "runs" / "saboteur__test"
    trajectory_dir = trial / "seats" / "scout_a" / "agent"
    trajectory_dir.mkdir(parents=True)
    (trajectory_dir / "trajectory.json").write_text('{"steps": []}')
    (trial / "result.json").write_text(json.dumps({"seat_results": [
        {"seat": "scout_a", "agent_result": {"cost_usd": 0}}, {"seat": "scout_b"},
    ]}))
    audit_dir = trial / "artifacts" / "logs" / "world"
    audit_dir.mkdir(parents=True)
    (audit_dir / "events.jsonl").write_text("\n".join(event.model_dump_json() for event in events) + "\n")
    return trial


def test_good_task(task: Path) -> None:
    report = lint_task(task)
    assert report.findings == []
    assert report.to_dict() == {"findings": [], "errors": 0, "warnings": 0, "ok": True}
    assert "0 error(s), 0 warning(s)" in render_lint_report(report)


@pytest.mark.parametrize(("rule", "path", "replacement"), [
    ("audit-missing-log", "task.toml", _TASK_TOML.replace("/logs/world/events.jsonl", "/logs/world/state.json")),
    ("audit-no-tokens", "environment/docker-compose.yaml", _COMPOSE.replace("TOKEN_SCOUT_B=unique-b", "SEAT=scout_b")),
    ("audit-shared-token", "environment/docker-compose.yaml", _COMPOSE.replace("unique-b", "unique-a")),
    ("audit-visibility-default", "environment/world.py", _WORLD.replace('record("scan", "scout_a", visibility="world_audit")',
                                                                      'record("scan", "scout_a")')),
    ("audit-visibility-default", "environment/world.py", _WORLD.replace("world_audit", "public")),
    ("audit-no-message-read", "environment/world.py", _WORLD.replace('record("message_read", "scout_b", visibility="world_audit")',
                                                                    'known_kind = "message_read"')),
    ("audit-missing-seat-instructions", "instructions/scout_b.md", None),
])
def test_static_error_rules(task: Path, rule: str, path: str, replacement: str | None) -> None:
    if replacement is None:
        (task / path).unlink()
    else:
        (task / path).write_text(replacement)
    report = lint_task(task)
    assert [(item.id, item.severity, item.path) for item in report.findings] == [(rule, "error", path)]
    assert not report.ok


def test_compose_missing_tokens_are_reported_per_seat(task: Path) -> None:
    path = task / "environment/docker-compose.yaml"
    path.write_text("services:\n  main: {}\n  scout_a: {}\n  scout_b: {}\n  cache: {}\n")
    findings = lint_task(task).findings
    assert [item.id for item in findings] == ["audit-no-tokens", "audit-no-tokens"]
    assert all(seat in item.message for seat, item in zip(("scout_a", "scout_b"), findings, strict=True))


def test_compose_does_not_treat_substitutions_as_literal_tokens(task: Path) -> None:
    path = task / "environment/docker-compose.yaml"
    path.write_text(_COMPOSE.replace("unique-a", '"${SOME_TOKEN}"').replace("- TOKEN_SCOUT_B=unique-b", "- TOKEN_SCOUT_B=${SOME_TOKEN}"))
    assert lint_task(task).findings == []
    path.write_text("services:\n  scout_a: {}\n  scout_b: {}\n")
    assert lint_task(task).findings == []


def test_world_source_fallback_and_positional_visibility_override(task: Path) -> None:
    root = task / "environment"
    (root / "world.py").unlink()
    (root / "service.py").write_text(_WORLD.replace("actor, *, visibility", "actor, visibility")
                                     .replace('visibility="world_audit")', '"world_audit")'))
    assert lint_task(task).findings == []


@pytest.mark.parametrize("payload", ['{"score": True}', '{"score": False}', '{"score": "1"}'])
def test_reward_payload_must_be_numeric(task: Path, payload: str) -> None:
    (task / "tests/verify.py").write_text(_VERIFIER.replace('{"score": 1.0, "safety": 0}', payload))
    report = lint_task(task)
    assert [(item.id, item.line) for item in report.findings] == [("audit-reward-contract", 7)]
    assert report.errors == 1
    assert "booleans" in report.findings[0].message


def test_reward_payload_stream_is_distinct_from_report_payload(task: Path) -> None:
    (task / "tests/verify.py").write_text('''\
import json
with open("reward.json", "w") as result:
    json.dump({"utility": False}, result)
with open("crucible_report.json", "w") as result_report:
    json.dump({"is_negative_control": True}, result_report)
''')
    assert [item.id for item in lint_task(task).findings] == ["audit-reward-contract"]


def test_shell_only_verifier_reports_warnings_and_invalid_json_reward(task: Path) -> None:
    (task / "tests/verify.py").unlink()
    (task / "tests/test.sh").write_text('''\
#!/bin/bash
REWARD="$LOGS/reward.json"
cat > "$REWARD" <<'JSON'
{"score": false}
JSON
''')
    report = lint_task(task)
    assert [(item.id, item.severity) for item in report.findings] == [
        ("audit-verifier-not-deterministic", "warning"),
        ("audit-missing-crucible-report", "warning"),
        ("audit-reward-contract", "error"),
    ]
    assert report.errors == 1
    assert report.warnings == 2


def test_shell_inline_python_counts_as_json_verifier(task: Path) -> None:
    (task / "tests/verify.py").unlink()
    (task / "tests/test.sh").write_text("#!/bin/bash\npython3 - <<'PY'\n" + _VERIFIER + "PY\n")
    assert lint_task(task).findings == []


def test_visibility_collapse_reports_each_affected_action_count() -> None:
    report = lint_events([
        _event(1, "scan", "world_private"), _event(2, "scan", "world_private"),
        _event(3, "stash", "world_private"), _event(4, "message_read", "world_private"),
    ])
    assert [(item.id, item.severity) for item in report.findings] == [
        ("event-visibility-collapse", "error"), ("event-no-public", "warning"),
        ("event-unaudited-actions", "error"),
    ]
    action = report.findings[-1]
    assert "scan=2, stash=1" in action.message
    assert action.hint is not None and "world_audit" in action.hint


def test_only_private_actions_are_flagged_in_an_otherwise_visible_log() -> None:
    report = lint_events([
        _event(1, "message_read"), _event(2, "scan", "world_audit"),
        _event(3, "hidden_yield", "world_private"), _event(4, "stash", "world_private"),
    ])
    assert [item.id for item in report.findings] == ["event-unaudited-actions"]
    assert "stash=1" in report.findings[0].message


@pytest.mark.parametrize(("visibility", "actor", "valid"), [
    ("dm:scout_a:scout_b", "scout_a", True), ("dm:scout_a:scout_b", "scout_c", False),
    ("dm:scout_a", "scout_a", False), ("dm:scout_a:", "scout_a", False),
    ("dm::scout_b", "scout_a", False), ("dm:scout_a:scout_b:main", "scout_a", False),
    ("dm:scout_a: ", "scout_a", False), ("dm", "scout_a", False),
])
def test_dm_requires_valid_audience_and_authenticated_sender(visibility: str, actor: str, valid: bool) -> None:
    report = lint_events([_event(1, "message_read"), _event(2, "message_dm", visibility, actor)])
    assert [item.id for item in report.findings] == ([] if valid else ["event-bad-audience"])


@pytest.mark.parametrize("previous", [2, 3])
def test_event_sequence_is_strictly_increasing(previous: int) -> None:
    report = lint_events([_event(previous, "message_read"), _event(2, "scan", "world_audit")])
    assert [item.id for item in report.findings] == ["event-seq-not-monotonic"]


def test_event_warnings_and_informational_findings() -> None:
    report = lint_events([_event(1, "impersonation_attempt"), _event(2, "impersonation_attempt")])
    assert [(item.id, item.severity) for item in report.findings] == [
        ("event-no-message-read", "warning"), ("event-impersonation", "info"),
    ]
    assert "2" in report.findings[-1].message
    assert report.ok and report.warnings == 1
    assert [item.id for item in lint_events([]).findings] == ["event-no-message-read"]
    solo = _event(1, "message_read", "world_audit").model_copy(update={
        "task_family": "epistemic-crucible", "condition": "hidden_profile_solo_ceiling",
    })
    assert lint_events([solo]).findings == []


def test_bundle_reports_missing_traces_and_unknown_cost(tmp_path: Path) -> None:
    trial = _trial(tmp_path, [_event(1, "message_read")])
    report = lint_bundle(load_trial_bundle(trial))
    assert [(item.id, item.severity) for item in report.findings] == [
        ("bundle-missing-traces", "warning"), ("bundle-usage-incomplete", "warning"),
    ]
    assert all("scout_b" in item.message and "scout_a" not in item.message for item in report.findings)


def test_cli_task_and_trial_exit_codes(task: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    clean = runner.invoke(app, ["lint-task", str(task)])
    assert clean.exit_code == 0, clean.output
    assert "Audit contract: 0 error(s), 0 warning(s)" in clean.output

    trial = _trial(tmp_path, [_event(2, "message_read"), _event(1, "scan", "world_audit")])
    bad = runner.invoke(app, ["lint-task", str(trial), "--json"])
    assert bad.exit_code == 1, bad.output
    summary = json.loads(bad.output)
    assert (summary["ok"], summary["errors"], summary["warnings"]) == (False, 1, 2)
    assert summary["findings"][0]["id"] == "event-seq-not-monotonic"
    assert summary["findings"][0]["path"] == "artifacts/logs/world/events.jsonl"


def test_cli_parent_discovers_tasks_and_trials_with_verifier_only(task: Path, tmp_path: Path) -> None:
    (task / "instructions/scout_a.md").unlink()
    trial = tmp_path / "runs" / "verifier-only"
    (trial / "verifier").mkdir(parents=True)
    (trial / "result.json").write_text("{}")
    parent = CliRunner().invoke(app, ["lint-task", str(tmp_path), "--json"])
    assert parent.exit_code == 1, parent.output
    assert {item["path"] for item in json.loads(parent.output)["findings"]} == {
        "task/instructions/scout_a.md", "runs/verifier-only/world/events.jsonl",
    }
