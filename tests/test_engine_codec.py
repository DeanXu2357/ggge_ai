"""The state codec: field parity with the Go structs, and the round trip.

The parity check parses the JSON tags of 'engine/protocol/state.go' here, in
the Python gate, because 'sandbox/model.py' is the authority: a change there
must fail the gate that a change there runs.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from ggge_ai.engine import codec
from ggge_ai.sandbox.model import (
    BattleState,
    Debuff,
    Decision,
    Faction,
    MoveKind,
    Reaction,
    Rules,
    Skill,
    Stance,
    StageEvent,
    Unit,
    Weapon,
)
from scripts.write_engine_fixtures import BOARDS, FIXTURES, build_case, render

STATE_GO = Path(__file__).resolve().parents[1] / "engine" / "protocol" / "state.go"

STRUCTS = {
    "Rules": Rules,
    "Weapon": Weapon,
    "Skill": Skill,
    "Debuff": Debuff,
    "Unit": Unit,
    "Reaction": Reaction,
    "Decision": Decision,
    "StageEvent": StageEvent,
    "BattleState": BattleState,
}

ENCODERS = {
    "Rules": lambda: codec.encode_rules(Rules()),
    "Weapon": lambda: codec.encode_weapon(Weapon(name="w", power=1.0)),
    "Skill": lambda: codec.encode_skill(Skill(kind=MoveKind.SKILL_HEAL)),
    "Debuff": lambda: codec.encode_debuff(Debuff("k", 1.0, 2)),
    "Unit": lambda: codec.encode_unit(Unit(unit_id="u", faction=Faction.ALLY)),
    "Reaction": lambda: codec.encode_reaction(Reaction(stance=Stance.DEFEND)),
    "Decision": lambda: codec.encode_decision(Decision(unit_id="u", kind=MoveKind.STANDBY)),
    "StageEvent": lambda: codec.encode_event(StageEvent("e", {}, {})),
    "BattleState": lambda: codec.encode_state(BattleState()),
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

    assert _go_structs()[name] == fields


@pytest.mark.parametrize("name", sorted(STRUCTS))
def test_the_codec_writes_every_field_of_the_dataclass(name):
    fields = [field.name for field in dataclasses.fields(STRUCTS[name])]

    assert list(ENCODERS[name]()) == fields


@pytest.mark.parametrize("board", BOARDS, ids=lambda board: board.__name__)
def test_the_state_survives_the_round_trip(board):
    _name, _note, state, rules, events = board()

    payload = codec.encode_state(state)

    assert codec.encode_state(codec.decode_state(payload)) == payload
    assert codec.decode_state(payload) == state
    assert codec.decode_rules(codec.encode_rules(rules)) == rules
    assert codec.decode_events(codec.encode_events(events)) == events


def test_a_three_valued_die_keeps_its_three_values():
    values = [None, True, False]

    payloads = [
        codec.encode_decision(Decision(unit_id="u", kind=MoveKind.ATTACK, hit=value))
        for value in values
    ]

    assert [payload["hit"] for payload in payloads] == values
    assert [codec.decode_decision(payload).hit for payload in payloads] == values


def test_an_absent_optional_field_decodes_to_the_same_value_as_null():
    full = codec.encode_decision(Decision(unit_id="u", kind=MoveKind.STANDBY))
    lean = {key: value for key, value in full.items() if value is not None}

    assert codec.decode_decision(lean) == codec.decode_decision(full)


def test_the_stance_none_never_reaches_the_wire():
    with pytest.raises(ValueError, match="none"):
        codec.encode_reaction(Reaction(stance=Stance.NONE))
    with pytest.raises(ValueError, match="none"):
        codec.decode_reaction({"stance": "none"})


def test_a_skill_enum_outside_the_contract_stops_the_decode():
    payload = codec.encode_skill(Skill(kind=MoveKind.SKILL_HEAL))

    with pytest.raises(ValueError, match="source"):
        codec.decode_skill({**payload, "source": "squad"})
    with pytest.raises(ValueError, match="affects"):
        codec.decode_skill({**payload, "affects": "self"})


def test_a_field_outside_the_contract_stops_the_decode():
    payload = codec.encode_unit(Unit(unit_id="u", faction=Faction.ALLY))

    with pytest.raises(ValueError, match="morale"):
        codec.decode_unit({**payload, "morale": 7})


def test_the_golden_fixtures_match_the_builder():
    stale = [
        case["name"]
        for case in (build_case(*board()) for board in BOARDS)
        if (FIXTURES / f"{case['name']}.json").read_text(encoding="utf-8") != render(case)
    ]

    assert stale == []


def test_every_golden_fixture_carries_the_case_format():
    for path in sorted(FIXTURES.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))

        assert path.stem == case["name"]
        assert set(case) == {"name", "note", "setup", "checks"}
        assert set(case["setup"]) == {"rules", "events", "state"}
        assert {check["op"] for check in case["checks"]} == {"state", "events", "rules"}
