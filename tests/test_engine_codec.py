"""The state codec: field parity with the Go structs, and the round trip.

The parity check parses the JSON tags of 'engine/protocol/state.go' here, in
the Python gate: 'engine/state.py' must hold every field that the wire holds,
and a change on either side must fail this gate.

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
    Reaction,
    Skill,
    StageEvent,
    TerrainCell,
    Unit,
    Weapon,
)

STATE_GO = Path(__file__).resolve().parents[1] / "engine" / "protocol" / "state.go"

STRUCTS = {
    "Weapon": Weapon,
    "Skill": Skill,
    "Debuff": Debuff,
    "Unit": Unit,
    "Reaction": Reaction,
    "Decision": Decision,
    "StageEvent": StageEvent,
    "TerrainCell": TerrainCell,
    "BattleState": BattleState,
}

ENCODERS = {
    "Weapon": lambda: codec.encode_weapon(Weapon(name="w", power=1.0)),
    "Skill": lambda: codec.encode_skill(Skill(kind=ActionKind.SKILL_HEAL)),
    "Debuff": lambda: codec.encode_debuff(Debuff("k", 1.0, 2)),
    "Unit": lambda: codec.encode_unit(Unit(unit_id="u", faction=Faction.ALLY)),
    "Reaction": lambda: codec.encode_reaction(Reaction(stance=Stance.DEFEND)),
    "Decision": lambda: codec.encode_decision(Decision(unit_id="u", kind=ActionKind.STANDBY)),
    "StageEvent": lambda: codec.encode_event(StageEvent("e", {}, {})),
    "TerrainCell": lambda: codec.encode_terrain_cell(TerrainCell((0, 0), Terrain.SPACE)),
    "BattleState": lambda: codec.encode_state(BattleState()),
}

ENGINE_ONLY = {
    "Unit": ["mech_hp", "mech_en", "mech_move_range", "mech_weapons"],
}

STRUCT = re.compile(r"^type (\w+) struct \{$")
TAG = re.compile(r'json:"([^",]+)')


def _go_structs() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    name = ""
    for line in STATE_GO.read_text(encoding="utf-8").splitlines():
        header = STRUCT.match(line)
        if header:
            name = header.group(1)
            out[name] = []
        elif line == "}":
            name = ""
        elif name:
            tag = TAG.search(line)
            if tag:
                out[name].append(tag.group(1))
    return out


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
        codec.encode_decision(Decision(unit_id="u", kind=ActionKind.ATTACK, hit=value))
        for value in values
    ]

    assert [payload["hit"] for payload in payloads] == values
    assert [codec.decode_decision(payload).hit for payload in payloads] == values


def test_an_absent_optional_field_decodes_to_the_same_value_as_null():
    full = codec.encode_decision(Decision(unit_id="u", kind=ActionKind.STANDBY))
    lean = {key: value for key, value in full.items() if value is not None}

    assert codec.decode_decision(lean) == codec.decode_decision(full)


def test_a_reaction_with_no_stance_never_reaches_the_wire():
    with pytest.raises(ValueError, match="no stance"):
        codec.encode_reaction(Reaction())


def test_the_stance_none_decodes():
    payload = codec.encode_reaction(Reaction(stance=Stance.NONE))

    assert codec.decode_reaction(payload).stance is Stance.NONE


def test_a_skill_enum_outside_the_contract_stops_the_decode():
    payload = codec.encode_skill(Skill(kind=ActionKind.SKILL_HEAL))

    with pytest.raises(ValueError, match="source"):
        codec.decode_skill({**payload, "source": "squad"})
    with pytest.raises(ValueError, match="affects"):
        codec.decode_skill({**payload, "affects": "self"})


def test_a_field_outside_the_contract_stops_the_decode():
    payload = codec.encode_unit(Unit(unit_id="u", faction=Faction.ALLY))

    with pytest.raises(ValueError, match="morale"):
        codec.decode_unit({**payload, "morale": 7})


def _board() -> tuple[BattleState, EventTable]:
    weapon = Weapon(name="rifle", power=1200.0, range_min=1, range_max=3, en_cost=10)
    skill = Skill(kind=ActionKind.SKILL_HEAL, amount=500.0)
    unit = Unit(
        unit_id="ally_1",
        faction=Faction.ALLY,
        pos=(1, 2),
        hp=8000,
        max_hp=9000,
        en=40,
        en_max=80,
        weapons=[weapon],
        skills=[skill],
        ammo={"rifle": 2},
        debuffs=[Debuff(kind="attack", magnitude=0.2, applied_phase=3)],
    )
    foe = Unit(unit_id="enemy_1", faction=Faction.ENEMY, pos=(5, 2), hp=7000, max_hp=7000)
    state = BattleState(units=[unit, foe], phase=Faction.ALLY, turn=2, bounds=((0, 0), (7, 7)))
    events = {"e1": StageEvent(event_id="e1", trigger={"type": "turn_start", "turn": 3},
                               effect={"type": "weaken", "uids": ["enemy_1"]})}
    return state, events


def test_the_terrain_of_the_map_survives_the_round_trip():
    state = BattleState(
        terrain=Terrain.GROUND,
        terrain_cells=(TerrainCell((3, 2), Terrain.UNDERWATER),),
        units=[Unit(unit_id="u", faction=Faction.ALLY)],
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
