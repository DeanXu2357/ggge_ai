"""Three-layer reconciliation: sim expectation vs game forecast vs outcome.

Answers the attribution question「這步是演算法算出來的，還是隊伍太強隨便打
都贏」: every attack decision gets a simulator expectation (formulas.py fed
from panel-read specs), the game's own forecast on the weapon-select and
battle-prep screens is read back as screen authority, and the 破壞數 counter
delivers the verdict. Divergences are classified so a win can be credited --
or explicitly not credited -- to the algorithm:

- [SIM-DIVERGE damage]      sim and game forecast disagree past tolerance
- [SIM-DIVERGE kill_flip]   sim and game disagree on lethality
- [SIM-DIVERGE support_defense]  battle-prep damage collapsed vs weapon
                            select (a defender is covering the target)
- [RNG-BRANCH]              expected kill missed with game hit < 100%: the
                            dice fell to a known worse branch, model intact
- [MODEL-DIVERGE]           certain-hit kill missed: our model is wrong
- [SIM-SKIP]                decision made without a grounded expectation;
                            such decisions can never earn algorithm credit

Expectations with quality != "grounded" are bookkeeping, not credit: a win
built on assumed numbers is a win of the roster, not of the algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import formulas
from .bridge import UnitSpec
from .panels import pilot_attack_for
from .sim import SimWeapon
from .vision import WeaponSelectForecast, BattlePrepForecast

DAMAGE_TOLERANCE = 0.15
# battle-prep attack below this fraction of the weapon-select prediction is
# read as a support defender absorbing the hit (halving is the common case)
SUPPORT_DEFENSE_RATIO = 0.85
KILL_CHECK_BUDGET = 12


@dataclass(frozen=True)
class Divergence:
    tag: str
    kind: str | None
    message: str
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SimExpectation:
    attacker_sig: str | None
    target_sig: str | None
    weapon_slot: int
    expected_damage: float | None
    target_hp_believed: int | None
    expect_kill: bool | None
    hit_probability: float | None
    source: str
    quality: str
    assumptions: tuple[str, ...] = ()


@dataclass
class PendingOutcome:
    """An attack awaiting its 破壞數 verdict. `armed` flips when 開始戰鬥 is
    actually confirmed -- before that the counter must not be judged."""

    expectation: SimExpectation
    game_damage: int | None
    target_hp_game: int | None
    game_expect_kill: bool | None
    counter_before: tuple[int, int] | None
    hit_pct: int | None = None
    armed: bool = False
    checks_left: int = KILL_CHECK_BUDGET


def compute_expectation(
    *,
    attacker_spec: UnitSpec | None,
    target_spec: UnitSpec | None,
    forecast: WeaponSelectForecast,
    slot: int,
    weapon: SimWeapon | None = None,
) -> SimExpectation:
    """Ground a damage/kill expectation in formulas.py, recording every
    input that had to be assumed. target_hp comes from the screen (always
    authoritative for current HP); specs supply the combat stats."""
    assumptions: list[str] = []
    target_hp = forecast.target_hp
    if target_hp is None and target_spec is not None and target_spec.max_hp is not None:
        target_hp = target_spec.max_hp
        assumptions.append("target HP unread on screen, using spec max_hp")

    if attacker_spec is None or target_spec is None:
        missing = " and ".join(
            name
            for name, spec in (("attacker", attacker_spec), ("target", target_spec))
            if spec is None
        )
        return SimExpectation(
            attacker_sig=forecast.our_name_sig,
            target_sig=forecast.target_name_sig,
            weapon_slot=slot,
            expected_damage=None,
            target_hp_believed=target_hp,
            expect_kill=None,
            hit_probability=None,
            source="heuristic_v1",
            quality="none",
            assumptions=(f"no spec for {missing}",),
        )

    if weapon is None and attacker_spec.weapons:
        index = slot - 1 if 0 < slot <= len(attacker_spec.weapons) else 0
        weapon = attacker_spec.weapons[index]
        if slot == 0:
            assumptions.append("pre-locked slot, assuming first known weapon")
    if weapon is None:
        return SimExpectation(
            attacker_sig=forecast.our_name_sig,
            target_sig=forecast.target_name_sig,
            weapon_slot=slot,
            expected_damage=None,
            target_hp_believed=target_hp,
            expect_kill=None,
            hit_probability=None,
            source="heuristic_v1",
            quality="none",
            assumptions=("attacker spec has no weapons",),
        )

    kind = None
    if weapon.name.endswith("_melee"):
        kind = "melee"
    elif weapon.name.endswith("_shooting"):
        kind = "shooting"
    pilot_attack = pilot_attack_for(attacker_spec, kind)
    if pilot_attack is None:
        pilot_attack = 1000.0
        assumptions.append("attacker pilot attack stat unread, assuming 1000")

    def stat(spec: UnitSpec, name: str, default: float, side: str) -> float:
        value = getattr(spec, name)
        if value is None:
            assumptions.append(f"{side} {name} unread, assuming {default:g}")
            return default
        return float(value)

    damage = formulas.expected_damage(
        weapon.power,
        pilot_attack,
        stat(target_spec, "pilot_defense", 1000.0, "target"),
        stat(attacker_spec, "unit_attack", 3000.0, "attacker"),
        stat(target_spec, "unit_defense", 1000.0, "target"),
    )
    hit = formulas.hit_probability(
        stat(attacker_spec, "mobility", 1000.0, "attacker"),
        stat(target_spec, "mobility", 1000.0, "target"),
        pilot_attack,
        stat(target_spec, "reaction", 1000.0, "target"),
    )
    if target_hp is None:
        assumptions.append("target HP unknown, kill call impossible")
    return SimExpectation(
        attacker_sig=forecast.our_name_sig,
        target_sig=forecast.target_name_sig,
        weapon_slot=slot,
        expected_damage=damage,
        target_hp_believed=target_hp,
        expect_kill=(damage >= target_hp) if target_hp is not None else None,
        hit_probability=hit,
        source="formulas",
        quality="grounded" if not assumptions else "assumed",
        assumptions=tuple(assumptions),
    )


def reconcile_weapon_select(
    expectation: SimExpectation,
    forecast: WeaponSelectForecast,
    counter: tuple[int, int] | None,
) -> tuple[PendingOutcome, list[Divergence]]:
    """Layer 1 vs layer 2: our expectation against the game's weapon-select
    prediction. The game's numbers are authoritative -- divergences indict
    the simulator, never the screen."""
    divergences: list[Divergence] = []
    game_damage = forecast.predicted_damage
    game_kill = (
        game_damage >= forecast.target_hp
        if game_damage is not None and forecast.target_hp is not None
        else None
    )
    if expectation.quality == "none":
        divergences.append(
            Divergence(
                tag="sim_skip",
                kind=None,
                message=(
                    f"[SIM-SKIP] attack decided without simulator grounding "
                    f"({'; '.join(expectation.assumptions)}) -- uncreditable"
                ),
                detail={"assumptions": list(expectation.assumptions)},
            )
        )
    elif expectation.expected_damage is not None and game_damage is not None:
        relative = abs(expectation.expected_damage - game_damage) / max(game_damage, 1)
        if relative > DAMAGE_TOLERANCE:
            divergences.append(
                Divergence(
                    tag="sim_diverge",
                    kind="damage",
                    message=(
                        f"[SIM-DIVERGE] damage: sim expected "
                        f"{expectation.expected_damage:.0f}, game forecasts "
                        f"{game_damage} ({relative:.0%} off, tolerance "
                        f"{DAMAGE_TOLERANCE:.0%})"
                    ),
                    detail={
                        "expected_damage": round(expectation.expected_damage),
                        "game_damage": game_damage,
                        "relative_error": round(relative, 3),
                    },
                )
            )
        if (
            expectation.expect_kill is not None
            and game_kill is not None
            and expectation.expect_kill != game_kill
        ):
            divergences.append(
                Divergence(
                    tag="sim_diverge",
                    kind="kill_flip",
                    message=(
                        f"[SIM-DIVERGE] kill_flip: sim says "
                        f"{'kill' if expectation.expect_kill else 'no kill'}, game says "
                        f"{'kill' if game_kill else 'no kill'} "
                        f"(sim {expectation.expected_damage:.0f} vs game {game_damage} "
                        f"on {forecast.target_hp} HP)"
                    ),
                    detail={
                        "sim_expect_kill": expectation.expect_kill,
                        "game_expect_kill": game_kill,
                        "target_hp": forecast.target_hp,
                    },
                )
            )
    return (
        PendingOutcome(
            expectation=expectation,
            game_damage=game_damage,
            target_hp_game=forecast.target_hp,
            game_expect_kill=game_kill,
            counter_before=counter,
        ),
        divergences,
    )


def reconcile_battle_prep(
    pending: PendingOutcome, prep: BattlePrepForecast
) -> tuple[PendingOutcome, list[Divergence]]:
    """Layer 2 refinement: the battle-prep confirmation can reveal a support
    defender (damage collapses vs the weapon-select prediction) and carries
    the authoritative hit%."""
    divergences: list[Divergence] = []
    updated = pending
    if prep.hit_pct is not None:
        updated.hit_pct = prep.hit_pct
    collapsed = (
        pending.game_damage is not None
        and prep.attack_value is not None
        and prep.attack_value < pending.game_damage * SUPPORT_DEFENSE_RATIO
    )
    if collapsed or prep.support_defense:
        was_kill = pending.game_expect_kill
        now_kill = (
            prep.attack_value >= pending.target_hp_game
            if prep.attack_value is not None and pending.target_hp_game is not None
            else None
        )
        updated.game_damage = prep.attack_value
        updated.game_expect_kill = now_kill
        divergences.append(
            Divergence(
                tag="sim_diverge",
                kind="support_defense",
                message=(
                    f"[SIM-DIVERGE] support_defense: battle-prep attack "
                    f"{prep.attack_value} collapsed below weapon-select forecast "
                    f"{pending.game_damage}"
                    + (
                        " -- expected kill no longer lethal"
                        if was_kill and now_kill is False
                        else ""
                    )
                ),
                detail={
                    "weapon_select_damage": pending.game_damage,
                    "battle_prep_damage": prep.attack_value,
                    "support_defense_flag": prep.support_defense,
                },
            )
        )
    return updated, divergences


def judge_outcome(
    pending: PendingOutcome, counter_after: tuple[int, int]
) -> tuple[str, list[Divergence]]:
    """Layer 3: the 破壞數 delta decides what actually happened. Returns the
    kill_check result plus any probabilistic/model divergences."""
    divergences: list[Divergence] = []
    if pending.counter_before is None:
        return "unverified_no_baseline", divergences
    delta = counter_after[0] - pending.counter_before[0]
    expected = pending.game_expect_kill
    if pending.expectation.quality == "grounded" and pending.expectation.expect_kill is not None:
        expected = pending.expectation.expect_kill
    if expected is None:
        return "unverified_no_expectation", divergences
    if expected and delta > 0:
        return "confirmed", divergences
    if not expected and delta == 0:
        return "confirmed", divergences
    if expected and delta == 0:
        if pending.hit_pct is not None and pending.hit_pct >= 100:
            divergences.append(
                Divergence(
                    tag="model_diverge",
                    kind=None,
                    message=(
                        "[MODEL-DIVERGE] certain-hit kill did not land "
                        f"(hit {pending.hit_pct}%, counter unchanged) -- "
                        "our engagement model is missing something"
                    ),
                    detail={"hit_pct": pending.hit_pct},
                )
            )
            return "model_diverge", divergences
        if pending.hit_pct is not None:
            divergences.append(
                Divergence(
                    tag="rng_branch",
                    kind=None,
                    message=(
                        f"[RNG-BRANCH] expected kill missed at hit {pending.hit_pct}% "
                        "-- the dice fell to the known worse branch"
                    ),
                    detail={"hit_pct": pending.hit_pct},
                )
            )
            return "rng_branch", divergences
        return "unverified_hit_unknown", divergences
    return "unexpected_kill", divergences
