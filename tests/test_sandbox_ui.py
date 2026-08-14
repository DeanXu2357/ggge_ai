"""沙盤網頁介面：腳本只准碰門面，操作端點走真的 HTTP 打一輪我方階段。"""

from __future__ import annotations

import ast
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ggge_ai.sandbox.facade import Sandbox
from scripts.sandbox_ui import build_handler

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = ROOT / "assets/scenarios/uc_hard_1_placeholder.json"
SCRIPT = ROOT / "scripts/sandbox_ui.py"


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


@pytest.fixture
def client():
    sandbox = Sandbox.from_scenario(PLACEHOLDER)
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(sandbox, seed=7))
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


def test_the_script_reaches_the_package_through_the_facade_only():
    reached = [name for name in _imported_names(SCRIPT) if name.startswith("ggge_ai")]

    assert reached == ["ggge_ai.sandbox.facade.Sandbox"]


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
    assert "合法清單" in payload["error"]


def test_an_illegal_reaction_answers_four_hundred(client):
    entry = client.get("/api/decision")["units"][0]
    shot = _first(entry, "attack")

    status, payload = client.post(
        "/api/act", {"candidate": shot, "reaction": {"stance": "sidestep"}}
    )

    assert status == 400
    assert "應戰姿態" in payload["error"]


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
    assert cell[0] == 400 and "格位" in cell[1]["error"]


def test_reactions_endpoint_rejects_a_candidate_without_an_engagement(client):
    entry = client.get("/api/decision")["units"][0]

    status, payload = client.post("/api/reactions", {"candidate": _first(entry, "standby")})

    assert status == 400
    assert "只有攻擊" in payload["error"]
