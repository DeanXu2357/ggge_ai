"""名冊掃描的面板輪詢：詳情頁轉場不算盡頭、盡頭要連兩輪、期望畫面遲到也接得住。

裝置與相機全是假件（幀是全黑合成圖），classify 由腳本吃到的畫面序列決定。
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from ggge_ai.battle.map_grid import FrameGrid
from ggge_ai.runtime import board, jumpscan, roster, screens
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
    scan = build_scan(tmp_path, [screens.BATTLE_MAP])
    monkeypatch.setattr(screens, "classify", scan.classified)
    monkeypatch.setattr(screens, "read_roster_strip", lambda frame: screens.ROSTER_COLLAPSED)
    monkeypatch.setattr(jumpscan, "blank_cell_tap", lambda *a, **k: None)

    with pytest.raises(Halt):
        scan.dismiss(roster.ENEMY, _view())

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
    marker = board.MarkerSignature(hsv=(100, 200, 200), tolerance=(5, 40, 40), size=(40.0, 40.0))
    monkeypatch.setattr(scan, "seed_marker", lambda *a, **k: (marker, (3, 4), (900.0, 500.0)))
    monkeypatch.setattr(
        scan, "carry_marker", lambda *a, **k: (marker, (3, 4), (900.0, 500.0), False)
    )
    monkeypatch.setattr(scan, "pan", lambda direction, reach=0.0: None)
    monkeypatch.setattr(scan, "look", lambda: None)

    assert scan.march_axis(("ally", 0), _view(), (5, 5), 0, "west") == scan_roster_jump.AxisResult()

    kinds = [json.loads(line)["kind"] for line in scan.journal.path.read_text().splitlines()]
    assert "march_reread" in kinds
    assert "march_failed" in kinds


def test_an_unreadable_pan_recovers_on_the_reread_instead_of_giving_up(tmp_path, monkeypatch):
    """重拍讀得出來就繼續走：鏡頭已經動了，重讀的是**新**視圖，不是推鏡前那張。"""
    bounded_grid = FrameGrid(cols=list(GRID.cols), rows=list(GRID.rows), west_bound=True)
    scan = build_scan(tmp_path, [])
    marker = board.MarkerSignature(hsv=(100, 200, 200), tolerance=(5, 40, 40), size=(40.0, 40.0))
    monkeypatch.setattr(scan, "seed_marker", lambda *a, **k: (marker, (3, 4), (900.0, 500.0)))
    monkeypatch.setattr(
        scan, "carry_marker", lambda *a, **k: (marker, (3, 4), (900.0, 500.0), False)
    )
    monkeypatch.setattr(scan, "pan", lambda direction, reach=0.0: None)
    monkeypatch.setattr(scan, "look", lambda: _view(bounded_grid))

    # 界那一幀的幀格 0 就是世界 0，所以目標的欄索引直接就是世界欄。
    assert scan.march_axis(("ally", 0), _view(), (5, 5), 0, "west").world == 5


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

    view, target = scan.land_ally(("ally", 0), np.zeros((4, 4, 3), np.uint8), "jump")

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


def test_two_grids_one_line_apart_at_the_far_edge_are_still_the_same_view():
    """0806 run 20260806-121910：三次 range_fit 成功全被「逐線全等」作廢，實際上只是
    格線偵測在邊緣多裁一條。格號對位只看原點相位。"""
    trimmed = FrameGrid(cols=list(GRID.cols[:-1]), rows=list(GRID.rows))

    assert scan_roster_jump.same_view(GRID, trimmed)


def test_a_grid_shifted_by_a_whole_cell_is_not_the_same_view():
    moved = FrameGrid(
        cols=[x + 130 for x in GRID.cols], rows=list(GRID.rows)
    )

    assert not scan_roster_jump.same_view(GRID, moved)


def test_a_capture_timeout_is_retried_once_before_giving_up(tmp_path):
    """adb exec-out screencap 偶發逾時，通道旋即恢復——截圖唯讀且冪等，重試一次。"""
    calls = []

    def shot():
        calls.append(1)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(cmd="adb exec-out screencap -p", timeout=30)
        return b"png"

    camera = scan_roster_jump.Camera(
        device=SimpleNamespace(screenshot=shot),
        journal=Journal(tmp_path / "roster_jump.jsonl"),
        sleep=lambda _: None,
    )

    assert camera.screenshot() == b"png"
    assert camera.shots == 1
    kinds = [json.loads(line)["kind"] for line in camera.journal.path.read_text().splitlines()]
    assert kinds == ["capture_retry"]


def test_a_second_capture_timeout_is_not_swallowed(tmp_path):
    def shot():
        raise subprocess.TimeoutExpired(cmd="adb exec-out screencap -p", timeout=30)

    camera = scan_roster_jump.Camera(
        device=SimpleNamespace(screenshot=shot),
        journal=Journal(tmp_path / "roster_jump.jsonl"),
        sleep=lambda _: None,
    )

    with pytest.raises(subprocess.TimeoutExpired):
        camera.screenshot()


def _marker():
    return board.MarkerSignature(hsv=(100, 200, 200), tolerance=(5, 40, 40), size=(40.0, 40.0))


def test_the_marker_is_reseeded_at_the_frontier_before_every_pan(tmp_path, monkeypatch):
    """0806 run 20260806-130539：65 筆 march_lost，48 筆倒在第 2 把、16 筆倒在第 1 把
    ——一顆標記撐不了幾把推鏡。每一把都在前緣重種（sweep_scan carry_marker 的紀律）。"""
    scan = build_scan(tmp_path, [])
    seeds: list[str | None] = []
    monkeypatch.setattr(
        scan,
        "seed_marker",
        lambda view, **kw: seeds.append(kw.get("toward")) or (_marker(), (3, 4), (900.0, 500.0)),
    )
    pans: list[float] = []

    def pan(direction, reach=0.0):
        pans.append(reach)
        return None if len(pans) >= 2 else _view()

    monkeypatch.setattr(scan, "pan", pan)
    monkeypatch.setattr(scan, "look", lambda: None)
    monkeypatch.setattr(scan_roster_jump.board, "find_marker", lambda *a, **k: None)

    scan.march_axis(("enemy", 0), _view(), (5, 5), 0, "west")

    assert seeds and all(toward == "west" for toward in seeds[1:])
    assert len(seeds) > 1


def _met_scan(tmp_path, monkeypatch, values, *, solved=("enemy", 9), world=(12, 3)):
    scan = build_scan(tmp_path, [])
    scan.entries = [
        roster.RosterEntry(faction="enemy", index=9, hp=83811, en=513, mobility=6),
        roster.RosterEntry(faction="enemy", index=3, hp=29265, en=424, mobility=6),
        roster.RosterEntry(faction="enemy", index=4, hp=29265, en=424, mobility=6),
    ]
    if solved is not None:
        scan.ledger.anchor(solved, world)
    monkeypatch.setattr(scan, "seed_marker", lambda *a, **k: (_marker(), (3, 4), (900.0, 500.0)))
    monkeypatch.setattr(
        scan, "carry_marker", lambda *a, **k: (_marker(), (3, 4), (900.0, 500.0), False)
    )
    monkeypatch.setattr(scan, "pan", lambda direction, reach=0.0: None)
    monkeypatch.setattr(scan, "look", lambda: None)
    scan.encounter = ((7, 2), values)
    return scan


def test_a_unit_bumped_into_while_seeding_settles_both_axes_on_the_spot(tmp_path, monkeypatch):
    """種標記那一下點到單位＝免費的辨識機會：數值唯一又已解，幀內格差直接出世界格。"""
    scan = _met_scan(tmp_path, monkeypatch, (83811, 513))

    result = scan.march_axis(("enemy", 0), _view(), (5, 5), 0, "west")

    # 認出來的那台在世界 (12,3)、這一幀的 (7,2)；目標在同一幀的 (5,5)。
    assert result == scan_roster_jump.AxisResult(met=(10, 6))
    assert "march_meet" in _kinds(scan)


def test_a_number_that_the_whole_squad_shares_names_nobody(tmp_path, monkeypatch):
    """同型雜魚整批 29265/424：撞名就是撞名，不猜，繼續推到界。"""
    scan = _met_scan(tmp_path, monkeypatch, (29265, 424))

    result = scan.march_axis(("enemy", 0), _view(), (5, 5), 0, "west")

    assert result.met is None
    assert "march_meet" in _kinds(scan)


def test_bumping_into_a_unit_before_anything_is_solved_settles_nothing(tmp_path, monkeypatch):
    """帳面空的時候認出誰都沒用——那台的世界格自己都還不知道。"""
    scan = _met_scan(tmp_path, monkeypatch, (83811, 513), solved=None)

    assert scan.march_axis(("enemy", 0), _view(), (5, 5), 0, "west").met is None


def _dock_scan(tmp_path, monkeypatch, seen, *, left=None, right=None):
    scan = build_scan(tmp_path, [seen])
    monkeypatch.setattr(screens, "classify", scan.classified)
    monkeypatch.setattr(scan_roster_jump.vision, "read_enemy_summary", lambda frame: left)
    monkeypatch.setattr(scan_roster_jump.vision, "read_ally_summary", lambda frame: right)
    scan.note_encounter((3, 3), np.zeros((4, 4, 3), np.uint8))
    return scan


def _summary(hp, en):
    return SimpleNamespace(hp=hp, en=en, name_sig="x")


def test_our_own_unit_is_read_off_the_right_dock_in_move_mode(tmp_path, monkeypatch):
    """我方點下去進單位移動模式，摘要卡在右塢（實幀 20260806-013500：38311/148）。"""
    scan = _dock_scan(
        tmp_path, monkeypatch, screens.BATTLE_UNIT_MOVE, right=_summary(38311, 148)
    )

    assert scan.encounter == ((3, 3), (38311, 148))


def test_the_weapon_select_lookalike_panel_is_never_read_as_an_encounter(tmp_path, monkeypatch):
    """battle-prep／選擇武裝的右面板長得一樣，讀到的卻是攻擊目標的數值——那是毒帳。"""
    scan = _dock_scan(
        tmp_path,
        monkeypatch,
        screens.BATTLE_WEAPON_SELECT,
        left=_summary(1, 2),
        right=_summary(3, 4),
    )

    assert scan.encounter is None


def test_a_reseeded_marker_moves_the_odometer_but_carrying_the_old_one_does_not(
    tmp_path, monkeypatch
):
    """新種的一顆才要把兩顆的幀格差入帳；沿用同一顆是同一個實體，世界格差不變。"""
    scan = build_scan(tmp_path, [])
    monkeypatch.setattr(scan, "seed_marker", lambda *a, **k: (_marker(), (3, 4), (900.0, 500.0)))
    carried = iter([(_marker(), (1, 6), (900.0, 500.0), True)])
    monkeypatch.setattr(scan, "carry_marker", lambda *a, **k: next(carried, None))
    monkeypatch.setattr(scan, "pan", lambda direction, reach=0.0: _view())
    monkeypatch.setattr(scan_roster_jump.board, "find_marker", lambda *a, **k: (900.0, 500.0))
    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(
        scan, "meet", lambda key, target_frame, axis, legs: seen.append(target_frame) or None
    )

    scan.march_axis(("enemy", 0), _view(), (5, 5), 0, "west")

    # 第一次是出發幀的目標格；重種到 (1,6) 之後，目標在同一幀仍然是 (5,5)。推完一把
    # 標記重認在 (5,3)，帶著重種補的 (-2,+2) 才算得出目標在新幀的 (9,2)。
    assert seen[:3] == [(5, 5), (5, 5), (9, 2)]


def test_the_stroke_is_capped_so_the_marker_cannot_be_pushed_out_of_view(tmp_path):
    """推過頭標記就出視野，新窗裡一個證人都沒有。"""
    scan = build_scan(tmp_path, [])
    view = _view()

    near_edge = scan.stride(view, (2200.0, 500.0), "west")
    room = scan.stride(view, (400.0, 500.0), "west")

    assert near_edge < room
    assert near_edge >= scan_roster_jump.board.PAN_MIN_REACH


def test_the_frontier_seed_goes_west_when_the_camera_is_heading_west(tmp_path, monkeypatch):
    scan = build_scan(tmp_path, [screens.BATTLE_MAP] * 4)
    monkeypatch.setattr(screens, "classify", scan.classified)
    monkeypatch.setattr(screens, "read_roster_strip", lambda frame: screens.ROSTER_COLLAPSED)
    taps: list[tuple[int, int]] = []
    scan.device = SimpleNamespace(tap=lambda x, y, intent="": taps.append((x, y)))
    monkeypatch.setattr(
        scan_roster_jump.jumpscan, "clean_points", lambda *a, **k: [(1800.0, 500.0), (300.0, 500.0)]
    )
    monkeypatch.setattr(scan_roster_jump.board, "find_unit_screen_hints", lambda frame: ())
    monkeypatch.setattr(
        scan_roster_jump.sweep,
        "classify_tap",
        lambda *a, **k: scan_roster_jump.sweep.TapOutcome(scan_roster_jump.sweep.TAP_EMPTY),
    )

    scan.seed_marker(_view(), signature=_marker(), toward="west")

    assert taps[0][0] == 300


def test_no_map_tap_happens_until_the_screen_is_confirmed_to_be_the_map(tmp_path, monkeypatch):
    """0806 run 20260806-130539 的 ally#2：返回退出後沒驗狀態就繼續點，選取殘留讓下一下
    開了武裝選單（誤攻擊前哨）。狀態不對就放棄這一台，一下都不點地圖。"""
    scan = build_scan(tmp_path, [screens.BATTLE_WEAPON_SELECT] * 12)
    monkeypatch.setattr(screens, "classify", scan.classified)
    taps: list[tuple[int, int]] = []
    scan.device = SimpleNamespace(tap=lambda x, y, intent="": taps.append((x, y)))

    assert scan.seed_marker(_view(), toward="west") is None
    assert scan.confirm_occupied(_view(), (1170.0, 540.0)) is False
    assert taps == []
    assert "map_tap_blocked" in _kinds(scan)


def test_an_expanded_card_strip_is_collapsed_before_any_map_tap(tmp_path, monkeypatch):
    """0806 run 20260806-141615：卡條被展開之後 classify 照樣回 battle_map，但地圖下緣
    被蓋住、格網從此讀不出來。畫面對不等於盤面可用。"""
    scan = build_scan(tmp_path, [screens.BATTLE_MAP] * 4)
    monkeypatch.setattr(screens, "classify", scan.classified)
    strips = iter([screens.ROSTER_EXPANDED, screens.ROSTER_COLLAPSED])
    monkeypatch.setattr(screens, "read_roster_strip", lambda frame: next(strips))
    taps: list[tuple[int, int]] = []
    scan.device = SimpleNamespace(tap=lambda x, y, intent="": taps.append((x, y)))

    assert scan.ready_for_map_tap() is True
    assert taps == [screens.ROSTER_TOGGLE_TAP]


def test_the_return_button_is_never_tapped_on_the_plain_map(tmp_path, monkeypatch):
    """(1798,971) 在純地圖上是「單位列表」鈕——盲點它就是 run 20260806-141615 的死因。"""
    scan = build_scan(tmp_path, [screens.BATTLE_MAP, screens.BATTLE_MAP])
    monkeypatch.setattr(screens, "classify", scan.classified)
    taps: list[tuple[int, int]] = []
    scan.device = SimpleNamespace(tap=lambda x, y, intent="": taps.append((x, y)))

    assert scan.leave_action_mode() is True
    assert taps == []


def test_an_unreadable_clean_frame_keeps_the_grid_from_the_move_mode_frame(tmp_path, monkeypatch):
    """我方那一叢圖示很密，乾淨幀常常 seed spacing implausible；鏡頭沒動就沿用擬合那張
    的格網，不要把已經到手的格丟掉。"""
    scan = build_scan(tmp_path, [screens.BATTLE_UNIT_MOVE, screens.BATTLE_MAP])
    monkeypatch.setattr(screens, "classify", scan.classified)
    scan.device = SimpleNamespace(tap=lambda x, y, intent="": None)
    monkeypatch.setattr(scan, "steady", lambda *a, **k: np.zeros((4, 4, 3), np.uint8))
    monkeypatch.setattr(scan, "range_cell", lambda key, moving: (4, 3))
    views = iter([_view(), None])
    monkeypatch.setattr(scan, "view", lambda frame: next(views))

    view, target = scan.land_ally(("ally", 0), np.zeros((4, 4, 3), np.uint8), "jump")

    assert target == (4, 3)
    assert view is not None and view.grid is GRID
    assert "grid_reused" in _kinds(scan)
