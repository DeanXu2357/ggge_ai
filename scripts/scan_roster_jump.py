"""名冊跳轉掃描：用「部隊資訊」的名冊逐台跳鏡頭，靠星座／邊界重認掛回世界座標。

不推鏡找單位——名冊是完整的（我軍 10、敵軍 18），每一台都點得開、跳得到，剩下的
問題只是「跳過去那一幀在世界的哪裡」。判斷全在 runtime.roster／runtime.jumpscan
（都有離線測試），這支只負責組裝、迴圈與落證據。

usage:
  uv run python scripts/scan_roster_jump.py --serial R5CRC37JBYJ --stage-node 544,667 \
      --stop-after borders
  # 分段停點：borders / roster / jump / settle
  uv run python scripts/scan_roster_jump.py … --stop-after roster
  uv run python scripts/scan_roster_jump.py … --no-abandon

前提：手機已經停在目標系列的關卡列表（選擇關卡頁）。--stage-node 必填，理由同
dry_run_entry（棄戰回來游標會飄）。

證據：data/runs/<時間戳>/roster_jump.jsonl＋frames/。名冊 JSON 出在 roster.json，
最終座標帳與矛盾清單出在 coords.json。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from ggge_ai.runtime import board, entry, jumpscan, roster, screens, sweep
from ggge_ai.runtime.coverage import WorldGrid
from ggge_ai.runtime.device import Adb, LiveDevice
from ggge_ai.runtime.journal import Journal, rotate_runs
from ggge_ai.runtime.keyguard import Keyguard
from ggge_ai.runtime.perceive import decode

log = logging.getLogger("scan_roster_jump")

RUNS_ROOT = Path("data/runs")
JOURNAL_NAME = "roster_jump.jsonl"
STAGES = ("borders", "roster", "jump", "settle")
IN_BATTLE_STAGES = (None, "borders", "roster", "jump", "settle")

# 四界定錨的推鏡上限，逐方向各一份（沿用 sweep_scan.ZERO_LEGS 的量級：一把約
# 240px 內容位移，地圖再大也用不到 24 把）。**不 import scripts/sweep_scan.py**。
BORDER_LEGS = 24
SETTLE_POLL_S = 0.5
PANEL_SETTLE_S = 1.2
JUMP_SETTLE_S = 1.5
# 迷路重試：連兩敗就記 UNRESOLVED 換下一台（與 jumpscan.next_target 的 give_up 對齊）。
JUMP_ATTEMPTS = 2
ROSTER_ATTEMPTS = 3
ROSTER_SETTLE_S = 1.0
# 面板判定一律輪詢：詳情頁開場有轉場動畫，單發 classify 會在動畫中途讀到底下的
# 部隊資訊（0806 run 20260806-024307 就是這樣把第一格誤判成列表盡頭）。
SCREEN_ATTEMPTS = 5
END_OF_LIST_CONFIRMATIONS = 2


class Halt(RuntimeError):
    """停在原地：印出原因與當下截圖，不再點任何東西。"""


@dataclass
class Camera:
    """唯一幀源：段界與失敗點存的就是當下判定用的那一張。"""

    device: LiveDevice
    journal: Journal
    raw: bytes | None = field(default=None, init=False)
    shots: int = field(default=0, init=False)

    def screenshot(self) -> bytes:
        self.raw = self.device.screenshot()
        self.shots += 1
        return self.raw

    def grab(self) -> np.ndarray:
        return decode(self.screenshot())

    def settled(self, wait: float, sleep: Callable[[float], None]) -> np.ndarray:
        sleep(wait)
        return self.grab()

    def keep(self, label: str) -> str | None:
        path = self.journal.save_frame(self.raw, self.shots)
        self.journal.record("frame", label=label, frame=path)
        return path


@dataclass
class Scan:
    device: LiveDevice
    camera: Camera
    journal: Journal
    stop_after: str | None = None
    node: tuple[int, int] | None = None
    expect_title: str | None = entry.DEFAULT_EXPECTED_TITLE
    sleep: Callable[[float], None] = time.sleep
    grid: WorldGrid | None = None
    offset: tuple[float, float] = (0.0, 0.0)
    landmarks: dict[str, float] = field(default_factory=dict)
    ledger: jumpscan.JumpLedger = field(default_factory=jumpscan.JumpLedger)
    entries: list[roster.RosterEntry] = field(default_factory=list)
    last_source: str = jumpscan.SOURCE_CONSTELLATION

    # ---------- 流程 ----------

    def run(self) -> None:
        capture, tap, nap = self.camera.grab, self.device.tap, self.sleep

        self.begin("borders")
        self.gate(
            "select",
            entry.select_stage(
                capture, tap, node=self.node, expect_title=self.expect_title, sleep=nap
            ),
        )
        self.gate("prep", entry.open_sortie_prep(capture, tap, entry.GateReport(), sleep=nap))
        self.gate("enter", entry.enter_stage(capture, tap, sleep=nap))
        self.prepare_board()
        self.anchor()
        if self.end("borders"):
            return

        self.begin("roster")
        self.read_roster()
        if self.end("roster"):
            return

        self.begin("jump")
        self.tour()
        if self.end("jump"):
            return

        self.begin("settle")
        self.settle()
        self.end("settle")

    # ---------- 掃描前置條件 ----------

    def prepare_board(self) -> None:
        """格線 ON ＋卡條收合。兩個都是這一支後面每一步的前置條件，不是可選項。

        格線設定沿用上一輪，OFF 的時候 `board.find_lattice` 就是 None，四界定錨與
        全部星座重認一起垮；展開的卡條蓋住地圖下緣，`board.find_units` 的峰與空白格
        挑選都會被污染（sweep_scan 全程也是收攏狀態在跑）。
        """
        report = entry.GateReport()
        entry.confirm_grid(self.camera.grab, self.device.tap, report, sleep=self.sleep)
        self.journal.record("gate", name="grid", trail=list(report.trail))
        self.camera.keep("borders:grid")
        if not report.ok:
            raise Halt(f"格線閘門未過：{report.trail}")
        self.collapse_roster()
        self.camera.keep("borders:roster_collapsed")

    def collapse_roster(self) -> None:
        """先讀再點：切換鈕是同一顆的兩個位置，讀不出來盲點一下會把收好的又展開。"""
        for _ in range(ROSTER_ATTEMPTS):
            strip = screens.read_roster_strip(self.camera.grab())
            self.journal.record("roster_strip", state=strip)
            if strip == screens.ROSTER_COLLAPSED:
                return
            if strip is None:
                raise Halt("卡條狀態讀不出來，不對著它盲點")
            self.device.tap(*screens.ROSTER_TOGGLE_TAP)
            self.sleep(ROSTER_SETTLE_S)
        raise Halt("卡條收不起來，掃描的前置條件不成立")

    # ---------- 四界定錨 ----------

    def anchor(self) -> None:
        """四方向各推到界出現，西北那一幀定義世界原點；不清帳也不巡迴。"""
        frame = self.camera.settled(SETTLE_POLL_S, self.sleep)
        borders = sweep.read_borders(frame)
        for side in ("west", "north"):
            for _ in range(BORDER_LEGS):
                if side in borders:
                    break
                frame = self.pan(side)
                borders = sweep.read_borders(frame)
        self.journal.record("borders", seen={k: round(v, 1) for k, v in borders.items()})
        if "west" not in borders or "north" not in borders:
            raise Halt(f"推不到西北角：同一幀只看到 {sorted(borders)}")
        lattice = board.find_lattice(frame)
        if lattice is None:
            raise Halt("角落幀讀不出格網，世界座標無從定義")
        anchored = sweep.anchor_northwest(lattice, borders)
        if anchored is None:
            raise Halt("角落幀的格距不合理，世界座標無從定義")
        self.grid, self.offset = anchored
        self.landmarks = {"west": 0.0, "north": 0.0}
        self.camera.keep("borders:northwest")
        # 東界與南界**不在這裡量**。這一段沒有追蹤推鏡位移，`borders[side] + offset`
        # 的 offset 還是西北角那一幀的值，量出來的東南地標是錯的（0806 實機 run
        # 20260806-022510 記到 east=1717 / south=409，真值 25x20 的東界該在 ~3200
        # 世界像素）。錯的地標比沒有更危險：jump 段單側看到東界時 border_offsets
        # 會拿它當鏡位直接用。改由 jump 段 `learn_landmarks()` 機會主義補——那裡的
        # offset 是星座裁決出來的，語意才立得住。
        self.journal.record(
            "world_anchored",
            phase=[round(v, 1) for v in self.grid.phase],
            pitch=[round(self.grid.col_pitch, 1), round(self.grid.row_pitch, 1)],
            landmarks={k: round(v, 1) for k, v in self.landmarks.items()},
        )

    def pan(self, direction: str) -> np.ndarray:
        """一把推鏡。這一段只要「界出現了沒」，不做逐手勢行程驗收——定位不靠它。"""
        frame = self.camera.grab()
        origin, stroke = board.pan_stroke(
            direction, board.PAN_MAX_REACH, board.find_sightings(frame)
        )
        x1, y1, x2, y2 = board.pan_gesture(direction, origin, stroke)
        self.device.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
        self.journal.record("pan", direction=direction, reach=round(stroke, 1))
        return self.camera.settled(board.PAN_SETTLE_S, self.sleep)

    # ---------- 名冊 ----------

    def read_roster(self) -> None:
        for faction in (roster.ALLY, roster.ENEMY):
            self.open_troop_info(faction)
            for index, point in enumerate(roster.cell_taps(faction)):
                frame = self.open_detail(point)
                if frame is None:
                    self.journal.record("roster_end", faction=faction, index=index)
                    break
                found = roster.read_detail(frame, index)
                self.camera.keep(f"roster:{faction}:{index}")
                if found is None:
                    raise Halt(f"{faction}#{index} 的詳情頁讀不出陣營帶")
                self.entries.append(found)
                self.journal.record("roster_entry", **asdict(found))
                self.tap(roster.DETAIL_CLOSE_TAP, expect=screens.TROOP_INFO)
            self.close_panel()
        self.write_json("roster.json", [asdict(found) for found in self.entries])

    def open_troop_info(self, faction: str) -> None:
        self.tap(entry.BATTLE_MENU_TAP, expect=screens.BATTLE_MENU)
        self.tap(roster.BATTLE_MENU_TROOP_INFO_TAP, expect=screens.TROOP_INFO)
        self.tap(roster.TAB_TAPS[faction], expect=screens.TROOP_INFO)

    def open_detail(self, point: tuple[int, int]) -> np.ndarray | None:
        """點一格開詳情。開不出來（畫面還是部隊資訊）＝列表盡頭，不是錯誤。

        盡頭要連續兩輪讀到部隊資訊才算數：一輪可能只是詳情頁的轉場還沒蓋滿。
        """
        self.device.tap(*point)
        seen = screens.UNKNOWN
        settled = 0
        for _ in range(SCREEN_ATTEMPTS):
            frame = self.camera.settled(PANEL_SETTLE_S, self.sleep)
            seen = screens.classify(frame)
            if seen == screens.UNIT_DETAIL:
                return frame
            settled = settled + 1 if seen == screens.TROOP_INFO else 0
            if settled >= END_OF_LIST_CONFIRMATIONS:
                return None
        raise Halt(f"點 {point} 之後畫面停在 {seen}，既不是詳情頁也不是名冊盡頭")

    def close_panel(self) -> None:
        self.tap(roster.TROOP_INFO_CLOSE_TAP, expect=screens.BATTLE_MENU)
        self.tap(entry.BATTLE_MENU_CLOSE_TAP, expect=None)

    # ---------- 跳轉巡迴 ----------

    def keys(self) -> list[jumpscan.Key]:
        return [(found.faction, found.index) for found in self.entries]

    def tour(self) -> None:
        roster_keys = self.keys()
        while True:
            key = jumpscan.next_target(self.ledger, roster_keys, give_up_after=JUMP_ATTEMPTS)
            if key is None:
                break
            if not self.jump(key):
                count = self.ledger.fail(key)
                self.journal.record("jump_failed", key=list(key), failures=count)
        # 全名冊輪完一輪還是零已解＝鏈根本沒長出來，後面每一步都建在空氣上。
        if not self.ledger.jumps:
            raise Halt("整份名冊都跳過了仍然沒有任何一台定得出位置，鏈起不了頭")

    def jump(self, key: jumpscan.Key) -> bool:
        faction, index = key
        self.open_troop_info(faction)
        point = roster.cell_taps(faction)[index]
        if self.open_detail(point) is None:
            raise Halt(f"{faction}#{index} 點不開詳情頁——名冊順序與跳轉對不上")
        self.device.tap(*roster.DETAIL_SELECT_TAP)
        landing = self.camera.settled(JUMP_SETTLE_S, self.sleep)
        self.camera.keep(f"jump:{faction}:{index}:landing")
        peaks = board.find_units(landing)
        target = jumpscan.target_peak(peaks)
        self.dismiss(faction, landing, peaks)
        clean = self.camera.settled(JUMP_SETTLE_S, self.sleep)
        self.camera.keep(f"jump:{faction}:{index}:clean")
        if target is None:
            return False
        offset = self.locate(clean)
        if offset is None:
            return False
        grid = self.world()
        cell = grid.cell_of((target[0] + offset[0], target[1] + offset[1]))
        self.ledger.record(
            jumpscan.Jump(
                key=key,
                cell=cell,
                source=self.last_source,
                offset=offset,
                peaks=tuple(board.find_units(clean)),
            )
        )
        self.journal.record(
            "jump",
            key=list(key),
            cell=list(cell),
            source=self.last_source,
            offset=[round(v, 1) for v in offset],
        )
        return True

    def locate(self, frame: np.ndarray) -> tuple[float, float] | None:
        """乾淨幀 → 鏡位。星座優先，界線是第二註冊來源；兩個都不說話就是迷路。"""
        grid = self.world()
        found = sweep.constellation_offset(self.ledger.references(), board.find_units(frame), grid)
        if found.offset is not None:
            self.last_source = jumpscan.SOURCE_CONSTELLATION
            self.learn_landmarks(frame, found.offset)
            return found.offset
        axes = sweep.border_offsets(grid, self.landmarks, sweep.read_borders(frame))
        if "x" in axes and "y" in axes:
            self.last_source = jumpscan.SOURCE_BORDER
            return (axes["x"], axes["y"])
        self.journal.record("lost", reason=found.reason, axes=sorted(axes))
        return None

    def learn_landmarks(self, frame: np.ndarray, offset: tuple[float, float]) -> None:
        """星座裁決過的鏡位＋這一幀看得到的界＝一條地標。**只吃星座的 offset**：
        拿界線解出來的 offset 回頭寫界線是循環論證。

        已經有的側不覆寫，只做一致性檢查——地標一旦寫錯，之後每一次單側重認都跟著
        錯，而且沒有任何後手察覺得到。對不上就記進流水帳等人看。
        """
        grid = self.world()
        for side, position in sweep.read_borders(frame).items():
            axis = 0 if side in ("west", "east") else 1
            pitch = grid.col_pitch if axis == 0 else grid.row_pitch
            world = position + offset[axis]
            known = self.landmarks.get(side)
            if known is None:
                self.landmarks[side] = world
                self.journal.record("landmark_learned", side=side, world=round(world, 1))
            elif abs(known - world) > sweep.EDGE_AGREEMENT_PITCH * pitch:
                self.journal.record(
                    "landmark_conflict",
                    side=side,
                    known=round(known, 1),
                    saw=round(world, 1),
                    slack=round(sweep.EDGE_AGREEMENT_PITCH * pitch, 1),
                )

    def dismiss(self, faction: str, frame: np.ndarray, peaks) -> None:
        """敵方＝點一個空白格；我方＝右下「返回」（移動格點下去是真的下移動指令）。"""
        if faction == roster.ALLY:
            self.device.tap(*jumpscan.ALLY_DISMISS_TAP, intent=jumpscan.ALLY_DISMISS_INTENT)
            return
        # 這裡還沒定位（解除要在 locate 之前，紅格會污染密度峰），所以格心不能用
        # 世界鏡位換算——`self.offset` 是西北角那一幀的值，跳轉之後早就過期了。
        # 改用落點幀自己的格線相位：空白格只需要「螢幕上哪一點是格心」。
        lattice = board.find_lattice(frame)
        screen_grid = None if lattice is None else WorldGrid.anchor(lattice)
        if screen_grid is None:
            raise Halt("落點幀讀不出格網，挑不出解除用的空白格")
        blank = jumpscan.blank_cell_tap(frame, screen_grid, (0.0, 0.0), peaks)
        if blank is None:
            raise Halt("落點幀找不到任何空白格可以解除敵方指定")
        self.device.tap(*blank)

    def world(self) -> WorldGrid:
        if self.grid is None:
            raise Halt("世界座標還沒定錨")
        return self.grid

    # ---------- 收尾 ----------

    def settle(self) -> None:
        grid = self.world()
        flags = jumpscan.audit(self.ledger, grid)
        report = jumpscan.ledger_report(self.ledger, self.keys())
        self.journal.record("settle", resolved=len(self.ledger.jumps), contradictions=len(flags))
        self.write_json(
            "coords.json",
            {
                "units": report,
                "contradictions": [
                    {
                        "seen_from": list(flag.seen_from),
                        "about": list(flag.about),
                        "expected": [round(v, 1) for v in flag.expected],
                        "nearest": None if flag.nearest is None else round(flag.nearest, 1),
                    }
                    for flag in flags
                ],
            },
        )
        log.info("resolved %d units, %d contradictions", len(self.ledger.jumps), len(flags))

    def abandon(self) -> None:
        self.begin("abandon")
        self.gate(
            "abandon", entry.abandon_battle(self.camera.grab, self.device.tap, sleep=self.sleep)
        )
        self.end("abandon")

    # ---------- 通用 ----------

    def tap(self, point: tuple[int, int], *, expect: str | None, intent: str = "") -> np.ndarray:
        self.device.tap(*point, intent=intent)
        if expect is None:
            return self.camera.settled(PANEL_SETTLE_S, self.sleep)
        seen = screens.UNKNOWN
        for _ in range(SCREEN_ATTEMPTS):
            frame = self.camera.settled(PANEL_SETTLE_S, self.sleep)
            seen = screens.classify(frame)
            if seen == expect:
                return frame
        raise Halt(f"點 {point} 之後畫面是 {seen}，期望 {expect}")

    def write_json(self, name: str, payload: object) -> None:
        path = self.journal.path.parent / name
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.journal.record("wrote", file=name)

    def begin(self, name: str) -> None:
        self.device.ensure_unlocked(force=True)
        self.journal.record("stage", name=name)
        self.camera.grab()
        self.camera.keep(f"{name}:start")

    def end(self, name: str) -> bool:
        log.info("stage %s done (frame %s)", name, self.camera.keep(f"{name}:end"))
        return self.stop_after == name

    def gate(self, name: str, report: entry.GateReport) -> None:
        self.journal.record("gate", name=name, trail=list(report.trail))
        if report.ok:
            return
        raise Halt(f"{name} 閘門未過：{report.trail} {[s.detail for s in report.failures]}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--stop-after", choices=STAGES, default=None)
    parser.add_argument("--stage-node", required=True, help="X,Y：要打的關卡節點（必填）")
    parser.add_argument("--expect-title", default=entry.DEFAULT_EXPECTED_TITLE)
    parser.add_argument("--abandon", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--run-dir", type=Path, default=None)
    return parser.parse_args()


def point(text: str) -> tuple[int, int]:
    x, y = (int(value) for value in text.split(","))
    return x, y


def title(text: str | None) -> str | None:
    return None if text is None or text.lower() == "none" else text


def open_run(run_dir: Path | None) -> Journal:
    if run_dir is None:
        rotate_runs(RUNS_ROOT)
        run_dir = RUNS_ROOT / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    return Journal(run_dir / JOURNAL_NAME)


def soft_capture(camera: Camera) -> Callable[[], np.ndarray | None]:
    def capture() -> np.ndarray | None:
        try:
            return camera.grab()
        except Exception:
            log.warning("keyguard capture failed", exc_info=True)
            return None

    return capture


def build(args: argparse.Namespace, journal: Journal) -> Scan:
    adb = Adb(serial=args.serial)
    device = LiveDevice(adb=adb)
    camera = Camera(device=device, journal=journal)
    device.keyguard = Keyguard(shell=adb.shell, capture=soft_capture(camera))
    return Scan(
        device=device,
        camera=camera,
        journal=journal,
        stop_after=args.stop_after,
        node=point(args.stage_node),
        expect_title=title(args.expect_title),
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    journal = open_run(args.run_dir)
    run_dir = journal.path.parent
    print(f"run dir: {run_dir}")
    scan = build(args, journal)
    journal.record("scan_start", stop_after=args.stop_after, stage_node=args.stage_node)
    try:
        scan.run()
        if args.abandon and args.stop_after in IN_BATTLE_STAGES:
            scan.abandon()
    except Halt as stop:
        frame = scan.camera.keep("halt")
        journal.record("halt", reason=str(stop), frame=frame)
        print(f"HALT: {stop}")
        print(f"當下截圖: {run_dir / frame if frame else '(無)'}")
        return 1
    except Exception as boom:
        frame = scan.camera.keep("crash")
        journal.record("crash", reason=repr(boom), frame=frame)
        print(f"CRASH: {boom!r}")
        raise
    journal.record("scan_end")
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
