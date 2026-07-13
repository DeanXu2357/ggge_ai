"""Run blackboard: the process-scoped memory of one execution.

One process = one explicit goal plus the allowed growth actions. Repeated
stage attempts within the process share this blackboard (stage intel,
attempt ledgers, belief updates); when the process exits the memory is
gone and the next run rebuilds it from scratch (docs/agent-architecture.md).
The dumped ledger files are engineering-analysis artifacts, never a prior
for a later run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..battle.ledger import BattleLedger

log = logging.getLogger(__name__)


def _default_out_dir() -> Path:
    return Path("data/runs") / time.strftime("%Y%m%d-%H%M%S")


@dataclass
class RunBlackboard:
    goal: str = ""
    out_dir: Path = field(default_factory=_default_out_dir)
    intel: dict[str, Any] = field(default_factory=dict)
    ledgers: list[BattleLedger] = field(default_factory=list)
    # a battle's ledger is opened at the stage-info screen (to log the victory
    # /defeat conditions frame) and reused by the battle that follows, so both
    # belong to one battle_NN.jsonl. None once the battle has claimed it.
    pending_ledger: BattleLedger | None = None

    def new_ledger(self) -> BattleLedger:
        idx = len(self.ledgers) + 1
        ledger = BattleLedger(
            frames_dir=self.out_dir / "frames" / f"battle_{idx:02d}",
            frame_rel_prefix=f"frames/battle_{idx:02d}",
            stream_path=self.out_dir / f"battle_{idx:02d}.jsonl",
        )
        self.ledgers.append(ledger)
        self.pending_ledger = ledger
        return ledger

    def open_ledger(self) -> BattleLedger:
        """Ledger for the upcoming battle: reuse one already opened at the
        stage-info screen this process, else start a fresh one."""
        return self.pending_ledger or self.new_ledger()

    def take_ledger(self) -> BattleLedger:
        """Claim the battle's ledger (opening one if none is pending) and
        clear the pending slot so the next battle starts clean."""
        ledger = self.pending_ledger or self.new_ledger()
        self.pending_ledger = None
        return ledger

    def archive(self, ledger: BattleLedger) -> None:
        idx = self.ledgers.index(ledger) + 1 if ledger in self.ledgers else len(self.ledgers)
        path = self.out_dir / f"battle_{idx:02d}.jsonl"
        ledger.dump(path)
        log.info("battle %d archived to %s: %s", idx, path, ledger.summary())
