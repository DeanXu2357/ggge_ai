"""Write the differential cases of the battle engine under tests/fixtures/engine/.

Python is the authority side of the differential harness: this script builds the
boards from 'ggge_ai.sandbox.model', writes the inputs and the expected outputs
as JSON, and the Go tests in 'engine/differential' read the same files and
compare.

A case file holds 'setup' (the rules, the event table and the board) and
'checks'. Each check names an 'op', its 'input', and the 'expect' that Python
produced. An op that the Go build does not implement is reported as skipped, so
a later port issue adds its checks to these files without a new format.

usage:
  uv run python scripts/write_engine_fixtures.py
  uv run python scripts/write_engine_fixtures.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ggge_ai.engine import codec  # noqa: E402
from ggge_ai.sandbox.model import (  # noqa: E402
    BattleState,
    Debuff,
    Faction,
    MoveKind,
    Rules,
    Skill,
    StageEvent,
    Unit,
    Weapon,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "engine"

BEAM = Weapon(name="beam rifle", power=1800.0, range_min=1, range_max=3, en_cost=10, accuracy=5.0)
SABER = Weapon(name="saber", power=2400.0, en_cost=0, accuracy=10.0)
NET = Weapon(
    name="wire net",
    power=900.0,
    range_min=1,
    range_max=2,
    en_cost=15,
    can_counter=False,
    debuff_kind="armor_break",
    debuff_magnitude=0.2,
)
MISSILE = Weapon(
    name="missile pod",
    power=1500.0,
    range_min=2,
    range_max=5,
    en_cost=20,
    map_weapon=True,
    blast=1,
)


def _unit(unit_id: str, faction: Faction, pos: tuple[int, int], **fields: Any) -> Unit:
    base: dict[str, Any] = {
        "hp": 12000,
        "max_hp": 12000,
        "en": 140,
        "en_max": 140,
        "unit_attack": 4200.0,
        "unit_defense": 3900.0,
        "pilot_attack": 220.0,
        "pilot_defense": 190.0,
        "reaction": 205.0,
        "mobility": 310.0,
        "move_range": 4,
        "weapons": [BEAM, SABER],
    }
    base.update(fields)
    return Unit(unit_id=unit_id, faction=faction, pos=pos, **base)


Board = tuple[str, str, BattleState, Rules, dict[str, StageEvent]]


def small_board() -> Board:
    state = BattleState(
        units=[
            _unit("ally_1", Faction.ALLY, (1, 1)),
            _unit("enemy_1", Faction.ENEMY, (4, 1), acted=True),
        ],
        bounds=((0, 0), (5, 4)),
    )
    return (
        "small_board",
        "Two units on a 6x5 board, one weapon pair, no option set.",
        state,
        Rules(),
        {},
    )


def blocker_board() -> Board:
    state = BattleState(
        units=[
            _unit("ally_1", Faction.ALLY, (0, 2), move_range=6),
            _unit("enemy_1", Faction.ENEMY, (2, 2), move_range=0, weapons=[SABER]),
            _unit("enemy_2", Faction.ENEMY, (5, 2)),
        ],
        phase=Faction.ALLY,
        turn=3,
        bounds=((0, 0), (6, 4)),
    )
    return (
        "blocker_board",
        "One enemy stands between the ally and its target: the path bends around it.",
        state,
        Rules(terrain=1.2, dodge_hit_penalty=25.0),
        {},
    )


def debuff_ammo_board() -> Board:
    striker = _unit(
        "ally_1",
        Faction.ALLY,
        (2, 3),
        hp=8400,
        en=95,
        weapons=[BEAM, NET, MISSILE],
        ammo={"missile pod": 2},
        skills=[
            Skill(kind=MoveKind.SKILL_EN_REFILL, amount=None, uses=1),
            Skill(kind=MoveKind.SKILL_HEAL, amount=3000.0, uses=2, ends_activation=False),
        ],
        has_shield=True,
        attack_shield=True,
        interception_reduction=0.15,
        chance_steps=1,
        chance_steps_max=1,
        support_defend_charges=1,
        support_defend_charges_max=1,
        support_attack_charges=2,
        support_attack_charges_max=2,
    )
    victim = _unit(
        "enemy_1",
        Faction.ENEMY,
        (4, 3),
        hp=5100,
        debuffs=[
            Debuff(kind="armor_break", magnitude=0.2, applied_phase=9),
            Debuff(kind="mobility_down", magnitude=0.1, applied_phase=10),
        ],
        weapons=[SABER],
        ammo={},
    )
    state = BattleState(
        units=[striker, victim, _unit("third_1", Faction.THIRD_PARTY, (6, 0))],
        phase=Faction.ENEMY,
        turn=4,
        bounds=((0, 0), (7, 5)),
    )
    return (
        "debuff_ammo_board",
        "Debuffs, ammunition, skills, shields and every charge counter carry a value.",
        state,
        Rules(),
        {},
    )


def event_board() -> Board:
    reinforcement = _unit("enemy_9", Faction.ENEMY, (7, 3), acted=True, weapons=[SABER])
    events = {
        "wave_2": StageEvent(
            event_id="wave_2",
            trigger={"type": "kill", "uid": "enemy_1", "within_turn": 5},
            effect={"type": "spawn", "units": [reinforcement]},
        ),
        "boss_weakens": StageEvent(
            event_id="boss_weakens",
            trigger={"type": "turn_start", "turn": 6},
            effect={
                "type": "weaken",
                "uids": ["enemy_1"],
                "attack_multiplier": 0.8,
                "defense_multiplier": 0.75,
            },
        ),
    }
    state = BattleState(
        units=[
            _unit("ally_1", Faction.ALLY, (1, 3)),
            _unit("enemy_1", Faction.ENEMY, (5, 3), hp=3000),
        ],
        phase=Faction.THIRD_PARTY,
        turn=5,
        bounds=None,
        pending_events=("wave_2",),
        fired_events=("boss_weakens",),
    )
    return (
        "event_board",
        "An event table with both trigger kinds, a spawn payload, and no bounds.",
        state,
        Rules(max_support_attackers=2),
        events,
    )


BOARDS = (small_board, blocker_board, debuff_ammo_board, event_board)


def build_case(
    name: str,
    note: str,
    state: BattleState,
    rules: Rules,
    events: dict[str, StageEvent],
) -> dict[str, Any]:
    setup = {
        "rules": codec.encode_rules(rules),
        "events": codec.encode_events(events),
        "state": codec.encode_state(state),
    }
    # The expectation comes back through the decoder, so a golden file records
    # what a full round trip gives, not what the builder wrote.
    return {
        "name": name,
        "note": note,
        "setup": setup,
        "checks": [
            {
                "op": "state",
                "input": None,
                "expect": codec.encode_state(codec.decode_state(setup["state"])),
            },
            {
                "op": "events",
                "input": None,
                "expect": codec.encode_events(codec.decode_events(setup["events"])),
            },
            {
                "op": "rules",
                "input": None,
                "expect": codec.encode_rules(codec.decode_rules(setup["rules"])),
            },
        ],
    }


def cases() -> list[dict[str, Any]]:
    return [build_case(*board()) for board in BOARDS]


def render(case: dict[str, Any]) -> str:
    return json.dumps(case, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true", help="report a stale file instead of writing it"
    )
    args = parser.parse_args(argv)

    FIXTURES.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    for case in cases():
        path = FIXTURES / f"{case['name']}.json"
        text = render(case)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
            continue
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    if stale:
        print("stale: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
