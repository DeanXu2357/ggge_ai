"""流水帳 jsonl（兩層共用格式）。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Journal:
    path: Path
    started_at: float = field(default_factory=time.time)
    seq: int = 0

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, **fields: Any) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "seq": self.seq,
            "t": round(time.time() - self.started_at, 3),
            "kind": kind,
            **fields,
        }
        self.seq += 1
        # 逐筆寫穿：主機中途死掉時磁碟上仍留得住已發生的事。
        # default=str 是安全網——流水帳不准因為某個欄位不可序列化就打斷跑批。
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return entry

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
