"""流水帳 jsonl＋逐 tick 原生幀（同一個 run 目錄），以及舊 run 壓縮輪替。"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FRAMES_DIRNAME = "frames"
ARCHIVE_SUFFIX = ".tar.gz"
STAGING_SUFFIX = ".part"


@dataclass
class FrameStore:
    """run 目錄裡的原生幀：拿到什麼位元組就寫什麼，不縮圖也不重新編碼
    ——縮過的圖擋掉過離線復現。"""

    run_dir: Path
    dirname: str = FRAMES_DIRNAME
    seq: int = 0

    @property
    def directory(self) -> Path:
        return self.run_dir / self.dirname

    def save(self, frame: bytes, tick: int) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        name = f"{self.seq:05d}-tick{tick:04d}.png"
        self.seq += 1
        (self.directory / name).write_bytes(frame)
        return f"{self.dirname}/{name}"


@dataclass
class Journal:
    path: Path
    started_at: float = field(default_factory=time.time)
    seq: int = 0
    frames: FrameStore = field(init=False)

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.frames = FrameStore(self.path.parent)

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

    def save_frame(self, frame: bytes | None, tick: int) -> str | None:
        """回傳相對 run 目錄的幀檔路徑，供流水帳指回這筆紀錄當下看的那張圖。"""
        if frame is None:
            return None
        return self.frames.save(frame, tick)

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]


def rotate_runs(runs_root: Path) -> tuple[Path, ...]:
    """開新 run 目錄之前呼叫：既有 run 目錄各自打包成 tar.gz 後刪除原目錄，
    任何時刻只有最新一個未壓縮。已壓縮的是檔案不是目錄，自然跳過。

    單一執行程序假設——兩個 run 同時開跑會互相壓對方，未做跨程序互斥。
    """
    if not runs_root.is_dir():
        return ()
    archives = [
        _archive(entry)
        for entry in sorted(runs_root.iterdir())
        if entry.is_dir() and not entry.is_symlink()
    ]
    return tuple(archives)


def _archive(run_dir: Path) -> Path:
    archive = run_dir.with_name(run_dir.name + ARCHIVE_SUFFIX)
    # 先落暫存名再改名：中途死掉時留下的殘檔不會被當成壓好的 run。
    staging = archive.with_name(archive.name + STAGING_SUFFIX)
    with tarfile.open(staging, "w:gz") as bundle:
        bundle.add(run_dir, arcname=run_dir.name)
    os.replace(staging, archive)
    shutil.rmtree(run_dir)
    return archive
