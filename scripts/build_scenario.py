"""名冊採集 run → scenario.json＋intel_report.json（離線，不碰實機）。

    uv run python scripts/build_scenario.py data/runs/<時間戳> [--no-llm]

--no-llm（或 GGGE_LLM=0）跑全離線：數字照樣齊，自由文字留佔位＋待補標記。
真值檔缺席時盤面退 25x20 預設，報告記 board_source。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ggge_ai.runtime.panel_text import OllamaPanelTextReader
from ggge_ai.stage.roster_offline import run_offline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--stage-truth", type=Path)
    args = parser.parse_args()

    reader = None if args.no_llm else OllamaPanelTextReader.from_env()
    truth = (
        json.loads(args.stage_truth.read_text(encoding="utf-8"))
        if args.stage_truth is not None
        else None
    )
    code = run_offline(args.run_dir, reader=reader, stage_truth=truth)
    print(f"scenario written under {args.run_dir} (llm={reader is not None}, exit={code})")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
