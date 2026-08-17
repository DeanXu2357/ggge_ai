"""沙盤網頁介面：腳本只准碰門面，外加一次真的起 server 打 /api/state 的煙霧測試。"""

from __future__ import annotations

import ast
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

from ggge_ai.sandbox.facade import Sandbox
from scripts.sandbox_ui import build_handler

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = ROOT / "assets/scenarios/uc_hard_1_placeholder.json"
SCRIPT = ROOT / "scripts/sandbox_ui.py"


@pytest.fixture(scope="module")
def sandbox():
    return Sandbox.from_scenario(PLACEHOLDER)


def _imported_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def test_the_script_reaches_the_package_through_the_facade_only():
    reached = [name for name in _imported_names(SCRIPT) if name.startswith("ggge_ai")]

    assert reached == ["ggge_ai.sandbox.facade.Sandbox"]


def test_server_answers_the_state_endpoint(sandbox):
    server = ThreadingHTTPServer(("127.0.0.1", 0), build_handler(sandbox))
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
    assert len(payload["units"]) == 28
    assert page.startswith("<!doctype html>")
