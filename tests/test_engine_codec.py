"""The state codec: field parity with the Go structs, and the round trip.

The parity check parses the JSON tags of 'engine/battle/snapshot.go' and
'engine/battle/decision.go' here, in the Python gate: 'engine/state.py' must
hold every field that the wire holds, and a change on either side must fail
this gate. It flattens an embedded struct at its position, as 'encoding/json'
flattens it, so the mirror stays flat where the Go side wraps a group.

A Go struct can hold a field that the dataclass does not, for a rule that the
engine alone runs. 'ENGINE_ONLY' names each one, so an undeclared Go field
still fails the gate.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from ggge_ai.engine import codec
from ggge_ai.engine.contract import ActionKind, Faction, Stance, Terrain
from ggge_ai.engine.state import (
    BattleState,
    EventTable,
    Debuff,
    Decision,
    MapWeapon,
    Mech,
    Pilot,
    ResponseAttack,
    ShapeRange,
    Skill,
    StageEvent,
    TerrainCell,
    Unit,
    Weapon,
)

CONTRACT = Path(__file__).resolve().parents[1] / "engine" / "battle"
STATE_GO = (CONTRACT / "snapshot.go", CONTRACT / "decision.go", CONTRACT.parent / "protocol" / "state.go")

STRUCTS = {
    "ShapeRange": ShapeRange,
    "Weapon": Weapon,
    "MapWeapon": MapWeapon,
    "Skill": Skill,
    "Debuff": Debuff,
    "Pilot": Pilot,
    "Mech": Mech,
    "Unit": Unit,
    "ResponseAttack": ResponseAttack,
    "Decision": Decision,
    "StageEvent": StageEvent,
    "TerrainCell": TerrainCell,
    "BattleState": BattleState,
}

ENCODERS = {
    "ShapeRange": lambda: codec.encode_shape_range(ShapeRange()),
    "Weapon": lambda: codec.encode_weapon(Weapon(name="w", power=1.0)),
    "MapWeapon": lambda: codec.encode_map_weapon(MapWeapon(name="w", power=1.0)),
    "Skill": lambda: codec.encode_skill(Skill(kind="skill_heal")),
    "Debuff": lambda: codec.encode_debuff(Debuff("k", 1.0, 2)),
    "Pilot": lambda: codec.encode_pilot(Pilot()),
    "Mech": lambda: codec.encode_mech(Mech()),
    "Unit": lambda: codec.encode_unit(Unit(faction=Faction.ALLY)),
    "ResponseAttack": lambda: codec.encode_response_attack(
        ResponseAttack(stance=Stance.DEFEND)
    ),
    "Decision": lambda: codec.encode_decision(Decision(unit_id=0, kind=ActionKind.STANDBY)),
    "StageEvent": lambda: codec.encode_event(StageEvent("e", {}, {})),
    "TerrainCell": lambda: codec.encode_terrain_cell(TerrainCell((0, 0), Terrain.SPACE)),
    "BattleState": lambda: codec.encode_state(BattleState()),
}

ENGINE_ONLY: dict[str, list[str]] = {}

STRUCT = re.compile(r"^type (\w+) struct \{$")
TAG = re.compile(r'json:"([^",]+)')
EMBEDDED = re.compile(r"^\t([A-Z]\w*)$")


def _go_members() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    name = ""
    for path in STATE_GO:
        for line in path.read_text(encoding="utf-8").splitlines():
            header = STRUCT.match(line)
            if header:
                name = header.group(1)
                out[name] = []
            elif line == "}":
                name = ""
            elif name:
                tag = TAG.search(line)
                embedded = EMBEDDED.match(line)
                if tag:
                    out[name].append(("field", tag.group(1)))
                elif embedded:
                    out[name].append(("embed", embedded.group(1)))
    return out


def _go_structs() -> dict[str, list[str]]:
    members = _go_members()

    def flatten(name: str) -> list[str]:
        out: list[str] = []
        for kind, value in members[name]:
            out.extend([value] if kind == "field" else flatten(value))
        return out

    return {name: flatten(name) for name in members}


@pytest.mark.parametrize("name", sorted(STRUCTS))
def test_the_go_struct_holds_every_field_of_the_dataclass(name):
    fields = [field.name for field in dataclasses.fields(STRUCTS[name])]

    assert _go_structs()[name] == fields + ENGINE_ONLY.get(name, [])


@pytest.mark.parametrize("name", sorted(STRUCTS))
def test_the_codec_writes_every_field_of_the_dataclass(name):
    fields = [field.name for field in dataclasses.fields(STRUCTS[name])]

    assert list(ENCODERS[name]()) == fields


def test_the_state_survives_the_round_trip():
    state, events = _board()

    payload = codec.encode_state(state)

    assert codec.encode_state(codec.decode_state(payload)) == payload
    assert codec.decode_state(payload) == state
    assert codec.decode_events(codec.encode_events(events)) == events


def test_a_three_valued_die_keeps_its_three_values():
    values = [None, True, False]

    payloads = [
        codec.encode_decision(Decision(unit_id=0, kind=ActionKind.ATTACK, hit=value))
        for value in values
    ]

    assert [payload["hit"] for payload in payloads] == values
    assert [codec.decode_decision(payload).hit for payload in payloads] == values


def test_an_absent_optional_field_decodes_to_the_same_value_as_null():
    full = codec.encode_decision(Decision(unit_id=0, kind=ActionKind.STANDBY))
    lean = {key: value for key, value in full.items() if value is not None}

    assert codec.decode_decision(lean) == codec.decode_decision(full)


def test_a_response_attack_with_no_stance_never_reaches_the_wire():
    with pytest.raises(ValueError, match="no stance"):
        codec.encode_response_attack(ResponseAttack())


def test_the_stance_none_decodes():
    payload = codec.encode_response_attack(ResponseAttack(stance=Stance.NONE))

    assert codec.decode_response_attack(payload).stance is Stance.NONE


def test_a_skill_enum_outside_the_contract_stops_the_decode():
    payload = codec.encode_skill(Skill(kind="skill_heal"))

    with pytest.raises(ValueError, match="source"):
        codec.decode_skill({**payload, "source": "squad"})
    with pytest.raises(ValueError, match="affects"):
        codec.decode_skill({**payload, "affects": "self"})


def test_the_categories_of_a_weapon_survive_the_round_trip():
    plain = codec.encode_weapon(Weapon(name="saber", power=1.0))
    tagged = codec.encode_weapon(Weapon(name="saber", power=1.0, categories=["melee", "awaken"]))

    assert plain["categories"] is None
    assert tagged["categories"] == ["melee", "awaken"]
    assert codec.decode_weapon(plain).categories == []
    assert codec.decode_weapon(tagged).categories == ["melee", "awaken"]


def test_a_field_outside_the_contract_stops_the_decode():
    payload = codec.encode_unit(Unit(faction=Faction.ALLY))

    with pytest.raises(ValueError, match="morale"):
        codec.decode_unit({**payload, "morale": 7})


def _board() -> tuple[BattleState, EventTable]:
    weapon = Weapon(name="rifle", power=1200.0, range_min=1, range_max=3, en_cost=10)
    area = MapWeapon(name="missile pod", power=1800.0, ammo_max=2)
    skill = Skill(kind="skill_heal", amount=500.0)
    unit = Unit(
        faction=Faction.ALLY,
        pos=(1, 2),
        hp=8000,
        max_hp=9000,
        en=40,
        en_max=80,
        mech=Mech(hp=9000, en=80, move_range=4, weapons=[weapon], map_weapons=[area]),
        pilot=Pilot(ranged=220.0, melee=180.0, awaken=240.0, defense=190.0, reaction=205.0, sp=45),
        skills=[skill],
        map_weapon_ammo=[2],
        debuffs=[Debuff(kind="attack", magnitude=0.2, applied_phase=3)],
    )
    foe = Unit(faction=Faction.ENEMY, pos=(5, 2), hp=7000, max_hp=7000)
    state = BattleState(units=[unit, foe], phase=Faction.ALLY, turn=2, bounds=((0, 0), (7, 7)))
    events = {"e1": StageEvent(event_id="e1", trigger={"type": "turn_start", "turn": 3},
                               effect={"type": "weaken", "uids": ["enemy_1"]})}
    return state, events


def test_the_terrain_of_the_map_survives_the_round_trip():
    state = BattleState(
        terrain=Terrain.GROUND,
        terrain_cells=(TerrainCell((3, 2), Terrain.UNDERWATER),),
        units=[Unit(faction=Faction.ALLY)],
    )

    payload = codec.encode_state(state)

    assert payload["terrain"] == "ground"
    assert payload["terrain_cells"] == [{"cell": [3, 2], "terrain": "underwater"}]
    assert codec.decode_state(payload) == state


def test_a_terrain_outside_the_contract_stops_the_decode():
    payload = codec.encode_state(BattleState(terrain=Terrain.SPACE))
    payload["terrain"] = "orbit"

    with pytest.raises(ValueError, match="terrain 'orbit' is not in the contract"):
        codec.decode_state(payload)
