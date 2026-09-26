from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from ggge_ai_2.mapparser.contract import MapReading
from ggge_ai_2.stream.contract import FramePoint, FrameVector
from ggge_ai_2.verdict import Verdict

WorldCell = tuple[int, int]
ViewCell = tuple[int, int]


@dataclass(frozen=True)
class CellVector:
    dx: float
    dy: float


class CellContent(StrEnum):
    OCCUPIED = "occupied"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class KnownMap:
    cells: Mapping[WorldCell, CellContent]


class Projection(Protocol):
    @property
    def frame_seq(self) -> int: ...

    @property
    def shift(self) -> WorldCell: ...

    def to_view(self, point: FramePoint) -> ViewCell | None: ...

    def to_frame(self, cell: WorldCell) -> FramePoint | None:
        """Return None when the cell is not in the tappable part of this frame."""
        ...

    def to_world(self, cell: ViewCell) -> WorldCell: ...

    def camera_move(self, displacement: FrameVector, at: FramePoint) -> CellVector:
        """Convert a content move measured near `at` into the camera move in cells.

        The camera moves against the content. The cell size changes with the
        position on the frame, so the result depends on `at`.
        """
        ...

    def pan_for(self, cell: WorldCell, to: FramePoint) -> FrameVector:
        """Return the content move that brings `cell` to the frame point `to`."""
        ...


class Edge(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class LocalBoard:
    projection: Projection
    extent: frozenset[WorldCell]
    cells: Mapping[WorldCell, CellContent]
    borders: Mapping[Edge, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        outside = set(self.cells) - self.extent
        if outside:
            raise ValueError(f"cells outside the extent: {sorted(outside)}")


@dataclass(frozen=True)
class CellAt:
    point: FramePoint
    cell: WorldCell

    def holds_on(self, board: LocalBoard) -> Verdict:
        view = board.projection.to_view(self.point)
        if view is None:
            return Verdict.UNREADABLE
        same = board.projection.to_world(view) == self.cell
        return Verdict.HOLDS if same else Verdict.DOES_NOT_HOLD


@dataclass(frozen=True)
class CellHolds:
    cell: WorldCell
    content: CellContent

    def holds_on(self, board: LocalBoard) -> Verdict:
        seen = board.cells.get(self.cell, CellContent.UNREADABLE)
        if self.cell not in board.extent or seen is CellContent.UNREADABLE:
            return Verdict.UNREADABLE
        return Verdict.HOLDS if seen is self.content else Verdict.DOES_NOT_HOLD


BoardFact = CellAt | CellHolds


class MapGeometry(Protocol):
    def fit(
        self,
        reading: MapReading,
        known: KnownMap,
        prior: Projection | None,
        displacement: FrameVector,
    ) -> LocalBoard | None:
        """Return None when the frame has no readable grid."""
        ...
