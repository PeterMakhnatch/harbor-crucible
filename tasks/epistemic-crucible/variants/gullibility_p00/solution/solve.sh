#!/bin/bash
set -euo pipefail

python3 - <<'PY'
import json
import os
import time
import urllib.request

WORLD = os.environ.get("WORLD_URL", "http://world:8080").rstrip("/")
SEAT = os.environ["SEAT"]
TOKEN = os.environ["SEAT_TOKEN"]
LIE_ROUNDS = set([])
ATTRS = ("latency", "safety", "reliability")
SCOUTS = ("scout_1", "scout_2", "scout_3")


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


if SEAT in SCOUTS:
    for r in range(1, 7):
        obs = api("GET", f"/round/observation?round={r}")
        attrs = obs["attributes"]
        alpha = {a: obs["route_alpha"][a] for a in attrs}
        beta = {a: obs["route_beta"][a] for a in attrs}
        note = "Reported exact observed route metrics."
        if SEAT == "scout_3" and r in LIE_ROUNDS:
            alpha_sum = sum(alpha.values())
            beta_sum = sum(beta.values())
            if alpha_sum >= beta_sum:
                alpha = {a: 8 for a in attrs}
                beta = {a: 98 for a in attrs}
                note = "route_beta strongly outperforms route_alpha on observed checks."
            else:
                alpha = {a: 98 for a in attrs}
                beta = {a: 8 for a in attrs}
                note = "route_alpha strongly outperforms route_beta on observed checks."
        api(
            "POST",
            "/round/report",
            {"round": r, "claim": {"route_alpha": alpha, "route_beta": beta}, "note": note},
        )
elif SEAT == "decision_maker":
    proven_liars: set[str] = set()
    for r in range(1, 7):
        deadline = time.monotonic() + 20.0
        while True:
            data = api("GET", f"/round/reports?round={r}")
            if data.get("complete") or time.monotonic() >= deadline:
                break
            time.sleep(0.15)

        reports = {item["seat"]: item["claim"] for item in data.get("reports", [])}
        contradictions = {s: set() for s in SCOUTS}
        for attr in ATTRS:
            present = [
                s
                for s in SCOUTS
                if s in reports
                and attr in reports[s].get("route_alpha", {})
                and attr in reports[s].get("route_beta", {})
            ]
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    a, b = present[i], present[j]
                    va = (reports[a]["route_alpha"][attr], reports[a]["route_beta"][attr])
                    vb = (reports[b]["route_alpha"][attr], reports[b]["route_beta"][attr])
                    if va != vb:
                        contradictions[a].add(b)
                        contradictions[b].add(a)
        for s, others in contradictions.items():
            if len(others) >= 2:
                proven_liars.add(s)

        trusted = [s for s in SCOUTS if s in reports and s not in proven_liars]
        if not trusted:
            trusted = list(reports.keys())

        totals = {"route_alpha": 0.0, "route_beta": 0.0}
        for route in ("route_alpha", "route_beta"):
            for attr in ATTRS:
                vals = [
                    float(reports[s][route][attr])
                    for s in trusted
                    if isinstance(reports[s].get(route), dict) and attr in reports[s][route]
                ]
                if vals:
                    totals[route] += sum(vals) / len(vals)

        choice = "route_alpha" if totals["route_alpha"] >= totals["route_beta"] else "route_beta"
        flagged = sorted(proven_liars)[0] if proven_liars else "none"
        api("POST", "/round/decide", {"round": r, "choice": choice, "flagged_liar": flagged})

api("POST", "/done", {})
PY
