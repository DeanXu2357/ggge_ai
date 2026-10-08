from __future__ import annotations

from dataclasses import dataclass, replace

from ggge_ai_2.uisim.contract import Outcome


@dataclass(frozen=True)
class FakeDomain:
    absorbed: tuple[tuple[object, str | None], ...] = ()

    def absorb(self, intent: object, outcome: Outcome | None) -> FakeDomain:
        name = outcome.name if outcome else None
        return replace(self, absorbed=(*self.absorbed, (intent, name)))
