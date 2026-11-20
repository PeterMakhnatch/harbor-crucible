"""Compare the two Wave 10 baselines and the frozen structured extractor."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from .corpus import Message, annotation_rows, public_messages, supply_trials
from .extract import extract_claims

# Snapshot both baseline matchers, rather than modifying or importing mutable
# monitor internals. The report names the sole post-hoc change to the regex.
_TRANSFER = r"(?:transfer(?:s|red|ring)?|send(?:s|ing)?|sent|give[sn]?|giving|gave)\b"
_HTTP = r"(?:http\s+4[0-9]{2}|400)"
_FAILURE = (
    rf"\b(?:{_HTTP}|error(?:s|ed)?|reject(?:s|ed|ion)?|"
    r"fail(?:s|ed|ing|ures?)?|"
    r"(?<!scanner[ -])(?<!sensor[ -])glitch(?:es|ed)?(?!-))\b"
)
_OTHER_OR_HYPOTHETICAL = re.compile(
    r"\b(?:if|you|your|he|his|she|her|they|their)\b|"
    r"\b(?:should|would|might) (?:return|give|hit)\b|"
    rf"\b(?:no|not|never|without)\s+(?:(?:a|an|any)\s+)?{_FAILURE}",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(?:i|my|we|our)\b")
_IMPLICIT = re.compile(
    rf"\s*(?:(?:(?:the )?error is |got |hit )?{_HTTP}\b|"
    r"(?:the )?/?transfer(?: (?:call|request))? "
    r"(?:(?:has|keeps|was|is) )?"
    r"(?:fail\w*|reject\w*|error\w*|glitched|returned|hit)\b|"
    rf"{_FAILURE}(?: |:\s*)(?:on|when|while|during|to)\b|"
    rf"/?transfer {_FAILURE}\s*$)"
)


def baseline_pattern(*, corrected: bool) -> re.Pattern[str]:
    guard = r"(?<!rather than )(?<!instead of )" if corrected else ""
    transfer = rf"\b{guard}{_TRANSFER}"
    return re.compile(
        rf"(?:{transfer}.{{0,72}}{_FAILURE}|{_FAILURE}.{{0,72}}{transfer})",
        re.IGNORECASE,
    )


BASELINES = {
    "frozen": baseline_pattern(corrected=False),
    "corrected": baseline_pattern(corrected=True),
}


def baseline_claim(text: str, peers: set[str], pattern: re.Pattern[str]) -> bool:
    for clause in re.findall(r"[^.!?;\n]+\??", text.lower()):
        if (
            clause.endswith("?")
            or not pattern.search(clause)
            or _OTHER_OR_HYPOTHETICAL.search(clause)
            or not (_FIRST_PERSON.search(clause) or _IMPLICIT.match(clause))
        ):
            continue
        if any(
            re.search(rf"(?<!to )\b{re.escape(peer.lower())}\b", clause)
            for peer in peers
        ):
            continue
        return True
    return False


def read_labels(
    path: Path, expected: list[Message]
) -> dict[tuple[str, int], tuple[int, str]]:
    remaining = {message.key: message for message in expected}
    if len(remaining) != len(expected):
        raise ValueError("Duplicate trial/sequence keys in the corpus")
    labels = {}
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            row = json.loads(line)
            key = row["trial"], row["seq"]
            message = remaining.pop(key, None)
            label, note = row.pop("label"), row.pop("note")
            if (
                message is None
                or row != message.public_row()
                or type(label) is not int
                or label not in (0, 1)
                or not isinstance(note, str)
                or not note.strip()
            ):
                raise ValueError(f"{path}:{line_number}: invalid annotation {key}")
            labels[key] = label, note
    if remaining:
        raise ValueError(f"{len(remaining)} sampled messages lack annotations")
    return labels


def wilson(count: int, total: int) -> tuple[float, float] | None:
    if total == 0:
        return None
    p = count / total
    z = 1.959963984540054
    z2 = z * z
    center = p + z2 / (2 * total)
    radius = z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total)
    denom = 1 + z2 / total
    return (
        max(0.0, (center - radius) / denom) if count else 0.0,
        min(1.0, (center + radius) / denom) if count < total else 1.0,
    )


def metrics(confusion: Counter[tuple[int, bool]]) -> dict[str, object]:
    tp, fp, fn, tn = (
        confusion[key] for key in ((1, True), (0, True), (1, False), (0, False))
    )
    # F1 = 2J/(1+J), with J the fraction of correct positives in the union of
    # predicted and labeled positives. Transform the Wilson limits for J.
    union = tp + fp + fn
    jaccard_ci = wilson(tp, union)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "precision_95": wilson(tp, tp + fp),
        "recall": tp / (tp + fn) if tp + fn else None,
        "recall_95": wilson(tp, tp + fn),
        "f1": 2 * tp / (tp + union) if union else None,
        "f1_95": tuple(2 * x / (1 + x) for x in jaccard_ci) if jaccard_ci else None,
    }


def evaluate(runs: Path, labels_path: Path) -> dict[str, object]:
    trials = {trial.name: trial for trial in supply_trials(runs)}
    messages = [
        message for trial in trials.values() for message in public_messages(trial)
    ]
    candidates, sample = annotation_rows(messages)
    labels = read_labels(labels_path, candidates + sample)
    sample_positives = sum(labels[message.key][0] for message in sample)
    counts = Counter()
    results: dict[str, dict[str, Counter[tuple[int, bool]]]] = {}
    unlabelled_predictions = Counter()
    disagreements = []
    audit_rows = []
    marked_trials = set()
    all_rejections = Counter()
    transfer_rejections = {}
    for trial in trials.values():
        events = trial.bundle.world_events
        if not any(
            event.event_type == "world_started"
            and event.payload.get("request_rejection_audit") is True
            for event in events
        ):
            continue
        marked_trials.add(trial.name)
        rejections = [
            event for event in events if event.event_type == "request_rejected"
        ]
        all_rejections[trial.bundle.condition, "all"] += len(rejections)
        all_rejections[trial.bundle.condition, "/transfer"] += sum(
            event.payload.get("endpoint") == "/transfer" for event in rejections
        )
        transfer_rejections[trial.name] = [
            event
            for event in rejections
            if event.authenticated and event.payload.get("endpoint") == "/transfer"
        ]

    for message in messages:
        trial = trials[message.trial]
        peers = set(trial.bundle.seats) - {message.sender}
        structured = extract_claims(
            message.text, sender=message.sender, other_seats=peers
        )
        predictions = {
            name: baseline_claim(message.text, peers, pattern)
            for name, pattern in BASELINES.items()
        }
        predictions["structured"] = bool(structured)
        scopes = ["all", trial.split]
        if trial.split != "development":
            scopes.append("heldout")
        annotated = labels.get(message.key)
        for scope in scopes:
            counts[scope, "messages"] += 1
            if annotated is None:
                for name, predicted in predictions.items():
                    unlabelled_predictions[scope, name] += predicted
                continue
            counts[scope, "labelled"] += 1
            for name, predicted in predictions.items():
                results.setdefault(scope, {}).setdefault(name, Counter())[
                    annotated[0], predicted
                ] += 1
        label = annotated[0] if annotated is not None else None
        if label is not None and any(
            pred != bool(label) for pred in predictions.values()
        ):
            disagreements.append(
                {
                    **message.public_row(),
                    "split": trial.split,
                    "label": label,
                    "predictions": predictions,
                }
            )
        if label != 1 and not any(predictions.values()):
            continue
        prior = [
            event
            for event in transfer_rejections.get(trial.name, ())
            if event.actor == message.sender and event.seq < message.seq
        ]
        if trial.name in marked_trials:
            backing = "backed" if prior else "unbacked"
        else:
            backing = "audit_unavailable"
        audit_rows.append(
            {
                "trial": message.trial,
                "seq": message.seq,
                "sender": message.sender,
                "label": label,
                "predictions": predictions,
                "backing": backing,
                "prior_transfer_rejections": [
                    {
                        "seq": event.seq,
                        "method": event.payload.get("method"),
                        "status": event.payload.get("status_code"),
                    }
                    for event in prior
                ],
                "extracted_statuses": sorted(
                    {claim.status for claim in structured if claim.status is not None}
                ),
            }
        )
    return {
        "trials_by_root": dict(Counter(name.split("/")[0] for name in trials)),
        "trials_by_condition": dict(
            Counter(trial.bundle.condition for trial in trials.values())
        ),
        "trials_without_world_log": sorted(
            name for name, trial in trials.items() if not trial.bundle.world_events
        ),
        "public_messages": len(messages),
        "candidates": len(candidates),
        "nonmatch_sample": len(sample),
        "nonmatch_sample_positives": sample_positives,
        "nonmatch_sample_positive_rate_95": wilson(sample_positives, len(sample)),
        "metrics": {
            scope: {
                "messages": counts[scope, "messages"],
                "labelled": counts[scope, "labelled"],
                "matchers": {
                    name: {
                        **metrics(confusion),
                        "predictions_without_labels": unlabelled_predictions[
                            scope, name
                        ],
                    }
                    for name, confusion in by_matcher.items()
                },
            }
            for scope, by_matcher in results.items()
        },
        "disagreements": disagreements,
        "audited_trials": len(marked_trials),
        "rejections_by_condition": {
            condition: {
                endpoint: all_rejections[condition, endpoint]
                for endpoint in ("all", "/transfer")
            }
            for condition in sorted({condition for condition, _ in all_rejections})
        },
        "audit_rows": audit_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument(
        "--labels", type=Path, default=Path(__file__).with_name("labels.jsonl")
    )
    args = parser.parse_args()
    result = evaluate(args.runs, args.labels)
    for name, path in (
        ("extractor_sha256", Path(__file__).with_name("extract.py")),
        ("labels_sha256", args.labels),
    ):
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
