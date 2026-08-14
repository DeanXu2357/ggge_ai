"""沙盤網頁介面：起一個本機伺服器，畫出情境檔的盤面並接受我方階段的操作。

只讀情境檔，不碰 adb、不寫任何檔案。盤面、候選、推進一律向 'Sandbox' 門面要；
本腳本只做路由、頁面與擲骰輸入合成，不含任何遊戲規則。

usage:
  uv run python scripts/sandbox_ui.py --scenario assets/scenarios/uc_hard_1_placeholder.json
  uv run python scripts/sandbox_ui.py --scenario <path> --host 0.0.0.0 --port 9000
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import threading
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ggge_ai.sandbox.facade import Sandbox  # noqa: E402

DICE_KEYS = ("hit", "counter_hit", "support_hit")
CANDIDATE_FIELDS = ("kind", "unit_id", "move_to", "target_id", "weapon", "amount", "aim")


def _candidate_key(raw: Mapping[str, Any]) -> tuple:
    return tuple(raw.get(field) for field in CANDIDATE_FIELDS)


def _reaction_key(raw: Mapping[str, Any]) -> tuple:
    return (
        str(raw.get("stance", "none")),
        raw.get("weapon"),
        bool(raw.get("support_defend", False)),
        bool(raw.get("support_attack", True)),
    )


class SandboxHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    sandbox: Sandbox
    lock: threading.Lock
    rng: random.Random

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", PAGE_HTML.encode("utf-8"))
        elif path == "/api/state":
            self._json(HTTPStatus.OK, self.sandbox.snapshot())
        elif path == "/api/decision":
            self._json(HTTPStatus.OK, self.sandbox.pending_decision())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path not in ("/api/reactions", "/api/act"):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._body()
            candidate = body.get("candidate")
            if not isinstance(candidate, dict):
                raise ValueError("請求要帶 candidate 物件")
            with self.lock:
                if path == "/api/reactions":
                    payload = self.sandbox.reaction_options(candidate)
                else:
                    payload = self._act(candidate, body)
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(HTTPStatus.OK, payload)

    def log_message(self, *args: Any) -> None:
        return

    def _act(self, candidate: dict[str, Any], body: Mapping[str, Any]) -> dict[str, Any]:
        reaction = body.get("reaction")
        if reaction is not None and not isinstance(reaction, dict):
            raise ValueError("reaction 要寫成物件或 null")
        rolled = dict(candidate)
        if body.get("draw"):
            rolled.update(self._draw(candidate, reaction))
        dice = {key: rolled.get(key) for key in DICE_KEYS}
        state = self.sandbox.act(rolled, reaction)
        return {"dice": dice, "state": state, "pending": self.sandbox.pending_decision()}

    def _draw(self, candidate: Mapping[str, Any], reaction: Mapping[str, Any] | None) -> dict:
        # 門面只給主命中率；反擊與支援命中率沒有酬載欄位，抽不了，留給模型預設。
        chance = self._hit_probability(candidate, reaction)
        return {} if chance is None else {"hit": self.rng.random() < chance}

    def _hit_probability(
        self, candidate: Mapping[str, Any], reaction: Mapping[str, Any] | None
    ) -> float | None:
        if candidate.get("kind") != "attack":
            return None
        if reaction is None:
            return self._pending_probability(candidate)
        picked = _reaction_key(reaction)
        for option in self.sandbox.reaction_options(candidate)["options"]:
            if _reaction_key(option) == picked:
                return option["hit_probability"]
        raise ValueError(f"這個應戰不在合法選項裡：{reaction}")

    def _pending_probability(self, candidate: Mapping[str, Any]) -> float | None:
        wanted = _candidate_key(candidate)
        for entry in self.sandbox.pending_decision()["units"]:
            for option in entry["candidates"]:
                if _candidate_key(option) == wanted:
                    return option["hit_probability"]
        return None

    def _body(self) -> dict[str, Any]:
        try:
            size = int(self.headers.get("Content-Length"))
        except (TypeError, ValueError):
            raise ValueError("請求要帶 Content-Length") from None
        try:
            body = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"請求主體不是 JSON：{exc}") from exc
        if not isinstance(body, dict):
            raise ValueError("請求主體要是 JSON 物件")
        return body

    def _json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", body)

    def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_handler(sandbox: Sandbox, *, seed: int | None = None) -> type[BaseHTTPRequestHandler]:
    return type(
        "BoundSandboxHandler",
        (SandboxHandler,),
        {"sandbox": sandbox, "lock": threading.Lock(), "rng": random.Random(seed)},
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
  main { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 18px; padding: 16px 18px 60px; }
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
  .cell.reach { background: #1d2a3a; }
  .cell.dest { background: #24405c; cursor: pointer; }
  .cell.aim { outline: 2px solid #e0c15f; outline-offset: -2px; }
  .piece {
    position: absolute; inset: 2px; border-radius: 5px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font: 11px/1 ui-monospace, monospace; color: #0d0f12; font-weight: 700;
  }
  .piece.ally { background: #5b9bea; }
  .piece.enemy { background: #e0665f; }
  .piece.third_party { background: #e0c15f; }
  .piece.acted { opacity: .45; }
  .piece.on { outline: 2px solid #f2f5fa; }
  .piece.actor { outline: 2px solid #7fd694; }
  .bar { position: absolute; left: 2px; right: 2px; bottom: 1px; height: 3px; background: #0d0f12; }
  .bar i { display: block; height: 100%; background: #7fd694; }

  .side { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  aside { background: #1b1f26; border: 1px solid #2c323c; border-radius: 8px; padding: 12px 14px; }
  aside h2 { margin: 0 0 8px; font-size: 16px; }
  aside h3 { margin: 12px 0 4px; font-size: 14px; color: #9fb6d6; }
  table { width: 100%; border-collapse: collapse; }
  td { border-top: 1px solid #262c36; padding: 4px 6px; vertical-align: top; font-size: 13px; }
  td.k { width: 45%; color: #8b93a1; }
  .wep { margin-top: 10px; }
  .wep div { border-top: 1px solid #262c36; padding: 5px 6px; font-size: 13px; }
  .wep b { color: #9fe0a8; font-weight: 600; }

  button.opt {
    display: block; width: 100%; margin: 3px 0; padding: 5px 8px; text-align: left;
    background: #222833; color: #e6e8eb; border: 1px solid #333b48; border-radius: 5px;
    font: 13px/1.4 system-ui, "Noto Sans TC", sans-serif; cursor: pointer;
  }
  button.opt:hover { border-color: #4c586b; }
  button.opt.on { background: #2f4a6b; border-color: #5b9bea; }
  button.opt:disabled { opacity: .45; cursor: default; }
  .units { display: flex; flex-wrap: wrap; gap: 4px; }
  .units button.opt { width: auto; margin: 0; }
  .dice { margin: 8px 0; }
  .die { display: flex; align-items: center; gap: 6px; margin: 3px 0; }
  .die span { flex: 1; }
  .die button.opt { width: auto; margin: 0; }
  .advice {
    margin: 8px 0; padding: 6px 8px; border: 1px dashed #3a4452; border-radius: 5px;
    color: #8b93a1; font-size: 13px; min-height: 32px;
  }
  .err { color: #e0665f; font-size: 13px; }
  .toggle { display: flex; align-items: center; gap: 6px; font-size: 13px; margin: 6px 0; }
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
  <div class="side">
    <aside id="play"></aside>
    <aside id="panel"><h2>單位資訊</h2><p class="dim">點盤面上的棋子看詳細數值。</p></aside>
  </div>
</main>
<script>
const FACTION_NAME = { ally: "我方", enemy: "敵方", third_party: "第三方" };
const STANCE_NAME = {
  none: "無反應", dodge: "閃避", defend: "防禦", shield: "防禦（盾牌）", counter: "反擊",
};
const KIND_NAME = {
  attack: "攻擊", map_attack: "地圖兵器", reposition: "移動", standby: "待機",
  skill_en_refill: "技能：EN 補給", skill_heal: "技能：修復",
};
const KIND_ORDER = [
  "attack", "map_attack", "skill_en_refill", "skill_heal", "reposition", "standby",
];

const el = (id) => document.getElementById(id);
let state = null;
let pending = null;
let actor = null;
let picked = null;
let engagement = null;
let option = null;
let dice = {};
let draw = false;
let lastDice = null;
let error = "";
let inspected = null;

function node(tag, className, text) {
  const out = document.createElement(tag);
  if (className) out.className = className;
  if (text !== undefined) out.textContent = text;
  return out;
}

function button(label, onClick, on) {
  const out = node("button", on ? "opt on" : "opt", label);
  out.addEventListener("click", onClick);
  return out;
}

function pct(value) {
  return value === null || value === undefined ? "—" : Math.round(value * 100) + "%";
}

function cellText(cell) {
  return cell ? "[" + cell[0] + "," + cell[1] + "]" : "—";
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || String(response.status));
  return payload;
}

function entryOf(uid) {
  return pending.units.find((entry) => entry.uid === uid) || null;
}

function apply(snapshot, decision) {
  state = snapshot;
  pending = decision;
  if (actor && !entryOf(actor)) actor = null;
  drawHeader();
  drawBoard();
  renderPlay();
  if (inspected) inspectUnit(inspected);
}

function drawHeader() {
  el("stage").textContent = state.stage;
  el("turn").textContent = "第 " + state.turn + " 回合";
  el("phase").textContent = "階段：" + (FACTION_NAME[state.phase] || state.phase);
  el("outcome").textContent = state.outcome ? "結果：" + state.outcome : "進行中";
  el("note").textContent = state.note || "";
  document.title = state.stage + " 沙盤盤面";
}

function drawBoard() {
  const cols = state.board.cols;
  const rows = state.board.rows;
  const axisX = el("axis-x");
  axisX.style.gridTemplateColumns = "repeat(" + cols + ", var(--cell))";
  axisX.textContent = "";
  for (let x = 0; x < cols; x += 1) axisX.appendChild(node("span", null, x));
  const axisY = el("axis-y");
  axisY.textContent = "";
  for (let y = 0; y < rows; y += 1) axisY.appendChild(node("span", null, y));

  const board = el("board");
  board.style.gridTemplateColumns = "repeat(" + cols + ", var(--cell))";
  board.textContent = "";
  const cells = [];
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const cell = node("div", "cell");
      cell.title = "[" + x + "," + y + "]";
      board.appendChild(cell);
      cells.push(cell);
    }
  }
  const at = (cell) => cells[cell[1] * cols + cell[0]];
  const entry = actor ? entryOf(actor) : null;
  if (entry) entry.moves.forEach((cell) => { const c = at(cell); if (c) c.classList.add("reach"); });
  if (entry) {
    entry.candidates
      .filter((candidate) => candidate.kind === "reposition")
      .forEach((candidate) => {
        const cell = at(candidate.move_to);
        if (!cell) return;
        cell.classList.add("dest");
        cell.addEventListener("click", () => pick(candidate));
      });
  }
  if (picked && picked.move_to) { const c = at(picked.move_to); if (c) c.classList.add("aim"); }
  if (picked && picked.aim) { const c = at(picked.aim); if (c) c.classList.add("aim"); }

  state.units.forEach((unit) => {
    const cell = at(unit.cell);
    if (!cell) return;
    const piece = node("div", "piece " + unit.faction + (unit.acted ? " acted" : ""), unit.uid);
    piece.dataset.uid = unit.uid;
    if (unit.uid === inspected) piece.classList.add("on");
    if (unit.uid === actor) piece.classList.add("actor");
    const bar = node("div", "bar");
    const fill = node("i");
    fill.style.width = Math.max(0, Math.round(100 * unit.hp / unit.max_hp)) + "%";
    bar.appendChild(fill);
    piece.appendChild(bar);
    piece.addEventListener("click", () => {
      inspectUnit(unit.uid);
      if (entryOf(unit.uid)) command(unit.uid);
      else drawBoard();
    });
    cell.appendChild(piece);
  });
}

function command(uid) {
  actor = uid;
  picked = null;
  engagement = null;
  option = null;
  dice = {};
  error = "";
  drawBoard();
  renderPlay();
}

function pick(candidate) {
  picked = candidate;
  engagement = null;
  option = null;
  dice = {};
  error = "";
  drawBoard();
  renderPlay();
  if (candidate.kind !== "attack") return;
  post("/api/reactions", { candidate: candidate })
    .then((payload) => { engagement = payload; renderPlay(); })
    .catch((exc) => { error = String(exc.message || exc); renderPlay(); });
}

function candidateLabel(candidate) {
  if (candidate.kind === "attack") {
    return "攻擊 " + candidate.target_id + "／" + candidate.weapon
      + "　命中 " + pct(candidate.hit_probability)
      + "　期望 " + candidate.expected_damage
      + (candidate.move_to ? "　移動 " + cellText(candidate.move_to) : "");
  }
  if (candidate.kind === "map_attack") {
    return "地圖兵器 " + candidate.weapon + " → " + cellText(candidate.aim)
      + "　期望 " + candidate.expected_damage + "（" + candidate.victims.length + " 台）";
  }
  if (candidate.kind === "reposition") return "移動 → " + cellText(candidate.move_to);
  if (candidate.kind === "standby") return "待機";
  return (KIND_NAME[candidate.kind] || candidate.kind)
    + (candidate.amount === null ? "" : " " + candidate.amount);
}

function optionLabel(entry) {
  const parts = [STANCE_NAME[entry.stance] || entry.stance];
  if (entry.weapon) parts.push(entry.weapon);
  if (entry.support_defend) parts.push("支援防禦 " + engagement.support_defender);
  if (entry.support_attackers.length) parts.push("支援攻擊 " + entry.support_attackers.join("、"));
  parts.push("命中 " + pct(entry.hit_probability));
  parts.push("受擊 " + entry.struck + " 期望 " + entry.expected_damage);
  return parts.join("／");
}

function roll(key) {
  return dice[key] === undefined ? true : dice[key];
}

function dieRow(wrap, key, label, chance) {
  const line = node("div", "die");
  line.appendChild(node("span", "dim", label + (chance === null ? "" : "（" + pct(chance) + "）")));
  [["命中", true], ["未命中", false]].forEach((pair) => {
    line.appendChild(button(pair[0], () => { dice[key] = pair[1]; renderPlay(); },
      roll(key) === pair[1]));
  });
  wrap.appendChild(line);
}

function renderDice(box) {
  const wrap = node("div", "dice");
  if (draw) {
    wrap.appendChild(node("div", "dim",
      "伺服器抽骰：主命中依酬載機率抽。反擊與支援沒有命中率欄位，維持模型預設命中。"));
  } else {
    dieRow(wrap, "hit", "主命中", option ? option.hit_probability : picked.hit_probability);
    if (option && option.stance === "counter") dieRow(wrap, "counter_hit", "反擊命中", null);
    if (option && option.support_attackers.length) {
      dieRow(wrap, "support_hit", "支援命中", null);
    }
  }
  box.appendChild(wrap);
}

function renderAdvice(box, payload) {
  const slot = node("div", "advice");
  const advice = payload && payload.advice;
  if (!advice) slot.textContent = "顧問建議：（issue #44 之前保持空白）";
  else slot.textContent = "顧問建議：" + advice.verdict + "／" + advice.reason;
  box.appendChild(slot);
}

function renderConfirm(box) {
  box.appendChild(node("h3", null, "確認"));
  box.appendChild(node("div", "dim", candidateLabel(picked)));
  if (picked.kind === "attack") renderDice(box);
  renderAdvice(box, engagement || pending);
  const ready = picked.kind !== "attack" || option !== null;
  const go = button(ready ? "執行" : "先選應戰選項", () => act(), false);
  go.disabled = !ready;
  box.appendChild(go);
}

function renderPlay() {
  const box = el("play");
  box.textContent = "";
  box.appendChild(node("h2", null, "操作模式"));
  box.appendChild(node("div", "dim",
    "第 " + pending.turn + " 回合／" + (FACTION_NAME[pending.phase] || pending.phase) + "階段"));

  const toggle = node("label", "toggle");
  const check = document.createElement("input");
  check.type = "checkbox";
  check.checked = draw;
  check.addEventListener("change", () => { draw = check.checked; renderPlay(); });
  toggle.appendChild(check);
  toggle.appendChild(node("span", null, "伺服器抽骰（預設手動擲骰）"));
  box.appendChild(toggle);

  if (lastDice) box.appendChild(node("div", "dim", "上一次擲骰：" + lastDice));
  if (error) box.appendChild(node("div", "err", error));

  if (state.phase !== "ally") {
    box.appendChild(node("p", "dim", "我方階段結束。敵方階段的操控是 issue #42。"));
    return;
  }
  if (!pending.units.length) {
    box.appendChild(node("p", "dim", "沒有待啟動的單位。"));
    return;
  }

  box.appendChild(node("h3", null, "待啟動（" + pending.units.length + "）"));
  const list = node("div", "units");
  pending.units.forEach((entry) => {
    list.appendChild(button(entry.uid, () => command(entry.uid), entry.uid === actor));
  });
  box.appendChild(list);

  const entry = actor ? entryOf(actor) : null;
  if (!entry) {
    box.appendChild(node("p", "dim", "選一台單位下令。"));
    return;
  }
  KIND_ORDER.forEach((kind) => {
    const group = entry.candidates.filter((candidate) => candidate.kind === kind);
    if (!group.length) return;
    box.appendChild(node("h3", null, KIND_NAME[kind] || kind));
    group.forEach((candidate) => {
      box.appendChild(button(candidateLabel(candidate), () => pick(candidate), candidate === picked));
    });
  });

  if (!picked) return;
  if (picked.kind === "attack") {
    box.appendChild(node("h3", null, "應戰"));
    if (!engagement) box.appendChild(node("div", "dim", "讀取應戰選項…"));
    else {
      engagement.options.forEach((entryOption) => {
        box.appendChild(button(optionLabel(entryOption), () => {
          option = entryOption;
          dice = {};
          renderPlay();
        }, entryOption === option));
      });
    }
  }
  renderConfirm(box);
}

function act() {
  const candidate = Object.assign({}, picked);
  if (!draw && picked.kind === "attack") {
    candidate.hit = roll("hit");
    if (option && option.stance === "counter") candidate.counter_hit = roll("counter_hit");
    if (option && option.support_attackers.length) candidate.support_hit = roll("support_hit");
  }
  const reaction = option === null ? null : {
    stance: option.stance,
    weapon: option.weapon,
    support_defend: option.support_defend,
    support_attack: option.support_attack,
  };
  post("/api/act", { candidate: candidate, reaction: reaction, draw: draw })
    .then((payload) => {
      lastDice = Object.keys(payload.dice)
        .filter((key) => payload.dice[key] !== null)
        .map((key) => key + "=" + (payload.dice[key] ? "命中" : "未命中"))
        .join("／") || "無命中節點";
      picked = null;
      engagement = null;
      option = null;
      dice = {};
      error = "";
      apply(payload.state, payload.pending);
    })
    .catch((exc) => { error = String(exc.message || exc); renderPlay(); });
}

function tableRow(table, key, value) {
  const line = table.insertRow();
  const left = line.insertCell();
  left.className = "k";
  left.textContent = key;
  line.insertCell().textContent = value;
}

function inspectUnit(uid) {
  inspected = uid;
  document.querySelectorAll(".piece").forEach((piece) => {
    piece.classList.toggle("on", piece.dataset.uid === uid);
  });
  const unit = state.units.find((candidate) => candidate.uid === uid);
  const panel = el("panel");
  panel.textContent = "";
  if (!unit) {
    panel.appendChild(node("h2", null, "單位資訊"));
    panel.appendChild(node("p", "dim", uid + " 已不在盤面上。"));
    return;
  }
  panel.appendChild(
    node("h2", null, unit.uid + "（" + (FACTION_NAME[unit.faction] || unit.faction) + "）"));
  const table = document.createElement("table");
  tableRow(table, "格位", cellText(unit.cell));
  tableRow(table, "HP", unit.hp + " / " + unit.max_hp);
  tableRow(table, "EN", unit.en + " / " + unit.en_max);
  tableRow(table, "已行動", unit.acted ? "是" : "否");
  tableRow(table, "移動力", unit.move_range);
  tableRow(table, "運動性", unit.mobility);
  tableRow(table, "機體攻擊／防禦", unit.unit_attack + " / " + unit.unit_defense);
  tableRow(table, "駕駛攻擊／防禦", unit.pilot_attack + " / " + unit.pilot_defense);
  tableRow(table, "反應", unit.reaction);
  tableRow(table, "盾牌", unit.has_shield ? "有" : "無");
  tableRow(table, "覺醒步數", unit.chance_steps);
  tableRow(table, "支援攻擊餘額", unit.support_attack_charges);
  tableRow(table, "支援防禦餘額", unit.support_defend_charges);
  tableRow(table, "技能", unit.skills.map((s) => s.kind + "×" + s.uses).join("、") || "無");
  panel.appendChild(table);
  const box = node("div", "wep");
  unit.weapons.forEach((weapon) => {
    const line = node("div");
    line.appendChild(node("b", null, weapon.name));
    const parts = [
      "威力 " + weapon.power,
      "射程 " + weapon.range_min + "-" + weapon.range_max,
      "EN " + weapon.en_cost,
      "命中補正 " + weapon.accuracy,
    ];
    if (weapon.ammo !== null && weapon.ammo !== undefined) parts.push("彈藥 " + weapon.ammo);
    if (!weapon.can_counter) parts.push("不可反擊");
    if (weapon.map_weapon) parts.push("地圖兵器");
    line.appendChild(node("div", "dim", parts.join("／")));
    box.appendChild(line);
  });
  panel.appendChild(box);
}

Promise.all([
  fetch("/api/state").then((response) => response.json()),
  fetch("/api/decision").then((response) => response.json()),
])
  .then((payloads) => apply(payloads[0], payloads[1]))
  .catch((exc) => {
    el("stage").textContent = "讀取盤面失敗：" + exc;
  });
</script>
</body>
</html>
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="沙盤網頁介面：呈現情境檔盤面並操作我方階段")
    parser.add_argument("--scenario", required=True, help="情境檔路徑（sandbox-scenario/1）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8642)
    parser.add_argument("--seed", type=int, default=None, help="伺服器抽骰的亂數種子")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    sandbox = Sandbox.from_scenario(args.scenario)
    board = sandbox.snapshot()

    handler = build_handler(sandbox, seed=args.seed)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"情境：{board['stage']}（{len(board['units'])} 台單位）")
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
