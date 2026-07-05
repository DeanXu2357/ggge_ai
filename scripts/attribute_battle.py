"""Post-battle attribution v1: split a battle into 數值差距 vs 程式缺陷.

usage: uv run python scripts/attribute_battle.py data/runs/20260705-232132
       uv run python scripts/attribute_battle.py data/runs/<ts>/battle_01.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ggge_ai.agent.attribution import _iter_paths, attribute_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "target", type=Path, help="run 目錄或單一 battle_NN.jsonl 檔"
    )
    args = parser.parse_args()

    paths = list(_iter_paths(args.target))
    if not paths:
        raise SystemExit(f"找不到流水帳：{args.target}")

    for i, path in enumerate(paths):
        if i:
            print()
        print(attribute_file(path).render())


if __name__ == "__main__":
    main()
