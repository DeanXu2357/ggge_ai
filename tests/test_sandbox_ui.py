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
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from ggge_ai.engine.client import BattleEngine
from ggge_ai.engine.contract import Faction
from ggge_ai.engine.fake import FakeEngine
from ggge_ai.engine.session import EngineSession
from ggge_ai.engine.state import BattleState, Unit, Weapon
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
    assert {"unit_id", "faction", "pos", "hp"} <= set(board["units"][0])


def test_the_decision_asks_the_engine_for_every_unit_of_the_phase(client):
    pending = client.get("/api/decision")

    assert pending["phase"] == "ally"
    assert pending["units"]
    first = pending["units"][0]
    assert first["actions"] == [{"unit_id": first["unit_id"], "kind": "standby"}]


def test_the_reaction_request_carries_the_strike_the_spec_names(client):
    pending = client.get("/api/decision")
    attacker = pending["units"][0]["unit_id"]
    body = {"candidate": {"unit_id": attacker, "kind": "attack", "target_id": attacker}}

    status, payload = client.post("/api/reactions", body)

    assert status == 200
    assert payload == {"reactions": []}


def test_an_action_that_names_no_target_asks_the_engine_nothing(client):
    body = {"candidate": {"unit_id": "x", "kind": "standby"}}

    status, payload = client.post("/api/reactions", body)

    assert status == 200
    assert payload == {"reactions": []}


def test_the_step_reads_the_board_back_from_the_engine(client):
    pending = client.get("/api/decision")
    unit = pending["units"][0]["unit_id"]

    status, payload = client.post(
        "/api/act", {"candidate": {"unit_id": unit, "kind": "standby"}}
    )

    assert status == 200
    assert payload["events"] == []
    acted = {entry["unit_id"]: entry["acted"] for entry in payload["state"]["units"]}
    assert acted[unit] is True, "the fake marks the unit, and 'export' brings it back"


def test_a_unit_that_acted_leaves_the_decision(client):
    pending = client.get("/api/decision")
    unit = pending["units"][0]["unit_id"]

    client.post("/api/act", {"candidate": {"unit_id": unit, "kind": "standby"}})

    after = client.get("/api/decision")
    assert unit not in [entry["unit_id"] for entry in after["units"]]


def test_the_engine_report_carries_the_command_entries_of_the_contract(client):
    report = client.get("/api/engine?unit=" + quote("x"))

    assert report["available"] is True
    assert "load" in report["answers"]
    entries = {entry["name"]: entry["implemented"] for entry in report["commands"]}
    assert entries["act"] is True
    assert entries["certify"] is False


def test_a_request_with_no_candidate_is_refused(client):
    status, payload = client.post("/api/act", {})

    assert status == 400
    assert "candidate" in payload["error"]


def test_an_unknown_route_is_not_found(client):
    head = "GET /nope HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"

    assert "404" in client.raw(head)


def _duel() -> BattleState:
    """Two units in one row that can reach each other, and one ally with no weapon.

    The accuracy of the weapon leaves room for both outcomes of a draw, so a
    sampled battle reads the random source of the engine at every strike.
    """
    beam = Weapon(name="beam rifle", power=1800.0, range_min=1, range_max=3, en_cost=10,
                  accuracy=70.0)
    panel = {
        "hp": 12000,
        "max_hp": 12000,
        "en": 140,
        "en_max": 140,
        "unit_attack": 4200.0,
        "unit_defense": 3900.0,
        "pilot_attack": 220.0,
        "pilot_defense": 190.0,
        "reaction": 205.0,
        "mobility": 310.0,
    }
    return BattleState(
        units=[
            Unit(unit_id="a1", faction=Faction.ALLY, pos=(0, 0), weapons=[beam], **panel),
            Unit(unit_id="a2", faction=Faction.ALLY, pos=(1, 0), **panel),
            Unit(unit_id="e1", faction=Faction.ENEMY, pos=(3, 0), weapons=[beam], **panel),
        ],
        phase=Faction.ALLY,
        turn=1,
        bounds=((0, 0), (6, 6)),
    )


@contextmanager
def _page(engine_executable, seed: int):
    with BattleEngine(engine_executable) as engine:
        session = EngineSession(engine, _duel(), seed=seed)
        server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(session, engine=engine))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        try:
            yield Client(f"http://{host}:{port}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def _living(state) -> set[str]:
    return {entry["faction"] for entry in state["units"] if entry["hp"] > 0}


def _play(client) -> list:
    """Play the board until one side is gone, one activation at a time.

    The engine reads no victory condition yet, so the caller holds the end of
    the battle.
    """
    log = []
    for _ in range(200):
        pending = client.get("/api/decision")
        if not pending["units"]:
            return log
        entry = pending["units"][0]
        candidate = entry["actions"][0]
        options = client.post("/api/reactions", {"candidate": candidate})[1]["reactions"]
        body = {"candidate": candidate, "reaction": options[-1] if options else None}
        status, payload = client.post("/api/act", body)
        assert status == 200, payload
        log.append(payload["events"])
        if len(_living(payload["state"])) < 2:
            return log
    raise AssertionError("the battle ran past 200 activations")


def test_the_page_plays_a_battle_end_to_end_through_the_engine(engine_executable):
    with _page(engine_executable, 42) as client:
        log = _play(client)
        end = client.get("/api/state")

    assert len(log) >= 4, log
    assert end["turn"] > 1, "the battle crossed at least one turn boundary"
    assert len(_living(end)) == 1, "one side is gone"
    assert any(
        event["kind"] == "phase" for events in log for event in events
    ), "the answer of the engine names the phase boundaries it crossed"


def test_one_seed_gives_one_battle(engine_executable):
    with _page(engine_executable, 42) as client:
        first = _play(client)
    with _page(engine_executable, 42) as client:
        second = _play(client)
    with _page(engine_executable, 43) as client:
        other = _play(client)

    assert first == second
    assert first != other
