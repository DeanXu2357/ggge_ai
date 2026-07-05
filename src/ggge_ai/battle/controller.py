"""Manual battle controller: drives combat ourselves instead of the
built-in AUTO AI.

v1 heuristic per confirmed direction: every actable unit attacks if a
target is in range (trying each weapon), otherwise moves toward the
enemy force (threat-cell centroid) and attacks if possible, else stands
by. Enemy turns play out on their own; we simply wait for our turn hub
to return.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ggge_ai.battle import vision
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.tacmap import TacticalMap
from ggge_ai.domain import screens
from ggge_ai.vision.motion import frame_diff, is_static

log = logging.getLogger(__name__)

AUTO_BUTTON = (1820, 54)
# panning works on the our-turn hub with no unit selected: dragging an
# empty map spot shifts the camera. drag opposite to the look direction,
# split evenly around the center so both endpoints stay inside the map
# area (vertical half-travel is shorter to clear the HUD and card strip)
PAN_CENTER = (1170, 500)
PAN_HALF = {"x": 300, "y": 200}
PAN_DIRS = (("east", (1, 0)), ("west", (-1, 0)), ("north", (0, -1)), ("south", (0, 1)))
WEAPON_SELECT_BTN = (2106, 965)
ATTACK_BTN = (2085, 977)
START_BATTLE_BTN = (2085, 988)
RETURN_BTN = (1804, 977)
STANDBY_BTN = (2100, 645)
END_TURN_BTN = (275, 182)
WEAPON_SLOTS = ((1176, 965), (1367, 965), (1556, 965))
# selecting a unit recenters the camera on it, so its HP arc lands near frame
# center. a red arc within this radius of the unit's move-cell centroid is
# discarded as a residual/overlapping self arc rather than taken as a target
SELF_ARC_RADIUS = 150
STORY_MENU = (2100, 49)
STORY_SKIP = (2103, 430)
# end-turn confirmation dialog: standby-and-end option and execute button.
# never pick the right-hand option, it hands leftover units to the built-in AI
END_TURN_STANDBY_OPTION = (997, 562)
END_TURN_EXECUTE = (1365, 850)

AUTO_STATE_IDS = ("btn_auto_full", "btn_auto_enemy", "btn_auto_manual")
MODE_LABELS = (
    "label_our_turn",
    "label_unit_move",
    "label_weapon_select",
    "label_battle_prep",
    "label_skill",
)

TERMINAL_SCREENS = (screens.BATTLE_RESULT, screens.REWARD)


@dataclass
class _ActionState:
    tried_in_place: bool = False
    moved: bool = False

    def reset(self) -> None:
        self.tried_in_place = False
        self.moved = False


@dataclass
class ManualBattleController:
    perception: object
    actuator: object
    keyguard: object | None = None
    ledger: BattleLedger | None = None
    settle_timeout_s: float = 45.0
    battle_timeout_s: float = 3600.0
    idle_timeout_s: float = 600.0
    lock_check_interval_s: float = 15.0
    _action: _ActionState = field(default_factory=_ActionState)
    _enemy_hint: tuple[float, float] | None = None
    _turn_scouted: bool = False
    _none_streak: int = 0
    _phase_break: bool = False
    tacmap: TacticalMap = field(default_factory=TacticalMap)

    def ensure_manual_auto(self, timeout_s: float = 60.0) -> bool:
        """Cycle the AUTO button until it is colorless (full manual)."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not is_static(self.perception.capture, threshold=0.02, gap_s=0.3):
                time.sleep(0.4)
                continue
            found = self.perception.probe(AUTO_STATE_IDS)
            if not found:
                time.sleep(0.4)
                continue
            state = max(found.values(), key=lambda e: e.confidence).id
            if state == "btn_auto_manual":
                return True
            log.info("AUTO is %s, cycling toward manual", state)
            self.actuator.tap(*AUTO_BUTTON)
            time.sleep(0.9)
        return False

    def run(self) -> str:
        """Play the battle until a terminal screen. Returns the screen id."""
        if not self.ensure_manual_auto():
            log.warning("could not confirm manual AUTO state, continuing anyway")
        deadline = time.time() + self.battle_timeout_s
        last_activity = time.time()
        next_lock_check = 0.0
        while time.time() < deadline:
            if self.keyguard is not None and time.time() >= next_lock_check:
                next_lock_check = time.time() + self.lock_check_interval_s
                if not self.keyguard.ensure_unlocked():
                    time.sleep(5.0)
                    continue
            if time.time() - last_activity > self.idle_timeout_s:
                log.warning("no battle activity for %.0fs, giving up", self.idle_timeout_s)
                self._log_finish("idle_timeout")
                return screens.UNKNOWN
            state = self.perception.observe()
            if state.screen in TERMINAL_SCREENS and state.screen_confidence >= 0.9:
                log.info("battle finished: %s", state.screen)
                self._log_finish(state.screen)
                return state.screen
            # our whole force wiped out: the FAILED screen is a dead end
            # (its buttons hand off to retry/stage-select). detect it and
            # finish cleanly so the ledger archives instead of idling out
            if vision.is_defeat_screen(self._frame()):
                log.info("battle finished: defeat screen")
                self._log_finish("defeat")
                return screens.UNKNOWN
            # detect stories by the MENU button itself, not the screen
            # classifier: mid-battle stories shift MENU left of the anchor
            # position and the frame then classifies as something else
            menu_pos = vision.locate_story_menu(self._frame(), threshold=0.7)
            if menu_pos is not None:
                log.info("mid-battle story (menu at %s), skipping", menu_pos)
                self._log("story_skip", menu=menu_pos)
                self.actuator.tap(*menu_pos)
                time.sleep(0.8)
                self.actuator.tap(menu_pos[0], STORY_SKIP[1])
                time.sleep(1.5)
                last_activity = time.time()
                continue
            if not is_static(self.perception.capture, threshold=0.015, gap_s=0.35):
                # animations count as activity: the battle is visibly running
                last_activity = time.time()
                time.sleep(0.5)
                continue
            if self.perception.probe(["dlg_end_turn"]):
                log.info("end-turn dialog: choosing standby-and-end")
                self._phase_break = True
                self.actuator.tap(*END_TURN_STANDBY_OPTION)
                time.sleep(0.8)
                self.actuator.tap(*END_TURN_EXECUTE)
                time.sleep(2.0)
                last_activity = time.time()
                continue
            mode = self._current_mode()
            if mode is None:
                # a dying unit pops a MENU-less inline dialogue line; advance
                # it before it is mistaken for a phase break and stalls us
                cursor = vision.locate_dialog_cursor(self._frame())
                if cursor is not None:
                    log.info("in-battle dialog (cursor at %s), advancing", cursor)
                    self._log("story_dialog", cursor=cursor)
                    self.actuator.tap(*cursor)
                    time.sleep(0.8)
                    self._none_streak = 0
                    last_activity = time.time()
                    continue
                # enemy turn or an animation between phases; two static
                # label-less frames in a row mean we left our own phase
                # (turns can end automatically once every unit has acted,
                # so the end-turn dialog is not a reliable turn boundary)
                self._none_streak += 1
                if self._none_streak >= 2:
                    self._phase_break = True
                time.sleep(0.8)
                continue
            self._none_streak = 0
            handler = getattr(self, f"_on_{mode.removeprefix('label_')}")
            handler()
            last_activity = time.time()
        log.warning("battle timeout reached")
        self._log_finish("battle_timeout")
        return screens.UNKNOWN

    def _log(self, kind: str, **data) -> None:
        if self.ledger is not None:
            self.ledger.record(kind, **data)

    def _log_finish(self, outcome: str) -> None:
        if self.ledger is not None:
            self.ledger.finish(outcome)

    def _current_mode(self) -> str | None:
        found = self.perception.probe(MODE_LABELS)
        if not found:
            return None
        return max(found.values(), key=lambda e: e.confidence).id

    def _frame(self):
        return self.perception.capture()

    def _on_our_turn(self) -> None:
        self._action.reset()
        frame = self._frame()
        if vision.unit_cards_present(frame):
            if self._phase_break:
                self._phase_break = False
                self._turn_scouted = False
                if self.ledger is not None:
                    self.ledger.next_turn()
                log.info("new turn detected (turn %d)", self.ledger.turn if self.ledger else 0)
            self._snapshot_factions(frame)
            self._scout(frame)
            log.info("selecting next actable unit")
            self._log("select_unit")
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
            time.sleep(1.8)
            return
        # the card strip animates in after the hub appears; confirm it is
        # really empty before ending the turn
        time.sleep(1.2)
        if vision.unit_cards_present(self._frame()):
            log.info("unit cards appeared late, selecting next unit")
            self._log("select_unit")
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
        else:
            log.info("no actable units left, ending turn")
            self.actuator.tap(*END_TURN_BTN)
            self._phase_break = True
            self._turn_scouted = False
        time.sleep(1.8)

    def _snapshot_factions(self, frame) -> None:
        if self.ledger is None:
            return
        self.ledger.snapshot(
            allies=vision.find_ally_units(frame, region=vision.HUB_SCAN_REGION),
            enemies=vision.find_enemy_units(frame, region=vision.HUB_SCAN_REGION),
            third_party=vision.find_third_party_units(frame, region=vision.HUB_SCAN_REGION),
        )

    def _scout(self, frame) -> None:
        """Rebuild the tactical map once per turn by pan-scanning the four
        directions around the hub view. Every pan is measured with phase
        correlation before world coordinates are assigned, and every leg
        pans back so all observations share the scan origin."""
        if self._turn_scouted:
            return
        self._turn_scouted = True
        self.tacmap.reset()
        camera = (0.0, 0.0)
        self._observe_map(frame, camera)
        cx, cy = PAN_CENTER
        prev = frame
        for name, (dx, dy) in PAN_DIRS:
            hx, hy = dx * PAN_HALF["x"], dy * PAN_HALF["y"]
            travel = (2 * hx, 2 * hy)
            self.actuator.swipe(cx + hx, cy + hy, cx - hx, cy - hy, 500)
            time.sleep(1.0)
            cur = self._frame()
            camera = self._advance_camera(camera, prev, cur, travel)
            self._observe_map(cur, camera)
            self.actuator.swipe(cx - hx, cy - hy, cx + hx, cy + hy, 500)
            time.sleep(0.8)
            back = self._frame()
            camera = self._advance_camera(camera, cur, back, (-travel[0], -travel[1]))
            prev = back
        self._enemy_hint = self._hint_from_map()
        self._log(
            "tactical_map",
            enemies=[(round(x), round(y)) for x, y in self.tacmap.enemies],
            allies=[(round(x), round(y)) for x, y in self.tacmap.allies],
            third_party=[(round(x), round(y)) for x, y in self.tacmap.third_party],
            camera_drift=(round(camera[0]), round(camera[1])),
        )
        log.info(
            "scout: tactical map has %d enemies / %d allies / %d third-party",
            len(self.tacmap.enemies),
            len(self.tacmap.allies),
            len(self.tacmap.third_party),
        )

    @staticmethod
    def _advance_camera(camera, prev, cur, nominal) -> tuple[float, float]:
        shift, response = vision.measure_camera_shift(prev, cur)
        if response < 0.05:
            # featureless view (open space): trust the gesture instead
            shift = nominal
        return (camera[0] + shift[0], camera[1] + shift[1])

    def _observe_map(self, frame, camera) -> None:
        self.tacmap.observe(
            camera,
            vision.find_enemy_units(frame, region=vision.HUB_SCAN_REGION),
            vision.find_ally_units(frame, region=vision.HUB_SCAN_REGION),
            vision.find_third_party_units(frame, region=vision.HUB_SCAN_REGION),
        )

    def _hint_from_map(self) -> tuple[float, float] | None:
        origin = vision.centroid([(round(x), round(y)) for x, y in self.tacmap.allies])
        if origin is None:
            origin = PAN_CENTER
        enemy = self.tacmap.nearest_enemy(origin)
        if enemy is None:
            return None
        dx, dy = enemy[0] - origin[0], enemy[1] - origin[1]
        n = max((dx * dx + dy * dy) ** 0.5, 1.0)
        return (dx / n, dy / n)

    def _on_unit_move(self) -> None:
        if not self._action.tried_in_place:
            log.info("opening weapon select in place")
            self._action.tried_in_place = True
            self.actuator.tap(*WEAPON_SELECT_BTN)
            time.sleep(1.8)
            return
        if not self._action.moved:
            frame = self._frame()
            cells = vision.find_move_cells(frame)
            target, basis = self._seek_move_target(frame, cells)
            if target and cells:
                cell = vision.nearest_point(cells, target)
                log.info("moving toward enemies via %s (basis %s)", cell, basis)
                self._log(
                    "move",
                    basis=basis,
                    target=(round(target[0]), round(target[1])),
                    cell=cell,
                )
                self._action.moved = True
                self.actuator.tap(*cell)
                time.sleep(2.0)
                return
            log.info("no enemy direction found, standing by")
            self._standby("no_target")
            return
        log.info("already moved and still no target, standing by")
        self._standby("moved_no_target")

    def _seek_move_target(
        self, frame, cells: list[tuple[int, int]]
    ) -> tuple[tuple[float, float] | None, str | None]:
        """Pick where to move, per unit, aiming at the enemy nearest to
        *this* unit rather than at a single force-wide heading.

        Priority: (1) the on-screen enemy arc nearest this unit -- the
        camera recenters on the selected unit, so any red arc close to the
        unit is its own residual arc and is excluded (SELF_ARC_RADIUS); the
        enemy red band was tightened to hue<=10 in 1ddc407, so the remaining
        arcs are true enemies and each unit steers toward its own closest
        one; (2) anchor the camera against the map and aim at the nearest
        world enemy; (3) fall back to the scouted world heading from our
        force toward the enemy mass -- a pure translation, so a world
        direction is a screen direction regardless of camera offset (a
        single force-wide heading, which walks front-line units away from a
        side/rear enemy: only reached when no enemy is on screen); (4) last
        resort, the on-screen threat-cell centroid."""
        if not cells:
            return None, None
        origin = vision.centroid(cells)
        onscreen = [
            e
            for e in vision.find_enemy_units(frame)
            if (e[0] - origin[0]) ** 2 + (e[1] - origin[1]) ** 2
            >= SELF_ARC_RADIUS * SELF_ARC_RADIUS
        ]
        if onscreen:
            target = vision.nearest_point(onscreen, origin)
            log.info(
                "on-screen enemy at %s nearest this unit (origin %s)",
                target,
                origin,
            )
            return (float(target[0]), float(target[1])), "enemy_onscreen"
        if self.tacmap.enemies:
            arcs = (
                vision.find_ally_units(frame)
                + vision.find_enemy_units(frame)
                + vision.find_third_party_units(frame)
            )
            t = self.tacmap.anchor(origin, arcs)
            if t is not None:
                world_enemy = self.tacmap.nearest_enemy((origin[0] + t[0], origin[1] + t[1]))
                if world_enemy is not None:
                    target = (world_enemy[0] - t[0], world_enemy[1] - t[1])
                    log.info(
                        "tactical-map enemy at %s (screen), camera offset %s",
                        (round(target[0]), round(target[1])),
                        (round(t[0]), round(t[1])),
                    )
                    return target, "tacmap"
        if self._enemy_hint is not None:
            hx, hy = self._enemy_hint
            log.info("no camera anchor, steering by scouted enemy heading (%.2f, %.2f)", hx, hy)
            return (origin[0] + hx * 1200, origin[1] + hy * 1200), "scout_hint"
        threat = vision.centroid(vision.find_threat_cells(frame))
        if threat:
            log.info("map empty, falling back to threat centroid %s", threat)
            return threat, "threat_centroid"
        return None, None

    def _on_weapon_select(self) -> None:
        frame = self._frame()
        if vision.attack_enabled(frame):
            log.info("target locked, attacking")
            self._attack(slot=0)
            return
        for i, slot in enumerate(WEAPON_SLOTS):
            self.actuator.tap(*slot)
            time.sleep(1.0)
            if vision.attack_enabled(self._frame()):
                log.info("weapon slot %d has a target, attacking", i + 1)
                self._attack(slot=i + 1)
                return
        if self._action.moved or not self._can_return():
            log.info("all weapons out of range, standing by")
            self._standby("out_of_range")
        else:
            log.info("all weapons out of range, going back to move")
            self.actuator.tap(*RETURN_BTN)
            time.sleep(1.5)

    def _can_return(self) -> bool:
        return not self._action.moved

    def _on_skill(self) -> None:
        # v1 does not use skills yet; leave the accidental skill screen
        log.info("skill screen open, returning")
        self.actuator.tap(*RETURN_BTN)
        time.sleep(1.5)

    def _on_battle_prep(self) -> None:
        found = self.perception.probe(["btn_start_battle"])
        pos = found["btn_start_battle"].bbox.center if found else START_BATTLE_BTN
        log.info("confirming battle start")
        self._log("engagement_confirm")
        self.actuator.tap(*pos)
        self._wait_animation()
        self._action.reset()

    def _attack(self, slot: int) -> None:
        self._log("attack", slot=slot)
        self.actuator.tap(*ATTACK_BTN)
        time.sleep(2.0)

    def _standby(self, reason: str) -> None:
        self._log("standby", reason=reason)
        self.actuator.tap(*STANDBY_BTN)
        time.sleep(1.8)
        self._action.reset()

    def _wait_animation(self) -> None:
        """Wait out the combat cut-in animation until frames settle."""
        t0 = time.time()
        prev = None
        while time.time() - t0 < self.settle_timeout_s:
            frame = self._frame()
            d = frame_diff(prev, frame) if prev is not None else 1.0
            prev = frame
            if time.time() - t0 > 5 and d < 0.008:
                return
            time.sleep(0.5)
