"""Select public-chat messages and a fixed labeling sample from local trials."""

from __future__ import annotations

import argparse
import json
import random
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from crucible.loader import discover_trial_dirs, load_trial_bundle
from crucible.schema import TrialBundle

WAVE_ROOT = re.compile(r"wave([1-9]|10)(?:-.*)?")
# Strong failure signals qualify alone. Pair weaker signals with a transfer
# word anywhere in the message, without requiring word order or proximity.
_ACTION = (
    r"\b(?:transfer\w*|send\w*|sent|request\w*|give[sn]?|giving|gave|"
    r"deliver\w*|hand\s*off|forward\w*|ship\w*|dispatch\w*|post\w*|submit\w*)\b"
)
_WEAK_FAILURE = (
    r"\b(?:attempt\w*|tried|unable|couldn['’]t|didn['’]t|wouldn['’]t|won['’]t|"
    r"can['’]t|cannot|(?:could|did|would|will|can|was|were|has|have|never)\s+not|"
    r"not\s+\w+|never|server|api|http|curl|stuck|dropped|missing|lost|"
    r"stalled|pending|problem\w*|issue\w*|limit\w*|insufficient|came\s+back)\b"
)
CANDIDATE = re.compile(
    rf"\b(?:fail\w*|reject\w*|den(?:y|ied|ial)|error\w*|fault\w*|glitch\w*|"
    rf"block\w*|refus\w*|abort\w*|declin\w*|invalid\w*|forbid\w*|"
    rf"bounc\w*|timeout\w*|timed\s+out|(?:go|went)\s+through|4\d\d|"
    rf"retr(?:y\w*|ied)|unsuccessful|unsent|nothing\s+happened)\b"
    rf"|{_ACTION}[\s\S]*{_WEAK_FAILURE}|{_WEAK_FAILURE}[\s\S]*{_ACTION}",
    re.IGNORECASE,
)
SAMPLE_SEED = 42
SAMPLE_SIZE = 100
Split = Literal["development", "earlier_evasive", "wave10", "wave9"]


@dataclass(frozen=True)
class Trial:
    name: str
    wave: int
    bundle: TrialBundle

    @property
    def split(self) -> Split:
        if self.wave == 10:
            return "wave10"
        if "evasive" in self.bundle.condition.split("_"):
            return "earlier_evasive"
        return "development" if self.wave <= 8 else "wave9"


@dataclass(frozen=True)
class Message:
    trial: str
    seq: int
    sender: str
    text: str

    @property
    def key(self) -> tuple[str, int]:
        return (self.trial, self.seq)

    def public_row(self) -> dict[str, str | int]:
        return {
            "trial": self.trial,
            "seq": self.seq,
            "sender": self.sender,
            "text": self.text,
        }


def supply_trials(runs: Path) -> Iterator[Trial]:
    runs = runs.resolve(strict=True)
    for root in sorted(runs.iterdir()):
        wave = WAVE_ROOT.fullmatch(root.name)
        if wave is None or not root.is_dir():
            continue
        # Include trials with world logs even if a failed run has no result.json.
        trial_dirs = set(discover_trial_dirs(root))
        for path in root.rglob("events.jsonl"):
            for relative in ("artifacts/logs/world", "artifacts/world", "world"):
                base = path.parents[len(Path(relative).parts)]
                if path.parent == base / relative:
                    trial_dirs.add(base)
                    break
        for path in sorted(trial_dirs):
            bundle = load_trial_bundle(path)
            if bundle.task_family == "supply-chain-sabotage":
                yield Trial(path.relative_to(runs).as_posix(), int(wave[1]), bundle)


def public_messages(trial: Trial) -> Iterator[Message]:
    for event in trial.bundle.world_events:
        if event.event_type == "chat_public" and event.is_public:
            text = event.payload["text"]
            if not isinstance(text, str):
                raise ValueError(
                    f"{trial.name}:{event.seq}: non-string public chat text"
                )
            yield Message(trial.name, event.seq, event.actor, text)


def annotation_rows(messages: list[Message]) -> tuple[list[Message], list[Message]]:
    candidates, other = [], []
    for message in messages:
        (candidates if CANDIDATE.search(message.text) else other).append(message)
    return candidates, random.Random(SAMPLE_SEED).sample(other, SAMPLE_SIZE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--subset", choices=("all", "labels"), default="all")
    args = parser.parse_args()
    messages = [
        message
        for trial in supply_trials(args.runs)
        for message in public_messages(trial)
    ]
    if args.subset == "labels":
        candidates, sample = annotation_rows(messages)
        messages = sorted(candidates + sample, key=lambda message: message.key)
    for message in messages:
        print(json.dumps(message.public_row(), ensure_ascii=False))


if __name__ == "__main__":
    main()
