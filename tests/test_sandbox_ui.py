"""沙盤網頁介面：腳本只准碰門面，操作端點走真的 HTTP 打一輪我方階段。"""

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

from ggge_ai.engine.client import BattleEngine
from ggge_ai.engine.contract import PROTOCOL_VERSION
from ggge_ai.sandbox.facade import Sandbox
from scripts.sandbox_ui import build_handler

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = ROOT / "assets/scenarios/uc_hard_1_placeholder.json"
SCRIPT = ROOT / "scripts/sandbox_ui.py"
REACHED = [
    "ggge_ai.engine.client.BattleEngine",
    "ggge_ai.engine.client.EngineDead",
    "ggge_ai.engine.client.EngineError",
    "ggge_ai.engine.client.EngineTimeout",
    "ggge_ai.sandbox.facade.Sandbox",
]


class Client:
    def __init__(self, base: str) -> None:
        self.base = base

    def get(self, path: str):
        with urlopen(self.base + path, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, path: str, body):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        request = Request(
            self.base + path, data=raw, headers={"Content-Type": "application/json"}
        )
        try:
            with urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def act(self, candidate, reaction=None, draw=False):
        status, payload = self.post(
            "/api/act", {"candidate": candidate, "reaction": reaction, "draw": draw}
        )
        assert status == 200, payload
        return payload

    def reactions(self, candidate):
        status, payload = self.post("/api/reactions", {"candidate": candidate})
        assert status == 200, payload
        return payload

    def raw(self, head: str) -> str:
        host, port = self.base.removeprefix("http://").split(":")
        with socket.create_connection((host, int(port)), timeout=5) as sock:
            sock.sendall(head.encode("utf-8"))
            sock.settimeout(5)
            return sock.recv(8192).decode("utf-8", "replace")


def _serve(engine=None):
    sandbox = Sandbox.from_scenario(PLACEHOLDER)
    handler = build_handler(sandbox, seed=7, engine=engine)
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


@pytest.fixture
def client():
    yield from _serve()


@pytest.fixture
def engine_client(engine_executable):
    with BattleEngine(engine_executable) as engine:
        yield from _serve(engine)


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def _hp(snapshot, uid):
    return next((unit["hp"] for unit in snapshot["units"] if unit["uid"] == uid), 0)


def _acted(snapshot, uid):
    return next(unit["acted"] for unit in snapshot["units"] if unit["uid"] == uid)


def _first(entry, kind):
    return next((c for c in entry["candidates"] if c["kind"] == kind), None)


def _defend(payload):
    return next(
        option
        for option in payload["options"]
        if option["stance"] == "defend" and not option["support_defend"]
    )


def _reaction(option):
    return {key: option[key] for key in ("stance", "weapon", "support_defend", "support_attack")}


def test_the_script_reaches_the_sandbox_through_the_facade_and_the_engine_through_its_client():
    reached = [name for name in _imported_names(SCRIPT) if name.startswith("ggge_ai")]

    assert sorted(reached) == REACHED


def test_server_answers_the_state_endpoint(client):
    payload = client.get("/api/state")
    page = None
    with urlopen(client.base + "/", timeout=5) as response:
        page = response.read().decode("utf-8")

    assert payload["stage"] == "UC HARD 1"
    assert len(payload["units"]) == 28
    assert page.startswith("<!doctype html>")


def test_decision_endpoint_serves_the_pending_activations(client):
    payload = client.get("/api/decision")

    assert payload["kind"] == "activation"
    assert (payload["turn"], payload["phase"]) == (1, "ally")
    assert len(payload["units"]) == 10
    assert payload["advice"] is None


def test_play_mode_walks_a_full_ally_phase(client):
    decision = client.get("/api/decision")
    engagements = 0
    struck = []

    while decision["phase"] == "ally" and decision["units"]:
        entry = decision["units"][0]
        shot = _first(entry, "attack")
        if shot is not None and engagements < 2:
            option = _defend(client.reactions(shot))
            landed = engagements == 0
            before = _hp(client.get("/api/state"), shot["target_id"])
            payload = client.act(
                {**shot, "hit": landed, "support_hit": landed},
                _reaction(option),
            )
            struck.append((before, _hp(payload["state"], shot["target_id"])))
            assert payload["dice"]["hit"] is landed
            engagements += 1
        else:
            payload = client.act(_first(entry, "standby"))
            assert payload["dice"] == {"hit": None, "counter_hit": None, "support_hit": None}

        assert _acted(payload["state"], entry["uid"])
        assert entry["uid"] not in [rest["uid"] for rest in payload["pending"]["units"]]
        decision = payload["pending"]

    hit_pair, miss_pair = struck
    assert hit_pair[1] < hit_pair[0]
    assert miss_pair[1] == miss_pair[0]
    assert engagements == 2
    assert decision["phase"] == "enemy"
    assert client.get("/api/state")["phase"] == "enemy"


def test_server_draw_fills_the_hit_die(client):
    entry = client.get("/api/decision")["units"][0]
    shot = _first(entry, "attack")
    option = _defend(client.reactions(shot))

    payload = client.act(shot, _reaction(option), draw=True)

    assert isinstance(payload["dice"]["hit"], bool)
    assert payload["dice"]["counter_hit"] is None


def test_an_illegal_act_answers_four_hundred(client):
    entry = client.get("/api/decision")["units"][0]
    wait = _first(entry, "standby")
    client.act(wait)

    status, payload = client.post("/api/act", {"candidate": wait})

    assert status == 400
    assert "not in the current legal list" in payload["error"]


def test_an_illegal_reaction_answers_four_hundred(client):
    entry = client.get("/api/decision")["units"][0]
    shot = _first(entry, "attack")

    status, payload = client.post(
        "/api/act", {"candidate": shot, "reaction": {"stance": "sidestep"}}
    )

    assert status == 400
    assert "Illegal reaction stance" in payload["error"]


def test_a_malformed_body_answers_four_hundred(client):
    entry = client.get("/api/decision")["units"][0]

    broken = client.post("/api/act", b"{not json")
    bare = client.post("/api/act", {"reaction": {"stance": "none"}})
    cell = client.post(
        "/api/act", {"candidate": {"kind": "reposition", "unit_id": entry["uid"],
                                   "move_to": [1, 2, 3]}}
    )

    assert broken[0] == 400 and "JSON" in broken[1]["error"]
    assert bare[0] == 400 and "candidate" in bare[1]["error"]
    assert cell[0] == 400 and "A cell must be" in cell[1]["error"]


def test_a_body_that_would_raise_a_type_error_answers_four_hundred(client):
    entry = client.get("/api/decision")["units"][0]
    shot = _first(entry, "attack")

    axis = client.post("/api/act", {"candidate": {**shot, "move_to": [None, 0]}})
    unhashable = client.post("/api/act", {"candidate": {**shot, "target_id": [shot["target_id"]]}})

    assert axis[0] == 400 and "must be integers" in axis[1]["error"]
    assert unhashable[0] == 400 and "must be a scalar" in unhashable[1]["error"]


def test_a_body_length_outside_the_bounds_answers_four_hundred(client):
    head = "POST /api/act HTTP/1.1\r\nHost: sandbox\r\nContent-Length: {}\r\n\r\n"

    negative = client.raw(head.format(-1))
    oversized = client.raw(head.format(1 << 30))

    assert "400" in negative.splitlines()[0] and "Content-Length" in negative
    assert "400" in oversized.splitlines()[0] and "Content-Length" in oversized


def test_the_server_draw_reads_a_candidate_the_facade_would_accept(client):
    decision = client.get("/api/decision")
    shot = next(
        candidate
        for entry in decision["units"]
        for candidate in entry["candidates"]
        if candidate["kind"] == "attack" and candidate["move_to"] is not None
    )
    loose = {**shot, "move_to": [str(axis) for axis in shot["move_to"]]}

    payload = client.act(loose, None, draw=True)

    assert isinstance(payload["dice"]["hit"], bool)


def test_reactions_endpoint_rejects_a_candidate_without_an_engagement(client):
    entry = client.get("/api/decision")["units"][0]

    status, payload = client.post("/api/reactions", {"candidate": _first(entry, "standby")})

    assert status == 400
    assert "Only an attack lets the defender react" in payload["error"]


def test_the_engine_panel_reports_that_no_engine_runs(client):
    payload = client.get("/api/engine")

    assert payload["available"] is False
    assert "--engine" in payload["reason"]


def test_the_engine_panel_shows_the_build_and_the_refusals(engine_client):
    payload = engine_client.get("/api/engine")

    assert payload["available"] is True
    assert payload["protocol"] == PROTOCOL_VERSION
    assert {entry["name"] for entry in payload["commands"] if entry["implemented"]} == {
        "hello",
        "ping",
        "load",
        "reach",
    }
    assert payload["answers"]["load"] == {"ok": True, "payload": {}}
    assert "reach" not in payload["answers"]
    assert {
        name: answer["code"] for name, answer in payload["answers"].items() if name != "load"
    } == {
        "roster": "not_implemented",
        "deploy_cells": "not_implemented",
    }


def test_the_engine_panel_answers_the_reach_of_the_selected_unit(engine_client):
    entry = engine_client.get("/api/decision")["units"][0]

    payload = engine_client.get("/api/engine?unit=" + quote(entry["uid"]))

    answer = payload["answers"]["reach"]
    assert answer["ok"] is True
    cells = [tuple(cell) for cell in answer["payload"]["cells"]]
    assert cells == sorted(cells)
    assert tuple(entry["cell"]) in cells
    assert set(cells) <= {tuple(cell) for cell in entry["moves"]}
    assert any(tuple(cell) not in set(cells) for cell in entry["moves"])


def test_the_engine_refuses_the_reach_of_a_unit_outside_the_board(engine_client):
    payload = engine_client.get("/api/engine?unit=ghost")

    assert payload["answers"]["reach"] == {
        "ok": False,
        "code": "illegal_action",
        "message": 'the board holds no unit "ghost"',
    }


def test_the_board_the_engine_receives_is_the_wire_form_of_the_model(client):
    sandbox = Sandbox.from_scenario(PLACEHOLDER)

    state = sandbox.engine_state()

    assert [unit["unit_id"] for unit in state["units"]] == [
        unit["uid"] for unit in client.get("/api/state")["units"]
    ]
    assert state["bounds"] == [[0, 0], [24, 19]]
    assert state["phase"] == "ally"
