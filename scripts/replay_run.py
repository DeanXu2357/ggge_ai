"""流水帳回放：起一個本機網頁伺服器，逐筆重放過去某一輪 run 的紀錄與留存幀。

只讀 `data/runs/` 下的流水帳 jsonl 與 frames/，不碰 adb、不寫任何檔案。
壓縮過的舊 run 直接吃 `.tar.gz`（解到暫存目錄，退出時清掉）。

usage:
  # 最新那一輪未壓縮的 run
  uv run python scripts/replay_run.py

  # 指定 run：目錄路徑／壓縮檔路徑／純 run 名稱（三種都吃）
  uv run python scripts/replay_run.py data/runs/20260801-212645
  uv run python scripts/replay_run.py data/runs/20260731-170423.tar.gz
  uv run python scripts/replay_run.py 20260731-170423

  # 換埠／對外開；同一個 run 目錄有多份 jsonl 時指定要放哪一份
  uv run python scripts/replay_run.py --host 0.0.0.0 --port 9000
  uv run python scripts/replay_run.py 20260731-170423 --journal stage.jsonl

網頁兩種模式：投影片（逐筆前後翻，沒有自帶幀的紀錄沿用前一張並壓暗）與條漫
（所有紀錄由上往下一路排開，點任一筆跳回投影片）。
"""

from __future__ import annotations

import argparse
import atexit
import json
import shutil
import sys
import tarfile
import tempfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

RUNS_ROOT = Path("data/runs")
ARCHIVE_SUFFIX = ".tar.gz"
FRAMES_PREFIX = "/frames/"
SURVEY_TICK = "survey_tick"
SURVEY_DUMP_DIR = "frames/survey"


def resolve_run(arg: str | None, runs_root: Path) -> Path:
    """回傳可直接讀的 run 目錄。壓縮檔會被解到暫存目錄（程序結束時清掉）。"""
    if arg is None:
        return _latest_run(runs_root)
    source = Path(arg)
    if source.is_dir():
        return source
    if source.is_file() and source.name.endswith(ARCHIVE_SUFFIX):
        return _extract(source)
    named = runs_root / arg
    if named.is_dir():
        return named
    archive = runs_root / (arg + ARCHIVE_SUFFIX)
    if archive.is_file():
        return _extract(archive)
    raise SystemExit(f"找不到 run：{arg}（不是目錄、不是壓縮檔，{runs_root} 下也沒有同名的）")


def find_journal(run_dir: Path, override: str | None) -> Path:
    if override is not None:
        path = run_dir / override
        if not path.is_file():
            raise SystemExit(f"找不到流水帳：{path}")
        return path
    found = sorted(run_dir.glob("*.jsonl"))
    if not found:
        raise SystemExit(f"{run_dir} 下沒有 *.jsonl 流水帳")
    if len(found) > 1:
        names = "、".join(path.name for path in found)
        raise SystemExit(f"{run_dir} 下有多份流水帳（{names}），請用 --journal 指定")
    return found[0]


def load_entries(journal_path: Path) -> list[dict[str, Any]]:
    """壞行跳過而不是整支炸掉——流水帳是逐筆寫穿的，主機中途死掉就會留半行。"""
    entries: list[dict[str, Any]] = []
    broken = 0
    with journal_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                broken += 1
                continue
            if isinstance(record, dict):
                entries.append(record)
            else:
                broken += 1
    if broken:
        print(f"警告：{journal_path} 有 {broken} 行讀不回來，已跳過", file=sys.stderr)
    return entries


def collect_attachments(run_dir: Path, entries: list[dict[str, Any]]) -> dict[int, list[str]]:
    """把 `--dump-survey-frames` 的側傾印掛回對應的紀錄（鍵＝entries 的索引）。

    側傾印**不寫進流水帳**，`frames/survey/t{tick}-{probe}.png` 這個命名慣例是
    紀錄與檔案之間唯一的連結（出處 scripts/dry_run_entry.py 的 SurveyFrames._dump）；
    撈不到檔就是那一輪沒開傾印，不是漏掉。
    """
    attachments: dict[int, list[str]] = {}
    for index, entry in enumerate(entries):
        if entry.get("kind") != SURVEY_TICK:
            continue
        tick = entry.get("tick")
        probe = entry.get("probe")
        if tick is None or probe is None:
            continue
        relative = f"{SURVEY_DUMP_DIR}/t{tick}-{probe}.png"
        if (run_dir / relative).is_file():
            attachments[index] = [relative]
    return attachments


def build_payload(run_dir: Path, journal_path: Path) -> dict[str, Any]:
    entries = load_entries(journal_path)
    attachments = collect_attachments(run_dir, entries)
    return {
        "name": run_dir.name,
        "journal": journal_path.name,
        "entries": entries,
        "attachments": {str(index): frames for index, frames in attachments.items()},
    }


def safe_frame_path(run_dir: Path, url_path: str) -> Path | None:
    """URL 直接當檔案路徑用，所以 resolve 之後一定要再比對根目錄——`../` 與
    符號連結都會在 resolve 這一步被攤平，只比字串擋不住。檔案不存在也回 None。
    """
    relative = unquote(urlsplit(url_path).path).lstrip("/")
    if not relative:
        return None
    root = run_dir.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


def _latest_run(runs_root: Path) -> Path:
    directories = sorted(path for path in runs_root.glob("*") if path.is_dir())
    if directories:
        return directories[-1]
    archives = sorted(
        path.name[: -len(ARCHIVE_SUFFIX)]
        for path in runs_root.glob("*" + ARCHIVE_SUFFIX)
        if path.is_file()
    )
    if archives:
        listed = "\n  ".join(archives)
        raise SystemExit(f"{runs_root} 下沒有未壓縮的 run，可指定這些壓縮 run：\n  {listed}")
    raise SystemExit(f"{runs_root} 下沒有任何 run")


def _extract(archive: Path) -> Path:
    workspace = Path(tempfile.mkdtemp(prefix="ggge-replay-"))
    atexit.register(shutil.rmtree, workspace, ignore_errors=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(workspace, filter="data")
    tops = [path for path in workspace.iterdir() if path.is_dir()]
    if len(tops) != 1:
        found = "、".join(sorted(path.name for path in tops)) or "（空的）"
        raise SystemExit(f"{archive} 內不是單一頂層 run 目錄：{found}")
    return tops[0]


class ReplayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    run_dir: Path
    payload: bytes

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            self._send("text/html; charset=utf-8", PAGE_HTML.encode("utf-8"))
        elif path == "/api/run":
            self._send("application/json; charset=utf-8", self.payload)
        elif path.startswith(FRAMES_PREFIX):
            frame = safe_frame_path(self.run_dir, path)
            if frame is None:
                self.send_error(HTTPStatus.NOT_FOUND)
            else:
                self._send("image/png", frame.read_bytes())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _send(self, content_type: str, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_handler(run_dir: Path, payload: bytes) -> type[BaseHTTPRequestHandler]:
    return type("BoundReplayHandler", (ReplayHandler,), {"run_dir": run_dir, "payload": payload})


PAGE_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>流水帳回放</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #14161a;
    color: #e6e8eb;
    font: 15px/1.6 system-ui, "Noto Sans TC", sans-serif;
  }
  header {
    position: sticky; top: 0; z-index: 5;
    display: flex; flex-wrap: wrap; gap: 12px;
    align-items: baseline; justify-content: space-between;
    padding: 10px 18px;
    background: #1b1f26;
    border-bottom: 1px solid #2c323c;
  }
  header .run { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
  header strong { font-size: 17px; letter-spacing: .5px; }
  .dim { color: #8b93a1; font-size: 13px; }
  button {
    background: #262c36; color: #e6e8eb;
    border: 1px solid #39404c; border-radius: 6px;
    padding: 6px 14px; font: inherit; cursor: pointer;
  }
  button:hover { background: #303845; }
  button:disabled { opacity: .4; cursor: default; }
  button.on { background: #3b6ea5; border-color: #4c86c4; }
  main { padding: 16px 18px 60px; }
  .hidden { display: none !important; }

  .nav { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
  .nav label { color: #b9c0cb; font-size: 13px; cursor: pointer; }
  #position { color: #b9c0cb; }

  .stage { display: grid; grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr); gap: 18px; }
  @media (max-width: 1100px) { .stage { grid-template-columns: minmax(0, 1fr); } }
  .shots { display: flex; flex-direction: column; gap: 12px; }
  .shots.carried { filter: brightness(.42) saturate(.7); }
  figure.shot { margin: 0; }
  figure.shot figcaption {
    font: 12px/1.5 ui-monospace, monospace; color: #d7b56d;
    margin-bottom: 4px; word-break: break-all;
  }
  figure.shot img { width: 100%; height: auto; display: block; border-radius: 6px; background: #0d0f12; }
  .carry {
    display: inline-block; margin-bottom: 10px;
    background: #241f14; border: 1px solid #4a5162;
    border-radius: 5px; padding: 4px 10px; font-size: 13px; color: #d7b56d;
  }
  .empty {
    display: flex; align-items: center; justify-content: center;
    min-height: 260px; border: 1px dashed #39404c; border-radius: 6px; color: #6f7787;
  }

  .headline { display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; margin-bottom: 10px; }
  .headline .seq { font-size: 20px; font-weight: 700; color: #7fb2ec; }
  .headline .kind {
    font-size: 17px; font-weight: 600; color: #9fe0a8;
    background: #22301f; border-radius: 5px; padding: 1px 9px;
  }
  .headline .time, .headline .tick { color: #8b93a1; font-size: 13px; }

  table.fields { width: 100%; border-collapse: collapse; }
  table.fields td { border-top: 1px solid #262c36; padding: 5px 8px; vertical-align: top; }
  table.fields td.k { width: 30%; color: #8b93a1; word-break: break-all; }
  table.fields td.v { word-break: break-word; }
  table.fields pre {
    margin: 0; white-space: pre-wrap; word-break: break-word;
    font: 12px/1.5 ui-monospace, monospace; color: #cbd3df;
  }

  #comic { max-width: 1480px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
  .card {
    background: #1b1f26; border: 1px solid #2c323c; border-radius: 8px;
    padding: 12px 14px; scroll-margin-top: 72px; cursor: pointer;
  }
  .card:hover { border-color: #4c86c4; }
  .card.paired {
    display: grid; grid-template-columns: minmax(260px, 1fr) minmax(0, 900px);
    gap: 16px; align-items: start;
  }
  @media (max-width: 900px) { .card.paired { grid-template-columns: minmax(0, 1fr); } }
</style>
</head>
<body>
<header>
  <div class="run">
    <strong id="run-name">載入中…</strong>
    <span class="dim" id="run-journal"></span>
    <span class="dim" id="run-count"></span>
  </div>
  <div>
    <button id="mode-slide" class="on">投影片</button>
    <button id="mode-comic">條漫</button>
  </div>
</header>
<main>
  <section id="slide">
    <div class="nav">
      <button id="prev">◀ 上一筆</button>
      <button id="next">下一筆 ▶</button>
      <span id="position"></span>
      <label><input type="checkbox" id="frames-only"> 只停在有圖的紀錄</label>
    </div>
    <div class="stage">
      <div>
        <div class="carry hidden" id="carry-note"></div>
        <div class="shots" id="shots"></div>
        <div class="empty" id="shot-empty">尚無畫面</div>
      </div>
      <div id="info"></div>
    </div>
  </section>
  <section id="comic" class="hidden"></section>
</main>
<script>
const TICK = /-tick(\d+)\.png$/;
const FRAME_VALUE = /^frames\/.+\.png$/;
const SHOT_FIELDS = ["frame", "prev", "curr"];
const state = {
  entries: [], attachments: {}, shots: [], index: 0, mode: "slide", framesOnly: false,
};
let comicBuilt = false;

const el = (id) => document.getElementById(id);
const frameUrl = (frame) => "/" + frame.split("/").map(encodeURIComponent).join("/");

function shotsOf(entry, index) {
  const shots = [];
  const seen = {};
  const add = (label, path, dump) => {
    if (typeof path !== "string" || !FRAME_VALUE.test(path) || seen[path]) return;
    seen[path] = true;
    shots.push({ label: label, path: path, dump: dump });
  };
  SHOT_FIELDS.forEach((key) => add(key, entry[key], false));
  Object.keys(entry).sort().forEach((key) => {
    if (SHOT_FIELDS.indexOf(key) === -1) add(key, entry[key], false);
  });
  (state.attachments[index] || []).forEach((path) => add(path.split("/").pop(), path, true));
  return shots;
}

function tickOf(entry, shots) {
  if (entry.tick !== undefined && entry.tick !== null) return String(entry.tick);
  for (const shot of shots) {
    const hit = shot.path.match(TICK);
    if (hit) return hit[1];
  }
  return null;
}

function shotFigure(shot, labelled) {
  const figure = document.createElement("figure");
  figure.className = "shot";
  if (labelled) {
    const caption = document.createElement("figcaption");
    caption.textContent = shot.label;
    figure.appendChild(caption);
  }
  const img = document.createElement("img");
  img.loading = "lazy";
  img.src = frameUrl(shot.path);
  img.alt = shot.label;
  figure.appendChild(img);
  return figure;
}

function fillShots(box, shots) {
  box.textContent = "";
  shots.forEach((shot) => box.appendChild(shotFigure(shot, shots.length > 1 || shot.dump)));
}

function headline(entry, shots) {
  const box = document.createElement("div");
  box.className = "headline";
  const seq = document.createElement("span");
  seq.className = "seq";
  seq.textContent = "#" + entry.seq;
  const kind = document.createElement("span");
  kind.className = "kind";
  kind.textContent = entry.kind;
  const time = document.createElement("span");
  time.className = "time";
  time.textContent = (typeof entry.t === "number" ? entry.t.toFixed(3) : entry.t) + " s";
  box.append(seq, kind, time);
  const tick = tickOf(entry, shots);
  if (tick !== null) {
    const mark = document.createElement("span");
    mark.className = "tick";
    mark.textContent = "tick " + tick;
    box.appendChild(mark);
  }
  return box;
}

function fieldTable(entry) {
  const table = document.createElement("table");
  table.className = "fields";
  for (const [key, value] of Object.entries(entry)) {
    if (key === "seq" || key === "t" || key === "kind") continue;
    const row = table.insertRow();
    const left = row.insertCell();
    left.className = "k";
    left.textContent = key;
    const right = row.insertCell();
    right.className = "v";
    if (value !== null && typeof value === "object") {
      const pre = document.createElement("pre");
      pre.textContent = JSON.stringify(value, null, 2);
      right.appendChild(pre);
    } else {
      right.textContent = String(value);
    }
  }
  return table;
}

function renderSlide() {
  const info = el("info");
  info.textContent = "";
  const entry = state.entries[state.index];
  if (!entry) {
    el("position").textContent = "第 0 / 0 筆";
    info.textContent = "這份流水帳沒有任何紀錄。";
    return;
  }
  el("position").textContent = "第 " + (state.index + 1) + " / " + state.entries.length + " 筆";
  el("prev").disabled = state.index === 0;
  el("next").disabled = state.index === state.entries.length - 1;

  let shots = state.shots[state.index];
  let carriedFrom = null;
  if (!shots.length) {
    for (let i = state.index - 1; i >= 0; i -= 1) {
      if (state.shots[i].length) {
        shots = state.shots[i];
        carriedFrom = state.entries[i].seq;
        break;
      }
    }
  }
  const box = el("shots");
  const key = shots.map((shot) => shot.path).join("|");
  // 同一組圖就不重建：重建 <img> 會讓瀏覽器整組重抓（一張原生幀約 2 MB）。
  if (box.dataset.key !== key) {
    box.dataset.key = key;
    fillShots(box, shots);
  }
  box.classList.toggle("carried", carriedFrom !== null);
  el("shot-empty").classList.toggle("hidden", shots.length > 0);

  const note = el("carry-note");
  if (carriedFrom !== null) {
    note.textContent = "沿用 seq " + carriedFrom + " 的圖";
    note.classList.remove("hidden");
  } else {
    note.classList.add("hidden");
  }

  info.appendChild(headline(entry, state.shots[state.index]));
  info.appendChild(fieldTable(entry));
}

function step(delta) {
  const total = state.entries.length;
  let target = state.index + delta;
  if (state.framesOnly) {
    while (target >= 0 && target < total && !state.shots[target].length) target += delta;
  }
  if (target < 0 || target >= total) return;
  state.index = target;
  renderSlide();
}

function buildComic() {
  const box = el("comic");
  box.textContent = "";
  state.entries.forEach((entry, index) => {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.index = String(index);
    const shots = state.shots[index];
    const text = document.createElement("div");
    text.appendChild(headline(entry, shots));
    text.appendChild(fieldTable(entry));
    card.appendChild(text);
    if (shots.length) {
      card.classList.add("paired");
      const stack = document.createElement("div");
      stack.className = "shots";
      fillShots(stack, shots);
      card.appendChild(stack);
    }
    card.addEventListener("click", () => {
      state.index = index;
      setMode("slide", true);
    });
    box.appendChild(card);
  });
  comicBuilt = true;
}

function nearestCardIndex() {
  let best = state.index;
  let closest = Infinity;
  document.querySelectorAll("#comic .card").forEach((card) => {
    const distance = Math.abs(card.getBoundingClientRect().top - 80);
    if (distance < closest) {
      closest = distance;
      best = Number(card.dataset.index);
    }
  });
  return best;
}

function setMode(mode, pinned) {
  if (mode === "comic") {
    if (!comicBuilt) buildComic();
    el("slide").classList.add("hidden");
    el("comic").classList.remove("hidden");
    const card = document.querySelector('#comic .card[data-index="' + state.index + '"]');
    if (card) card.scrollIntoView({ block: "start" });
  } else {
    // pinned＝點某張卡片指名要看那一筆；不擋掉的話會被捲動位置回推的索引蓋掉。
    if (!pinned && state.mode === "comic" && comicBuilt) state.index = nearestCardIndex();
    el("comic").classList.add("hidden");
    el("slide").classList.remove("hidden");
    window.scrollTo(0, 0);
    renderSlide();
  }
  state.mode = mode;
  el("mode-slide").classList.toggle("on", mode === "slide");
  el("mode-comic").classList.toggle("on", mode === "comic");
}

el("prev").addEventListener("click", () => step(-1));
el("next").addEventListener("click", () => step(1));
el("mode-slide").addEventListener("click", () => setMode("slide"));
el("mode-comic").addEventListener("click", () => setMode("comic"));
el("frames-only").addEventListener("change", (event) => {
  state.framesOnly = event.target.checked;
});
document.addEventListener("keydown", (event) => {
  if (state.mode !== "slide") return;
  if (event.key === "ArrowLeft") step(-1);
  else if (event.key === "ArrowRight") step(1);
});

fetch("/api/run")
  .then((response) => response.json())
  .then((data) => {
    state.entries = data.entries || [];
    state.attachments = data.attachments || {};
    state.shots = state.entries.map((entry, index) => shotsOf(entry, index));
    el("run-name").textContent = data.name;
    el("run-journal").textContent = data.journal;
    el("run-count").textContent = state.entries.length + " 筆";
    document.title = data.name + " 流水帳回放";
    renderSlide();
  })
  .catch((error) => {
    el("info").textContent = "讀取流水帳失敗：" + error;
  });
</script>
</body>
</html>
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回放過去某一輪 run 的流水帳與留存幀")
    parser.add_argument(
        "run",
        nargs="?",
        default=None,
        help="run 目錄、.tar.gz 壓縮檔或純 run 名稱；省略時取 data/runs/ 下最新的未壓縮 run",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--journal",
        default=None,
        help="run 目錄下的 jsonl 檔名；同時有多份時必填",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    run_dir = resolve_run(args.run, RUNS_ROOT)
    journal_path = find_journal(run_dir, args.journal)
    payload = build_payload(run_dir, journal_path)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    server = ThreadingHTTPServer((args.host, args.port), build_handler(run_dir, body))
    print(
        f"run: {run_dir.name}（{journal_path.name}，{len(payload['entries'])} 筆，"
        f"側傾印 {len(payload['attachments'])} 筆）"
    )
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
