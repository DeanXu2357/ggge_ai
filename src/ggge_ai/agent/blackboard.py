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

    def new_ledger(self) -> BattleLedger:
        ledger = BattleLedger()
        self.ledgers.append(ledger)
        return ledger

    def archive(self, ledger: BattleLedger) -> None:
        idx = self.ledgers.index(ledger) + 1 if ledger in self.ledgers else len(self.ledgers)
        path = self.out_dir / f"battle_{idx:02d}.jsonl"
        ledger.dump(path)
        log.info("battle %d archived to %s: %s", idx, path, ledger.summary())
