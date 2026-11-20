"""Re-score recorded epistemic trials without modifying their artifacts."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ROOT / "tasks/epistemic-crucible/variants"
TASK_PREFIX = "crucible/epistemic-crucible-"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def replay(trial: Path, variant: str) -> dict:
    world = trial / "artifacts/logs/world"
    events = world / "events.jsonl"
    state = world / "state.json"
    for path in (events, state):
        if not path.is_file():
            raise FileNotFoundError(path)
    with tempfile.TemporaryDirectory(prefix="epistemic-replay-") as work_dir:
        subprocess.run(
            ["bash", str(VARIANTS / variant / "tests/test.sh")],
            check=True,
            env={
                **os.environ,
                "CRUCIBLE_EVENTS_PATH": str(events),
                "CRUCIBLE_STATE_PATH": str(state),
                "CRUCIBLE_SEATS_DIR": str(trial / "seats"),
                "CRUCIBLE_VERIFIER_DIR": work_dir,
            },
        )
        return load(Path(work_dir) / "crucible_report.json")


def main() -> None:
    trials = []
    for path in sorted((ROOT / "runs").rglob("result.json")):
        result = load(path)
        task_name = result.get("task_name", "")
        if not task_name.startswith(TASK_PREFIX):
            continue
        trial = path.parent
        variant = task_name.removeprefix(TASK_PREFIX)
        recorded = load(trial / "verifier/reward.json")
        if recorded != result["verifier_result"]["rewards"]:
            raise ValueError(f"Recorded rewards disagree for {trial}")
        updated_report = replay(trial, variant)
        updated = updated_report["metrics"]
        agent = result["agent_info"]
        trials.append(
            {
                "trial": str(trial.relative_to(ROOT)),
                "variant": variant,
                "agent": agent["name"],
                "model": agent.get("model_info"),
                "recorded": recorded,
                "replayed": updated,
                "changed_legacy_keys": sorted(
                    key for key, value in recorded.items() if updated.get(key) != value
                ),
                "rounds": [
                    {
                        "round": row["round"],
                        "correct": row["correct"],
                        "scout_report_available_before_decision": row[
                            "scout_report_available_before_decision"
                        ],
                    }
                    for row in updated_report["findings"]
                    if "round" in row
                ],
            }
        )
    if not trials:
        raise ValueError("No recorded epistemic trials")
    print(json.dumps({"trials": trials}, indent=2))


if __name__ == "__main__":
    main()
