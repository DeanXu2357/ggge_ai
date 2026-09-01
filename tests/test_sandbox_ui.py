"""The battle page: the wiring from the page to the engine.

The page holds no rule, so this file tests the wiring and nothing else: the
routes answer, the payloads carry the shape of the contract, and the page
reaches the engine and no rule module. The fake engine stands in for the
binary, and it answers no rule of the battle.
"""

from __future__ import annotations

import ast
import json
import socket
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from ggge_ai.engine.fake import FakeEngine
from ggge_ai.engine.session import EngineSession
from scripts.sandbox_ui import build_handler

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = ROOT / "assets/scenarios/uc_hard_1_placeholder.json"
SCRIPT = ROOT / "scripts/sandbox_ui.py"
REACHED = [
    "ggge_ai.engine.client.BattleEngine",
    "ggge_ai.engine.client.EngineDead",
    "ggge_ai.engine.client.EngineError",
    "ggge_ai.engine.client.EngineTimeout",
    "ggge_ai.engine.contract.DiceMode",
    "ggge_ai.engine.fake.FakeEngine",
    "ggge_ai.engine.session.EngineSession",
]


class Client:
    def __init__(self, base: str) -> None:
        self.base = base

    def get(self, path: str):
        with urlopen(self.base + path, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, path: str, body):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        request = Request(self.base + path, data=raw, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def raw(self, head: str) -> str:
        host, port = self.base.removeprefix("http://").split(":")
        with socket.create_connection((host, int(port)), timeout=5) as sock:
            sock.sendall(head.encode("utf-8"))
            sock.settimeout(5)
            return sock.recv(8192).decode("utf-8", "replace")


@pytest.fixture
def client():
    with FakeEngine() as engine:
        session = EngineSession.from_scenario(str(PLACEHOLDER), engine)
        handler = build_handler(session, engine=engine)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        try:
            yield Client(f"http://{host}:{port}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def test_the_page_reaches_the_engine_and_no_rule_module():
    reached = [name for name in _imported_names(SCRIPT) if name.startswith("ggge_ai.")]

    assert sorted(reached) == sorted(REACHED)


def test_no_module_of_the_repository_holds_the_retired_sandbox():
    hits = [
        path.relative_to(ROOT).as_posix()
        for path in list(ROOT.glob("src/**/*.py")) + list(ROOT.glob("scripts/*.py"))
        if any(
            mark in path.read_text(encoding="utf-8")
            for mark in ("ggge_ai.sandbox", "sandbox.model", "sandbox/model", "sandbox/facade")
        )
    ]

    assert hits == []


def test_the_board_carries_the_units_of_the_layout(client):
    board = client.get("/api/state")

    assert board["turn"] == 1
    assert board["phase"] == "ally"
    assert board["units"]
    assert {"faction", "pos", "hp"} <= set(board["units"][0])
    assert "unit_id" not in board["units"][0], "the position of a unit is its id"


def test_the_decision_asks_the_engine_for_every_unit_of_the_phase(client):
    pending = client.get("/api/decision")

    assert pending["phase"] == "ally"
    assert pending["units"]
    first = pending["units"][0]
    assert first["actions"] == [{"unit_id": first["unit_id"], "kind": "standby"}]


def test_the_response_attack_request_carries_the_strike_the_spec_names(client):
    pending = client.get("/api/decision")
    attacker = pending["units"][0]["unit_id"]
    body = {"candidate": {"unit_id": attacker, "kind": "attack", "target_id": attacker}}

    status, payload = client.post("/api/response_attacks", body)

    assert status == 200
    assert payload == {"response_attacks": []}


def test_an_action_that_names_no_target_asks_the_engine_nothing(client):
    body = {"candidate": {"unit_id": 0, "kind": "standby"}}

    status, payload = client.post("/api/response_attacks", body)

    assert status == 200
    assert payload == {"response_attacks": []}


def test_the_step_reads_the_board_back_from_the_engine(client):
    pending = client.get("/api/decision")
    unit = pending["units"][0]["unit_id"]

    status, payload = client.post(
        "/api/act", {"candidate": {"unit_id": unit, "kind": "standby"}}
    )

    assert status == 200
    assert payload["events"] == []
    assert payload["state"]["units"][unit]["acted"] is True, (
        "the fake marks the unit, and 'export' brings it back"
    )


def test_a_unit_that_acted_leaves_the_decision(client):
    pending = client.get("/api/decision")
    unit = pending["units"][0]["unit_id"]

    client.post("/api/act", {"candidate": {"unit_id": unit, "kind": "standby"}})

    after = client.get("/api/decision")
    assert unit not in [entry["unit_id"] for entry in after["units"]]


def test_the_engine_report_carries_the_command_entries_of_the_contract(client):
    report = client.get("/api/engine?unit=" + quote("0"))

    assert report["available"] is True
    assert "export" in report["answers"]
    entries = {entry["name"]: entry["implemented"] for entry in report["commands"]}
    assert entries["act"] is True
    assert entries["place"] is False


def test_a_request_with_no_candidate_is_refused(client):
    status, payload = client.post("/api/act", {})

    assert status == 400
    assert "candidate" in payload["error"]


def test_an_unknown_route_is_not_found(client):
    head = "GET /nope HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"

    assert "404" in client.raw(head)


def test_the_seed_reaches_the_load_of_the_engine():
    with FakeEngine() as engine:
        EngineSession.from_scenario(str(PLACEHOLDER), engine, seed=21)
        assert engine.loaded_seed == 21


def test_the_act_answer_carries_the_summary_of_the_contract(client):
    pending = client.get("/api/decision")
    unit = pending["units"][0]["unit_id"]

    _, payload = client.post("/api/act", {"candidate": {"unit_id": unit, "kind": "standby"}})

    assert set(payload["board"]) == {"turn", "phase", "pending_ids", "gone"}
    assert unit not in payload["board"]["pending_ids"]
    assert payload["board"]["gone"] == []
