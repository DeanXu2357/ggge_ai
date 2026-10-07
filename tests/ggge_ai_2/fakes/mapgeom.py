from __future__ import annotations

from ggge_ai_2.mapgeom.contract import Alignment, KnownMap, LocalBoard


class NoMapGeometry:
    def align(
        self, board: LocalBoard, known: KnownMap, prior: Alignment | None
    ) -> Alignment | None:
        raise AssertionError("no map on these screens")

    def merge(self, known: KnownMap, board: LocalBoard, alignment: Alignment) -> KnownMap:
        raise AssertionError("no map on these screens")
