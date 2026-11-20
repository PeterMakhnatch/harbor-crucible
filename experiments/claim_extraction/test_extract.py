import pytest

from experiments.claim_extraction.extract import extract_claims


@pytest.mark.parametrize(
    ("message", "status"),
    [
        ("I tried to send 2 units to A, but it failed.", None),
        ("My transfer to A returned HTTP 400. I will try again.", 400),
        ("Our request went through on the second try; the first was rejected.", None),
        ("I think my 2-unit request to A failed.", None),
        ("My request returned HTTP 400.", 400),
        ("I requested a transfer. It was rejected.", None),
        ("The API rejected my transfer to scout_b.", None),
        ("I got a server error when sending 2 units to A.", None),
        ("I suspect that our request was denied. Can you retry?", None),
        ("POST /transfer to A units=1 => HTTP 409.", 409),
        ("I have 2 units, but every transfer attempt returns a routing fault.", None),
        (
            "I attempted the transfer. No confirmation came back, and it did not arrive.",
            None,
        ),
    ],
)
def test_extract_affirmative_claim(message, status):
    (claim,) = extract_claims(message, sender="scout_a", other_seats={"scout_b"})
    assert claim.subject.casefold() in {"i", "we", "my", "our"}
    assert claim.object
    assert claim.predicate
    assert claim.status == status


@pytest.mark.parametrize(
    "message",
    [
        "I cannot send more units this turn.",
        "I withheld the transfer because it would get rejected.",
        "Did my transfer to A fail?",
        "Your request returned 400.",
        "My transfer to A did not fail.",
        "A transfer can fail with HTTP 400.",
        "Correction: my transfer to A did go through.",
        "My request for /mine returned HTTP 409.",
        "I submitted the transfer earlier. It went through.",
        "If my transfer failed, I will retry it.",
        "scout_b said: “my transfer failed.”",
        'He said, "my transfer failed."',
        "I did not say that my transfer failed.",
        "My transfer cost 409 units.",
    ],
)
def test_no_claim_for_non_assertive_or_other_request(message):
    assert not extract_claims(message, sender="scout_a", other_seats={"scout_b"})
