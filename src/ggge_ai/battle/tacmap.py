"""World-coordinate tactical map built by pan-scanning the battle map.

The camera offset is measured, never assumed: every pan compares the
frames before and after with phase correlation, so gesture inertia and
map-edge clamping cannot corrupt the coordinate frame. A world point is
its screen position plus the camera offset at observation time; the
origin is wherever the camera sat when the scan started. Rebuilt every
turn (units move), so stale positions live at most one turn.

The pool is FACTIONLESS (定案 5): arc detection only ever says "a unit
stands here" -- faction comes from the identify pass (banner dock side)
and lives with identities, never here. Threat cells ("!" overlay) keep
their own list: they only render around the enemy force, so they remain
a classification-independent bearing toward the enemy mass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[float, float]

MERGE_RADIUS = 70.0
ANCHOR_MATCH_RADIUS = 60.0


def _merge(points: list[Point], p: Point, radius: float = MERGE_RADIUS) -> None:
    for i, q in enumerate(points):
        if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 < radius * radius:
            points[i] = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            return
    points.append(p)


@dataclass
class TacticalMap:
    units: list[Point] = field(default_factory=list)
    threats: list[Point] = field(default_factory=list)

    def reset(self) -> None:
        self.units.clear()
        self.threats.clear()

    def observe(
        self,
        camera: Point,
        points: list[tuple[int, int]],
        threats: list[tuple[int, int]] = (),
    ) -> None:
        for p in points:
            _merge(self.units, (p[0] + camera[0], p[1] + camera[1]))
        for p in threats:
            _merge(self.threats, (p[0] + camera[0], p[1] + camera[1]))

    def nearest_unit(self, world_pos: Point) -> Point | None:
        if not self.units:
            return None
        return min(
            self.units,
            key=lambda e: (e[0] - world_pos[0]) ** 2 + (e[1] - world_pos[1]) ** 2,
        )

    def threat_centroid(self) -> Point | None:
        if not self.threats:
            return None
        n = len(self.threats)
        return (sum(p[0] for p in self.threats) / n, sum(p[1] for p in self.threats) / n)

    def locate(self, visible_arcs: list[tuple[int, int]]) -> Point | None:
        """Camera offset of an arbitrary view (no selection assumption):
        every (visible arc, world point) pairing proposes a translation,
        the one most arcs agree with wins, two coincidences minimum --
        the survey's bring-to-view navigation re-anchors with this
        between pans."""
        if not self.units or not visible_arcs:
            return None
        best: tuple[int, Point] | None = None
        for a in visible_arcs:
            for w in self.units:
                t = (w[0] - a[0], w[1] - a[1])
                score = 0
                for b in visible_arcs:
                    p = (b[0] + t[0], b[1] + t[1])
                    if any(
                        (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                        < ANCHOR_MATCH_RADIUS * ANCHOR_MATCH_RADIUS
                        for q in self.units
                    ):
                        score += 1
                if best is None or score > best[0]:
                    best = (score, t)
        if best is None or best[0] < 2:
            return None
        return best[1]

    def anchor(
        self, unit_screen: Point, visible_arcs: list[tuple[int, int]]
    ) -> Point | None:
        """Recover the camera offset of the current view after the game
        recentered on a selected unit (an untracked jump). Each scanned
        point is hypothesized to be the selected unit; the translation
        that makes the most visible arcs coincide with scanned world
        points wins. Needs a second coinciding arc to disambiguate,
        unless only one unit exists at all."""
        if not self.units or not visible_arcs:
            return None
        if len(self.units) == 1 and len(visible_arcs) == 1:
            w = self.units[0]
            return (w[0] - unit_screen[0], w[1] - unit_screen[1])
        best: tuple[int, Point] | None = None
        for w in self.units:
            t = (w[0] - unit_screen[0], w[1] - unit_screen[1])
            score = 0
            for a in visible_arcs:
                p = (a[0] + t[0], a[1] + t[1])
                if any(
                    (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                    < ANCHOR_MATCH_RADIUS * ANCHOR_MATCH_RADIUS
                    for q in self.units
                ):
                    score += 1
            if best is None or score > best[0]:
                best = (score, t)
        if best is None or best[0] < 2:
            return None
        return best[1]
