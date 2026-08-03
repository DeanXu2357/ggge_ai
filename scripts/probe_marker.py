"""標記格的實機標定探針：點一個空格、看它填出什麼色、看它撐得住幾種推法。

前提：手機已經停在戰鬥地圖上、顯示方格已經開著（`dry_run_entry.py --stop-after grid`
跑完就是這個狀態）。這支**會點畫面也會推畫面**，但只點沒有單位的空格——點到有單位
的格是選取單位，那不是這支要問的事。

要標的三件事，全部靠這一輪的幀與 JSON：

1. **填色長什麼樣**：色簽的 HSV 與尺寸（`board.MARKER_TOLERANCE` 目前是暫定值，
   要靠這裡量出來的分佈調）。
2. **它撐得住哪種推法**：輕推（短行程）與重推（`PAN_MAX_REACH`）各一次，每把之後
   都重找一次——使用者實測填色很容易因為移動地圖而消失，這裡量的是「哪一種推法會
   弄丟它」。
3. **再點同一格會怎樣**：填色留著、消失、還是換個樣子。

usage:
  uv run python scripts/probe_marker.py [--serial R5CRC37JBYJ] [--settle 1.5]

證據：data/runs/<時間戳>-marker-probe/probe.jsonl＋frames/（每一步各一張原生幀）。
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from ggge_ai.runtime import board, coverage
from ggge_ai.runtime.device import Adb, LiveDevice, TapRefused, check_tap
from ggge_ai.runtime.journal import Journal, rotate_runs
from ggge_ai.runtime.perceive import decode

log = logging.getLogger("probe_marker")

RUNS_ROOT = Path("data/runs")
JOURNAL_NAME = "probe.jsonl"
RUN_SUFFIX = "-marker-probe"
TAP_INTENT = "mark"
# 輕推與重推：短行程問「日常的一把推移弄不弄得掉它」，滿行程問「歸零那種用力推
# 之後還在不在」。兩個數字就是掃描實際會打出去的兩種手勢。
LIGHT_REACH = coverage.LEG_LIMIT["x"] / coverage.NOMINAL_GAIN
HEAVY_REACH = board.PAN_MAX_REACH


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--settle", type=float, default=board.PAN_SETTLE_S)
    return parser.parse_args()


def open_run() -> Journal:
    rotate_runs(RUNS_ROOT)
    run_dir = RUNS_ROOT / (time.strftime("%Y%m%d-%H%M%S") + RUN_SUFFIX)
    run_dir.mkdir(parents=True, exist_ok=True)
    return Journal(run_dir / JOURNAL_NAME)


class Probe:
    def __init__(self, device: LiveDevice, journal: Journal, settle: float) -> None:
        self.device = device
        self.journal = journal
        self.settle = settle
        self.shots = 0

    def grab(self, label: str) -> np.ndarray:
        raw = self.device.screenshot()
        self.shots += 1
        path = self.journal.save_frame(raw, self.shots)
        self.journal.record("frame", label=label, frame=path)
        print(f"[{label}] frame -> {path}")
        return decode(raw)

    def look(self, label: str, signature: board.MarkerSignature | None) -> tuple[np.ndarray, ...]:
        frame = self.grab(label)
        spot = None if signature is None else board.find_marker(frame, signature)
        self.journal.record(
            "marker_seen",
            label=label,
            spot=None if spot is None else [round(value, 1) for value in spot],
        )
        print(f"[{label}] find_marker -> {spot}")
        return (frame, spot)

    def tap(self, point: board.Point, label: str) -> None:
        self.journal.record("tap", label=label, point=[int(point[0]), int(point[1])])
        print(f"[{label}] tap {int(point[0])},{int(point[1])}")
        self.device.tap(int(point[0]), int(point[1]), intent=TAP_INTENT)
        time.sleep(self.settle)

    def pan(self, direction: str, reach: float, origin: board.Point, label: str) -> None:
        x1, y1, x2, y2 = board.pan_gesture(direction, origin, reach)
        self.journal.record(
            "pan", label=label, direction=direction, reach=round(reach, 1), gesture=[x1, y1, x2, y2]
        )
        print(f"[{label}] pan {direction} reach={reach:.0f} {x1},{y1} -> {x2},{y2}")
        self.device.swipe(x1, y1, x2, y2, board.PAN_DURATION_S)
        time.sleep(self.settle)

    def learn(self, before: np.ndarray, after: np.ndarray, point: board.Point, label: str):
        signature = board.learn_marker(before, after, point)
        self.journal.record(
            "learn_marker", label=label, signature=None if signature is None else asdict(signature)
        )
        print(f"[{label}] learn_marker -> {signature}")
        return signature


def empty_cells(frame: np.ndarray) -> list[board.Point]:
    """畫面上沒有目擊、點得下去、整格在地圖區內的格心（離畫面中心近的排前面）。"""
    lattice = board.find_lattice(frame)
    if lattice is None:
        return []
    seen = board.find_sightings(frame)
    pitch = (lattice.col_pitch, lattice.row_pitch)
    x, y, w, h = board.MAP_REGION
    out: list[board.Point] = []
    for x0, x1 in zip(lattice.cols, lattice.cols[1:], strict=False):
        for y0, y1 in zip(lattice.rows, lattice.rows[1:], strict=False):
            if x0 < x or y0 < y or x1 > x + w or y1 > y + h:
                continue
            near = (x0 - pitch[0] / 2, y0 - pitch[1] / 2, x1 + pitch[0] / 2, y1 + pitch[1] / 2)
            if any(
                near[0] <= point[0] <= near[2] and near[1] <= point[1] <= near[3]
                for point in (sighting.point for sighting in seen)
            ):
                continue
            centre = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
            try:
                check_tap(int(centre[0]), int(centre[1]))
            except TapRefused:
                continue
            out.append(centre)
    middle = (x + w / 2.0, y + h / 2.0)
    return sorted(out, key=lambda c: (c[0] - middle[0]) ** 2 + (c[1] - middle[1]) ** 2)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    journal = open_run()
    probe = Probe(LiveDevice(adb=Adb(serial=args.serial)), journal, args.settle)

    start = probe.grab("start")
    cells = empty_cells(start)
    print(f"[start] empty cells: {len(cells)}")
    if len(cells) < 2:
        journal.record("halt", reason="no empty cell to tap")
        print("找不到兩個沒有目擊的空格——確認畫面停在戰鬥地圖上且顯示方格已開。")
        return

    first = cells[0]
    probe.tap(first, "tap:first")
    marked, _ = probe.look("after:first-tap", None)
    signature = probe.learn(start, marked, first, "learn:first")
    if signature is None:
        journal.record("halt", reason="no fill appeared")
        print("點下去沒有出現合格的填色塊——比對 frames 看是點到單位還是點擊被吃掉。")
        return

    origin = board.pick_pan_origin(board.find_sightings(marked))
    for name, reach in (("light", LIGHT_REACH), ("heavy", HEAVY_REACH)):
        probe.pan("east", reach, origin, f"pan:{name}")
        probe.look(f"after:pan-{name}", signature)

    # 再點同一格：使用者說填色會留在原格，這一步是拿實機把那句話釘死。推移後
    # 重找不到就跳過——舊螢幕座標下面已經是別的格，點下去問不出「同一格」的事。
    frame, spot = probe.look("before:retap", signature)
    if spot is not None:
        probe.tap(spot, "tap:same-cell")
        probe.look("after:retap", signature)
    else:
        journal.record("skip", label="tap:same-cell", reason="marker not found after pans")
        print("[tap:same-cell] 跳過——推移後重找不到標記，同格座標已失準。")

    # 點另一個空格：填色應該整塊搬過去，舊格恢復原樣。空格清單要用當下幀重算——
    # 起始幀算的螢幕點經過兩把推移，下面可能已經站著單位。
    before, _ = probe.look("before:second-tap", signature)
    fresh = empty_cells(before)
    if not fresh:
        journal.record("halt", reason="no empty cell for the second tap")
        print("當下幀找不到空格可點——第二段量測作罷。")
        return
    second = max(
        fresh,
        key=lambda c: (c[0] - first[0]) ** 2 + (c[1] - first[1]) ** 2
        if spot is None
        else (c[0] - spot[0]) ** 2 + (c[1] - spot[1]) ** 2,
    )
    probe.tap(second, "tap:second")
    moved, _ = probe.look("after:second-tap", signature)
    probe.learn(before, moved, second, "learn:second")

    print(f"done -> {journal.path.parent}")


if __name__ == "__main__":
    main()
