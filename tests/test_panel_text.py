"""The free-text channel: schema closure, vocabulary alignment, injection.

Nothing here talks to ollama. The transport is a callable the reader takes as a
field, so a stubbed transport exercises the exact production request-building
and response-coercion path with no server involved.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from ggge_ai.runtime import panel_text
from ggge_ai.runtime.panel_text import (
    ABILITY_EFFECTS,
    ABILITY_SCHEMA,
    BRIEF_SCHEMA,
    LINES_SCHEMA,
    MAX_LINE_CHARS,
    MAX_LINES,
    SKILL_KINDS,
    WEAPON_EFFECTS,
    WEAPON_SCHEMA,
    AbilityTexts,
    OllamaPanelTextReader,
    PanelTextReader,
    StageBrief,
    WeaponText,
    align,
    coerce_abilities,
    coerce_brief,
    coerce_lines,
    coerce_weapon,
)

PATCH = np.zeros((40, 200, 3), np.uint8)


def stub(reply: dict):
    sent: list[dict] = []

    def transport(url: str, payload: dict, timeout_s: float) -> str:
        sent.append(payload)
        return json.dumps(reply)

    return transport, sent


class FakeReader:
    """The shape callers program against; the suite's stand-in for ollama."""

    def __init__(self, weapon: WeaponText | None = None, abilities: AbilityTexts | None = None):
        self._weapon = weapon
        self._abilities = abilities

    def weapon(self, patch):
        return self._weapon

    def abilities(self, patch):
        return self._abilities


def test_fake_satisfies_the_protocol():
    reader: PanelTextReader = FakeReader(weapon=WeaponText(name="光束軍刀"))
    assert reader.weapon(PATCH) == WeaponText(name="光束軍刀")
    assert reader.abilities(PATCH) is None


def test_schemas_are_closed_over_implemented_mechanics():
    assert WEAPON_SCHEMA["additionalProperties"] is False
    assert WEAPON_SCHEMA["properties"]["effect"]["enum"] == [*WEAPON_EFFECTS, None]
    entry = ABILITY_SCHEMA["properties"]["entries"]["items"]
    assert entry["additionalProperties"] is False
    assert entry["properties"]["effect"]["enum"] == [*ABILITY_EFFECTS, *SKILL_KINDS, None]
    assert entry["properties"]["owner"]["enum"] == ["unit", "pilot"]


def test_request_carries_the_schema_as_the_decode_format():
    transport, sent = stub({"name": "光束軍刀", "effect": None, "magnitude": 0, "unsupported": []})
    reader = OllamaPanelTextReader(transport=transport, terms={})
    reader.weapon(PATCH)
    assert sent[0]["format"] == WEAPON_SCHEMA
    assert sent[0]["options"]["temperature"] == 0
    assert sent[0]["stream"] is False


def test_a_card_without_a_note_is_not_asked_for_an_effect():
    """The deterministic layer already knows there is no effect line, so the
    schema must not offer the model a slot to fill."""
    transport, sent = stub({"name": "光束軍刀"})
    reader = OllamaPanelTextReader(transport=transport, terms={"weapons": ("光束軍刀",)})
    text = reader.weapon(PATCH, has_note=False)
    assert sent[0]["format"] == panel_text.WEAPON_NAME_SCHEMA
    assert "effect" not in sent[0]["format"]["properties"]
    assert text == WeaponText(name="光束軍刀", matched=True, effect=None)


def test_weapon_effect_inside_the_schema_is_kept():
    transport, _ = stub(
        {
            "name": "感應砲",
            "effect": "damage_taken_up",
            "magnitude": 0.1,
            "unsupported": [],
        }
    )
    reader = OllamaPanelTextReader(transport=transport, terms={"weapons": ("感應砲",)})
    text = reader.weapon(PATCH)
    assert text == WeaponText(name="感應砲", matched=True, effect="damage_taken_up", magnitude=0.1)


def test_effect_outside_the_schema_is_demoted_to_unsupported():
    """A server that ignored the format must not smuggle a new mechanic in."""
    text = coerce_weapon(
        {
            "name": "超絕火箭砲",
            "effect": "power_up_with_distance",
            "magnitude": 0.05,
            "unsupported": [],
        }
    )
    assert text is not None
    assert text.effect is None
    assert text.magnitude == 0.0
    assert text.unsupported == ("effect=power_up_with_distance",)


def test_unmapped_wording_is_carried_verbatim():
    text = coerce_weapon(
        {
            "name": "超絕火箭砲",
            "effect": None,
            "magnitude": 0,
            "unsupported": ["距離敵方越遠，武裝POWER越為提升（最高提升5%）"],
        }
    )
    assert text is not None
    assert text.unsupported == ("距離敵方越遠，武裝POWER越為提升（最高提升5%）",)


def test_magnitude_is_dropped_without_an_effect():
    text = coerce_weapon({"name": "光束軍刀", "effect": None, "magnitude": 0.3, "unsupported": []})
    assert text is not None and text.magnitude == 0.0


def test_nameless_or_malformed_reply_is_refused():
    assert coerce_weapon({"effect": None, "magnitude": 0, "unsupported": []}) is None
    assert coerce_weapon({"name": "  "}) is None
    assert coerce_weapon(["光束軍刀"]) is None
    assert coerce_abilities({"entries": "none"}) is None


def test_a_name_without_word_characters_is_refused():
    """gemma4:31b emitted a '//' ability entry off the tab's separator rules."""
    assert coerce_weapon({"name": "//"}) is None
    texts = coerce_abilities(
        {"entries": [{"name": "//", "owner": "unit", "effect": None, "magnitude": 0}]}
    )
    assert texts is not None and texts.entries == ()


def test_transport_failure_yields_none():
    def broken(url, payload, timeout_s):
        raise OSError("connection refused")

    reader = OllamaPanelTextReader(transport=broken, terms={})
    assert reader.weapon(PATCH) is None
    assert reader.abilities(PATCH) is None


def test_non_json_reply_yields_none():
    reader = OllamaPanelTextReader(transport=lambda *_: "not json", terms={})
    assert reader.weapon(PATCH) is None


def test_ability_entries_split_by_owner_and_effect():
    transport, sent = stub(
        {
            "entries": [
                {"name": "盾牌防禦", "owner": "unit", "effect": "shield_defense", "magnitude": 0.2},
                {"name": "複製新人類", "owner": "pilot", "effect": None, "magnitude": 0},
                {"name": "支援防禦強化", "owner": "pilot", "effect": "support_defend_charge", "magnitude": 1},
            ],
            "unsupported": ["自身覺醒值及反應值提升10%"],
        }
    )
    reader = OllamaPanelTextReader(transport=transport, terms={"abilities": ("盾牌防禦",)})
    texts = reader.abilities(PATCH)
    assert sent[0]["format"] == ABILITY_SCHEMA
    assert texts is not None
    assert [(entry.name, entry.owner, entry.effect) for entry in texts.entries] == [
        ("盾牌防禦", "unit", "shield_defense"),
        ("複製新人類", "pilot", None),
        ("支援防禦強化", "pilot", "support_defend_charge"),
    ]
    assert texts.entries[0].matched is True
    assert texts.entries[1].matched is False
    assert texts.unsupported == ("自身覺醒值及反應值提升10%",)


def test_ability_entry_with_an_unknown_owner_is_dropped_not_guessed():
    texts = coerce_abilities(
        {"entries": [{"name": "I力場", "owner": "machine", "effect": None, "magnitude": 0}]}
    )
    assert texts is not None
    assert texts.entries == ()
    assert texts.unsupported == ("owner=machine name=I力場",)


@pytest.mark.parametrize(
    ("raw", "expected", "matched"),
    [
        ("光束軍刀", "光束軍刀", True),
        (" 光束軍刀 ", "光束軍刀", True),
        ("胸部mega粒子砲", "胸部MEGA粒子砲", True),
        ("光束車刀", "光束軍刀", True),
        ("完全沒見過的武裝", "完全沒見過的武裝", False),
        ("", "", False),
    ],
)
def test_align_against_the_vocabulary(raw, expected, matched):
    terms = ("光束軍刀", "胸部MEGA粒子砲", "感應砲")
    assert align(raw, terms) == (expected, matched)


def test_align_refuses_an_ambiguous_near_miss():
    assert align("光束軍力", ("光束軍刀", "光束軍才")) == ("光束軍力", False)


def test_align_corrects_a_three_character_near_miss():
    """gemma4:31b returned 感應炮 for 感應砲 on the kshatriya fixture."""
    assert align("感應炮", ("感應砲", "光束軍刀")) == ("感應砲", True)


def test_align_never_corrects_a_two_character_name():
    assert align("力場", ("力壁",)) == ("力場", False)


def test_shipped_vocabulary_covers_the_fixture_weapons():
    terms = panel_text.vocabulary()
    assert "光束軍刀" in terms["weapons"]
    assert "盾牌防禦" in terms["abilities"]
    assert "_note" not in terms


def test_coerce_lines_keeps_the_printed_lines_and_drops_the_blanks():
    assert coerce_lines({"lines": ["光束軍刀", "  ", "命中時 敵方 受到的傷害提升10%"]}) == (
        "光束軍刀",
        "命中時 敵方 受到的傷害提升10%",
    )


def test_coerce_lines_reports_failure_apart_from_emptiness():
    assert coerce_lines(None) is None
    assert coerce_lines({"lines": "光束軍刀"}) is None
    assert coerce_lines({"lines": []}) == ()


def test_a_truncated_reply_cannot_pollute_a_transcription():
    """回覆中途截斷會變成一條超長串；截到上限，別讓截斷看起來像面板文案。"""
    long_line = "字" * (MAX_LINE_CHARS + 50)
    lines = coerce_lines({"lines": [long_line] * (MAX_LINES + 5)})
    assert lines is not None
    assert len(lines) == MAX_LINES
    assert all(len(line) == MAX_LINE_CHARS for line in lines)


def test_coerce_brief_needs_at_least_one_sentence():
    assert coerce_brief({"victory": "擊墜所有敵方單位", "defeat": ""}) == StageBrief(
        victory="擊墜所有敵方單位", defeat=""
    )
    assert coerce_brief({"victory": "", "defeat": ""}) is None
    assert coerce_brief(["擊墜所有敵方單位"]) is None


def test_transcription_requests_carry_the_lines_schema():
    transport, sent = stub({"lines": ["盾牌防禦", "防禦時減輕傷害20%"]})
    reader = OllamaPanelTextReader(transport=transport, terms={})

    assert reader.ability_lines(PATCH) == ("盾牌防禦", "防禦時減輕傷害20%")
    assert sent[0]["format"] == LINES_SCHEMA
    assert sent[0]["options"]["temperature"] == 0


def test_weapon_lines_transcribe_without_any_effect_enum():
    transport, sent = stub({"lines": ["感應砲", "距離敵方越遠，武裝POWER越為提升"]})
    reader = OllamaPanelTextReader(transport=transport, terms={"weapons": ("感應砲",)})

    assert reader.weapon_lines(PATCH) == ("感應砲", "距離敵方越遠，武裝POWER越為提升")
    assert "effect" not in sent[0]["format"]["properties"]


def test_stage_brief_transcribes_both_conditions():
    transport, sent = stub({"victory": "擊墜所有敵方單位", "defeat": "我方全滅"})
    reader = OllamaPanelTextReader(transport=transport, terms={})

    assert reader.stage_brief(PATCH) == StageBrief(victory="擊墜所有敵方單位", defeat="我方全滅")
    assert sent[0]["format"] == BRIEF_SCHEMA


def test_a_dead_server_leaves_the_transcriptions_unread():
    def broken(url, payload, timeout_s):
        raise OSError("connection refused")

    reader = OllamaPanelTextReader(transport=broken, terms={})
    assert reader.ability_lines(PATCH) is None
    assert reader.weapon_lines(PATCH) is None
    assert reader.stage_brief(PATCH) is None


def test_from_env_is_off_when_disabled(monkeypatch):
    monkeypatch.setenv("GGGE_LLM", "0")
    assert OllamaPanelTextReader.from_env() is None


def test_from_env_is_off_when_unreachable(monkeypatch):
    monkeypatch.delenv("GGGE_LLM", raising=False)
    monkeypatch.setattr(panel_text, "_server_reachable", lambda url, timeout_s=2.0: False)
    assert OllamaPanelTextReader.from_env() is None
