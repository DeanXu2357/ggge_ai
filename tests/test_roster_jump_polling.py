"""名冊掃描的面板輪詢：詳情頁轉場不算盡頭、盡頭要連兩輪、期望畫面遲到也接得住。

裝置與相機全是假件（幀是全黑合成圖），classify 由腳本吃到的畫面序列決定。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from ggge_ai.battle.map_grid import FrameGrid
from ggge_ai.runtime import jumpscan, roster, screens
from ggge_ai.runtime.journal import Journal
from scripts import scan_roster_jump
from scripts.scan_roster_jump import Halt, Scan

GRID = FrameGrid(cols=list(range(140, 2260, 128)), rows=list(range(90, 1020, 120)))


def build_scan(tmp_path, sequence: list[str]) -> Scan:
    seen = iter(sequence)
    frames = []

    def grab() -> np.ndarray:
        frame = np.zeros((4, 4, 3), np.uint8)
        frame[0, 0, 0] = len(frames)
        frames.append(frame)
        return frame

    camera = SimpleNamespace(
        grab=grab,
        keep=lambda label: None,
        settled=lambda wait, sleep: grab(),
        shots=0,
    )
    scan = Scan(
        device=SimpleNamespace(tap=lambda x, y, intent="": None),
        camera=camera,
        journal=Journal(tmp_path / "roster_jump.jsonl"),
        sleep=lambda _: None,
    )
    scan.classified = lambda frame: next(seen)  # type: ignore[attr-defined]
    return scan


@pytest.fixture
def classify(monkeypatch):
    def install(scan: Scan) -> None:
        monkeypatch.setattr(screens, "classify", scan.classified)

    return install


def test_a_detail_page_that_is_still_animating_is_not_the_end_of_the_list(tmp_path, classify):
    scan = build_scan(tmp_path, [screens.TROOP_INFO, screens.UNIT_DETAIL])
    classify(scan)

    assert scan.open_detail((729, 267)) is not None


def test_two_troop_info_readings_in_a_row_are_the_end_of_the_list(tmp_path, classify):
    scan = build_scan(tmp_path, [screens.TROOP_INFO, screens.TROOP_INFO])
    classify(scan)

    assert scan.open_detail((729, 267)) is None


def test_a_screen_that_is_neither_detail_nor_roster_halts_instead_of_ending_the_list(
    tmp_path, classify
):
    scan = build_scan(tmp_path, [screens.UNKNOWN] * 5)
    classify(scan)

    with pytest.raises(Halt):
        scan.open_detail((729, 267))


def test_the_expected_screen_is_accepted_even_when_it_arrives_late(tmp_path, classify):
    scan = build_scan(tmp_path, [screens.UNKNOWN, screens.UNKNOWN, screens.BATTLE_MENU])
    classify(scan)

    assert scan.tap((1172, 992), expect=screens.BATTLE_MENU) is not None


def test_the_expected_screen_never_arriving_halts(tmp_path, classify):
    scan = build_scan(tmp_path, [screens.TROOP_INFO] * 5)
    classify(scan)

    with pytest.raises(Halt):
        scan.tap((1172, 992), expect=screens.BATTLE_MENU)


def test_no_blank_cell_halts_and_leaves_a_journal_line(tmp_path, monkeypatch):
    """挑不出解除點就停在原地——但要留下流水帳，不然實機只看到一行 Halt。"""
    scan = build_scan(tmp_path, [])
    monkeypatch.setattr(jumpscan, "blank_cell_tap", lambda *a, **k: None)
    monkeypatch.setattr(scan_roster_jump, "frame_grid", lambda frame: GRID)

    with pytest.raises(Halt):
        scan.dismiss(roster.ENEMY, np.zeros((1080, 2340, 3), np.uint8))

    kinds = [json.loads(line)["kind"] for line in scan.journal.path.read_text().splitlines()]
    assert "no_blank_cell" in kinds


def _view(grid=GRID):
    return scan_roster_jump.View(
        np.zeros((1080, 2340, 3), np.uint8), grid, scan_roster_jump.grid_centres(grid)
    )


def test_a_pan_that_cannot_be_read_never_reaches_the_grid_as_none(tmp_path, monkeypatch):
    """0806 第九輪實機 CRASH：`pan()` 回 None 之後 continue，下一輪開頭拿 None.grid
    炸 AttributeError。讀不出來要重拍重讀，還是讀不出來才計 lost。"""
    scan = build_scan(tmp_path, [])
    monkeypatch.setattr(scan, "seed_marker", lambda *a, **k: (object(), (3, 4)))
    monkeypatch.setattr(scan, "pan", lambda direction: None)
    monkeypatch.setattr(scan, "look", lambda: None)

    assert scan.march_axis(("ally", 0), _view(), (5, 5), 0, "west") is None

    kinds = [json.loads(line)["kind"] for line in scan.journal.path.read_text().splitlines()]
    assert "march_reread" in kinds
    assert "march_failed" in kinds


def test_an_unreadable_pan_recovers_on_the_reread_instead_of_giving_up(tmp_path, monkeypatch):
    """重拍讀得出來就繼續走：鏡頭已經動了，重讀的是**新**視圖，不是推鏡前那張。"""
    bounded_grid = FrameGrid(cols=list(GRID.cols), rows=list(GRID.rows), west_bound=True)
    scan = build_scan(tmp_path, [])
    monkeypatch.setattr(scan, "seed_marker", lambda *a, **k: (object(), (3, 4)))
    monkeypatch.setattr(scan, "pan", lambda direction: None)
    monkeypatch.setattr(scan, "look", lambda: _view(bounded_grid))

    # 界那一幀的幀格 0 就是世界 0，所以目標的欄索引直接就是世界欄。
    assert scan.march_axis(("ally", 0), _view(), (5, 5), 0, "west") == 5


def _kinds(scan) -> list[str]:
    if not scan.journal.path.exists():
        return []
    return [json.loads(line)["kind"] for line in scan.journal.path.read_text().splitlines()]


def test_the_panels_are_closed_layer_by_layer_before_any_menu_tap(tmp_path, classify):
    """0806 run 20260806-103335 收尾 halt：失敗路徑沒收面板，下一台開選單就撞上
    troop_info。開選單前一律逐層關閉。"""
    scan = build_scan(
        tmp_path, [screens.UNIT_DETAIL, screens.TROOP_INFO, screens.BATTLE_MENU, screens.UNKNOWN]
    )
    classify(scan)
    taps: list[tuple[int, int]] = []
    scan.device = SimpleNamespace(tap=lambda x, y, intent="": taps.append((x, y)))

    assert scan.close_panels() is True
    assert taps == [
        roster.DETAIL_CLOSE_TAP,
        roster.TROOP_INFO_CLOSE_TAP,
        scan_roster_jump.entry.BATTLE_MENU_CLOSE_TAP,
    ]


def test_a_panel_that_will_not_close_is_reported_not_assumed_away(tmp_path, classify):
    scan = build_scan(tmp_path, [screens.TROOP_INFO] * 5)
    classify(scan)

    assert scan.close_panels() is False


def test_the_landing_frame_waits_for_the_camera_to_stop_moving(tmp_path, monkeypatch):
    """固定 1.5 秒的落點幀常常還是跳轉**前**的鏡位（同一輪 run 的 ally#0：落點幀與
    乾淨幀根本不是同一個鏡頭），兩幀不同鏡位時指定標示的比對整個沒有意義。"""
    moving = np.zeros((1080, 2340, 3), np.uint8)
    still = np.full((1080, 2340, 3), 90, np.uint8)
    frames = iter([moving, still, still, still])
    scan = build_scan(tmp_path, [])
    scan.camera = SimpleNamespace(grab=lambda: next(frames), keep=lambda label: None, shots=0)

    found = scan.steady()

    assert found[0, 0, 0] == 90
    assert "camera_unsteady" not in _kinds(scan)


def test_a_camera_that_never_settles_says_so_instead_of_pretending(tmp_path):
    frames = iter([np.full((1080, 2340, 3), (v % 2) * 200, np.uint8) for v in range(9)])
    scan = build_scan(tmp_path, [])
    scan.camera = SimpleNamespace(grab=lambda: next(frames), keep=lambda label: None, shots=0)

    scan.steady()

    assert "camera_unsteady" in _kinds(scan)


def test_an_ally_that_did_not_enter_unit_move_is_left_alone(tmp_path, classify):
    """已行動的單位跳不進移動模式。不猜、不點地圖、把面板收乾淨。"""
    scan = build_scan(tmp_path, [screens.BATTLE_MAP, screens.BATTLE_MAP])
    classify(scan)
    taps: list[tuple[int, int]] = []
    scan.device = SimpleNamespace(tap=lambda x, y, intent="": taps.append((x, y)))

    view, target, sig = scan.land_ally(
        ("ally", 0), np.zeros((4, 4, 3), np.uint8), None, "jump"
    )

    assert (view, target) == (None, None)
    assert taps == []
    assert "jump_not_taken" in _kinds(scan)


def test_the_ally_cell_is_the_centre_of_the_move_range_diamond(tmp_path, monkeypatch):
    """跳轉直接進單位移動模式，遊戲自己把可抵達格畫成以該台為中心、半徑＝移動力的
    菱形——中心就是它站的格，全程零 map tap。"""
    scan = build_scan(tmp_path, [])
    scan.entries = [
        roster.RosterEntry(faction=roster.ALLY, index=0, hp=1, en=1, mobility=2, lv=1)
    ]
    centres = scan_roster_jump.grid_centres(GRID)
    reach = {
        cell for cell in centres if abs(cell[0] - 4) + abs(cell[1] - 3) <= 2 and cell != (4, 3)
    }
    monkeypatch.setattr(
        scan_roster_jump.jumpscan,
        "range_marks",
        lambda frame, pitch: tuple(centres[cell] for cell in sorted(reach)),
    )
    moving = _view()

    assert scan.range_cell(("ally", 0), moving) == (4, 3)


def test_an_ally_whose_mobility_was_never_read_stays_unresolved(tmp_path):
    scan = build_scan(tmp_path, [])
    scan.entries = [
        roster.RosterEntry(faction=roster.ALLY, index=0, hp=1, en=1, mobility=None, lv=1)
    ]

    assert scan.range_cell(("ally", 0), _view()) is None
    assert "range_fit" in _kinds(scan)


def test_the_tour_runs_the_enemy_roster_first_by_default(tmp_path):
    scan = build_scan(tmp_path, [])
    scan.entries = [
        roster.RosterEntry(faction=roster.ALLY, index=0, hp=1, en=1, mobility=1, lv=1),
        roster.RosterEntry(faction=roster.ENEMY, index=0, hp=1, en=1, mobility=1, lv=None),
        roster.RosterEntry(faction=roster.ENEMY, index=1, hp=1, en=1, mobility=1, lv=None),
    ]

    assert scan.keys() == [("enemy", 0), ("enemy", 1), ("ally", 0)]

    scan.tour_first = roster.ALLY
    assert scan.keys()[0] == ("ally", 0)


def _entry(index=0):
    return roster.RosterEntry(faction=roster.ENEMY, index=index, hp=1, en=2, mobility=3, lv=None)


def test_a_detail_page_still_fading_in_is_read_again_not_halted_on(tmp_path, monkeypatch):
    """0806 run 20260806-120326 的 enemy#16：淡入轉場中的半透明幀 classify 過得了
    （字模形狀還在），陣營帶與 HP/EN/移動力卻一起讀成 None。"""
    scan = build_scan(tmp_path, [])
    readings = iter([None, _entry(16)])
    monkeypatch.setattr(roster, "read_detail", lambda frame, index: next(readings))

    found = scan.read_entry(roster.ENEMY, 16)

    assert found == _entry(16)
    assert _kinds(scan).count("detail_retry") == 1


def test_a_detail_page_that_never_reads_clean_gives_up_after_three_tries(tmp_path, monkeypatch):
    scan = build_scan(tmp_path, [])
    monkeypatch.setattr(roster, "read_detail", lambda frame, index: None)

    assert scan.read_entry(roster.ENEMY, 16) is None
    assert _kinds(scan).count("detail_retry") == 3


def test_half_read_numbers_are_retried_too_not_just_the_faction_band(tmp_path, monkeypatch):
    """淡入吃掉的不只是陣營帶——同一張幀的數值欄一樣讀不出來，讀不齊就重來。"""
    partial = roster.RosterEntry(faction=roster.ENEMY, index=16, hp=None, en=2, mobility=3)
    readings = iter([partial, _entry(16)])
    scan = build_scan(tmp_path, [])
    monkeypatch.setattr(roster, "read_detail", lambda frame, index: next(readings))

    assert scan.read_entry(roster.ENEMY, 16).complete
    assert _kinds(scan).count("detail_retry") == 1


def test_the_steady_gate_only_watches_the_region_it_was_given(tmp_path):
    """面板用讀值區當尺，地圖用地圖區——區域外面的動靜不該把讀值卡住。"""
    quiet = np.full((1080, 2340, 3), 60, np.uint8)
    noisy = quiet.copy()
    noisy[0:100, 0:2340] = 250
    frames = iter([quiet, noisy, noisy])
    scan = build_scan(tmp_path, [])
    scan.camera = SimpleNamespace(grab=lambda: next(frames), keep=lambda label: None, shots=0)

    scan.steady(scan_roster_jump.DETAIL_REGION)

    assert "camera_unsteady" not in _kinds(scan)
