"""沙盤網頁介面：序列化形狀，外加一次真的起 server 打 /api/state 的煙霧測試。"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

from ggge_ai.sandbox import scenario as scenario_mod
from scripts.sandbox_ui import build_handler, serialize_state

PLACEHOLDER = Path(__file__).resolve().parents[1] / "assets/scenarios/uc_hard_1_placeholder.json"


@pytest.fixture(scope="module")
def built():
    scenario = scenario_mod.load(PLACEHOLDER)
    state, _rules, _events = scenario.build()
    return scenario, state


def test_serialize_state_carries_board_and_units(built):
    scenario, state = built

    payload = serialize_state(scenario, state)

    assert payload["board"] == {"cols": 25, "rows": 20}
    assert (payload["turn"], payload["phase"], payload["outcome"]) == (1, "ally", None)
    assert len(payload["units"]) == 22
    enemy = next(u for u in payload["units"] if u["cell"] == [9, 4])
    assert (enemy["uid"], enemy["hp"], enemy["en_max"]) == ("e1", 83811, 513)
    assert {"name", "power", "range_min", "range_max", "en_cost", "accuracy", "ammo"} <= set(
        enemy["weapons"][0]
    )


def test_serialize_state_reports_skills_and_charges(built):
    scenario, state = built

    payload = serialize_state(scenario, state)
    support = next(u for u in payload["units"] if u["has_shield"])

    assert support["skills"] == [{"kind": "skill_en_refill", "amount": 120.0, "uses": 1}]
    assert support["support_defend_charges"] == 1


def test_server_answers_the_state_endpoint(built):
    scenario, state = built
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(scenario, state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        with urlopen(f"http://{host}:{port}/api/state", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        with urlopen(f"http://{host}:{port}/", timeout=5) as response:
            page = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload["stage"] == "UC HARD 1"
    assert len(payload["units"]) == 22
    assert page.startswith("<!doctype html>")
