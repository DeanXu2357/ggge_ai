"""名冊採集幀 → sandbox-scenario/1：解析、對帳失敗模式、組裝自驗。

自由文字一律以字串保存：轉錄到的效果句與能力詞條不得改寫任何結構欄。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ggge_ai.runtime import sweep
from ggge_ai.runtime.panel_text import StageBrief
from ggge_ai.stage import scenario as scenario_mod
from ggge_ai.engine.contract import Faction
from ggge_ai.stage.intel import UnitIntel
from ggge_ai.stage.roster_offline import (
    ARBITRARY,
    EXACT,
    GROUP_ASSIGNED,
    OBSERVED_ONLY,
    BoardFacts,
    CellFact,
    ParsedUnit,
    UnitCapture,
    build_report,
    build_scenario,
    collect_captures,
    parse_unit,
    pick_for,
    reconcile,
    run_offline,
    sweep_facts,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vision"
BOARD = {"cols": 25, "rows": 20}

KSHATRIYA = {
    "stats0": "stage_panels/enemy_detail_stats_kshatriya.png",
    "weapons": "stage_panels/enemy_detail_weapons_kshatriya.png",
    "abilities": "stage_panels/enemy_detail_abilities_kshatriya.png",
}
NT_GUNDAM = {
    "basic": "stage_panels/ally_detail_basicinfo_ntgundam.png",
    "weapons": "stage_panels/ally_detail_weapons_ntgundam.png",
}


class FakeTranscriber:
    """轉錄用的替身：只吐字串，不做任何欄位映射。"""

    def __init__(self, weapon=("光束軍刀", "命中時敵方受到的傷害提升10%"), ability=("盾牌防禦",)):
        self.weapon = weapon
        self.ability = ability
        self.brief = StageBrief(victory="擊墜所有敵方單位", defeat="我方全滅")

    def weapon_lines(self, patch):
        return self.weapon

    def ability_lines(self, patch):
        return self.ability

    def stage_brief(self, patch):
        return self.brief


def parsed(faction: str, index: int, hp: int, en: int, **fields) -> ParsedUnit:
    return ParsedUnit(
        faction=faction,
        index=index,
        record=UnitIntel(f"{faction}_{index}", max_hp=hp, en_max=en, **fields),
    )


def facts(*rows) -> BoardFacts:
    return BoardFacts(
        tuple(CellFact(cell=cell, verdict=verdict, hp=hp, en=en) for verdict, cell, hp, en in rows)
    )


def deployment_of(recon, intel_id):
    return [item for item in recon.deployments if item.intel_id == intel_id]


def issues_of(recon, kind):
    return [item for item in recon.issues if item["kind"] == kind]


def test_parse_unit_reads_the_numbers_without_any_reader():
    result = parse_unit(UnitCapture("enemy", 0, dict(KSHATRIYA)), FIXTURES, None)

    assert (result.record.max_hp, result.record.en_max) == (167817, 594)
    assert result.record.move_range == 4
    assert (result.record.unit_attack, result.record.unit_defense) == (7206.0, 9077.0)
    assert [weapon.power for weapon in result.record.weapons] == [3500.0, 4100.0, 3800.0]


def test_the_strongest_weapon_badge_picks_the_pilot_offence_column():
    result = parse_unit(UnitCapture("enemy", 0, dict(KSHATRIYA)), FIXTURES, None)

    assert result.record.pilot_attack == result.record.pilot_shooting
    assert "pilot_attack:unpicked" not in result.gaps


def test_pick_for_returns_none_without_a_badge():
    class Row:
        power = 100.0
        categories = ()

    assert pick_for([Row()]) is None
    assert pick_for([]) is None


def test_unread_free_text_is_a_declared_gap_not_a_guess():
    result = parse_unit(UnitCapture("enemy", 0, dict(KSHATRIYA)), FIXTURES, None)

    assert [weapon.name for weapon in result.record.weapons] == [
        "weapon_0",
        "weapon_1",
        "weapon_2",
    ]
    assert "weapon0:name" in result.gaps
    assert result.weapon_names_pending == (0, 1, 2)
    assert result.abilities_pending is True
    assert result.ability_lines == ()


def test_missing_pages_are_named():
    result = parse_unit(UnitCapture("enemy", 0, {"weapons": KSHATRIYA["weapons"]}), FIXTURES, None)

    assert "basic" in result.missing_pages
    assert "abilities" in result.missing_pages


def test_an_unreadable_frame_path_is_reported_not_raised():
    result = parse_unit(UnitCapture("enemy", 0, {"weapons": "nope/missing.png"}), FIXTURES, None)

    assert result.unreadable_pages == ("weapons",)
    assert "weapons" in result.gaps


def test_free_text_is_transcribed_as_strings_and_touches_no_structural_field():
    """效果句寫「傷害提升10%」、詞條寫「盾牌防禦」，兩者都不准改寫 schema 欄。"""
    result = parse_unit(UnitCapture("enemy", 0, dict(KSHATRIYA)), FIXTURES, FakeTranscriber())

    assert result.record.weapons[0].name == "光束軍刀"
    assert result.record.weapons[0].debuff_kind is None
    assert result.record.weapons[0].debuff_magnitude == 0.0
    assert result.weapon_notes[0] == "weapon0: 命中時敵方受到的傷害提升10%"
    assert result.ability_lines == ("盾牌防禦",)
    assert result.abilities_pending is False
    assert result.record.has_shield is False
    assert result.record.skills == ()
    assert "abilities" in result.gaps


def test_the_scrolled_weapon_page_does_not_duplicate_cards():
    pages = dict(KSHATRIYA)
    pages["weapons_more"] = KSHATRIYA["weapons"]

    result = parse_unit(UnitCapture("enemy", 0, pages), FIXTURES, None)

    assert len(result.record.weapons) == 3


def test_collect_captures_groups_pages_and_keeps_failures():
    entries = [
        {"kind": "roster_capture", "faction": "enemy", "index": 0, "page": "basic",
         "ok": True, "frame": "frames/a.png"},
        {"kind": "roster_capture", "faction": "enemy", "index": 0, "page": "weapons",
         "ok": False, "reason": "panel_unknown"},
        {"kind": "roster_capture", "faction": "ally", "index": 0, "page": "basic",
         "ok": True, "frame": "frames/b.png"},
        {"kind": "verdict", "cell": [1, 1], "verdict": "empty"},
    ]

    captures = collect_captures(entries)

    assert [(cap.faction, cap.index) for cap in captures] == [("enemy", 0), ("ally", 0)]
    assert captures[0].pages == {"basic": "frames/a.png"}
    assert captures[0].failures == (("weapons", "panel_unknown"),)


def test_sweep_facts_replays_verdicts_with_the_last_one_winning():
    entries = [
        {"kind": "verdict", "cell": [3, 3], "verdict": sweep.UNSURE},
        {"kind": "verdict", "cell": [3, 3], "verdict": sweep.ENEMY, "hp": 100, "en": 20},
        {"kind": "verdict", "cell": [4, 4], "verdict": sweep.EMPTY},
    ]

    result = sweep_facts(entries)

    assert result.source == "verdict_replay"
    assert result.enemy_cells == (CellFact(cell=(3, 3), verdict=sweep.ENEMY, hp=100, en=20),)
    assert len(result.cells) == 2


def test_a_later_verdict_without_numbers_does_not_erase_the_observed_ones():
    entries = [
        {"kind": "verdict", "cell": [3, 3], "verdict": sweep.ENEMY, "hp": 100, "en": 20},
        {"kind": "verdict", "cell": [3, 3], "verdict": sweep.ENEMY},
    ]

    assert sweep_facts(entries).enemy_cells[0].hp == 100


def test_the_ledger_dump_settles_the_final_cell_set():
    entries = [
        {"kind": "verdict", "cell": [3, 3], "verdict": sweep.ENEMY, "hp": 100, "en": 20},
        {"kind": "verdict", "cell": [9, 9], "verdict": sweep.ENEMY, "hp": 50, "en": 5},
        {"kind": "ledger_dump", "cells": [[3, 3, sweep.ENEMY], [4, 4, sweep.EMPTY]]},
    ]

    result = sweep_facts(entries)

    assert result.source == "ledger_dump"
    assert [fact.cell for fact in result.cells] == [(3, 3), (4, 4)]
    assert result.enemy_cells[0].hp == 100


def test_a_lone_enemy_template_binds_its_cell_exactly():
    recon = reconcile(
        [parsed("enemy", 0, 100, 20)],
        facts((sweep.ENEMY, (3, 3), 100, 20)),
    )

    bound = deployment_of(recon, "enemy_hp100_en20")
    assert [(item.cell, item.assignment) for item in bound] == [((3, 3), EXACT)]
    assert recon.issues == []


def test_same_hp_en_units_share_one_template_and_say_the_cells_are_arbitrary():
    recon = reconcile(
        [parsed("enemy", 0, 100, 20), parsed("enemy", 1, 100, 20)],
        facts((sweep.ENEMY, (3, 3), 100, 20), (sweep.ENEMY, (5, 5), 100, 20)),
    )

    bound = deployment_of(recon, "enemy_hp100_en20")
    assert {item.cell for item in bound} == {(3, 3), (5, 5)}
    assert {item.assignment for item in bound} == {GROUP_ASSIGNED}
    assert recon.groups[0]["members"] == [0, 1]
    assert issues_of(recon, "count_mismatch") == []


def test_group_differences_beyond_hp_and_en_are_reported_not_merged_silently():
    recon = reconcile(
        [parsed("enemy", 0, 100, 20), parsed("enemy", 1, 100, 20, mobility=3.0)],
        facts((sweep.ENEMY, (3, 3), 100, 20), (sweep.ENEMY, (5, 5), 100, 20)),
    )

    assert recon.groups[0]["differences"] == [{"index": 1, "differs": ["mobility"]}]


def test_more_intel_than_cells_is_a_count_mismatch_with_the_leftovers_named():
    recon = reconcile(
        [parsed("enemy", 0, 100, 20), parsed("enemy", 1, 100, 20)],
        facts((sweep.ENEMY, (3, 3), 100, 20)),
    )

    assert issues_of(recon, "count_mismatch")[0]["intel_units"] == 2
    assert issues_of(recon, "unmatched_intel")[0]["units"] == [1]
    assert len(deployment_of(recon, "enemy_hp100_en20")) == 1


def test_a_cell_no_template_matches_keeps_the_board_complete_as_observed_intel():
    recon = reconcile(
        [parsed("enemy", 0, 100, 20)],
        facts((sweep.ENEMY, (3, 3), 100, 20), (sweep.ENEMY, (7, 7), 777, 66)),
    )

    extra = deployment_of(recon, "enemy_unmatched_1")
    assert [(item.cell, item.assignment) for item in extra] == [((7, 7), OBSERVED_ONLY)]
    assert recon.intel.record("enemy_unmatched_1").max_hp == 777
    assert issues_of(recon, "unmatched_cell")[0]["cell"] == [7, 7]


def test_a_known_glyph_error_shape_is_only_a_hint_never_an_automatic_match():
    """開頭多插 1 是已定讞的字模錯型；提示歸提示，配對仍要精確相等。"""
    recon = reconcile(
        [parsed("enemy", 0, 67817, 594)],
        facts((sweep.ENEMY, (7, 7), 167817, 594)),
    )

    assert recon.near_misses[0]["near"] == ["enemy_hp67817_en594"]
    assert deployment_of(recon, "enemy_hp67817_en594") == []
    assert deployment_of(recon, "enemy_unmatched_1")[0].assignment == OBSERVED_ONLY


def test_the_eight_nine_confusion_is_also_only_a_hint():
    recon = reconcile(
        [parsed("enemy", 0, 83811, 513)],
        facts((sweep.ENEMY, (9, 4), 93811, 513)),
    )

    assert recon.near_misses[0]["near"] == ["enemy_hp83811_en513"]


def test_our_own_units_match_exactly_and_each_keeps_its_own_template():
    recon = reconcile(
        [parsed("ally", 0, 39955, 131), parsed("ally", 1, 42000, 240)],
        facts((sweep.ALLY, (2, 6), 42000, 240), (sweep.ALLY, (3, 6), 39955, 131)),
    )

    assert {(item.intel_id, item.cell) for item in recon.deployments} == {
        ("ally_1", (2, 6)),
        ("ally_0", (3, 6)),
    }
    assert {item.assignment for item in recon.deployments} == {EXACT}


def test_an_ally_cell_without_numbers_falls_back_to_an_arbitrary_assignment():
    recon = reconcile(
        [parsed("ally", 0, 39955, 131)],
        facts((sweep.ALLY, (2, 6), None, None)),
    )

    assert recon.deployments[0].assignment == ARBITRARY
    assert issues_of(recon, "arbitrary_assignment")[0]["cell"] == [2, 6]


def test_two_allies_with_identical_numbers_are_assigned_arbitrarily():
    recon = reconcile(
        [parsed("ally", 0, 100, 20), parsed("ally", 1, 100, 20)],
        facts((sweep.ALLY, (2, 6), 100, 20), (sweep.ALLY, (3, 6), 100, 20)),
    )

    assert {item.assignment for item in recon.deployments} == {ARBITRARY}


def test_an_npc_seen_only_on_the_board_gets_a_minimal_synthesised_record():
    recon = reconcile([], facts((sweep.NPC, (8, 8), 5000, 60)))

    item = recon.deployments[0]
    assert (item.faction, item.assignment) == (Faction.THIRD_PARTY.value, OBSERVED_ONLY)
    assert recon.intel.record(item.intel_id).max_hp == 5000
    assert issues_of(recon, "npc_observed_only")[0]["cell"] == [8, 8]


def test_unsure_cells_are_reported_and_never_deployed():
    recon = reconcile([], facts((sweep.UNSURE, (1, 1), None, None)))

    assert recon.deployments == []
    assert issues_of(recon, "unsure_cell")[0]["cell"] == [1, 1]


def test_the_assembled_scenario_loads_and_builds():
    recon = reconcile(
        [parsed("enemy", 0, 100, 20), parsed("ally", 0, 39955, 131)],
        facts(
            (sweep.ENEMY, (3, 3), 100, 20),
            (sweep.ALLY, (2, 6), 39955, 131),
            (sweep.NPC, (8, 8), 5000, 60),
        ),
    )

    data = build_scenario(recon, "UC HARD 1", BOARD, StageBrief("擊墜全部敵人", "我方全滅"), "run x")
    scenario = scenario_mod.from_dict(json.loads(json.dumps(data)))
    state, _events = scenario.build()

    assert data["format"] == "sandbox-scenario/1"
    assert len(state.enemies()) == 1
    assert len(state.allies()) == 1
    assert {unit.faction for unit in state.units} == {
        Faction.ENEMY,
        Faction.ALLY,
        Faction.THIRD_PARTY,
    }
    assert "擊墜全部敵人" in data["note"] and "run x" in data["note"]


def test_the_victory_and_defeat_conditions_are_marked_as_assumptions():
    recon = reconcile([], facts())

    data = build_scenario(recon, "UC HARD 1", BOARD)

    assert data["victory"] == {"type": "annihilation", "source": "assumed_default"}
    assert data["defeat"] == {"type": "ally_annihilation", "source": "assumed_default"}
    assert scenario_mod.from_dict(data).victory["source"] == "assumed_default"


def test_the_report_carries_every_pending_item():
    parsed_unit = parse_unit(UnitCapture("enemy", 0, dict(KSHATRIYA)), FIXTURES, None)
    recon = reconcile([parsed_unit], facts((sweep.ENEMY, (3, 3), 1, 1)))

    report = build_report(
        recon,
        run="20260810-000000",
        stage="UC HARD 1",
        board=BOARD,
        board_source="stage_truth",
        brief=None,
        captures=[UnitCapture("enemy", 0, dict(KSHATRIYA))],
        counts={"enemy": 1},
    )

    assert report["units"][0]["abilities_pending"] is True
    assert "weapon0:name" in report["units"][0]["gaps"]
    assert report["units"][0]["missing_pages"]
    assert report["stage_brief"]["pending"] is True
    assert report["list_counts"] == {"enemy": 1}
    assert [item["kind"] for item in report["issues"]] == [
        "count_mismatch",
        "unmatched_intel",
        "unmatched_cell",
    ]
    assert report["deployments"][0]["assignment"] == OBSERVED_ONLY


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    frames = tmp_path / "frames"
    frames.mkdir()
    entries = []
    for page, relative in KSHATRIYA.items():
        name = f"enemy0_{page}.png"
        shutil.copy(FIXTURES / relative, frames / name)
        entries.append(
            {
                "kind": "roster_capture",
                "faction": "enemy",
                "index": 0,
                "page": page,
                "ok": True,
                "frame": f"frames/{name}",
            }
        )
    entries.append({"kind": "roster_list_end", "faction": "enemy", "count": 1})
    entries.append(
        {"kind": "verdict", "cell": [3, 3], "verdict": sweep.ENEMY, "hp": 167817, "en": 594}
    )
    entries.append({"kind": "stage_truth", "stage": "UC HARD 1", "found": True})
    (tmp_path / "sweep.jsonl").write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_run_offline_writes_a_scenario_that_validates(run_dir: Path):
    code = run_offline(run_dir, reader=None, stage_truth={"stage": "UC", "board": BOARD})

    assert code == 0
    data = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    assert data["board"] == BOARD
    assert data["deployment"][0]["cell"] == [3, 3]
    assert data["deployment"][0]["assignment"] == EXACT
    report = json.loads((run_dir / "intel_report.json").read_text(encoding="utf-8"))
    assert report["validation_error"] is None
    assert report["stage"] == "UC"


def test_run_offline_without_a_truth_file_falls_back_to_the_default_board(run_dir: Path):
    run_offline(run_dir, reader=None, stage_truth=None)

    report = json.loads((run_dir / "intel_report.json").read_text(encoding="utf-8"))
    assert report["board"] == {"cols": 25, "rows": 20}
    assert report["board_source"] == "default_25x20"
    assert report["stage"] == "UC HARD 1"


def test_a_scenario_that_will_not_build_is_kept_aside_not_raised(run_dir: Path):
    code = run_offline(run_dir, reader=None, stage_truth={"stage": "UC", "board": {"cols": 2, "rows": 2}})

    assert code == 1
    assert not (run_dir / "scenario.json").exists()
    assert (run_dir / "scenario.invalid.json").exists()
    report = json.loads((run_dir / "intel_report.json").read_text(encoding="utf-8"))
    assert "越界" in report["validation_error"]


def test_run_offline_transcribes_the_stage_brief_when_a_reader_is_present(run_dir: Path):
    frames = run_dir / "frames"
    shutil.copy(FIXTURES / "stage_panels/stage_info_auto_off.png", frames / "info.png")
    with (run_dir / "sweep.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(
            json.dumps({"kind": "frame", "label": "stage_info:end", "frame": "frames/info.png"})
            + "\n"
        )

    run_offline(run_dir, reader=FakeTranscriber(), stage_truth={"stage": "UC", "board": BOARD})

    report = json.loads((run_dir / "intel_report.json").read_text(encoding="utf-8"))
    assert report["stage_brief"] == {
        "victory": "擊墜所有敵方單位",
        "defeat": "我方全滅",
        "pending": False,
    }
    data = json.loads((run_dir / "scenario.json").read_text(encoding="utf-8"))
    assert "擊墜所有敵方單位" in data["note"]
