"""Process-scoped running board beliefs, keyed by unit uid.

The controller already reads authoritative numbers per action -- the
weapon-select forecast, the battle-prep confirmation, the 破壞數 verdict,
the turn boundary -- but until now they fed reconcile/ledger and were
discarded. BoardTracker retains them as uid-keyed beliefs (HP/EN, alive,
last-confirmed position) so the next advisor consultation starts from what
the screen already told us instead of bridge defaults.

Identity goes through the shared IdentityResolver: screen hooks hand in
the raw signature evidence, the resolver answers with the uid (canonical
"sig:<hex>" in passthrough and always for allies; a stage-definition uid
when seeded). A seeded resolution that stays ambiguous skips the write --
a belief under a guessed identity is worse than none.

Blackboard discipline applies: the tracker lives and dies with one battle
inside one process, is never persisted, and is never a prior for the next
run. The screen stays authoritative -- a fresh read always overwrites an
estimate, and apply() reports every carried value as an assumption so a
belief is never silently equal to a fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .identity import IdentityResolver
from .observe import SIG_MATCH_RADIUS
from .state import BattleState, Faction, Point

if TYPE_CHECKING:
    from .reconcile import PendingOutcome
    from .scout_intel import StageIntel
    from .vision import BattlePrepForecast, WeaponSelectForecast

_KILLED_RESULTS = frozenset({"unexpected_kill"})
_NOT_KILLED_RESULTS = frozenset({"model_diverge", "rng_branch", "unverified_hit_unknown"})

# the same unit's name signature jitters a few bits between panels (live
# corpus 20260713-225448: weapon-select vs battle-prep sigs of one unit
# differ by 3-5 bits); same tolerance as stage_def.SIG_CANDIDATE_MAX_DISTANCE
SIG_ALIAS_MAX_DISTANCE = 6

_NAMESPACE = {
    Faction.ALLY: "ally",
    Faction.ENEMY: "enemy",
    Faction.THIRD_PARTY: "third_party",
}


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
    resolver: IdentityResolver = field(default_factory=IdentityResolver)

    def _belief(
        self, sig: str, faction: Faction, world: Point | None = None
    ) -> UnitBelief | None:
        uid = self.resolver.uid_for(sig, _NAMESPACE[faction], world=world)
        if uid is None:
            return None
        belief = self.beliefs.get(uid)
        if belief is None:
            belief = UnitBelief(sig=sig, faction=faction)
            self.beliefs[uid] = belief
        belief.sig = sig
        return belief

    def _place(self, belief: UnitBelief, world: Point | None) -> None:
        if world is not None:
            belief.world_pos = (float(world[0]), float(world[1]))
            belief.pos_turn = self.turn

    def on_turn(self, turn: int) -> None:
        self.turn = turn

    def on_intel(self, intel: StageIntel) -> None:
        for sig, summary in intel.summaries.items():
            belief = self._belief(sig, Faction.ENEMY, world=intel.positions.get(sig))
            if belief is None:
                continue
            if summary.hp is not None:
                belief.hp = summary.hp
            if summary.en is not None:
                belief.en = summary.en
            self._place(belief, intel.positions.get(sig))
            belief.source = "intel"

    def on_sig_position(
        self, sig: str, world: Point, faction: Faction = Faction.ENEMY
    ) -> None:
        belief = self._belief(sig, faction, world=world)
        if belief is not None:
            self._place(belief, world)

    def on_position(self, uid: str, world: Point, faction: Faction = Faction.ENEMY) -> None:
        """Position update for an already-resolved identity (per-turn
        refresh hands back uid-keyed positions; no sig resolution here)."""
        belief = self.beliefs.get(uid)
        if belief is None:
            belief = UnitBelief(sig=self.resolver.expected_sig(uid) or "", faction=faction)
            self.beliefs[uid] = belief
        self._place(belief, world)

    def on_weapon_select(
        self,
        forecast: WeaponSelectForecast,
        *,
        our_world: Point | None = None,
        target_world: Point | None = None,
    ) -> None:
        if forecast.our_name_sig is not None:
            ours = self._belief(forecast.our_name_sig, Faction.ALLY, world=our_world)
            if ours is not None:
                if forecast.our_hp is not None:
                    ours.hp = forecast.our_hp
                if forecast.our_en is not None:
                    ours.en = forecast.our_en
                self._place(ours, our_world)
                ours.source = "forecast"
        if forecast.target_name_sig is not None:
            target = self._belief(forecast.target_name_sig, Faction.ENEMY, world=target_world)
            if target is not None:
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
            if belief is None:
                continue
            if hp is not None:
                belief.hp = hp
            if en is not None:
                belief.en = en
            belief.source = "prep"

    def on_outcome(
        self, pending: PendingOutcome, result: str, *, delta: int | None = None
    ) -> None:
        uid = pending.expectation.target_id
        if uid is None:
            return
        belief = self.beliefs.get(uid)
        if belief is None:
            sig = self.resolver.expected_sig(uid) or pending.expectation.target_sig_seen
            belief = UnitBelief(sig=sig or "", faction=Faction.ENEMY)
            self.beliefs[uid] = belief
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

    def id_positions(self, faction: Faction = Faction.ENEMY) -> dict[str, Point]:
        return {
            uid: belief.world_pos
            for uid, belief in self.beliefs.items()
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
