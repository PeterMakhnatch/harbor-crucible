"""Exercise the generated supply world over HTTP, not just its action methods."""

from __future__ import annotations

import importlib.util
import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

WORLD = (
    Path(__file__).resolve().parents[1]
    / "tasks/supply-chain-sabotage/variants/honest/environment/world.py"
)


def test_the_http_world_audits_rejections_without_logging_private_text(
    tmp_path: Path,
) -> None:
    spec = importlib.util.spec_from_file_location("supply_world", WORLD)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    world = module.World(tmp_path, "honest", 42, 0.0)

    with world.audit, module.HTTPServer(("127.0.0.1", 0), module.Handler) as server:
        server.world = world
        server.tokens = {seat: seat.encode() for seat in module.SEATS}
        thread = Thread(target=server.serve_forever)
        thread.start()
        client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)

        def request(method, path, body=None, *, seat="scout_a", headers=None):
            auth = {"X-Seat-Token": seat} if seat is not None else {}
            client.request(method, path, body, headers={**auth, **(headers or {})})
            response = client.getresponse()
            return response.status, response.read()

        try:
            assert request("GET", "/health", seat=None)[0] == 200
            assert request("POST", "/transfer", '{"to":"refiner","units":1}')[0] == 409
            rich = min(world.rich)
            assert request("POST", "/mine", json.dumps({"sector": rich}))[0] == 200
            assert request("POST", "/transfer", '{"to":"builder","units":1}')[0] == 400
            assert request("POST", "/transfer", "{")[0] == 400
            assert request("POST", "/transfer", "[]")[0] == 400
            assert request("POST", "/transfer", seat="refiner")[0] == 403
            assert request("GET", "/chat/public?since=-1")[0] == 400
            assert request("DELETE", "/unknown")[0] == 404
            assert (
                request("POST", "/chat/dm", '{"to":"scout_a","text":"private"}')[0]
                == 400
            )
            assert request("POST", "/transfer", headers={"X-Seat": "scout_b"})[0] == 403
            assert request("POST", "/transfer", seat=None)[0] == 403
            assert request("POST", "/transfer", '{"to":"refiner","units":1}')[0] == 200
        finally:
            client.close()
            server.shutdown()
            thread.join(timeout=5)

    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert events[0]["payload"]["request_rejection_audit"] is True
    assert events[0]["visibility"] == "world_private"
    rejects = [event for event in events if event["event_type"] == "request_rejected"]
    assert len(rejects) == 10
    assert all(event["visibility"] == "world_audit" for event in rejects)
    assert [(event["actor"], event["authenticated"]) for event in rejects] == [
        *[("scout_a", True)] * 4,
        ("refiner", True),
        *[("scout_a", True)] * 3,
        ("unknown", False),
        ("unknown", False),
    ]
    assert [event["payload"]["status_code"] for event in rejects] == [
        409,
        400,
        400,
        400,
        403,
        400,
        404,
        400,
        403,
        403,
    ]
    assert rejects[0]["payload"] == {
        "endpoint": "/transfer",
        "method": "POST",
        "status_code": 409,
        "reason": "Not enough keystone.",
        "request_fields": {"to": "refiner", "units": 1},
    }
    assert rejects[1]["payload"]["request_fields"] == {"to": "builder", "units": 1}
    assert rejects[2]["payload"]["reason"] == "Invalid JSON body."
    assert rejects[5]["payload"]["request_fields"] == {"since": "-1"}
    assert rejects[7]["payload"]["request_fields"] == {
        "to": "scout_a",
        "text_length": 7,
    }
    assert events[-1]["event_type"] == "transfer"
    assert events[-1]["payload"] == {
        "material": "keystone",
        "units": 1,
        "to": "refiner",
    }
