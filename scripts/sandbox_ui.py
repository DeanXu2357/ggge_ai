"""沙盤網頁介面（第一階段）：起一個本機伺服器，把情境檔的初盤面畫出來。

只讀情境檔，不碰 adb、不寫任何檔案；這一階段唯讀呈現，沒有任何操作端點。

usage:
  uv run python scripts/sandbox_ui.py --scenario assets/scenarios/uc_hard_1_placeholder.json
  uv run python scripts/sandbox_ui.py --scenario <path> --host 0.0.0.0 --port 9000
"""

from __future__ import annotations

import argparse
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ggge_ai.sandbox import scenario as scenario_mod  # noqa: E402
from ggge_ai.sandbox.model import BattleState, Unit  # noqa: E402


def serialize_unit(unit: Unit) -> dict[str, Any]:
    return {
        "uid": unit.unit_id,
        "faction": str(unit.faction),
        "cell": list(unit.pos),
        "hp": unit.hp,
        "max_hp": unit.max_hp,
        "en": unit.en,
        "en_max": unit.en_max,
        "acted": unit.acted,
        "move_range": unit.move_range,
        "mobility": unit.mobility,
        "unit_attack": unit.unit_attack,
        "unit_defense": unit.unit_defense,
        "pilot_attack": unit.pilot_attack,
        "pilot_defense": unit.pilot_defense,
        "reaction": unit.reaction,
        "has_shield": unit.has_shield,
        "attack_shield": unit.attack_shield,
        "chance_steps": unit.chance_steps,
        "support_attack_charges": unit.support_attack_charges,
        "support_defend_charges": unit.support_defend_charges,
        "weapons": [
            {
                "name": weapon.name,
                "power": weapon.power,
                "range_min": weapon.range_min,
                "range_max": weapon.range_max,
                "en_cost": weapon.en_cost,
                "accuracy": weapon.accuracy,
                "can_counter": weapon.can_counter,
                "map_weapon": weapon.map_weapon,
                "ammo": unit.ammo.get(weapon.name),
            }
            for weapon in unit.weapons
        ],
        "skills": [
            {"kind": str(skill.kind), "amount": skill.amount, "uses": skill.uses}
            for skill in unit.skills
        ],
    }


def serialize_state(
    scenario: scenario_mod.Scenario, state: BattleState
) -> dict[str, Any]:
    return {
        "stage": scenario.stage,
        "note": scenario.note,
        "board": {"cols": scenario.board.cols, "rows": scenario.board.rows},
        "turn": state.turn,
        "phase": str(state.phase),
        "outcome": scenario_mod.check_outcome(scenario, state),
        "units": [serialize_unit(unit) for unit in state.units],
    }


class SandboxHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    scenario: scenario_mod.Scenario
    state: BattleState

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            self._send("text/html; charset=utf-8", PAGE_HTML.encode("utf-8"))
        elif path == "/api/state":
            body = json.dumps(
                serialize_state(self.scenario, self.state), ensure_ascii=False
            ).encode("utf-8")
            self._send("application/json; charset=utf-8", body)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, *args: Any) -> None:
        return

    def _send(self, content_type: str, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_handler(
    scenario: scenario_mod.Scenario, state: BattleState
) -> type[BaseHTTPRequestHandler]:
    return type(
        "BoundSandboxHandler", (SandboxHandler,), {"scenario": scenario, "state": state}
    )


PAGE_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>沙盤盤面</title>
<style>
  :root { color-scheme: dark; --cell: 34px; }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: #14161a; color: #e6e8eb;
    font: 15px/1.6 system-ui, "Noto Sans TC", sans-serif;
  }
  header {
    display: flex; gap: 18px; align-items: baseline; flex-wrap: wrap;
    padding: 10px 18px; background: #1b1f26; border-bottom: 1px solid #2c323c;
  }
  header strong { font-size: 17px; letter-spacing: .5px; }
  .dim { color: #8b93a1; font-size: 13px; }
  main { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 18px; padding: 16px 18px 60px; }
  @media (max-width: 1100px) { main { grid-template-columns: minmax(0, 1fr); } }

  .boardwrap { overflow: auto; }
  .axis-x { display: grid; margin-left: var(--cell); }
  .axis-x span, .axis-y span {
    font: 10px/1 ui-monospace, monospace; color: #6f7787;
    display: flex; align-items: center; justify-content: center;
    width: var(--cell); height: var(--cell);
  }
  .row { display: flex; }
  .axis-y { display: flex; flex-direction: column; }
  .board { display: grid; border-top: 1px solid #2c323c; border-left: 1px solid #2c323c; }
  .cell {
    width: var(--cell); height: var(--cell);
    border-right: 1px solid #232830; border-bottom: 1px solid #232830;
    position: relative; background: #191d23;
  }
  .piece {
    position: absolute; inset: 2px; border-radius: 5px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font: 11px/1 ui-monospace, monospace; color: #0d0f12; font-weight: 700;
  }
  .piece.ally { background: #5b9bea; }
  .piece.enemy { background: #e0665f; }
  .piece.third_party { background: #e0c15f; }
  .piece.on { outline: 2px solid #f2f5fa; }
  .bar { position: absolute; left: 2px; right: 2px; bottom: 1px; height: 3px; background: #0d0f12; }
  .bar i { display: block; height: 100%; background: #7fd694; }

  aside { background: #1b1f26; border: 1px solid #2c323c; border-radius: 8px; padding: 12px 14px; }
  aside h2 { margin: 0 0 8px; font-size: 16px; }
  table { width: 100%; border-collapse: collapse; }
  td { border-top: 1px solid #262c36; padding: 4px 6px; vertical-align: top; font-size: 13px; }
  td.k { width: 45%; color: #8b93a1; }
  .wep { margin-top: 10px; }
  .wep div { border-top: 1px solid #262c36; padding: 5px 6px; font-size: 13px; }
  .wep b { color: #9fe0a8; font-weight: 600; }
</style>
</head>
<body>
<header>
  <strong id="stage">載入中…</strong>
  <span class="dim" id="turn"></span>
  <span class="dim" id="phase"></span>
  <span class="dim" id="outcome"></span>
  <span class="dim" id="note"></span>
</header>
<main>
  <div class="boardwrap">
    <div class="axis-x" id="axis-x"></div>
    <div class="row">
      <div class="axis-y" id="axis-y"></div>
      <div class="board" id="board"></div>
    </div>
  </div>
  <aside id="panel"><h2>單位資訊</h2><p class="dim">點盤面上的棋子看詳細數值。</p></aside>
</main>
<script>
const FACTION_NAME = { ally: "我方", enemy: "敵方", third_party: "第三方" };
const el = (id) => document.getElementById(id);
let data = null;
let selected = null;

function drawBoard() {
  const cols = data.board.cols;
  const rows = data.board.rows;
  const axisX = el("axis-x");
  axisX.style.gridTemplateColumns = "repeat(" + cols + ", var(--cell))";
  axisX.textContent = "";
  for (let x = 0; x < cols; x += 1) {
    const mark = document.createElement("span");
    mark.textContent = x;
    axisX.appendChild(mark);
  }
  const axisY = el("axis-y");
  axisY.textContent = "";
  for (let y = 0; y < rows; y += 1) {
    const mark = document.createElement("span");
    mark.textContent = y;
    axisY.appendChild(mark);
  }
  const board = el("board");
  board.style.gridTemplateColumns = "repeat(" + cols + ", var(--cell))";
  board.textContent = "";
  const cells = [];
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.title = "[" + x + "," + y + "]";
      board.appendChild(cell);
      cells.push(cell);
    }
  }
  data.units.forEach((unit) => {
    const index = unit.cell[1] * cols + unit.cell[0];
    const cell = cells[index];
    if (!cell) return;
    const piece = document.createElement("div");
    piece.className = "piece " + unit.faction;
    piece.textContent = unit.uid;
    piece.dataset.uid = unit.uid;
    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("i");
    fill.style.width = Math.max(0, Math.round(100 * unit.hp / unit.max_hp)) + "%";
    bar.appendChild(fill);
    piece.appendChild(bar);
    piece.addEventListener("click", () => select(unit.uid));
    cell.appendChild(piece);
  });
}

function row(table, key, value) {
  const line = table.insertRow();
  const left = line.insertCell();
  left.className = "k";
  left.textContent = key;
  line.insertCell().textContent = value;
}

function select(uid) {
  selected = uid;
  document.querySelectorAll(".piece").forEach((piece) => {
    piece.classList.toggle("on", piece.dataset.uid === uid);
  });
  const unit = data.units.find((candidate) => candidate.uid === uid);
  const panel = el("panel");
  panel.textContent = "";
  const title = document.createElement("h2");
  title.textContent = unit.uid + "（" + (FACTION_NAME[unit.faction] || unit.faction) + "）";
  panel.appendChild(title);
  const table = document.createElement("table");
  row(table, "格位", "[" + unit.cell[0] + "," + unit.cell[1] + "]");
  row(table, "HP", unit.hp + " / " + unit.max_hp);
  row(table, "EN", unit.en + " / " + unit.en_max);
  row(table, "已行動", unit.acted ? "是" : "否");
  row(table, "移動力", unit.move_range);
  row(table, "運動性", unit.mobility);
  row(table, "機體攻擊／防禦", unit.unit_attack + " / " + unit.unit_defense);
  row(table, "駕駛攻擊／防禦", unit.pilot_attack + " / " + unit.pilot_defense);
  row(table, "反應", unit.reaction);
  row(table, "盾牌", unit.has_shield ? "有" : "無");
  row(table, "覺醒步數", unit.chance_steps);
  row(table, "支援攻擊餘額", unit.support_attack_charges);
  row(table, "支援防禦餘額", unit.support_defend_charges);
  row(table, "技能", unit.skills.map((s) => s.kind + "×" + s.uses).join("、") || "無");
  panel.appendChild(table);
  const box = document.createElement("div");
  box.className = "wep";
  unit.weapons.forEach((weapon) => {
    const line = document.createElement("div");
    const name = document.createElement("b");
    name.textContent = weapon.name;
    line.appendChild(name);
    const parts = [
      "威力 " + weapon.power,
      "射程 " + weapon.range_min + "-" + weapon.range_max,
      "EN " + weapon.en_cost,
      "命中補正 " + weapon.accuracy,
    ];
    if (weapon.ammo !== null && weapon.ammo !== undefined) parts.push("彈藥 " + weapon.ammo);
    if (!weapon.can_counter) parts.push("不可反擊");
    if (weapon.map_weapon) parts.push("地圖兵器");
    const detail = document.createElement("div");
    detail.className = "dim";
    detail.textContent = parts.join("／");
    line.appendChild(detail);
    box.appendChild(line);
  });
  panel.appendChild(box);
}

fetch("/api/state")
  .then((response) => response.json())
  .then((payload) => {
    data = payload;
    el("stage").textContent = payload.stage;
    el("turn").textContent = "第 " + payload.turn + " 回合";
    el("phase").textContent = "階段：" + (FACTION_NAME[payload.phase] || payload.phase);
    el("outcome").textContent = payload.outcome ? "結果：" + payload.outcome : "進行中";
    el("note").textContent = payload.note || "";
    document.title = payload.stage + " 沙盤盤面";
    drawBoard();
    if (selected) select(selected);
  })
  .catch((error) => {
    el("stage").textContent = "讀取盤面失敗：" + error;
  });
</script>
</body>
</html>
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="沙盤網頁介面：呈現情境檔的初盤面")
    parser.add_argument("--scenario", required=True, help="情境檔路徑（sandbox-scenario/1）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8642)
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    scenario = scenario_mod.load(args.scenario)
    state, _rules, _events = scenario.build()

    server = ThreadingHTTPServer((args.host, args.port), build_handler(scenario, state))
    print(f"情境：{scenario.stage}（{len(state.units)} 台單位）")
    print(f"開啟 http://{args.host}:{args.port}/ ——Ctrl-C 結束")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
