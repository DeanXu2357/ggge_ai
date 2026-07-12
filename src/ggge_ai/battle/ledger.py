"""Battle ledger: the per-battle event log feeding the run blackboard.

Everything recorded here comes from what the screen showed during one
battle. It is attribution evidence for the current process only and must
never seed a future run (docs/agent-architecture.md).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2

log = logging.getLogger(__name__)

Point = tuple[int, int]

# events worth a screenshot: the decision points a human would need to see
# to judge whether the move made sense. everything else (animations,
# faction snapshots, engagement confirms) shares the same screen a nearby
# decision event already captured.
FRAME_KINDS = frozenset(
    {
        "select_unit",
        "move",
        "attack",
        "standby",
        "tactical_map",
        "story_dialog",
        "neutral_tap",
        "llm_read",
        "auto_guard",
        "hidden_battle_warning",
        "unit_detail_modal",
        "stage_info",
        "post_select_probe",
        "end_turn",
        "finish",
    }
)
FRAME_MAX_EDGE = 1280
FRAME_JPEG_QUALITY = 85


@dataclass
class BattleLedger:
    started_at: float = field(default_factory=time.time)
    events: list[dict[str, Any]] = field(default_factory=list)
    turn: int = 1
    outcome: str | None = None
    frames_dir: Path | None = None
    frame_rel_prefix: str = ""

    def record(self, kind: str, frame: Any = None, **data: Any) -> None:
        event = {
            "t": round(time.time() - self.started_at, 1),
            "turn": self.turn,
            "kind": kind,
            **data,
        }
        if kind in FRAME_KINDS:
            event["frame"] = self._save_frame(frame, kind, len(self.events))
        self.events.append(event)

    def _save_frame(self, frame: Any, kind: str, seq: int) -> str | None:
        if frame is None or self.frames_dir is None:
            return None
        try:
            h, w = frame.shape[:2]
            long_edge = max(h, w)
            if long_edge > FRAME_MAX_EDGE:
                scale = FRAME_MAX_EDGE / long_edge
                frame = cv2.resize(frame, (round(w * scale), round(h * scale)))
            self.frames_dir.mkdir(parents=True, exist_ok=True)
            name = f"t{seq:04d}_turn{self.turn}_{kind}.jpg"
            path = self.frames_dir / name
            ok = cv2.imwrite(
                str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, FRAME_JPEG_QUALITY]
            )
            if not ok:
                return None
            return f"{self.frame_rel_prefix}/{name}" if self.frame_rel_prefix else name
        except Exception:
            log.warning("failed to save frame for event %r, skipping", kind, exc_info=True)
            return None

    def snapshot(
        self, allies: list[Point], enemies: list[Point], third_party: list[Point]
    ) -> None:
        self.record("factions", allies=allies, enemies=enemies, third_party=third_party)

    def next_turn(self, frame: Any = None) -> None:
        self.record("end_turn", frame=frame)
        self.turn += 1

    def finish(self, outcome: str, frame: Any = None) -> None:
        self.outcome = outcome
        self.record("finish", frame=frame, outcome=outcome)

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for e in self.events:
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        snaps = [e for e in self.events if e["kind"] == "factions"]

        def factions(s: dict[str, Any]) -> dict[str, int]:
            return {k: len(s[k]) for k in ("allies", "enemies", "third_party")}

        return {
            "outcome": self.outcome,
            "turns": self.turn,
            "duration_s": self.events[-1]["t"] if self.events else 0.0,
            "event_counts": counts,
            "first_factions": factions(snaps[0]) if snaps else None,
            "last_factions": factions(snaps[-1]) if snaps else None,
        }

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for e in self.events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
