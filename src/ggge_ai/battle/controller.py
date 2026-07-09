"""Manual battle controller: drives combat ourselves instead of the
built-in AUTO AI.

Lifecycle (docs/battle-phase-states.md): every iteration is either
ACTIONABLE (a MODE_LABELS template matched -- we have something to do,
dispatched to the matching `_on_*` handler) or NOT_ACTIONABLE (`_on_
not_actionable`; enemy turn, third-party turn, or a transition, none of
which we need to tell apart -- just wait, or answer the one popup that
needs us). Interrupts (keyguard, modals, story, the end-turn dialog) are
checked ahead of both and can fire regardless of phase.

v1 heuristic per confirmed direction: every actable unit attacks if a
target is in range (trying each weapon), otherwise moves toward the
enemy force (threat-cell centroid) and attacks if possible, else stands
by.
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
# hidden-battle WARNING modal buttons: 不挑戰 (blue, left) declines and skips
# the secret fight, 挑戰 (orange, right) accepts it. verified on the 20260705
# popup capture. neither hands units to the built-in AI -- the AUTO chip in
# this modal's corner is the animation/story toggle, unrelated to control
DECLINE_HIDDEN_BATTLE = (1018, 977)
CHALLENGE_HIDDEN_BATTLE = (1404, 977)
# 關閉 button of the 單位設置詳情 modal a stray keyguard drag can open on a map
# unit; tapping it dismisses the modal and hands control back to the battle
UNIT_DETAIL_CLOSE = (1176, 992)

AUTO_STATE_IDS = ("btn_auto_full", "btn_auto_enemy", "btn_auto_manual")
MODE_LABELS = (
    "label_our_turn",
    "label_unit_move",
    "label_weapon_select",
    "label_battle_prep",
    "label_skill",
)

TERMINAL_SCREENS = (screens.BATTLE_RESULT, screens.REWARD)


def ensure_manual_auto(perception, actuator, timeout_s: float = 60.0) -> bool:
    """Cycle the AUTO toggle until it reads colorless (full manual).

    Shared by the battle controller and the pre-battle stage-info screen,
    whose AUTO chip uses the same three-state templates (btn_auto_full at the
    same corner). Waits for a static frame before each read so the toggle's
    own transition animation is not misread, and gives up after timeout_s so
    a screen whose AUTO chip never resolves cannot stall the run."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not is_static(perception.capture, threshold=0.02, gap_s=0.3):
            time.sleep(0.4)
            continue
        found = perception.probe(AUTO_STATE_IDS)
        if not found:
            time.sleep(0.4)
            continue
        state = max(found.values(), key=lambda e: e.confidence).id
        if state == "btn_auto_manual":
            return True
        log.info("AUTO is %s, cycling toward manual", state)
        actuator.tap(*AUTO_BUTTON)
        time.sleep(0.9)
    return False


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
    # "challenge" or "decline": the hidden-battle modal offers a secret fight.
    # default "challenge" -- clearing hidden battles is a project goal and our
    # force is usually over-spec. the OCR power-gap check (建議 vs 我軍戰鬥力)
    # is a future on-device upgrade; for now we do not read the numbers
    hidden_battle_policy: str = "challenge"
    _action: _ActionState = field(default_factory=_ActionState)
    _enemy_hint: tuple[float, float] | None = None
    _turn_scouted: bool = False
    _none_streak: int = 0
    _phase_break: bool = False
    _turn_marker: object | None = None
    tacmap: TacticalMap = field(default_factory=TacticalMap)

    def ensure_manual_auto(self, timeout_s: float = 60.0) -> bool:
        """Cycle the AUTO button until it is colorless (full manual)."""
        return ensure_manual_auto(self.perception, self.actuator, timeout_s)

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
            # the hidden-battle WARNING modal is a dead stop the controller
            # would otherwise idle out on: pick 挑戰/不挑戰 per policy, log the
            # decision frame (for future OCR power-gap calibration), continue
            warning_frame = self._frame()
            if vision.is_hidden_battle_warning(warning_frame):
                decision = "decline" if self.hidden_battle_policy == "decline" else "challenge"
                button = (
                    DECLINE_HIDDEN_BATTLE if decision == "decline" else CHALLENGE_HIDDEN_BATTLE
                )
                log.info("hidden-battle warning modal: %s", decision)
                self._log("hidden_battle_warning", frame=warning_frame, decision=decision)
                self.actuator.tap(*button)
                time.sleep(2.0)
                last_activity = time.time()
                continue
            # a stray keyguard drag or tap can open a modal over the live
            # battle; it carries no phase label, so close it here before the
            # label-less path below mistakes it for a phase break and idles out
            if self._handle_known_modal():
                last_activity = time.time()
                continue
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
                if self._on_not_actionable():
                    last_activity = time.time()
            else:
                self._none_streak = 0
                handler = getattr(self, f"_on_{mode.removeprefix('label_')}")
                handler()
                last_activity = time.time()
        log.warning("battle timeout reached")
        self._log_finish("battle_timeout")
        return screens.UNKNOWN

    def _log(self, kind: str, frame=None, **data) -> None:
        if self.ledger is not None:
            self.ledger.record(kind, frame=frame, **data)

    def _log_finish(self, outcome: str) -> None:
        if self.ledger is not None:
            self.ledger.finish(outcome, frame=self._safe_frame())

    def _handle_known_modal(self) -> bool:
        """Escape hatch for modals that a stray tap / keyguard drag can open
        over a live battle. Each carries no phase label, so the main loop would
        treat it as a phase break and idle out; detect and dismiss it instead.
        Structured as a table so more modals can be added later."""
        frame = self._frame()
        modals = ((vision.is_unit_detail_modal, "unit_detail_modal", UNIT_DETAIL_CLOSE),)
        for detect, kind, close_btn in modals:
            if detect(frame):
                log.warning("%s open mid-battle, closing", kind)
                self._log(kind, frame=frame)
                self.actuator.tap(*close_btn)
                time.sleep(1.5)
                return True
        return False

    def _current_mode(self) -> str | None:
        found = self.perception.probe(MODE_LABELS)
        if not found:
            return None
        return max(found.values(), key=lambda e: e.confidence).id

    def _frame(self):
        return self.perception.capture()

    def _safe_frame(self):
        try:
            return self._frame()
        except Exception:
            log.warning("frame capture failed, event will record without a frame", exc_info=True)
            return None

    def _on_not_actionable(self) -> bool:
        """No MODE_LABELS matched: we cannot act right now (docs/
        battle-phase-states.md's NOT_ACTIONABLE) -- enemy turn, third-party
        turn, or an unlabeled transition, none of which the controller needs
        to tell apart. There is exactly one thing here that needs our input:
        the enemy defense-reaction popup (#3, 應戰決策). Its screen anchor
        has not been calibrated on a live device yet, so it is not detected
        below; this is the method to extend once it is.

        Returns whether this counts as activity (an idle-timeout should not
        fire while we're actively responding to something)."""
        # a dying unit pops a MENU-less inline dialogue line; advance it
        # before it is mistaken for a phase break and stalls us
        dialog_frame = self._frame()
        cursor = vision.locate_dialog_cursor(dialog_frame)
        if cursor is not None:
            log.info("in-battle dialog (cursor at %s), advancing", cursor)
            self._log("story_dialog", frame=dialog_frame, cursor=cursor)
            self.actuator.tap(*cursor)
            time.sleep(0.8)
            self._none_streak = 0
            return True
        # two static label-less frames in a row mean we left our own phase
        # (turns can end automatically once every unit has acted, so the
        # end-turn dialog is not a reliable turn boundary)
        self._none_streak += 1
        if self._none_streak >= 2:
            self._phase_break = True
        time.sleep(0.8)
        return False

    def _on_our_turn(self) -> None:
        self._action.reset()
        frame = self._frame()
        if vision.unit_cards_present(frame):
            marker = vision.crop_turn_marker(frame)
            if self._phase_break:
                self._phase_break = False
                self._turn_scouted = False
                # a phase break must be corroborated by the on-screen TURN
                # number actually changing: a stalled modal used to inflate the
                # counter while the screen still read the same turn
                if vision.turn_marker_changed(self._turn_marker, marker):
                    self._turn_marker = marker
                    if self.ledger is not None:
                        self.ledger.next_turn(frame=frame)
                    log.info(
                        "new turn detected (turn %d)", self.ledger.turn if self.ledger else 0
                    )
                else:
                    log.warning("phase break without an on-screen TURN change; not advancing")
            elif self._turn_marker is None:
                self._turn_marker = marker
            self._snapshot_factions(frame)
            self._scout(frame)
            log.info("selecting next actable unit")
            self._log("select_unit", frame=frame)
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
            self._probe_after_select()
            return
        # the card strip animates in after the hub appears; confirm it is
        # really empty before ending the turn
        time.sleep(1.2)
        late_frame = self._frame()
        if vision.unit_cards_present(late_frame):
            log.info("unit cards appeared late, selecting next unit")
            self._log("select_unit", frame=late_frame)
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
            self._probe_after_select()
        else:
            log.info("no actable units left, ending turn")
            self.actuator.tap(*END_TURN_BTN)
            self._phase_break = True
            self._turn_scouted = False
            time.sleep(1.8)

    def _probe_after_select(self, count: int = 3, interval_s: float = 1.0) -> None:
        """Instrument the first-unit-card tap: save a few frames after it so an
        offline replay can show what the tap opened -- a unit selection, a
        transition, or a stray modal (the unexplained 20260706 HARD-2 case
        where a modal appeared ~4s after select with no keyguard event).
        Doubles as the post-tap settle wait."""
        for _ in range(count):
            time.sleep(interval_s)
            self._log("post_select_probe", frame=self._safe_frame())

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
            frame=frame,
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
                    frame=frame,
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
        self._log("attack", frame=self._safe_frame(), slot=slot)
        self.actuator.tap(*ATTACK_BTN)
        time.sleep(2.0)

    def _standby(self, reason: str) -> None:
        self._log("standby", frame=self._safe_frame(), reason=reason)
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
