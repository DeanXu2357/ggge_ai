from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ggge_ai_2.mapgeom.contract import Alignment, KnownMap, WorldCell


@dataclass(frozen=True)
class Probe:
    cell: WorldCell


@dataclass(frozen=True)
class Explored:
    pass


class MapSyncPlan(Protocol):
    def next(self, known: KnownMap, camera: Alignment) -> Probe | Explored | None:
        """Return None when no cell to probe is in view."""
        ...
