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
from ggge_ai.domain import screens
from ggge_ai.vision.motion import frame_diff, is_static

log = logging.getLogger(__name__)

AUTO_BUTTON = (1820, 54)
# panning works on the our-turn hub with no unit selected: dragging an
# empty map spot shifts the camera. drag opposite to the look direction.
PAN_CENTER = (1170, 500)
PAN_DIST = 600
PAN_DIRS = (("east", (1, 0)), ("west", (-1, 0)), ("north", (0, -1)), ("south", (0, 1)))
WEAPON_SELECT_BTN = (2106, 965)
ATTACK_BTN = (2085, 977)
START_BATTLE_BTN = (2085, 988)
RETURN_BTN = (1804, 977)
STANDBY_BTN = (2100, 645)
END_TURN_BTN = (275, 182)
WEAPON_SLOTS = ((1176, 965), (1367, 965), (1556, 965))
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
    settle_timeout_s: float = 45.0
    battle_timeout_s: float = 3600.0
    idle_timeout_s: float = 600.0
    lock_check_interval_s: float = 15.0
    _action: _ActionState = field(default_factory=_ActionState)
    _enemy_hint: tuple[int, int] | None = None
    _turn_scouted: bool = False

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
                return screens.UNKNOWN
            state = self.perception.observe()
            if state.screen in TERMINAL_SCREENS and state.screen_confidence >= 0.9:
                log.info("battle finished: %s", state.screen)
                return state.screen
            # detect stories by the MENU button itself, not the screen
            # classifier: mid-battle stories shift MENU left of the anchor
            # position and the frame then classifies as something else
            menu_pos = vision.locate_story_menu(self._frame(), threshold=0.7)
            if menu_pos is not None:
                log.info("mid-battle story (menu at %s), skipping", menu_pos)
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
                self.actuator.tap(*END_TURN_STANDBY_OPTION)
                time.sleep(0.8)
                self.actuator.tap(*END_TURN_EXECUTE)
                time.sleep(2.0)
                last_activity = time.time()
                continue
            mode = self._current_mode()
            if mode is None:
                # enemy turn or an animation between phases
                time.sleep(0.8)
                continue
            handler = getattr(self, f"_on_{mode.removeprefix('label_')}")
            handler()
            last_activity = time.time()
        log.warning("battle timeout reached")
        return screens.UNKNOWN

    def _current_mode(self) -> str | None:
        found = self.perception.probe(MODE_LABELS)
        if not found:
            return None
        return max(found.values(), key=lambda e: e.confidence).id

    def _frame(self):
        return self.perception.capture()

    def _on_our_turn(self) -> None:
        self._action.reset()
        if vision.unit_cards_present(self._frame()):
            self._scout()
            log.info("selecting next actable unit")
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
            time.sleep(1.8)
            return
        # the card strip animates in after the hub appears; confirm it is
        # really empty before ending the turn
        time.sleep(1.2)
        if vision.unit_cards_present(self._frame()):
            log.info("unit cards appeared late, selecting next unit")
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
        else:
            log.info("no actable units left, ending turn")
            self.actuator.tap(*END_TURN_BTN)
            self._turn_scouted = False
        time.sleep(1.8)

    def _scout(self) -> None:
        """Refresh the enemy direction hint from the hub. When no enemy is
        on screen, pan around once per turn to find where they are; the
        camera recenters on the unit as soon as one is selected, so panned
        views need no undo when the scout ends on a hit."""
        enemies = vision.find_enemy_units(self._frame(), region=vision.HUB_SCAN_REGION)
        if enemies:
            c = vision.centroid(enemies)
            self._enemy_hint = self._direction_to(c)
            return
        if self._turn_scouted:
            return
        self._turn_scouted = True
        cx, cy = PAN_CENTER
        for name, (dx, dy) in PAN_DIRS:
            self.actuator.swipe(cx, cy, cx - dx * PAN_DIST, cy - dy * PAN_DIST, 500)
            time.sleep(1.0)
            enemies = vision.find_enemy_units(self._frame(), region=vision.HUB_SCAN_REGION)
            if enemies:
                log.info("scout: %d enemy unit(s) to the %s", len(enemies), name)
                self._enemy_hint = (dx, dy)
                return
            self.actuator.swipe(cx - dx * PAN_DIST, cy - dy * PAN_DIST, cx, cy, 500)
            time.sleep(0.8)
        log.info("scout: no enemies found in any direction")

    @staticmethod
    def _direction_to(point: tuple[int, int]) -> tuple[int, int]:
        dx = point[0] - PAN_CENTER[0]
        dy = point[1] - PAN_CENTER[1]
        n = max((dx * dx + dy * dy) ** 0.5, 1.0)
        return (round(dx / n), round(dy / n))

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
            target = None
            enemies = vision.find_enemy_units(frame)
            if enemies and cells:
                # the move range surrounds the unit, so its centroid is a
                # good proxy for the unit's own position
                origin = vision.centroid(cells)
                target = vision.nearest_point(enemies, origin)
                log.info("seeking nearest enemy unit at %s (of %d seen)", target, len(enemies))
            if target is None:
                target = vision.centroid(vision.find_threat_cells(frame))
                if target:
                    log.info("no enemy arcs visible, using threat centroid %s", target)
            if target is None and self._enemy_hint is not None:
                hx, hy = self._enemy_hint
                target = (PAN_CENTER[0] + hx * 1200, PAN_CENTER[1] + hy * 1200)
                log.info("using scouted enemy direction (%d, %d)", hx, hy)
            if target and cells:
                cell = vision.nearest_point(cells, target)
                log.info("moving toward enemies via %s", cell)
                self._action.moved = True
                self.actuator.tap(*cell)
                time.sleep(2.0)
                return
            log.info("no enemy direction found, standing by")
        else:
            log.info("already moved and still no target, standing by")
        self._standby()

    def _on_weapon_select(self) -> None:
        frame = self._frame()
        if vision.attack_enabled(frame):
            log.info("target locked, attacking")
            self._attack()
            return
        for i, slot in enumerate(WEAPON_SLOTS):
            self.actuator.tap(*slot)
            time.sleep(1.0)
            if vision.attack_enabled(self._frame()):
                log.info("weapon slot %d has a target, attacking", i + 1)
                self._attack()
                return
        if self._action.moved or not self._can_return():
            log.info("all weapons out of range, standing by")
            self._standby()
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
        self.actuator.tap(*pos)
        self._wait_animation()
        self._action.reset()

    def _attack(self) -> None:
        self.actuator.tap(*ATTACK_BTN)
        time.sleep(2.0)

    def _standby(self) -> None:
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
