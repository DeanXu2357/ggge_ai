from __future__ import annotations

from dataclasses import dataclass, replace

from ggge_ai_2.mapgeom.contract import KnownMap, LocalBoard
from ggge_ai_2.uisim.contract import Outcome


@dataclass(frozen=True)
class FakeDomain:
    absorbed: tuple[tuple[object, str | None], ...] = ()
    boards: int = 0

    def absorb(self, intent: object, outcome: Outcome | None) -> FakeDomain:
        name = outcome.name if outcome else None
        return replace(self, absorbed=(*self.absorbed, (intent, name)))

    def observe(self, board: LocalBoard) -> FakeDomain:
        return replace(self, boards=self.boards + 1)

    def known_map(self) -> KnownMap:
        return KnownMap({})
