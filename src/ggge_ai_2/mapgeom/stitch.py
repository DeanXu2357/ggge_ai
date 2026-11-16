from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from ggge_ai_2.mapgeom.contract import (
    Axis,
    CellContent,
    CellSeen,
    MapCell,
    MapJudgment,
    MapUnit,
    NameMask,
    Side,
    UnitId,
    View,
    ViewUnit,
)

# A shift (dx, dy) moves a cell (x, y) of one frame to (x + dx, y + dy) of another frame.
Shift = tuple[int, int]
_ToMap = Callable[[tuple[int, int], Shift], MapCell]

MIN_SHAPE_OVERLAP = 12
MIN_SHAPE_OCCUPIED = 2
SHAPE_AGREEMENT = 0.9
JOIN_AGREEMENT = 0.8
CELL_AGREEMENT = 2 / 3
SAME_NAME = 0.75
NAME_SLACK = (4, 3)

_CONTENT = {CellSeen.OCCUPIED: CellContent.OCCUPIED, CellSeen.EMPTY: CellContent.EMPTY}


@dataclass
class _Group:
    members: dict[int, Shift]


class StitchMapGeometry:
    """Join views by a shared tap mark, a common map border on both axes, or the shape of the
    occupied cells, in this order. The brief of a unit is not join evidence: generic enemies
    share every value of the brief.

    The lattice of one view is either all right or all wrong, so a view is trusted inside
    itself. Only the shift between two views needs evidence, and the map borders limit
    every shift.
    """

    def judge(self, views: Sequence[View]) -> MapJudgment | None:
        if not views:
            return None
        owner = list(range(len(views)))
        groups = {index: _Group({index: (0, 0)}) for index in range(len(views))}
        for new in range(1, len(views)):
            if not views[new].cells:
                continue
            for old in range(new - 1, -1, -1):
                if owner[old] == owner[new] or not views[old].cells:
                    continue
                shift = _join(views, groups[owner[old]], old, groups[owner[new]], new)
                if shift is None:
                    continue
                absorbed = groups.pop(owner[new])
                kept = groups[owner[old]]
                for member, (x, y) in absorbed.members.items():
                    kept.members[member] = (x + shift[0], y + shift[1])
                    owner[member] = owner[old]

        last = len(views) - 1
        # The rules below pick the group to output. The contract leaves the choice open.
        # - Output the group of the last view when other views joined it.
        # - When the last view joined no other view, output the group of the newest
        #   earlier view, and mark the range of the current view as unknown.
        # - When there is only one view, output that view alone.
        group = groups[owner[last]]
        if len(group.members) == 1 and last > 0:
            group = groups[owner[last - 1]]
        if not any(views[member].cells for member in group.members):
            return None
        return _judgment(views, group, last)


def _join(
    views: Sequence[View], old_group: _Group, old: int, new_group: _Group, new: int
) -> Shift | None:
    """Return the shift from the frame of the new group to the frame of the old group."""

    def group_shift(pair: Shift) -> Shift:
        old_x, old_y = old_group.members[old]
        new_x, new_y = new_group.members[new]
        return (old_x + pair[0] - new_x, old_y + pair[1] - new_y)

    def fits(pair: Shift, agreement: float) -> bool:
        overlap, agreed, _ = _compare(views[old], views[new], pair)
        if overlap and agreed / overlap < agreement:
            return False
        return _borders_hold(_placed(views, old_group, new_group, group_shift(pair)))

    old_view, new_view = views[old], views[new]
    if old_view.tap_mark and new_view.tap_mark and old_view.tap_mark.tap == new_view.tap_mark.tap:
        (old_x, old_y), (new_x, new_y) = old_view.tap_mark.cell, new_view.tap_mark.cell
        pair = (old_x - new_x, old_y - new_y)
        if fits(pair, JOIN_AGREEMENT):
            return group_shift(pair)

    border_shift = _border_shift(views, old_group, new_group)
    if border_shift is not None:
        old_x, old_y = old_group.members[old]
        new_x, new_y = new_group.members[new]
        pair = (border_shift[0] - old_x + new_x, border_shift[1] - old_y + new_y)
        if fits(pair, JOIN_AGREEMENT):
            return border_shift

    shape_fits = [
        pair for pair in _shape_candidates(old_view, new_view) if fits(pair, SHAPE_AGREEMENT)
    ]
    strongest = _strongest(old_view, new_view, shape_fits)
    return None if strongest is None else group_shift(strongest)


def _border_shift(views: Sequence[View], old_group: _Group, new_group: _Group) -> Shift | None:
    """Return the shift of the new group when the two groups show a common border on each
    axis. Return None when an axis has no common border.
    """
    old_edges = _edges(views, old_group)
    new_edges = _edges(views, new_group)

    def common(sides: tuple[Side, Side]) -> int | None:
        return next(
            (
                old_edges[side] - new_edges[side]
                for side in sides
                if side in old_edges and side in new_edges
            ),
            None,
        )

    x, y = common((Side.LEFT, Side.RIGHT)), common((Side.TOP, Side.BOTTOM))
    return None if x is None or y is None else (x, y)


def _edges(views: Sequence[View], group: _Group) -> dict[Side, int]:
    edges: dict[Side, int] = {}
    for member, (dx, dy) in group.members.items():
        x0, y0, x1, y1 = _extent(views[member].cells)
        sides = {Side.LEFT: x0 + dx, Side.TOP: y0 + dy, Side.RIGHT: x1 + dx, Side.BOTTOM: y1 + dy}
        for side in views[member].borders:
            edges[side] = sides[side]
    return edges


def _strongest(old: View, new: View, pairs: Sequence[Shift]) -> Shift | None:
    # Evenly spaced units let several shifts fit two views of one camera place. A
    # demand for one fitting shift drops the true shift, and the join then takes an
    # older view at a wrong shift. So the shift with the most agreeing occupied cells
    # wins, then the shift with the highest agreement. A tie gives no join.
    def evidence(pair: Shift) -> tuple[int, float]:
        overlap, agreed, occupied = _compare(old, new, pair)
        return occupied, agreed / overlap

    ranked = sorted(((evidence(pair), pair) for pair in pairs), reverse=True)
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None
    return ranked[0][1]


def _shape_candidates(old: View, new: View) -> list[Shift]:
    old_x0, old_y0, old_x1, old_y1 = _extent(old.cells)
    new_x0, new_y0, new_x1, new_y1 = _extent(new.cells)
    candidates: list[Shift] = []
    for dx in range(old_x0 - new_x1, old_x1 - new_x0 + 1):
        for dy in range(old_y0 - new_y1, old_y1 - new_y0 + 1):
            overlap, agreed, occupied = _compare(old, new, (dx, dy))
            if (
                overlap >= MIN_SHAPE_OVERLAP
                and occupied >= MIN_SHAPE_OCCUPIED
                and agreed / overlap >= SHAPE_AGREEMENT
            ):
                candidates.append((dx, dy))
    return candidates


def _compare(old: View, new: View, shift: Shift) -> tuple[int, int, int]:
    """Return the overlap, the agreeing cells and the agreeing occupied cells.

    Only cells that both views read as occupied or empty count.
    """
    overlap = agreed = occupied = 0
    for (x, y), seen in new.cells.items():
        if seen is CellSeen.UNREADABLE:
            continue
        other = old.cells.get((x + shift[0], y + shift[1]))
        if other is None or other is CellSeen.UNREADABLE:
            continue
        overlap += 1
        if other is seen:
            agreed += 1
            if seen is CellSeen.OCCUPIED:
                occupied += 1
    return overlap, agreed, occupied


def _placed(
    views: Sequence[View], old_group: _Group, new_group: _Group, shift: Shift
) -> Iterable[tuple[View, Shift]]:
    for member, place in old_group.members.items():
        yield views[member], place
    for member, (x, y) in new_group.members.items():
        yield views[member], (x + shift[0], y + shift[1])


def _borders_hold(placed: Iterable[tuple[View, Shift]]) -> bool:
    """Return False when a placed view reaches past a border that another view shows."""
    edges: dict[Side, set[int]] = {side: set() for side in Side}
    boxes: list[tuple[int, int, int, int]] = []
    for view, (dx, dy) in placed:
        x0, y0, x1, y1 = _extent(view.cells)
        box = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        boxes.append(box)
        sides = {Side.LEFT: box[0], Side.TOP: box[1], Side.RIGHT: box[2], Side.BOTTOM: box[3]}
        for side in view.borders:
            edges[side].add(sides[side])
    if any(len(found) > 1 for found in edges.values()):
        return False
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)
    return (
        all(edge <= top for edge in edges[Side.TOP])
        and all(edge >= bottom for edge in edges[Side.BOTTOM])
        and all(edge <= left for edge in edges[Side.LEFT])
        and all(edge >= right for edge in edges[Side.RIGHT])
    )


def _extent(cells: Iterable[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs, ys = zip(*cells, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def same_name(a: NameMask | None, b: NameMask | None) -> bool:
    if a is None or b is None:
        return False
    slack_x, slack_y = NAME_SLACK
    found, template = a.mask, b.mask
    if (
        abs(template.shape[1] - found.shape[1]) > slack_x
        or abs(template.shape[0] - found.shape[0]) > slack_y
    ):
        return False
    padded = cv2.copyMakeBorder(
        found,
        slack_y,
        slack_y + max(0, template.shape[0] - found.shape[0]),
        slack_x,
        slack_x + max(0, template.shape[1] - found.shape[1]),
        cv2.BORDER_CONSTANT,
        value=0,
    )
    scores = cv2.matchTemplate(
        padded.astype(np.float32), template.astype(np.float32), cv2.TM_CCOEFF_NORMED
    )
    _, best, _, _ = cv2.minMaxLoc(scores)
    return float(best) >= SAME_NAME


def _judgment(views: Sequence[View], group: _Group, last: int) -> MapJudgment:
    newest_first = sorted(group.members, reverse=True)
    votes: dict[MapCell, Counter[CellContent]] = {}
    reach: set[MapCell] = set()
    for member, (dx, dy) in group.members.items():
        for (x, y), seen in views[member].cells.items():
            cell = (x + dx, y + dy)
            reach.add(cell)
            if seen is not CellSeen.UNREADABLE:
                votes.setdefault(cell, Counter())[_CONTENT[seen]] += 1
    left, top, right, bottom = _extent(reach)

    def to_map(cell: tuple[int, int], shift: Shift) -> MapCell:
        return (cell[0] + shift[0] - left, cell[1] + shift[1] - top)

    cells: dict[MapCell, CellContent] = {}
    for cell, count in votes.items():
        content, agreed = count.most_common(1)[0]
        if agreed / count.total() >= CELL_AGREEMENT:
            cells[to_map(cell, (0, 0))] = content
    width, height = right - left + 1, bottom - top + 1
    uncertain = frozenset(
        (x, y) for x in range(width) for y in range(height) if (x, y) not in cells
    )
    borders = {side for member in group.members for side in views[member].borders}
    unit_cells, units = _units(views, group, newest_first, cells, to_map)
    current = (
        frozenset(to_map(cell, group.members[last]) for cell in views[last].cells)
        if last in group.members
        else None
    )
    return MapJudgment(
        stage=next((views[m].stage for m in newest_first if views[m].stage is not None), None),
        turn=next((views[m].turn for m in newest_first if views[m].turn is not None), None),
        phase=next((views[m].phase for m in newest_first if views[m].phase is not None), None),
        columns=Axis(width, Side.LEFT in borders, Side.RIGHT in borders),
        rows=Axis(height, Side.TOP in borders, Side.BOTTOM in borders),
        cells=cells,
        uncertain=uncertain,
        unit_cells=unit_cells,
        units=units,
        current=current,
    )


@dataclass(frozen=True)
class _Seen:
    member: int
    unit: ViewUnit
    footprint: frozenset[MapCell]


def _units(
    views: Sequence[View],
    group: _Group,
    newest_first: Sequence[int],
    cells: dict[MapCell, CellContent],
    to_map: _ToMap,
) -> tuple[dict[MapCell, UnitId], dict[UnitId, MapUnit]]:
    seen: list[_Seen] = []
    for member in newest_first:
        shift = group.members[member]
        for unit in views[member].units:
            x, y = to_map(unit.pos, shift)
            width, height = unit.size
            footprint = frozenset((x + i, y + j) for i in range(width) for j in range(height))
            seen.append(_Seen(member, unit, footprint))

    clusters: list[list[_Seen]] = []
    for item in seen:
        touching = [
            cluster
            for cluster in clusters
            if any(item.footprint & other.footprint for other in cluster)
        ]
        merged = [item] + [other for cluster in touching for other in cluster]
        clusters = [cluster for cluster in clusters if all(cluster is not t for t in touching)]
        clusters.append(merged)

    kept: list[tuple[frozenset[MapCell], list[_Seen]]] = []
    for cluster in clusters:
        footprint = Counter(item.footprint for item in cluster).most_common(1)[0][0]
        if all(cells.get(cell) is CellContent.OCCUPIED for cell in footprint):
            kept.append((footprint, sorted(cluster, key=lambda item: -item.member)))
    kept.sort(key=lambda entry: min((y, x) for x, y in entry[0]))

    unit_cells: dict[MapCell, UnitId] = {}
    units: dict[UnitId, MapUnit] = {}
    for unit_id, (footprint, cluster) in enumerate(kept):
        for cell in footprint:
            unit_cells[cell] = unit_id
        units[unit_id] = MapUnit(
            controllable=next(
                (s.unit.controllable for s in cluster if s.unit.controllable is not None), None
            ),
            faction=next((s.unit.faction for s in cluster if s.unit.faction is not None), None),
            brief=next((s.unit.brief for s in cluster if s.unit.brief is not None), None),
        )
    return unit_cells, units
