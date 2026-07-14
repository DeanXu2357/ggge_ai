"""Process-scoped running board beliefs, keyed by name signature.

The controller already reads authoritative numbers per action -- the
weapon-select forecast, the battle-prep confirmation, the 破壞數 verdict,
the turn boundary -- but until now they fed reconcile/ledger and were
discarded. BoardTracker retains them as sig-keyed beliefs (HP/EN, alive,
last-confirmed position) so the next advisor consultation starts from what
the screen already told us instead of bridge defaults.

Blackboard discipline applies: the tracker lives and dies with one battle
inside one process, is never persisted, and is never a prior for the next
run. The screen stays authoritative -- a fresh read always overwrites an
estimate, and apply() reports every carried value as an assumption so a
belief is never silently equal to a fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .observe import SIG_MATCH_RADIUS
from .state import BattleState, Faction, Point
from .vision import signature_distance

if TYPE_CHECKING:
    from .reconcile import PendingOutcome
    from .scout_intel import StageIntel
    from .vision import BattlePrepForecast, WeaponSelectForecast

_KILLED_RESULTS = frozenset({"unexpected_kill"})
_NOT_KILLED_RESULTS = frozenset({"model_diverge", "rng_branch", "unverified_hit_unknown"})

# the same unit's name signature jitters a few bits between panels (live
# corpus 20260713-225448: weapon-select vs battle-prep sigs of one unit
# differ by 3-5 bits); same tolerance as stage_cache.SIG_MATCH_MAX_DISTANCE
SIG_ALIAS_MAX_DISTANCE = 6


@dataclass
class UnitBelief:
    sig: str
    faction: Faction
    hp: int | None = None
    en: int | None = None
    world_pos: Point | None = None
    pos_turn: int = 0
    alive: bool = True
    source: str = ""


@dataclass
class BoardTracker:
    beliefs: dict[str, UnitBelief] = field(default_factory=dict)
    turn: int = 1

    def _belief(self, sig: str, faction: Faction) -> UnitBelief:
        belief = self.beliefs.get(sig)
        if belief is None:
            canon = self._canonical(sig, faction)
            if canon is not None:
                return self.beliefs[canon]
            belief = UnitBelief(sig=sig, faction=faction)
            self.beliefs[sig] = belief
        return belief

    def _canonical(self, sig: str, faction: Faction) -> str | None:
        """The existing belief key this jittered signature really is, if
        any -- keeps one unit from splitting into several beliefs."""
        best, best_distance = None, SIG_ALIAS_MAX_DISTANCE + 1
        for existing, belief in self.beliefs.items():
            if belief.faction is not faction:
                continue
            distance = signature_distance(sig, existing)
            if distance < best_distance:
                best, best_distance = existing, distance
        return best

    def _place(self, belief: UnitBelief, world: Point | None) -> None:
        if world is not None:
            belief.world_pos = (float(world[0]), float(world[1]))
            belief.pos_turn = self.turn

    def on_turn(self, turn: int) -> None:
        self.turn = turn

    def on_intel(self, intel: StageIntel) -> None:
        for sig, summary in intel.summaries.items():
            belief = self._belief(sig, Faction.ENEMY)
            if summary.hp is not None:
                belief.hp = summary.hp
            if summary.en is not None:
                belief.en = summary.en
            self._place(belief, intel.positions.get(sig))
            belief.source = "intel"

    def on_sig_position(
        self, sig: str, world: Point, faction: Faction = Faction.ENEMY
    ) -> None:
        belief = self._belief(sig, faction)
        self._place(belief, world)

    def on_weapon_select(
        self,
        forecast: WeaponSelectForecast,
        *,
        our_world: Point | None = None,
        target_world: Point | None = None,
    ) -> None:
        if forecast.our_name_sig is not None:
            ours = self._belief(forecast.our_name_sig, Faction.ALLY)
            if forecast.our_hp is not None:
                ours.hp = forecast.our_hp
            if forecast.our_en is not None:
                ours.en = forecast.our_en
            self._place(ours, our_world)
            ours.source = "forecast"
        if forecast.target_name_sig is not None:
            target = self._belief(forecast.target_name_sig, Faction.ENEMY)
            if forecast.target_hp is not None:
                target.hp = forecast.target_hp
            if forecast.target_en is not None:
                target.en = forecast.target_en
            self._place(target, target_world)
            target.source = "forecast"

    def on_battle_prep(self, prep: BattlePrepForecast) -> None:
        attacker_faction = Faction.ENEMY if prep.is_reaction else Faction.ALLY
        defender_faction = Faction.ALLY if prep.is_reaction else Faction.ENEMY
        sides = (
            (prep.attacker_name_sig, attacker_faction, prep.attacker_hp, prep.attacker_en),
            (prep.defender_name_sig, defender_faction, prep.defender_hp, prep.defender_en),
        )
        for sig, faction, hp, en in sides:
            if sig is None:
                continue
            belief = self._belief(sig, faction)
            if hp is not None:
                belief.hp = hp
            if en is not None:
                belief.en = en
            belief.source = "prep"

    def on_outcome(
        self, pending: PendingOutcome, result: str, *, delta: int | None = None
    ) -> None:
        sig = pending.expectation.target_sig
        if sig is None:
            return
        belief = self._belief(sig, Faction.ENEMY)
        killed = self._killed(pending, result, delta)
        if killed is True:
            belief.alive = False
            belief.hp = 0
            belief.source = "outcome"
        elif killed is False and self._certain_hit(pending) and pending.game_damage is not None:
            before = belief.hp if belief.hp is not None else pending.target_hp_game
            if before is not None:
                belief.hp = max(1, before - pending.game_damage)
                belief.source = "estimate"

    @staticmethod
    def _killed(pending: PendingOutcome, result: str, delta: int | None) -> bool | None:
        if delta is not None:
            return delta > 0
        if result == "confirmed":
            expected = pending.game_expect_kill
            expectation = pending.expectation
            if expectation.quality == "grounded" and expectation.expect_kill is not None:
                expected = expectation.expect_kill
            return expected
        if result in _KILLED_RESULTS:
            return True
        if result in _NOT_KILLED_RESULTS:
            return False
        return None

    @staticmethod
    def _certain_hit(pending: PendingOutcome) -> bool:
        return pending.hit_pct is None or pending.hit_pct >= 100

    def sig_positions(self, faction: Faction = Faction.ENEMY) -> dict[str, Point]:
        return {
            sig: belief.world_pos
            for sig, belief in self.beliefs.items()
            if belief.faction is faction and belief.alive and belief.world_pos is not None
        }

    def apply(self, battle: BattleState) -> list[str]:
        """Write carried HP/EN onto the board where the current scan left
        them unknown; every write is reported so the ledger can tell a
        carried belief from a screen fact."""
        notes: list[str] = []
        for unit in battle.units:
            belief = self.beliefs.get(unit.unit_id)
            if belief is None or belief.faction is not unit.faction or not belief.alive:
                continue
            self._fill(unit, belief, notes)
        taken: set[str] = set()
        for belief in self.beliefs.values():
            if belief.faction is not Faction.ALLY or not belief.alive:
                continue
            if belief.world_pos is None:
                continue
            match = self._nearest_ally(battle, belief.world_pos, taken)
            if match is not None:
                taken.add(match.unit_id)
                self._fill(match, belief, notes)
        return notes

    def _fill(self, unit, belief: UnitBelief, notes: list[str]) -> None:
        stale = f", position from turn {belief.pos_turn}" if belief.pos_turn < self.turn else ""
        if unit.hp is None and belief.hp is not None:
            unit.hp = belief.hp
            notes.append(f"{unit.unit_id}: HP {belief.hp} from tracker ({belief.source}{stale})")
        if unit.en is None and belief.en is not None:
            unit.en = belief.en
            notes.append(f"{unit.unit_id}: EN {belief.en} from tracker ({belief.source}{stale})")

    @staticmethod
    def _nearest_ally(battle: BattleState, world: Point, taken: set[str]):
        best, best_d2 = None, SIG_MATCH_RADIUS**2
        for unit in battle.allies():
            if unit.unit_id in taken or unit.world_pos is None:
                continue
            d2 = (unit.world_pos[0] - world[0]) ** 2 + (unit.world_pos[1] - world[1]) ** 2
            if d2 <= best_d2:
                best, best_d2 = unit, d2
        return best
