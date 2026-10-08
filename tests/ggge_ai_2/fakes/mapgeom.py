from __future__ import annotations

from ggge_ai_2.mapgeom.contract import Alignment, KnownMap


class NoMapGeometry:
    def align(self, *args) -> Alignment | None:
        raise AssertionError("no map on these screens")

    def merge(self, *args) -> KnownMap:
        raise AssertionError("no map on these screens")
