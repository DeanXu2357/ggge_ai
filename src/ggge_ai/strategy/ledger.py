"""資源帳本：開機同步、動作效果更新、一致性探針。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Ledger:
    resources: dict[str, int] = field(default_factory=dict)
    synced: bool = False

    def sync(self) -> None:
        raise NotImplementedError("批 3：帳本 v1")

    def apply(self, effects: Mapping[str, int]) -> None:
        raise NotImplementedError("批 3：帳本 v1")

    def probe(self, observed: Mapping[str, int]) -> bool:
        raise NotImplementedError("批 3：帳本 v1")

    def symbols(self) -> dict[str, Any]:
        symbols: dict[str, Any] = {"ledger_synced": self.synced}
        symbols.update({f"resource.{name}": value for name, value in self.resources.items()})
        return symbols


class OfflineLedger(Ledger):
    """dry-run 假帳本：不碰畫面，同步是空動作。"""

    def sync(self) -> None:
        self.synced = True
