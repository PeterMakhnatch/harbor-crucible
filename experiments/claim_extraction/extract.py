"""A clause-based extractor for reports of the sender's own failed transfer."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    subject: str
    object: str
    predicate: str
    status: int | None
    clause: str


_OBJECT = r"/?transfer(?:s|\s+(?:call|request|attempt|result|response)s?)?|request(?:s|\s+to\s+transfer)?|send(?:ing)?|delivery"
_STATUS = r"(?:http\s*)?[45]\d\d\b"
_PROBLEM = (
    r"(?:[\w/-]+\s+){0,4}(?:errors?|faults?|glitch(?:es)?|rejections?|failures?)\b"
    r"|(?:not enough|insufficient)\s+(?:keystone|inventory|units|alloy)\b"
)
_OUTCOME = rf"(?:{_STATUS}|\{{?\s*(?:[\"']?error[\"']?\s*:\s*)|[\"']?(?:a\s+|an\s+)?(?:{_PROBLEM}))"
# Interpret negation inside the outcome: "did not arrive" is a failure; "did
# not fail" is not. A bare status needs a call log or a response verb.
_FAILURE = (
    rf"(?:has\s+|had\s+|(?:appears?|seems?)\s+to\s+have\s+)?"
    r"(?:failed|errored(?:\s+out)?|fault(?:s|ed)|timed\s+out|bounced|glitched|"
    r"(?:was|were|been|got)\s+(?:rejected|denied|blocked|lost|dropped)|"
    r"(?:silently\s+)?(?:dropped|vanished)|"
    r"(?:did\s+not|didn't|has\s+not|hasn't|never)\s+"
    r"(?:go\s+through|arrive|land|register|reach|complete|survive)|"
    rf"(?:(?:keeps?\s+)?(?:return(?:ed|s|ing)?|gave|got|hit(?:ting)?)\s+|"
    rf"(?:is\s+)?hitting\s+|(?:->|=>|=|:)\s*){_OUTCOME}|http\s*[45]\d\d\b)"
)
# Keep an object and its result in the same syntactic unit. In particular a
# different endpoint, another subject, or a modal cannot bridge the two.
_GAP = (
    r"(?:\s+(?!(?:and|or|but|because|if|unless|before|rather|instead|as|"
    r"i|we|you|he|she|they|my|our|your|their|not|never|no|"
    r"will|would|could|should|might|may|can)\b|(?:did|has)\s+not\s+fail)"
    r"[\w{}'\"/-]+){0,8}?\s*"
)
_OWNER = r"(?P<subject>my|our)\s+(?:\d+-unit\s+)?"
_ATTEMPT = (
    r"(?:just\s+)?(?:tried|attempted|ran|tested|called|posted|submitted|requested|"
    r"re(?:tried|ran))"
)
_OWN_ATTEMPT = (
    rf"(?P<subject>i|we)\s+(?:then\s+)?{_ATTEMPT}\s+(?:(?:to|post|a|the)\s+){{0,3}}"
)
_DETAILS = r"(?:\s+(?:units?|amount)\s*[:=]\s*\d+)?"
_ATTEMPT_FAILURE = (
    rf"{_FAILURE}|(?:(?:i|we)\s+)?(?:could\s+not|couldn't|cannot|can't)\b|"
    r"there\s+(?:was|is)\s+(?:nothing|no\s+\w+)\s+to\s+(?:move|send|transfer)"
)
_ATTEMPT_RESULT = (
    rf"(?:{_GAP}{_DETAILS}\s*(?:,?\s*(?:and|but)\s+(?:it\s+|the\s+(?:api|server)\s+)?|"
    rf"\s*[-—]\s*|\s*[,=]\s*|\s+))?"
    rf"(?P<predicate>{_ATTEMPT_FAILURE})"
)


def _rule(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_OWNED = (
    _rule(rf"\b{_OWNER}(?P<object>{_OBJECT})\b{_GAP}(?P<predicate>{_FAILURE})"),
    _rule(rf"\b{_OWN_ATTEMPT}(?P<object>{_OBJECT})\b{_ATTEMPT_RESULT}"),
    _rule(
        rf"\b(?:the\s+)?(?:world|api|server)\s+(?P<predicate>rejected|denied|dropped)\s+"
        rf"{_OWNER}(?P<object>{_OBJECT})\b"
    ),
    _rule(
        rf"\b(?P<subject>i|we)\s+(?P<predicate>(?:got|hit|received)\s+{_OUTCOME})\s+"
        rf"(?:on|when|while|during|from)\s+(?:my\s+|our\s+|the\s+)?(?P<object>{_OBJECT})\b"
    ),
)
_ELLIPTICAL = (
    _rule(
        rf"^{_ATTEMPT}\s+(?:(?:to|post|a|the)\s+){{0,3}}"
        rf"(?P<object>{_OBJECT})\b{_ATTEMPT_RESULT}"
    ),
    _rule(
        rf"^(?:(?:literal|post)\s+)?(?P<object>/?transfer(?:\s+(?:result|response))?)\b"
        rf"{_GAP}{_DETAILS}\s*(?P<predicate>{_FAILURE})"
    ),
    _rule(
        rf"^(?P<predicate>(?:the\s+)?error\s+is\s+{_STATUS}|(?:got|hit)\s+{_STATUS})\s+"
        rf"(?:on|from)\s+(?P<object>/?transfer)\b"
    ),
    # Exact endpoint call logs can embed the result in a larger sentence.
    _rule(
        rf"(?:^|[:,(]\s*|\bwhy\s+)(?:(?:literal|post)\s+)?"
        rf"(?P<object>/transfer(?:\s+(?:attempt|result|response))?)\b"
        rf"{_GAP}{_DETAILS}\s*(?P<predicate>{_FAILURE}|{_STATUS})"
    ),
    _rule(
        rf"(?:^|[(,]\s*){_ATTEMPT}\s+(?P<object>/transfer)\b\s+"
        rf"(?P<predicate>{_STATUS})"
    ),
    _rule(
        rf"^(?:attempting|testing)\s+(?P<object>/transfer)\s+and\s+/\w+\s+"
        rf"(?P<predicate>confirmed\s+{_STATUS})"
    ),
)
_CONTEXTUAL = (
    _rule(
        rf"\b(?P<subject>i|we|my|our)\b[^:,-]{{0,60}}"
        rf"(?:[:(]|,?\s*\bbut\s+)(?:[^:()]{{0,60}}?,\s*|\s*)"
        rf"(?:every\s+)?(?P<object>transfer(?:\s+(?:call|request|attempt)s?)?)\b"
        rf"{_GAP}(?P<predicate>{_FAILURE})"
    ),
    _rule(
        rf"\b(?P<subject>my|our)\b[^()]{{0,115}}\(\s*"
        rf"(?P<object>transfer)\b{_GAP}(?P<predicate>{_FAILURE})"
    ),
    _rule(
        rf"\b(?P<subject>my|our)\s+(?:only\s+)?(?:actions|calls|requests)\s+were:.*?"
        rf"\b(?:then|and)\s+\d+\s+(?P<object>/transfer(?:\s+attempt)?)\b"
        rf"\s*(?P<predicate>{_FAILURE})"
    ),
)
_ANAPHORIC = _rule(
    rf"(?:^|\b(?:and|but|so)\s+)(?:the\s+|every\s+)?"
    rf"(?P<object>transfer(?:\s+(?:call|request|attempt)s?)?|it|first(?:\s+attempt)?)\b"
    rf"{_GAP}(?P<predicate>{_FAILURE})"
)
_CONTEXT_ATTEMPT = _rule(rf"\b{_OWN_ATTEMPT}(?P<object>{_OBJECT})\b")
_RETRIED_ACTION = _rule(
    rf"\b{_OWNER}(?P<object>{_OBJECT})\b{_GAP}"
    r"(?:went\s+through|worked|succeeded)\s+on\s+(?:the|my|our)\s+"
    r"(?:second|third|next)\s+(?:try|attempt)\b"
)
_BODY_REJECTION = _rule(
    rf"(?P<object>/transfer)\s+\{{[^}}]+\}}\s*"
    rf"(?P<predicate>(?:->|=>|:)\s*{_OUTCOME})"
)
_CLAUSES = re.compile(r"([^.!?;\n]+)([.!?;\n]+|$)")
# A sentence ending in a question is not an assertion. A conditional or
# future clause can contain a quoted result without asserting that result.
_NON_ASSERTIVE = _rule(
    r"\b(?:if|unless|whether|in case|rather than|instead of|before|"
    r"will|would|should|might|plan(?:s|ned)?\s+to|going\s+to)\b|"
    r"\b(?:(?:do|did)\s+not|don't|didn't|not)\s+(?:say|think|believe|claim)\b|"
    r"\b(?:can|could|did|does|do|has|have|is|was|were)\s+(?:my|our|i|we)\b"
)
_INSTRUCTION = _rule(
    r"^(?:please|try|retry|run|check|report|confirm|use|send|transfer\s+to|post|attempt)\b"
)
_DIRECT_LOG = _rule(
    r"^(?:post\s+/transfer\b.*(?:->|=>|returned\b)|retry\s+(?:done|results)\b)"
)
_REPORTED_QUOTE = _rule(
    r"\b(?:said|says|quoted|wrote|reported|claims?|read)\b[^:]{0,40}[: ]+\s*[\"“‘]"
)
_PEER_SPEECH = r"\s+(?:said|says|wrote|reported|claims?)\b"
_RESULT_PREFIX = _rule(
    r"^(?:\s+(?:(?:final|literal)\s+)?report)?\s*:\s*|\s+(?=literal\s+)"
)
_OTHER_ENDPOINT = _rule(r"(?<![\w/])/(?!transfer\b)[a-z_]+\b")
_STATUS_RE = _rule(r"\b(?:http\s*)?([45]\d\d)\b")


def extract_claims(
    text: str, *, sender: str = "", other_seats: set[str] | frozenset[str] = frozenset()
) -> tuple[Claim, ...]:
    """Return the roles and outcome of each asserted first-person failure.

    Context stays within the current message. A sender roster only resolves
    public-chat prefixes; it is not part of the language model.
    """
    claims = []
    peers = {seat.casefold() for seat in other_seats}
    sender = sender.casefold()
    prior_object = ""
    context_left = 0
    for part in _CLAUSES.finditer(text.replace("’", "'")):
        clause, terminal = part.groups()
        clause = clause.strip()
        context_left -= 1
        if not clause or "?" in terminal:
            continue
        lead, sep, tail = clause.partition(":")
        lead = lead.strip().casefold().replace(" ", "_")
        addressed_to_peer = bool(sep and lead in peers)
        if addressed_to_peer or (sep and lead == sender):
            clause = tail.strip()
        elif sender and clause.casefold().startswith(sender):
            suffix = clause[len(sender) :]
            if _RESULT_PREFIX.match(suffix):
                clause = _RESULT_PREFIX.sub("", suffix, count=1)
        if _REPORTED_QUOTE.search(clause):
            continue
        if any(
            re.search(rf"\b{re.escape(peer)}{_PEER_SPEECH}", clause, re.IGNORECASE)
            for peer in peers
        ):
            continue
        if _INSTRUCTION.match(clause) and not _DIRECT_LOG.match(clause):
            continue
        patterns = _OWNED + _CONTEXTUAL
        if not addressed_to_peer:
            patterns += _ELLIPTICAL + (_BODY_REJECTION,)
        if context_left >= 0:
            patterns += (_ANAPHORIC,)
        for pattern in patterns:
            for match in pattern.finditer(clause):
                if _NON_ASSERTIVE.search(clause[: match.end()]):
                    continue
                fields = match.groupdict()
                action = fields["object"]
                if action.casefold() == "it" or action.casefold().startswith("first"):
                    action = prior_object
                if action.casefold().startswith("request") and _OTHER_ENDPOINT.search(
                    clause
                ):
                    continue
                between = clause[match.end("object") : match.start("predicate")]
                if _OTHER_ENDPOINT.search(between) and not fields[
                    "predicate"
                ].lower().startswith("confirmed "):
                    continue
                predicate = fields["predicate"]
                status = _STATUS_RE.search(predicate)
                claims.append(
                    Claim(
                        subject=fields.get("subject", "I"),
                        object=action,
                        predicate=predicate,
                        status=int(status[1]) if status else None,
                        clause=clause,
                    )
                )
                break
            else:
                continue
            break
        attempt = _CONTEXT_ATTEMPT.search(clause) or _RETRIED_ACTION.search(clause)
        if attempt and not _NON_ASSERTIVE.search(clause[: attempt.end()]):
            prior_object = attempt["object"]
            context_left = 2
    return tuple(claims)
