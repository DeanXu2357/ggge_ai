"""帳目閉合檢查（silent-events 批C，issue #27）：離線讀流水帳，重建每單位
per-turn HP 時間線，把 HP 變化分配給具名事件，輸出未解殘差率＝完備性分數。

純離線工程分析，輸出不得當任何執行路徑的先驗（docs/silent-events.md 紅線）。

usage:
    uv run python scripts/audit_run.py data/runs/20260713-225448
    uv run python scripts/audit_run.py data/runs/<ts>/battle_01.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ggge_ai.agent.closure import close_target, run_summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="run 目錄或單一 battle_NN.jsonl 檔")
    args = parser.parse_args()

    reports = close_target(args.target)
    if not reports:
        raise SystemExit(f"找不到流水帳：{args.target}")

    for i, report in enumerate(reports):
        if i:
            print()
        print(report.render())

    if len(reports) > 1:
        print()
        print(run_summary(reports))


if __name__ == "__main__":
    main()
