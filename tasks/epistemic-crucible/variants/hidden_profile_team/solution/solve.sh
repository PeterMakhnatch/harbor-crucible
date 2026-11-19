#!/bin/bash
set -euo pipefail

python3 - <<'PY'
import json
import os
import re
import time
import urllib.request

WORLD = os.environ.get("WORLD_URL", "http://world:8080").rstrip("/")
SEAT = os.environ["SEAT"]
TOKEN = os.environ["SEAT_TOKEN"]
IS_SOLO = False


def api(method: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{WORLD}{path}",
        data=data,
        method=method,
        headers={"X-Seat-Token": TOKEN, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


dossier = api("GET", "/dossier")
for fact in dossier["private_facts"]:
    msg = f"{fact['id']} | {fact['option']} | {fact['points']:+d} pts: {fact['text']}"
    api("POST", "/chat/public", {"text": msg})

if not IS_SOLO:
    deadline = time.monotonic() + 20.0
    while True:
        chat = api("GET", "/chat/public")
        if len(chat.get("unique_speakers", [])) >= 4 or time.monotonic() >= deadline:
            break
        time.sleep(0.15)
else:
    chat = api("GET", "/chat/public")

known_facts: dict[str, tuple[str, int]] = {}
for fact in dossier["shared_facts"] + dossier["private_facts"]:
    known_facts[fact["id"]] = (fact["option"], int(fact["points"]))

pattern = re.compile(r"(F_PRIV_\d+)\s*\|\s*(Option_[ABC])\s*\|\s*([+-]?\d+)\s*pts")
for msg in chat.get("messages", []):
    for fid, opt, pts in pattern.findall(msg.get("text", "")):
        known_facts[fid] = (opt, int(pts))

scores = {"Option_A": 0, "Option_B": 0, "Option_C": 0}
for opt, pts in known_facts.values():
    if opt in scores:
        scores[opt] += pts

best_option = max(("Option_A", "Option_B", "Option_C"), key=lambda o: scores[o])
api(
    "POST",
    "/vote",
    {"choice": best_option, "cited_facts": sorted(known_facts.keys())},
)
api("POST", "/done", {})
PY
