"""實機通道唯讀探針：截一張圖，報畫面名、AUTO 態、格網、單位目擊。

**不點任何東西**——只驗證 adb 通道、原生幀直通與辨識層在實機上的判讀，給
live-tester 當第一步對帳工具。

usage:
  uv run python scripts/probe_live_channel.py [--serial R5CRC37JBYJ] [--save out.png]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ggge_ai.runtime import board, screens
from ggge_ai.runtime.device import Adb, LiveDevice
from ggge_ai.runtime.perceive import LivePerceiver, decode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", default=None)
    parser.add_argument("--save", type=Path, default=None, help="把原生幀位元組落檔")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = LiveDevice(adb=Adb(serial=args.serial))
    observation = LivePerceiver(device=device).look()
    raw = observation.frame or b""
    frame = decode(raw)

    print(f"frame        : {len(raw)} bytes, decoded {frame.shape[1]}x{frame.shape[0]}")
    print(f"screen       : {observation.screen}")
    print(f"scores       : { {k: round(v, 3) for k, v in screens.scores(frame).items() if v > 0.5} }")
    print(f"auto switch  : {observation.evidence['auto']}")
    print(f"grid setting : {observation.evidence['grid_setting']}")
    print(f"frame sig    : {observation.evidence['frame_sig']}")

    lattice = board.read_lattice(frame)
    if lattice is None:
        print("lattice      : none (顯示方格 OFF 或不在地圖上)")
    else:
        print(
            f"lattice      : {len(lattice.cols)} cols x {len(lattice.rows)} rows, "
            f"pitch {lattice.col_pitch:.1f}/{lattice.row_pitch:.1f}"
        )
    sightings = board.find_sightings(frame)
    print(f"unit peaks   : {len(sightings)}")
    for sighting in sightings:
        print(f"   ({sighting.point[0]:7.1f},{sighting.point[1]:7.1f}) hint={sighting.hint}")

    if args.save is not None:
        args.save.write_bytes(raw)
        print(f"saved        : {args.save}")


if __name__ == "__main__":
    main()
