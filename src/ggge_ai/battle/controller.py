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
from collections.abc import Callable
from dataclasses import dataclass, field

from ggge_ai.battle import executor, reconcile, vision
from ggge_ai.battle.actions import ActionKind
from ggge_ai.battle.identity import IdentityResolver
from ggge_ai.battle.ledger import BattleLedger
from ggge_ai.battle.scout_intel import SurveyIncomplete
from ggge_ai.battle import stage_def as stage_def_mod
from ggge_ai.battle.state import Faction
from ggge_ai.battle.tacmap import TacticalMap
from ggge_ai.battle.tracker import BoardTracker
from ggge_ai.domain import screens
from ggge_ai.vision.motion import frame_diff

log = logging.getLogger(__name__)

AUTO_BUTTON = (1820, 54)
# panning works on the our-turn hub with no unit selected: dragging an
# empty map spot shifts the camera. drag opposite to the look direction,
# split evenly around the center so both endpoints stay inside the map
# area (vertical half-travel is shorter to clear the HUD and card strip)
PAN_CENTER = (1170, 500)
PAN_HALF = {"x": 300, "y": 200}
PAN_DIRS = (("east", (1, 0)), ("west", (-1, 0)), ("north", (0, -1)), ("south", (0, 1)))
# serpentine full-map scan (turn 1): a pan whose measured travel is under
# this fraction of the gesture means the camera hit the map edge; leg
# budgets bound worst-case scan time on huge maps
SCAN_EDGE_RATIO = 0.3
SCAN_CORNER_MAX_LEGS = 8
SCAN_MAX_LEGS = 28
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
# nudge spot for scenes nothing recognizes: top-center hosts no interactive
# element on any battle screen (AUTO/MENU sit right of x1780, 回合結束 left of
# x400, objective text is not tappable), while dialog-style scenes advance on
# a tap anywhere -- so an unrecognized NOT_ACTIONABLE stretch gets nudged here
# instead of stalling forever (user direction 2026-07-11). also resets the
# game's 3-minute idle power-save timer as a side effect
NEUTRAL_TAP = (1170, 90)
NEUTRAL_TAP_AFTER_MISSES = 3
# directional-step move (no extractable cells): one grid cell is ~90-100px
MOVE_STEP_PX = 260
MOVE_STEP_NEAR_PX = 150

AUTO_STATE_IDS = ("btn_auto_full", "btn_auto_enemy", "btn_auto_manual")
MODE_LABELS = (
    "label_our_turn",
    "label_unit_move",
    "label_weapon_select",
    "label_battle_prep",
    "label_skill",
)
# confusable banners probed alongside MODE_LABELS: the enemy-turn banner
# shares three of four glyphs with 我軍回合 and cross-matches label_our_turn
# above the element gate (0.81 raw / 0.83 highpass, 2026-07-11 on-device),
# so a distractor winning the argmax means NOT_ACTIONABLE, not a threshold
DISTRACTOR_LABELS = ("label_enemy_turn",)


def resolve_mode(confidences: dict[str, float]) -> str | None:
    """Best label among phase labels and distractors; None unless a real
    phase label wins. Shared with the fixture harness so tests exercise the
    same decision the controller runs."""
    if not confidences:
        return None
    best = max(confidences, key=lambda k: confidences[k])
    return best if best in MODE_LABELS else None

TERMINAL_SCREENS = (screens.BATTLE_RESULT, screens.REWARD)


# after tapping AUTO the chip must visibly change state within this window,
# otherwise the tap is treated as eaten (power-save lock, mid-animation) and
# retried -- the 20260711 battle sortied with a residual full-auto chip
# because the old guard gave up silently and "continued anyway"
AUTO_CYCLE_VERIFY_S = 6.0


def _best_auto_state(found: dict) -> str | None:
    if not found:
        return None
    return max(found.values(), key=lambda e: e.confidence).id


def read_auto_chip(perception, settle_s: float = 0.4) -> str | None:
    """Confirmed AUTO-chip state: two agreeing reads settle_s apart, None
    when the chip is absent or mid-animation. A global wait-for-static cannot
    work here, ambient map animation keeps frames changing forever."""
    first = _best_auto_state(perception.probe(AUTO_STATE_IDS))
    time.sleep(settle_s)
    second = _best_auto_state(perception.probe(AUTO_STATE_IDS))
    return first if first == second else None


def force_manual_auto(perception, actuator, timeout_s: float = 30.0) -> str:
    """Drive the AUTO toggle to colorless full manual, verifying every
    transition: tap, then require the chip to actually change state within
    AUTO_CYCLE_VERIFY_S before the next decision (act -> verify -> retry).

    Returns "manual" (confirmed), "absent" (chip never seen -- normal on
    story/loading screens; callers decide whether that blocks), or
    "unconfirmed" (chip seen but never confirmed manual within timeout_s --
    the dangerous outcome, callers must not sortie on it)."""
    deadline = time.monotonic() + timeout_s
    seen_chip = False
    while time.monotonic() < deadline:
        state = read_auto_chip(perception)
        if state is None:
            continue
        seen_chip = True
        if state == "btn_auto_manual":
            return "manual"
        log.info("AUTO is %s, cycling toward manual", state)
        actuator.tap(*AUTO_BUTTON)
        verify_deadline = time.monotonic() + AUTO_CYCLE_VERIFY_S
        while time.monotonic() < verify_deadline:
            time.sleep(0.5)
            after = read_auto_chip(perception)
            if after is not None and after != state:
                break
        else:
            log.warning("AUTO tap did not change the chip (still %s), retrying", state)
    return "unconfirmed" if seen_chip else "absent"


def ensure_manual_auto(perception, actuator, timeout_s: float = 60.0) -> bool:
    """Bool adapter over force_manual_auto for callers that only need
    "is it confirmed manual"."""
    return force_manual_auto(perception, actuator, timeout_s) == "manual"


class PilotAbort(Exception):
    """An alignment failure between executor, observer and game: per the
    user's fail-fast call the battle ends immediately, screen left as-is."""


@dataclass
class _ActionState:
    tried_in_place: bool = False
    moved: bool = False
    plan: executor.ActivationPlan | None = None

    def reset(self) -> None:
        self.tried_in_place = False
        self.moved = False
        self.plan = None


@dataclass
class Expectation:
    """One act -> verify contract: after `action` (fired while `source` was
    on screen) the next confirmed mode should land in `targets`.

    Verdicts, checked against every confirmed mode read:
    - observed in targets: transition verified.
    - observed == source: the tap was eaten (power-save lock, mid-animation
      UI) -- on_eaten repairs any handler flag that assumed success, so the
      reactive dispatch retries the action instead of walking a wrong branch.
    - observed is some other real mode: a miss. The screen is authoritative,
      so reality wins and the miss is only recorded (ledger + log) as
      evidence that our transition model of the game is wrong somewhere.
    - no label at all: neutral (animations and interrupts look like this);
      only `checks_left` label-less reads are budgeted before the contract
      expires as unverifiable -- counted in reads, not wall time, so story
      skips and long animations do not burn it."""

    action: str
    source: str | None
    targets: frozenset[str]
    checks_left: int
    on_eaten: Callable[[], None] | None = None
    retries_left: int = 1


@dataclass
class ManualBattleController:
    perception: object
    actuator: object
    keyguard: object | None = None
    ledger: BattleLedger | None = None
    llm: object | None = None
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
    _turn_marker: object | None = None
    _miss_streak: int = 0
    _last_probe: dict = field(default_factory=dict)
    _mode_flicker: tuple | None = None
    _state_desc: str | None = None
    _state_checks: int = 0
    _expectation: Expectation | None = None
    _dispatched_mode: str | None = None
    # reconciliation chain (M4a): specs_by_id is filled by stage intel
    # (M3b); until then expectations are ungrounded and say so
    specs_by_id: dict = field(default_factory=dict)
    # M3b enemy-intel acquisition, run once on the first our-turn hub.
    # None disables it (the default until the flow is live-validated);
    # flow.py arms it via GGGE_INTEL=1
    intel_enabled: bool = False
    stage_id: str | None = None
    intel_cache_root: object | None = None
    # M4b advisor consultation (GGGE_ADVISOR=1): proposals are logged and
    # reconciled against what actually happens, never executed -- v1 still
    # picks the first card
    advisor_enabled: bool = False
    advisor_time_budget_s: float = 3.0
    # pilot execution (GGGE_PILOT=1): the solver drives each activation;
    # "no opinion" demotes one activation to greedy, an alignment failure
    # aborts the battle (fail-fast, user's 2026-07-14 call)
    pilot_enabled: bool = False
    pilot_time_budget_s: float = 3.0
    _intel_done: bool = False
    _full_scan_done: bool = False
    _turn_advised: bool = False
    _turn_sig_refreshed: bool = False
    _proposal: object | None = None
    _card_count: int | None = None
    _id_positions: dict = field(default_factory=dict)
    _pending: reconcile.PendingOutcome | None = None
    _seen_sigs: set = field(default_factory=set)
    _sig_names: dict = field(default_factory=dict)
    tacmap: TacticalMap = field(default_factory=TacticalMap)
    # running board beliefs fed by the read-back hooks (forecast, prep,
    # kill counter, turn boundary); process-scoped, never persisted
    tracker: BoardTracker = field(default_factory=BoardTracker)
    # observations -> uids; passthrough (sig-degraded) until a stage
    # definition seeds it. Shared with the tracker so both canonicalize
    # jittered signatures against the same first-seen registry.
    resolver: IdentityResolver = field(default_factory=IdentityResolver)

    def __post_init__(self) -> None:
        self.tracker.resolver = self.resolver

    def ensure_manual_auto(self, timeout_s: float = 60.0) -> bool:
        """Cycle the AUTO button until it is colorless (full manual)."""
        return ensure_manual_auto(self.perception, self.actuator, timeout_s)

    def force_manual_auto(self, timeout_s: float = 30.0) -> str:
        return force_manual_auto(self.perception, self.actuator, timeout_s)

    def run(self) -> str:
        """Play the battle until a terminal screen. Returns the screen id."""
        # short budget on purpose: the opening screen is often a story or
        # loading frame without the chip, and burning a long timeout there
        # (the old 60s) delays the battle for nothing -- the hub guard
        # re-verifies on every our-turn visit, where the chip is guaranteed
        status = self.force_manual_auto(timeout_s=15.0)
        if status == "absent":
            log.info("AUTO chip not on screen yet, hub guard will enforce manual")
        elif status == "unconfirmed":
            frame = self._safe_frame()
            log.error("AUTO chip visible but never confirmed manual, guard stays armed")
            self._log("auto_guard", frame=frame, where="battle_start", result=status)
            self._llm_read(frame, reason="auto_guard_unconfirmed", force=True)
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
            # no wait-for-static gate here: ambient map animation (snowfall,
            # pulsing range markers) keeps frames changing forever on some
            # maps, which starved this loop of any action for a whole battle
            # (2026-07-11). ACTIONABLE is decided by the phase-label probe
            # alone; one-frame template flukes on animated frames are screened
            # by requiring two agreeing reads before anything is trusted
            if self._confirmed_probe("dlg_end_turn"):
                log.info("end-turn dialog: choosing standby-and-end")
                self.actuator.tap(*END_TURN_STANDBY_OPTION)
                time.sleep(0.8)
                self.actuator.tap(*END_TURN_EXECUTE)
                time.sleep(2.0)
                last_activity = time.time()
                continue
            mode = self._confirmed_mode()
            self._log_state(mode)
            self._check_expectation(mode)
            if mode is not None:
                self._judge_pending(mode)
            if mode is None:
                if self._on_not_actionable():
                    last_activity = time.time()
            else:
                self._miss_streak = 0
                self._dispatched_mode = mode
                handler = getattr(self, f"_on_{mode.removeprefix('label_')}")
                try:
                    handler()
                except PilotAbort as exc:
                    log.error("pilot abort ends the battle: %s", exc)
                    self._log_finish("pilot_abort")
                    return screens.UNKNOWN
                except SurveyIncomplete as exc:
                    log.error("stage survey incomplete, aborting the battle: %s", exc)
                    self._log("survey_abort", reason=str(exc), frame=self._safe_frame())
                    self._log_finish("survey_abort")
                    return screens.UNKNOWN
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
        found = self.perception.probe(MODE_LABELS + DISTRACTOR_LABELS)
        self._last_probe = {eid: e.confidence for eid, e in found.items()}
        return resolve_mode(self._last_probe)

    def _confirmed_mode(self, settle_s: float = 0.35) -> str | None:
        """Two agreeing label reads ~settle_s apart. A transition that briefly
        shows (or leaves behind) a label reads inconsistently and lands in the
        NOT_ACTIONABLE branch, which is exactly where a transition belongs."""
        self._mode_flicker = None
        first = self._current_mode()
        if first is None:
            return None
        time.sleep(settle_s)
        second = self._current_mode()
        if second == first:
            return first
        self._mode_flicker = (first, second)
        return None

    def _describe_state(self, mode: str | None) -> str:
        """One-line answer to "what does the controller think it is looking
        at right now", with the probe evidence that produced the verdict."""
        if mode is not None:
            conf = self._last_probe.get(mode)
            tail = f" ({conf:.2f})" if conf is not None else ""
            return f"ACTIONABLE {mode.removeprefix('label_')}{tail}"
        if self._mode_flicker is not None:
            a, b = self._mode_flicker
            return f"TRANSITION ({a} -> {b})"
        if self._last_probe:
            best, conf = max(self._last_probe.items(), key=lambda kv: kv[1])
            return f"NOT_ACTIONABLE {best.removeprefix('label_')} ({conf:.2f})"
        return "NOT_ACTIONABLE no-label"

    def _log_state(self, mode: str | None) -> None:
        desc = self._describe_state(mode)
        if desc == self._state_desc:
            self._state_checks += 1
            return
        if self._state_desc is not None:
            log.info("state: %s (held %d checks) -> %s", self._state_desc, self._state_checks, desc)
        else:
            log.info("state: %s", desc)
        self._state_desc = desc
        self._state_checks = 1

    def _expect(
        self,
        action: str,
        targets: tuple[str, ...],
        checks: int = 8,
        on_eaten: Callable[[], None] | None = None,
        retries: int = 1,
    ) -> None:
        """Register the transition contract for an action just fired from the
        currently dispatched mode. One at a time: a newer action supersedes
        whatever contract was still open."""
        self._expectation = Expectation(
            action=action,
            source=self._dispatched_mode,
            targets=frozenset(targets),
            checks_left=checks,
            on_eaten=on_eaten,
            retries_left=retries,
        )

    def _check_expectation(self, mode: str | None) -> None:
        exp = self._expectation
        if exp is None:
            return
        if mode is None:
            exp.checks_left -= 1
            if exp.checks_left <= 0:
                log.warning(
                    "transition after %s unverifiable (no phase label for too long)", exp.action
                )
                self._log(
                    "expectation_expired",
                    frame=self._safe_frame(),
                    action=exp.action,
                    expected=sorted(exp.targets),
                )
                self._expectation = None
            return
        if mode in exp.targets:
            log.info("transition verified: %s -> %s", exp.action, mode)
            self._log("expectation_met", action=exp.action, observed=mode)
        elif mode == exp.source and exp.retries_left > 0:
            exp.retries_left -= 1
            log.warning("%s left the screen unchanged (tap eaten?), retrying", exp.action)
            self._log("expectation_retry", action=exp.action, observed=mode)
            if exp.on_eaten is not None:
                exp.on_eaten()
            return
        elif mode == exp.source:
            log.warning("%s still stuck on %s after retrying, giving up on it", exp.action, mode)
            self._log(
                "expectation_expired",
                frame=self._safe_frame(),
                action=exp.action,
                expected=sorted(exp.targets),
                observed=mode,
            )
        else:
            log.warning(
                "expected one of %s after %s, observed %s -- accepting the screen",
                sorted(exp.targets),
                exp.action,
                mode,
            )
            self._log(
                "expectation_miss",
                frame=self._safe_frame(),
                action=exp.action,
                expected=sorted(exp.targets),
                observed=mode,
            )
        self._expectation = None

    def _confirmed_probe(self, element_id: str, settle_s: float = 0.3) -> bool:
        """Two agreeing probes ~settle_s apart, for dialogs that must not be
        answered off a one-frame fluke now that no static gate runs."""
        if not self.perception.probe([element_id]):
            return False
        time.sleep(settle_s)
        return bool(self.perception.probe([element_id]))

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
        # before it stalls us
        dialog_frame = self._frame()
        cursor = vision.locate_dialog_cursor(dialog_frame)
        if cursor is not None:
            log.info("in-battle dialog (cursor at %s), advancing", cursor)
            self._log("story_dialog", frame=dialog_frame, cursor=cursor)
            self.actuator.tap(*cursor)
            time.sleep(0.8)
            self._miss_streak = 0
            return True
        # nothing recognized this scene at all: after a few misses, nudge a
        # non-button spot -- dialog-style scenes advance on any tap, and
        # anything else safely ignores it. an unrecognized variant of a known
        # scene (e.g. a dialog whose cursor sits outside the calibrated band)
        # then advances instead of stalling until the idle timeout
        self._miss_streak += 1
        if self._miss_streak >= NEUTRAL_TAP_AFTER_MISSES:
            self._miss_streak = 0
            log.info("scene unrecognized for %d checks, neutral tap", NEUTRAL_TAP_AFTER_MISSES)
            # ask the LLM what this is before nudging (rate-limited inside the
            # reader); skip when a distractor label already names the scene
            if not self._last_probe:
                self._llm_read(dialog_frame, reason="unrecognized_scene")
            self._log("neutral_tap", frame=dialog_frame)
            self.actuator.tap(*NEUTRAL_TAP)
        time.sleep(0.8)
        return False

    def _guard_auto(self) -> None:
        """Re-verify the control red line on every our-turn hub visit, where
        the AUTO chip is guaranteed on screen: a residual or stray full/enemy
        state hands units to the built-in AI mid-battle, so it is forced back
        to manual the moment it is seen. Trigger is one cheap probe; the
        enforcement itself re-reads with confirmation, so a one-frame fluke
        costs one force_manual_auto call that returns immediately."""
        state = _best_auto_state(self.perception.probe(AUTO_STATE_IDS))
        if state in (None, "btn_auto_manual"):
            return
        log.error("AUTO left on %s at the hub, forcing manual", state)
        frame = self._safe_frame()
        status = self.force_manual_auto(timeout_s=20.0)
        self._log("auto_guard", frame=frame, where="hub", state=state, result=status)
        if status != "manual":
            self._llm_read(frame, reason="auto_guard_unconfirmed", force=True)

    def _llm_read(self, frame, reason: str, force: bool = False) -> None:
        """Advisory LLM description of a frame nothing else recognized: one
        log line plus a ledger event, never control authority."""
        if self.llm is None or frame is None:
            return
        reading = self.llm.read(frame, force=force)
        if reading is None:
            return
        log.info("llm read (%s): %s", reason, reading.summary())
        self._log("llm_read", frame=frame, reason=reason, **reading.to_event())

    def _on_our_turn(self) -> None:
        self._action.reset()
        self._guard_auto()
        frame = self._frame()
        if vision.unit_cards_present(frame):
            # the turn boundary is the on-screen TURN number changing between
            # hub visits: turns auto-advance once every unit has acted, so the
            # end-turn dialog is not reliable, and quiet label-less stretches
            # (the old phase-break streak) also occur mid-turn during attack
            # animations. primary read is digit OCR of the number itself (the
            # HARD 1 ledger sat on turn=1 all battle because the marker-diff
            # compare never fired); the marker compare stays as the fallback
            # for frames where the chip does not read
            turn_number = vision.read_turn_number(frame)
            if turn_number is not None:
                current = self.ledger.turn if self.ledger is not None else 0
                if turn_number - current > 3:
                    # a single bad read must not poison the counter forever
                    # (every later true value would compare lower); jumps
                    # this size are misreads, real skips are 1-2 turns
                    log.warning(
                        "TURN read %d jumps too far from %d, ignoring as a misread",
                        turn_number,
                        current,
                    )
                elif turn_number > current:
                    self._turn_scouted = False
                    self._turn_advised = False
                    self._turn_sig_refreshed = False
                    self.tracker.on_turn(turn_number)
                    if self.ledger is not None:
                        self.ledger.next_turn(frame=frame, turn=turn_number)
                    log.info("new turn detected (TURN %d on screen)", turn_number)
                self._turn_marker = vision.crop_turn_marker(frame)
            else:
                marker = vision.crop_turn_marker(frame)
                if self._turn_marker is None:
                    self._turn_marker = marker
                elif vision.turn_marker_changed(self._turn_marker, marker):
                    self._turn_marker = marker
                    self._turn_scouted = False
                    self._turn_advised = False
                    self._turn_sig_refreshed = False
                    self.tracker.on_turn(self.tracker.turn + 1)
                    if self.ledger is not None:
                        self.ledger.next_turn(frame=frame)
                    log.info(
                        "new turn detected (marker change, turn %d)",
                        self.ledger.turn if self.ledger else 0,
                    )
            self._card_count = vision.count_unit_cards(frame)
            self._snapshot_factions(frame)
            self._scout(frame)
            self._ensure_stage_definition(frame)
            self._refresh_sig_positions(frame)
            self._consult_advisor()
            log.info("selecting next actable unit")
            self._log("select_unit", frame=frame, cards=self._card_count)
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
            self._expect("select_unit", ("label_unit_move", "label_weapon_select"))
            self._probe_after_select()
            return
        # the card strip animates in after the hub appears; confirm it is
        # really empty before ending the turn
        time.sleep(1.2)
        late_frame = self._frame()
        if vision.unit_cards_present(late_frame):
            log.info("unit cards appeared late, selecting next unit")
            self._card_count = vision.count_unit_cards(late_frame)
            self._log("select_unit", frame=late_frame, cards=self._card_count)
            self.actuator.tap(*vision.FIRST_UNIT_CARD)
            self._expect("select_unit", ("label_unit_move", "label_weapon_select"))
            self._probe_after_select()
        else:
            log.info("no actable units left, ending turn")
            self.actuator.tap(*END_TURN_BTN)
            self._turn_scouted = False
            time.sleep(1.8)

    def _ensure_stage_definition(self, frame) -> None:
        """S6: the stage definition is the solver's game description.
        Warm start: load + census-validate against this turn's sweep,
        adopt on success. Anything else -- no file, old schema, failed
        validation -- falls back to a full fail-loud survey (cold start),
        which writes the definition for every later entry. Runs once per
        battle on the first our-turn hub."""
        if not self.intel_enabled or self._intel_done:
            return
        self._intel_done = True
        if self.stage_id is None:
            raise SurveyIncomplete("intel enabled but no stage_id given")
        from .scout_intel import survey_stage, validate_stage

        scan = [tuple(p) for p in self.tacmap.enemies + self.tacmap.third_party]
        factions = ["enemy"] * len(self.tacmap.enemies) + ["third_party"] * len(
            self.tacmap.third_party
        )
        defn = stage_def_mod.load_stage_def(self.stage_id, self.intel_cache_root)
        if defn is not None and defn.status == "complete":
            report = validate_stage(
                defn,
                scan,
                capture=self._frame,
                tap=self.actuator.tap,
                bring_to_view=self._bring_to_view,
                ledger_log=self._log,
            )
            self._log(
                "stage_validation",
                ok=report.ok,
                taps=report.taps,
                mismatches=report.mismatches[:8],
            )
            if report.ok and report.resolver is not None:
                log.info("stage definition validated, warm start")
                self._adopt_definition(defn, report.resolver)
                return
            defn.status = "stale"
            stage_def_mod.save_stage_def(defn, self.intel_cache_root)
            log.warning("stage definition stale, falling back to a live survey")
        defn = survey_stage(
            self._frame,
            self.actuator.tap,
            scan,
            stage_id=self.stage_id,
            bring_to_view=self._bring_to_view,
            factions=factions,
            llm=self.llm,
            ledger_log=self._log,
            root=self.intel_cache_root,
        )
        resolver = IdentityResolver(defn)
        seed = resolver.seed(scan)
        if not seed.ok:
            raise SurveyIncomplete(
                f"fresh definition failed its own census: {len(seed.unmatched_uids)} "
                "layout units unmatched"
            )
        self._adopt_definition(defn, resolver)

    def _adopt_definition(self, defn, resolver: IdentityResolver) -> None:
        """Swap the shared resolver to the seeded one and load the game
        description: specs per uid, positions from the census, opening
        HP/EN beliefs from the file (spot-validated; apply() still
        reports every carried value as an assumption)."""
        self.resolver = resolver
        self.tracker.resolver = resolver
        for unit in defn.layout:
            if unit.stats:
                try:
                    spec, assumptions = unit.to_spec()
                except TypeError:
                    self._log(
                        "definition_assumptions",
                        uid=unit.uid,
                        assumptions=["stats incomplete, unit stays spec-less"],
                    )
                else:
                    self.specs_by_id[unit.uid] = spec
                    if assumptions:
                        self._log(
                            "definition_assumptions", uid=unit.uid, assumptions=assumptions
                        )
            if unit.sig is not None and unit.name_text:
                self._sig_names[unit.sig] = unit.name_text
        for uid, pos in resolver.positions().items():
            self._id_positions[uid] = pos
            self.tracker.on_position(uid, pos)
            belief = self.tracker.beliefs.get(uid)
            unit = next((u for u in defn.layout if u.uid == uid), None)
            if belief is not None and unit is not None:
                if belief.hp is None:
                    belief.hp = unit.stats.get("hp")
                if belief.en is None:
                    belief.en = unit.stats.get("en")
                belief.source = "definition"
        log.info(
            "definition adopted: %d units, %d specs",
            len(defn.layout),
            len(self.specs_by_id),
        )

    def _bring_to_view(self, world) -> tuple[float, float] | None:
        """Pan until a world point sits inside the tappable map area and
        return its screen point. Constellation locate() recovers the
        camera before each leg, so pan drift cannot accumulate; edge
        saturation with the target still outside means the board and the
        map disagree -- the caller treats None as fail-loud evidence.
        Live validation is the S9b probe."""
        x0, y0, w, h = vision.HUB_SCAN_REGION
        margin = 60
        for _ in range(8):
            frame = self._frame()
            arcs = (
                vision.find_ally_units(frame)
                + vision.find_enemy_units(frame)
                + vision.find_third_party_units(frame)
            )
            camera = self.tacmap.locate(arcs)
            if camera is None:
                return None
            screen = (world[0] - camera[0], world[1] - camera[1])
            if (
                x0 + margin <= screen[0] <= x0 + w - margin
                and y0 + margin <= screen[1] <= y0 + h - margin
            ):
                return screen
            direction = (
                (screen[0] > x0 + w - margin) - (screen[0] < x0 + margin),
                (screen[1] > y0 + h - margin) - (screen[1] < y0 + margin),
            )
            new_camera, _, actual, requested = self._pan_leg(camera, frame, direction)
            if abs(actual[0]) + abs(actual[1]) < (
                abs(requested[0]) + abs(requested[1])
            ) * SCAN_EDGE_RATIO:
                return None
        return None

    def _build_board(self):
        """Perceived board for the solver: fresh scan positions, tracked
        identities (dead sigs excluded), carried beliefs applied on top.
        Returns (battle, notes) where notes report every carried value."""
        from .observe import build_battle_state

        positions = {
            uid: pos
            for uid, pos in self._id_positions.items()
            if uid not in self.tracker.beliefs or self.tracker.beliefs[uid].alive
        }
        notes: list[str] = []
        battle = build_battle_state(
            self.tacmap,
            specs_by_id=self.specs_by_id,
            id_positions=positions,
            ally_id_positions=self.tracker.id_positions(Faction.ALLY),
            turn=self.ledger.turn if self.ledger is not None else self.tracker.turn,
            # the tacmap is scouted on our-turn hub frames, where the pinned
            # pink-ally bug makes enemy arcs untrustworthy; per the settled
            # M4 verdict (H/S/V identical on the mixed-faction fixture) only
            # sig-confirmed enemies enter the simulation
            hub_poisoned=True,
            notes=notes,
        )
        notes += self.tracker.apply(battle)
        if self._card_count is not None and self._card_count > len(battle.allies()):
            notes.append(
                f"unit cards visible {self._card_count} > allies on board "
                f"{len(battle.allies())}: board is missing allies"
            )
        return battle, notes

    def _refresh_sig_positions(self, frame) -> None:
        """M5: once per turn, re-anchor tracked enemy identities to the
        fresh scan so the sig match does not decay as enemies move.
        Quiet nearest-neighbour updates when unambiguous; budgeted
        summary-card taps only for contested candidates."""
        if self._turn_sig_refreshed:
            return
        self._turn_sig_refreshed = True
        known = self.tracker.id_positions()
        if not known:
            return
        candidates = vision.find_enemy_units(frame, region=vision.HUB_SCAN_REGION)
        if not candidates:
            return
        from .scout_intel import refresh_sig_positions

        refresh = refresh_sig_positions(
            self._frame,
            self.actuator.tap,
            [(float(x), float(y)) for x, y in candidates],
            known,
            ledger_log=self._log,
            resolve=lambda sig, point: self.resolver.uid_for(sig, world=point),
        )
        for uid, pos in refresh.positions.items():
            self._id_positions[uid] = pos
            self.tracker.on_position(uid, pos)
        self._log(
            "sig_refresh_summary",
            quiet=refresh.matched_quietly,
            taps=refresh.taps,
            updated=len(refresh.positions),
            unresolved=refresh.unresolved[:8],
        )
        log.info(
            "sig refresh: %d quiet, %d taps, %d unresolved",
            refresh.matched_quietly,
            refresh.taps,
            len(refresh.unresolved),
        )

    def _consult_advisor(self) -> None:
        """M4b: ask the simulator's advisor for its best first decision,
        once per turn -- logged as a proposal, never executed. When the
        weapon-select forecast later names a different target than the
        proposal, that lands as [SIM-DIVERGE] proposal_target evidence."""
        if not self.advisor_enabled or self._turn_advised:
            return
        self._turn_advised = True
        self._proposal = None
        from . import advisor as advisor_mod

        battle, belief_notes = self._build_board()
        advice = advisor_mod.advise(
            battle,
            self.specs_by_id,
            advisor_mod.AdvisorConfig(time_budget_s=self.advisor_time_budget_s, cell_size=95.0),
        )
        if advice is None:
            log.info("advisor: nothing to propose on this board")
            return
        self._proposal = advice
        self._log(
            "decision",
            action="proposal",
            unit=advice.unit_id,
            proposal_kind=advice.kind,
            target=advice.target_id,
            weapon=advice.weapon,
            value=round(advice.value, 1),
            pv_kinds=advice.pv_kinds[:8],
            assumptions=advice.assumptions[:8],
            beliefs=belief_notes[:8],
        )
        log.info(
            "advisor proposal: %s %s -> %s (value %.0f, %d assumptions) -- not executed, v1 compares only",
            advice.unit_id,
            advice.kind,
            self._describe_id(advice.target_id) or advice.target_id,
            advice.value,
            len(advice.assumptions),
        )

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
        """Rebuild the tactical map once per turn. The first scan of a
        battle is a corner-start serpentine sweep of the whole map (the
        user's 2026-07-12 direction: sync every unit into the backend
        simulation, partial views miss whole forces); later turns refresh
        with the cheap four-direction local scan around the hub view.
        Every pan is measured with phase correlation before world
        coordinates are assigned."""
        if self._turn_scouted:
            return
        self._turn_scouted = True
        self.tacmap.reset()
        camera = (0.0, 0.0)
        self._observe_map(frame, camera)
        if not self._full_scan_done:
            self._full_scan_done = True
            camera, legs = self._scout_serpentine(frame, camera)
            scan = f"serpentine({legs} legs)"
        else:
            camera = self._scout_local(frame, camera)
            scan = "local"
        self._enemy_hint = self._hint_from_map()
        self._log(
            "tactical_map",
            frame=frame,
            scan=scan,
            enemies=[(round(x), round(y)) for x, y in self.tacmap.enemies],
            allies=[(round(x), round(y)) for x, y in self.tacmap.allies],
            third_party=[(round(x), round(y)) for x, y in self.tacmap.third_party],
            camera_drift=(round(camera[0]), round(camera[1])),
        )
        log.info(
            "scout (%s): tactical map has %d enemies / %d allies / %d third-party",
            scan,
            len(self.tacmap.enemies),
            len(self.tacmap.allies),
            len(self.tacmap.third_party),
        )

    def _scout_local(self, frame, camera) -> tuple[float, float]:
        """Four out-and-back legs around the current view; all observations
        share the scan origin."""
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
        return camera

    def _pan_leg(self, camera, prev, direction):
        """One measured pan. Returns (camera, frame, actual, requested);
        actual << requested means the camera hit the map edge -- at an edge
        the two frames are identical, so phase correlation reads ~0 with a
        strong response (the featureless-view fallback only fires on weak
        response and cannot mask an edge)."""
        dx, dy = direction
        hx, hy = dx * PAN_HALF["x"], dy * PAN_HALF["y"]
        cx, cy = PAN_CENTER
        self.actuator.swipe(cx + hx, cy + hy, cx - hx, cy - hy, 500)
        time.sleep(1.0)
        cur = self._frame()
        requested = (2 * hx, 2 * hy)
        new_camera = self._advance_camera(camera, prev, cur, requested)
        actual = (new_camera[0] - camera[0], new_camera[1] - camera[1])
        return new_camera, cur, actual, requested

    @staticmethod
    def _at_edge(actual, requested, axis: int) -> bool:
        return abs(actual[axis]) < abs(requested[axis]) * SCAN_EDGE_RATIO

    def _scout_serpentine(self, frame, camera) -> tuple[tuple[float, float], int]:
        """Corner-start full-map sweep: pan to the northwest corner (a leg
        saturates when the map stops moving), then snake east/west with
        south steps until the bottom edge, observing at every stop. The
        leg budget bounds worst-case scan time on huge maps."""
        prev = frame
        legs = 0
        pending = {"west": (-1, 0), "north": (0, -1)}
        while pending and legs < SCAN_CORNER_MAX_LEGS:
            for name in list(pending):
                camera, prev, actual, requested = self._pan_leg(camera, prev, pending[name])
                legs += 1
                self._observe_map(prev, camera)
                axis = 0 if name == "west" else 1
                if self._at_edge(actual, requested, axis):
                    del pending[name]
                if legs >= SCAN_CORNER_MAX_LEGS:
                    break
        heading = (1, 0)
        bottom_row = False
        while legs < SCAN_MAX_LEGS:
            camera, prev, actual, requested = self._pan_leg(camera, prev, heading)
            legs += 1
            self._observe_map(prev, camera)
            if self._at_edge(actual, requested, 0):
                if bottom_row:
                    break
                camera, prev, actual, requested = self._pan_leg(camera, prev, (0, 1))
                legs += 1
                self._observe_map(prev, camera)
                if self._at_edge(actual, requested, 1):
                    # bottom edge: one last row still needs walking, or the
                    # far bottom corner is never observed
                    bottom_row = True
                heading = (-heading[0], 0)
        return camera, legs

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
            threats=vision.find_threat_cells(frame),
        )

    def _hint_from_map(self) -> tuple[float, float] | None:
        """Heading from our force toward the enemy mass. Threat cells first:
        HP-arc faction colors misread on the our-turn hub (the pinned hp_arc
        bug fed 22 phantom enemies into a 14-enemy map and steered the hint
        west while the enemy force sat north, 20260712 run), while the "!"
        overlay only ever renders around real enemies."""
        origin = vision.centroid([(round(x), round(y)) for x, y in self.tacmap.allies])
        if origin is None:
            origin = PAN_CENTER
        toward = self.tacmap.threat_centroid()
        if toward is None:
            toward = self.tacmap.nearest_enemy(origin)
        if toward is None:
            return None
        dx, dy = toward[0] - origin[0], toward[1] - origin[1]
        n = max((dx * dx + dy * dy) ** 0.5, 1.0)
        return (dx / n, dy / n)

    def _pilot_abort(self, reason: str, frame=None, **detail) -> None:
        log.error("pilot abort: %s %s", reason, detail)
        self._log(
            "pilot_abort",
            frame=frame if frame is not None else self._safe_frame(),
            reason=reason,
            **detail,
        )
        raise PilotAbort(reason)

    def _pilot_begin(self) -> bool:
        """Identify the selected unit, ask the solver for its activation,
        and pin the plan. False = no opinion, the greedy body takes this
        activation; alignment failures raise instead of returning."""
        frame = self._frame()
        cells = vision.find_move_cells(frame)
        origin = vision.centroid(cells) if cells else None
        if origin is None:
            origin = PAN_CENTER
        found = executor.identify(frame, self.tacmap, origin)
        if found is None:
            self._pilot_abort("anchor_failed", frame=frame, origin=list(origin))
        unit_world, camera = found
        battle, notes = self._build_board()
        ally_id = executor.resolve_ally(battle, unit_world)
        if ally_id is None:
            self._pilot_abort(
                "identify_ambiguous",
                frame=frame,
                unit_world=[round(unit_world[0]), round(unit_world[1])],
            )
        from . import advisor as advisor_mod

        advice = advisor_mod.advise(
            battle,
            self.specs_by_id,
            advisor_mod.AdvisorConfig(time_budget_s=self.pilot_time_budget_s, cell_size=95.0),
            unit_id=ally_id,
        )
        if advice is None:
            self._log("pilot_fallback", reason="no_advice", unit=ally_id)
            return False
        if advice.kind not in (ActionKind.ATTACK, ActionKind.MOVE, ActionKind.STANDBY):
            self._log(
                "pilot_fallback", reason="unsupported_kind",
                advice_kind=advice.kind, unit=ally_id,
            )
            return False
        slot = None
        if advice.kind == ActionKind.ATTACK:
            if not executor.verifiable_target(advice.target_id, self.resolver):
                self._log(
                    "pilot_fallback", reason="unverifiable_target",
                    unit=ally_id, target=advice.target_id,
                )
                return False
            slot = executor.slot_for(advice, self.specs_by_id.get(ally_id))
            if slot is None:
                self._pilot_abort(
                    "weapon_unresolved", frame=frame, unit=ally_id, weapon=advice.weapon
                )
        self._action.plan = executor.ActivationPlan(
            advice=advice,
            ally_id=ally_id,
            unit_world=unit_world,
            camera=camera,
            weapon_slot=slot,
        )
        self._log(
            "pilot_plan",
            frame=frame,
            unit=ally_id,
            advice_kind=advice.kind,
            target=advice.target_id,
            weapon=advice.weapon,
            slot=slot,
            move_world=(
                [round(advice.move_world[0]), round(advice.move_world[1])]
                if advice.move_world is not None
                else None
            ),
            value=round(advice.value, 1),
            assumptions=advice.assumptions[:8],
            beliefs=notes[:8],
        )
        log.info(
            "pilot plan: %s %s -> %s (weapon %s, move %s)",
            ally_id,
            advice.kind,
            self._describe_id(advice.target_id) or advice.target_id,
            advice.weapon,
            advice.move_world,
        )
        return True

    def _pilot_unit_move(self) -> bool:
        """True when the pilot handled this unit-move visit; False demotes
        the activation to the greedy body."""
        if self._action.plan is None:
            if self._action.tried_in_place or self._action.moved:
                return False
            if not self._pilot_begin():
                return False
        plan = self._action.plan
        advice = plan.advice
        if advice.kind == ActionKind.STANDBY:
            self._log("pilot_step", step="standby", unit=plan.ally_id)
            self._standby("pilot_standby")
            return True
        if advice.move_world is not None and not plan.move_done:
            frame = self._frame()
            cells = vision.find_move_cells(frame)
            mv = executor.move_tap(advice, plan.camera, cells)
            if mv is None:
                self._pilot_abort(
                    "move_unreachable",
                    frame=frame,
                    unit=plan.ally_id,
                    move_world=[round(advice.move_world[0]), round(advice.move_world[1])],
                    cells=len(cells),
                )
            basis, point = mv
            plan.move_done = True
            self._action.moved = True
            self._log(
                "pilot_step", step="move", frame=frame,
                unit=plan.ally_id, basis=basis, cell=list(point),
            )
            self.actuator.tap(*point)
            time.sleep(2.0)
            return True
        if advice.kind == ActionKind.MOVE:
            self._log("pilot_step", step="standby_after_move", unit=plan.ally_id)
            self._standby("pilot_move_done")
            return True
        self._action.tried_in_place = True
        self._log("pilot_step", step="open_weapon_select", unit=plan.ally_id)
        self.actuator.tap(*WEAPON_SELECT_BTN)
        self._expect(
            "open_weapon_select",
            ("label_weapon_select",),
            on_eaten=lambda: setattr(self._action, "tried_in_place", False),
        )
        time.sleep(1.8)
        return True

    def _pilot_weapon_select(self, plan: executor.ActivationPlan) -> None:
        slot = plan.weapon_slot
        self.actuator.tap(*WEAPON_SLOTS[slot - 1])
        time.sleep(1.0)
        frame = self._frame()
        if not vision.attack_enabled(frame):
            self._pilot_abort(
                "weapon_not_lit", frame=frame, slot=slot, weapon=plan.advice.weapon
            )
        forecast = vision.read_weapon_select_forecast(frame)
        while (
            not self._pilot_target_ok(forecast, plan.advice) and plan.switch_budget > 0
        ):
            found = self.perception.probe(["btn_switch_target"])
            if not found:
                break
            plan.switch_budget -= 1
            self._log(
                "pilot_step",
                step="switch_target",
                seen=forecast.target_name_sig if forecast is not None else None,
                want=plan.advice.target_id,
            )
            self.actuator.tap(*found["btn_switch_target"].bbox.center)
            time.sleep(1.0)
            frame = self._frame()
            forecast = vision.read_weapon_select_forecast(frame)
        if not self._pilot_target_ok(forecast, plan.advice):
            self._pilot_abort(
                "target_mismatch",
                frame=frame,
                want=plan.advice.target_id,
                seen=forecast.target_name_sig if forecast is not None else None,
            )
        if forecast.our_name_sig is not None:
            self.tracker.on_sig_position(forecast.our_name_sig, plan.unit_world, Faction.ALLY)
        self._log(
            "pilot_step", step="attack", unit=plan.ally_id, slot=slot,
            target=plan.advice.target_id,
        )
        self._register_attack_decision(frame, slot=slot)
        self._attack(slot=slot)

    def _on_unit_move(self) -> None:
        if self.pilot_enabled and self._pilot_unit_move():
            return
        if not self._action.tried_in_place:
            log.info("opening weapon select in place")
            self._action.tried_in_place = True
            self.actuator.tap(*WEAPON_SELECT_BTN)
            # an eaten tap must clear the flag, or the next visit walks the
            # move branch believing weapon select was already tried
            self._expect(
                "open_weapon_select",
                ("label_weapon_select",),
                on_eaten=lambda: setattr(self._action, "tried_in_place", False),
            )
            time.sleep(1.8)
            return
        if not self._action.moved:
            frame = self._frame()
            cells = vision.find_move_cells(frame)
            target, basis = self._seek_move_target(frame, cells)
            if target is not None and cells:
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
            if target is not None:
                # cell extraction failed (bright maps: the outline mask
                # saturates on snow ground, 20260712 analysis) but we do know
                # the direction -- step the selected unit (screen center
                # after the recenter) toward it and let the follow-up weapon
                # try / standby flow judge the result
                point = self._directional_step(frame, target)
                log.info("no cells extracted, directional step to %s (basis %s)", point, basis)
                self._log(
                    "move",
                    frame=frame,
                    basis=f"directional_{basis}",
                    target=(round(target[0]), round(target[1])),
                    cell=point,
                )
                self._action.moved = True
                self.actuator.tap(*point)
                time.sleep(2.0)
                return
            log.info(
                "no enemy direction found (move cells %d, tacmap enemies %d, scout hint %s), standing by",
                len(cells),
                len(self.tacmap.enemies),
                self._enemy_hint,
            )
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
        one; (2) the on-screen threat-cell centroid -- the "!" overlay only
        renders around real enemies, so it survives the arc-color
        misclassification that poisons the tacmap and scout hint (20260712:
        the hint pointed west while the enemy force sat due north); (3)
        anchor the camera against the map and aim at the nearest world
        enemy; (4) fall back to the scouted world heading from our force
        toward the enemy mass -- a pure translation, so a world direction is
        a screen direction regardless of camera offset (a single force-wide
        heading, which walks front-line units away from a side/rear enemy)."""
        origin = vision.centroid(cells) if cells else PAN_CENTER
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
        threat = vision.centroid(vision.find_threat_cells(frame))
        if threat:
            log.info("steering by on-screen threat centroid %s", threat)
            return (float(threat[0]), float(threat[1])), "threat_centroid"
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
        return None, None

    @staticmethod
    def _directional_step(frame, target: tuple[float, float]) -> tuple[int, int]:
        """A map tap stepping the selected unit toward `target` when no move
        cells could be extracted. The unit sits near screen center after the
        selection recenter; step ~2.5 cells out (clamped to the map region),
        pulling back to ~1.5 cells if the spot lands on a detected unit arc
        so the tap orders a move instead of inspecting someone."""
        ox, oy = PAN_CENTER
        dx, dy = target[0] - ox, target[1] - oy
        n = max((dx * dx + dy * dy) ** 0.5, 1.0)
        arcs = (
            vision.find_enemy_units(frame)
            + vision.find_ally_units(frame)
            + vision.find_third_party_units(frame)
        )
        x0, y0, w, h = vision.MAP_REGION
        for step in (MOVE_STEP_PX, MOVE_STEP_NEAR_PX):
            px = min(max(ox + dx / n * step, x0 + 30), x0 + w - 30)
            py = min(max(oy + dy / n * step, y0 + 30), y0 + h - 30)
            point = (round(px), round(py))
            if not any((a[0] - px) ** 2 + (a[1] - py) ** 2 < 70 * 70 for a in arcs):
                return point
        return point

    def _on_weapon_select(self) -> None:
        plan = self._action.plan
        if self.pilot_enabled and plan is not None and plan.advice.kind == ActionKind.ATTACK:
            self._pilot_weapon_select(plan)
            return
        frame = self._frame()
        if vision.attack_enabled(frame):
            log.info("target locked, attacking")
            self._register_attack_decision(frame, slot=0)
            self._attack(slot=0)
            return
        for i, slot in enumerate(WEAPON_SLOTS):
            self.actuator.tap(*slot)
            time.sleep(1.0)
            slot_frame = self._frame()
            if vision.attack_enabled(slot_frame):
                log.info("weapon slot %d has a target, attacking", i + 1)
                self._register_attack_decision(slot_frame, slot=i + 1)
                self._attack(slot=i + 1)
                return
            log.debug("weapon slot %d: no target in range", i + 1)
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

    def _register_attack_decision(self, frame, slot: int) -> None:
        """The reconciliation chain's layer-1/2 handshake, run just before
        the attack tap: ground a simulator expectation, read the game's own
        weapon-select forecast, and log both plus their divergences. The
        pending outcome then waits for battle-prep and the 破壞數 verdict."""
        forecast = vision.read_weapon_select_forecast(frame)
        if forecast is None:
            log.debug("weapon-select forecast unreadable, attack proceeds unreconciled")
            return
        counter = vision.read_kill_counter(frame)
        self._note_sig(forecast.our_name_sig, frame, vision.FORECAST_RIGHT_NAME_REGION, "ours")
        self._note_sig(forecast.target_name_sig, frame, vision.FORECAST_LEFT_NAME_REGION, "enemy")
        self.tracker.on_weapon_select(forecast)
        attacker_id = (
            self.resolver.uid_for(forecast.our_name_sig, "ally")
            if forecast.our_name_sig is not None
            else None
        )
        target_id = (
            self.resolver.uid_for(forecast.target_name_sig)
            if forecast.target_name_sig is not None
            else None
        )
        expectation = reconcile.compute_expectation(
            attacker_spec=self.specs_by_id.get(attacker_id),
            target_spec=self.specs_by_id.get(target_id),
            forecast=forecast,
            slot=slot,
            attacker_id=attacker_id,
            target_id=target_id,
        )
        self._log(
            "forecast_weapon_select",
            frame=frame,
            our_sig=forecast.our_name_sig,
            our_hp=forecast.our_hp,
            our_en=forecast.our_en,
            target_sig=forecast.target_name_sig,
            target_hp=forecast.target_hp,
            target_en=forecast.target_en,
            predicted_damage=forecast.predicted_damage,
            counter=list(counter) if counter else None,
        )
        if self._pending is not None and self._pending.armed:
            log.debug("previous attack outcome never verified, superseding it")
            self._log("kill_check", result="superseded")
        pending, divergences = reconcile.reconcile_weapon_select(expectation, forecast, counter)
        self._pending = pending
        for d in divergences:
            log.warning(d.message)
            self._log(d.tag, frame=frame, divergence=d.kind, **d.detail)
        proposal = self._proposal
        if (
            proposal is not None
            and getattr(proposal, "target_id", None) is not None
            and expectation.target_id is not None
            and proposal.target_id in self._id_positions
            and proposal.target_id != expectation.target_id
        ):
            log.warning(
                "[SIM-DIVERGE] proposal_target: advisor proposed attacking %s, "
                "actual target is %s",
                self._describe_id(proposal.target_id),
                self._describe_id(expectation.target_id),
            )
            self._log(
                "sim_diverge",
                divergence="proposal_target",
                proposal_unit=proposal.unit_id,
                proposal_target=proposal.target_id,
                actual_target=expectation.target_id,
            )
        self._log(
            "decision",
            action="attack",
            slot=slot,
            attacker=self._describe_id(expectation.attacker_id),
            target=self._describe_id(expectation.target_id),
            expected_damage=(
                round(expectation.expected_damage)
                if expectation.expected_damage is not None
                else None
            ),
            target_hp=expectation.target_hp_believed,
            expect_kill=expectation.expect_kill,
            hit_probability=(
                round(expectation.hit_probability, 3)
                if expectation.hit_probability is not None
                else None
            ),
            source=expectation.source,
            quality=expectation.quality,
            assumptions=list(expectation.assumptions),
        )
        log.info(
            "decision: %s attacks %s with slot %d, sim expects %s damage on %s HP -> %s [%s]",
            self._describe_id(expectation.attacker_id),
            self._describe_id(expectation.target_id),
            slot,
            "?" if expectation.expected_damage is None else round(expectation.expected_damage),
            expectation.target_hp_believed,
            {True: "kill", False: "no kill", None: "no call"}[expectation.expect_kill],
            expectation.quality,
        )

    def _describe_id(self, uid: str | None) -> str | None:
        if uid is None:
            return None
        return self._describe_sig(self.resolver.expected_sig(uid)) or uid

    def _pilot_target_ok(self, forecast, advice) -> bool:
        belief = self.tracker.beliefs.get(advice.target_id)
        return executor.target_ok(
            forecast,
            advice,
            self.resolver,
            believed_hp=belief.hp if belief is not None else None,
        )

    def _describe_sig(self, sig: str | None) -> str | None:
        if sig is None:
            return None
        name = self._sig_names.get(sig)
        return f"{name} (sig {sig[:6]})" if name else f"sig {sig[:6]}"

    def _note_sig(self, sig: str | None, frame, region: tuple[int, int, int, int], role: str) -> None:
        """First sighting of a unit signature: archive its name-plate crop
        and ask the LLM (rate-limited, advisory) for a human-readable name
        so logs can say 鋼彈F90 instead of a hash."""
        if sig is None or sig in self._seen_sigs:
            return
        self._seen_sigs.add(sig)
        x, y, w, h = region
        crop = frame[y : y + h, x : x + w]
        name = None
        if self.llm is not None:
            name = self.llm.transcribe(
                crop,
                "Transcribe the unit name on this game UI name plate "
                "(Traditional Chinese / Japanese, single line).",
            )
        if name:
            self._sig_names[sig] = name
        self._log("unit_intel", frame=crop, sig=sig, role=role, name=name)
        log.info("new unit signature %s (%s)%s", sig, role, f" -> {name}" if name else "")

    def _judge_pending(self, mode: str) -> None:
        """Layer 3: once the engagement resolved (any actionable mode after
        battle-prep), the 破壞數 delta is the verdict on the expected kill."""
        pending = self._pending
        if pending is None or not pending.armed or mode == "label_battle_prep":
            return
        counter = vision.read_kill_counter(self._frame())
        if counter is None:
            pending.checks_left -= 1
            if pending.checks_left <= 0:
                log.warning("kill counter stayed unreadable, attack outcome unverified")
                self._log("kill_check", result="unverified_counter_unreadable")
                self._pending = None
            return
        result, divergences = reconcile.judge_outcome(pending, counter)
        delta = counter[0] - pending.counter_before[0] if pending.counter_before else None
        self.tracker.on_outcome(pending, result, delta=delta)
        for d in divergences:
            log.warning(d.message)
            self._log(d.tag, frame=self._safe_frame(), divergence=d.kind, **d.detail)
        log.info(
            "kill check: %s (破壞數 %s -> %s)",
            result,
            pending.counter_before,
            counter,
        )
        self._log(
            "kill_check",
            result=result,
            counter_before=list(pending.counter_before) if pending.counter_before else None,
            counter_after=list(counter),
            expect_kill=pending.expectation.expect_kill,
            game_expect_kill=pending.game_expect_kill,
            hit_pct=pending.hit_pct,
            quality=pending.expectation.quality,
        )
        self._pending = None

    def _on_battle_prep(self) -> None:
        frame = self._frame()
        prep = vision.read_battle_prep_forecast(frame)
        if prep is not None:
            self.tracker.on_battle_prep(prep)
            self._log(
                "forecast_battle_prep",
                frame=frame,
                is_reaction=prep.is_reaction,
                attack_value=prep.attack_value,
                defense_value=prep.defense_value,
                hit_pct=prep.hit_pct,
                attacker_sig=prep.attacker_name_sig,
                attacker_hp=prep.attacker_hp,
                attacker_en=prep.attacker_en,
                defender_sig=prep.defender_name_sig,
                defender_hp=prep.defender_hp,
                defender_en=prep.defender_en,
                defender_hp_delta=prep.defender_hp_delta,
            )
            if prep.is_reaction:
                self._note_sig(
                    prep.attacker_name_sig, frame, vision.FORECAST_LEFT_NAME_REGION, "enemy"
                )
                log.info(
                    "incoming attack: %s hits %s for %s (hit %s%%)",
                    self._describe_sig(prep.attacker_name_sig),
                    self._describe_sig(prep.defender_name_sig),
                    prep.attack_value,
                    prep.hit_pct,
                )
        if self._pending is not None and not self._pending.armed:
            if prep is None or not prep.is_reaction:
                if prep is not None:
                    self._pending, divergences = reconcile.reconcile_battle_prep(
                        self._pending, prep
                    )
                    for d in divergences:
                        log.warning(d.message)
                        self._log(d.tag, frame=frame, divergence=d.kind, **d.detail)
                self._pending.armed = True
        found = self.perception.probe(["btn_start_battle"])
        pos = found["btn_start_battle"].bbox.center if found else START_BATTLE_BTN
        log.info("confirming battle start")
        self._log("engagement_confirm")
        self.actuator.tap(*pos)
        # generous budget: the battle animation is long, and for a reaction
        # popup (#3) the enemy turn continues afterwards -- an expiry here is
        # informative ledger noise, not a failure. label_battle_prep is a
        # legal target: consecutive reaction popups re-enter this screen
        self._expect(
            "battle_execute",
            ("label_our_turn", "label_unit_move", "label_weapon_select", "label_battle_prep"),
            checks=20,
        )
        self._wait_animation()
        self._action.reset()

    def _attack(self, slot: int) -> None:
        extras: dict = {}
        if self._pending is not None:
            e = self._pending.expectation
            extras = {
                "attacker": e.attacker_id,
                "target": e.target_id,
                "target_sig_seen": e.target_sig_seen,
                "predicted_damage_game": self._pending.game_damage,
                "expected_damage_sim": (
                    round(e.expected_damage) if e.expected_damage is not None else None
                ),
                "expect_kill": (
                    e.expect_kill if e.expect_kill is not None else self._pending.game_expect_kill
                ),
                "quality": e.quality,
            }
        self._log("attack", frame=self._safe_frame(), slot=slot, **extras)
        self.actuator.tap(*ATTACK_BTN)
        self._expect("attack", ("label_battle_prep",))
        time.sleep(2.0)

    def _standby(self, reason: str) -> None:
        if self._pending is not None and not self._pending.armed:
            log.debug("attack decision abandoned before engagement, dropping its outcome")
            self._pending = None
        self._log("standby", frame=self._safe_frame(), reason=reason)
        self.actuator.tap(*STANDBY_BTN)
        self._expect("standby", ("label_our_turn",), checks=12)
        time.sleep(1.8)
        self._action.reset()

    def _wait_animation(self) -> None:
        """Wait out the combat cut-in animation. Two exits: frames settling
        (terminal screens, calm maps) or the phase label coming back (maps
        whose ambient animation never lets frames settle)."""
        t0 = time.time()
        prev = None
        while time.time() - t0 < self.settle_timeout_s:
            frame = self._frame()
            d = frame_diff(prev, frame) if prev is not None else 1.0
            prev = frame
            if time.time() - t0 > 5:
                if d < 0.008:
                    return
                if self._current_mode() is not None:
                    return
            time.sleep(0.5)
