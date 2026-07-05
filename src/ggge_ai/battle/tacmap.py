"""World-coordinate tactical map built by pan-scanning the battle map.

The camera offset is measured, never assumed: every pan compares the
frames before and after with phase correlation, so gesture inertia and
map-edge clamping cannot corrupt the coordinate frame. A world point is
its screen position plus the camera offset at observation time; the
origin is wherever the camera sat when the scan started. Rebuilt every
turn (units move), so stale positions live at most one turn.
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
    enemies: list[Point] = field(default_factory=list)
    allies: list[Point] = field(default_factory=list)
    third_party: list[Point] = field(default_factory=list)

    def reset(self) -> None:
        self.enemies.clear()
        self.allies.clear()
        self.third_party.clear()

    def observe(
        self,
        camera: Point,
        enemies: list[tuple[int, int]],
        allies: list[tuple[int, int]],
        third_party: list[tuple[int, int]] = (),
    ) -> None:
        for screen, world in (
            (enemies, self.enemies),
            (allies, self.allies),
            (third_party, self.third_party),
        ):
            for p in screen:
                _merge(world, (p[0] + camera[0], p[1] + camera[1]))

    def nearest_enemy(self, world_pos: Point) -> Point | None:
        if not self.enemies:
            return None
        return min(
            self.enemies,
            key=lambda e: (e[0] - world_pos[0]) ** 2 + (e[1] - world_pos[1]) ** 2,
        )

    def anchor(
        self, unit_screen: Point, visible_arcs: list[tuple[int, int]]
    ) -> Point | None:
        """Recover the camera offset of the current view after the game
        recentered on a selected unit (an untracked jump). Each scanned
        ally is hypothesized to be the selected unit; the translation
        that makes the most visible arcs of any faction coincide with
        scanned world points wins. Needs a second coinciding arc to
        disambiguate, unless only one ally exists at all."""
        world_points = self.enemies + self.allies + self.third_party
        if not self.allies or not visible_arcs:
            return None
        if len(self.allies) == 1 and len(visible_arcs) == 1:
            w = self.allies[0]
            return (w[0] - unit_screen[0], w[1] - unit_screen[1])
        best: tuple[int, Point] | None = None
        for w in self.allies:
            t = (w[0] - unit_screen[0], w[1] - unit_screen[1])
            score = 0
            for a in visible_arcs:
                p = (a[0] + t[0], a[1] + t[1])
                if any(
                    (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                    < ANCHOR_MATCH_RADIUS * ANCHOR_MATCH_RADIUS
                    for q in world_points
                ):
                    score += 1
            if best is None or score > best[0]:
                best = (score, t)
        if best is None or best[0] < 2:
            return None
        return best[1]
