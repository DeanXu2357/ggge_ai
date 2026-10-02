from __future__ import annotations

from ggge_ai_2.mapgeom.contract import LocalBoard


class NoMapGeometry:
    def fit(self, *args) -> LocalBoard | None:
        raise AssertionError("no map on these screens")
