"""Battle ledger: the per-battle event log feeding the run blackboard.

Everything recorded here comes from what the screen showed during one
battle. It is attribution evidence for the current process only and must
never seed a future run (docs/agent-architecture.md).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Point = tuple[int, int]


@dataclass
class BattleLedger:
    started_at: float = field(default_factory=time.time)
    events: list[dict[str, Any]] = field(default_factory=list)
    turn: int = 1
    outcome: str | None = None

    def record(self, kind: str, **data: Any) -> None:
        self.events.append(
            {
                "t": round(time.time() - self.started_at, 1),
                "turn": self.turn,
                "kind": kind,
                **data,
            }
        )

    def snapshot(
        self, allies: list[Point], enemies: list[Point], third_party: list[Point]
    ) -> None:
        self.record("factions", allies=allies, enemies=enemies, third_party=third_party)

    def next_turn(self) -> None:
        self.record("end_turn")
        self.turn += 1

    def finish(self, outcome: str) -> None:
        self.outcome = outcome
        self.record("finish", outcome=outcome)

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
