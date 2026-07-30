"""進戰鬥檢查閘門：AUTO 主動確認、格線地面真相、入圖複核、陷阱防呆。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

import cv2

from ggge_ai.runtime import entry, screens
from ggge_ai.runtime.device import check_tap
from tests.fixtures.frames import load, path_of

MAP_GRID_ON = "grid/hub_grid_on_20260719"
MAP_GRIDLESS = "grid/hub_gridless_20260719"
STAGE_INFO_AUTO_ON = "stage_panels/stage_info_conditions"
MAP_AUTO_OFF = "stage_panels/battle_map_turn1_r2"
MAP_AUTO_ACTIVE = "stage_panels/battle_map_turn1"
PREP = "stage_panels/prep_screen"
SETTINGS_GRID_ON = "settings/grid_on_20260706"


@dataclass
class Screen:
    """腳本化畫面序列。tap 只被記錄，畫面推進由腳本指定（下一幀就是下一格）。"""

    frames: list[np.ndarray]
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    looks: int = 0

    def capture(self) -> np.ndarray:
        frame = self.frames[min(self.looks, len(self.frames) - 1)]
        self.looks += 1
        return frame

    def tap(self, x: int, y: int, *, intent: str = "") -> None:
        check_tap(x, y, intent)
        self.taps.append((x, y, intent))

    def points(self) -> list[tuple[int, int]]:
        return [(x, y) for x, y, _ in self.taps]


def blank() -> np.ndarray:
    return np.zeros((1080, 2340, 3), np.uint8)


def stage_info_with_auto(state: str) -> np.ndarray:
    """關卡資訊頁 + 指定 AUTO 態。0730 只留下 AUTO=ON 的整幀樣本，OFF 態是
    另存的開關裁片，所以把裁片貼回原位合成——貼的是真實像素，合成只換那顆
    開關。"""
    frame = load(STAGE_INFO_AUTO_ON).copy()
    chip = cv2.imread(str(path_of(f"stage_panels/stage_info_auto_{state}")))
    x, y, w, h = screens.AUTO_SWITCH_REGION
    frame[y : y + h, x : x + w] = chip
    return frame


def test_an_auto_switch_already_off_is_never_tapped():
    """暗＝OFF 勿點：點下去反而會打開自動戰鬥（0730 定則）。"""
    screen = Screen([load(MAP_AUTO_OFF)])
    report = entry.GateReport()

    step = entry.confirm_auto_off(screen.capture, screen.tap, report, sleep=lambda _: None)

    assert step.ok
    assert screen.taps == []


def test_an_auto_switch_left_on_is_turned_off_and_reconfirmed():
    screen = Screen([load(STAGE_INFO_AUTO_ON), load(MAP_AUTO_OFF)])
    report = entry.GateReport()

    step = entry.confirm_auto_off(screen.capture, screen.tap, report, sleep=lambda _: None)

    assert step.ok
    assert screen.points() == [screens.AUTO_SWITCH_TAP]
    assert screen.taps[0][2] == "auto_switch"


def test_an_auto_switch_stuck_on_fails_the_gate_instead_of_continuing():
    screen = Screen([load(STAGE_INFO_AUTO_ON)])
    report = entry.GateReport()

    step = entry.confirm_auto_off(screen.capture, screen.tap, report, attempts=2, sleep=lambda _: None)

    assert not step.ok
    assert step.outcome == "stuck"
    assert not report.ok


def test_an_unreadable_auto_switch_is_not_assumed_off():
    screen = Screen([blank()])
    report = entry.GateReport()

    step = entry.confirm_auto_off(screen.capture, screen.tap, report, attempts=2, sleep=lambda _: None)

    assert step.outcome == "unreadable"
    assert screen.taps == []


def test_an_auto_battle_already_running_is_caught_as_a_failure():
    """AUTO 執行中（實心紅）是事故現場：閘門必須擋住，不能當成 ON 待機處理完
    就放行。"""
    screen = Screen([load(MAP_AUTO_ACTIVE), load(MAP_AUTO_ACTIVE)])
    report = entry.GateReport()

    step = entry.confirm_auto_off(screen.capture, screen.tap, report, attempts=2, sleep=lambda _: None)

    assert step.outcome == "stuck"
    assert screens.AUTO_ACTIVE in step.detail


def test_the_grid_gate_trusts_the_map_not_the_settings_slider():
    """地面真相＝地圖上讀不讀得出格網，順便證明選單沒被留著開。"""
    screen = Screen([load(MAP_GRID_ON)])
    report = entry.GateReport()

    step = entry.confirm_grid(screen.capture, screen.tap, report, sleep=lambda _: None)

    assert step.ok
    assert screen.taps == []


def test_a_gridless_map_drives_the_settings_flow():
    screen = Screen([load(MAP_GRIDLESS), load(SETTINGS_GRID_ON), load(MAP_GRID_ON)])
    report = entry.GateReport()

    step = entry.confirm_grid(screen.capture, screen.tap, report, attempts=2, sleep=lambda _: None)

    assert step.ok
    assert entry.BATTLE_MENU_TAP in screen.points()
    assert entry.BATTLE_MENU_SETTINGS_TAP in screen.points()
    # 顯示方格已經是 on，所以流程確認完就走，不去翻開關。
    assert screens.GRID_TOGGLE_TAP not in screen.points()


def test_the_grid_flow_never_touches_the_auto_battle_row():
    screen = Screen([load(MAP_GRIDLESS), load(SETTINGS_GRID_ON), load(MAP_GRIDLESS)])
    report = entry.GateReport()

    entry.confirm_grid(screen.capture, screen.tap, report, attempts=2, sleep=lambda _: None)

    assert all(not (245 <= y <= 345) for _, y in screen.points())


def test_the_grid_gate_reports_unverified_rather_than_pretending():
    screen = Screen([load(MAP_GRIDLESS)])
    report = entry.GateReport()

    step = entry.confirm_grid(screen.capture, screen.tap, report, attempts=1, sleep=lambda _: None)

    assert step.outcome == "unverified"


def test_the_in_map_recheck_wants_the_map_auto_off_and_a_lattice():
    screen = Screen([load(MAP_GRID_ON)])

    report = entry.confirm_in_map(screen.capture, screen.tap, entry.GateReport(), sleep=lambda _: None)

    assert report.ok
    assert report.trail == ("in_map:ok", "auto_recheck:ok", "grid:ok")


def test_the_in_map_recheck_fails_when_auto_is_running():
    screen = Screen([load(MAP_AUTO_ACTIVE)])

    report = entry.confirm_in_map(screen.capture, screen.tap, entry.GateReport(), sleep=lambda _: None)

    assert not report.ok
    assert "auto_recheck:unconfirmed" in report.trail


def test_expect_screen_recaptures_until_the_page_is_the_one_we_think_it_is():
    """解鎖的 wake-tap 可能誤觸 TAP TO NEXT 把人推進下一頁（0730 實測），所以
    每步操作前重新確認所在頁。"""
    screen = Screen([blank(), blank(), load(STAGE_INFO_AUTO_ON)])

    name, frame = entry.expect_screen(screen.capture, (screens.STAGE_INFO,), sleep=lambda _: None)

    assert name == screens.STAGE_INFO
    assert frame is not None
    assert screen.looks == 3


def test_expect_screen_gives_up_honestly():
    screen = Screen([blank()])

    name, _ = entry.expect_screen(
        screen.capture, (screens.STAGE_INFO,), attempts=2, sleep=lambda _: None
    )

    assert name == screens.UNKNOWN


def sortie_script() -> Screen:
    return Screen(
        [
            load(PREP),
            stage_info_with_auto("on"),
            stage_info_with_auto("on"),
            stage_info_with_auto("off"),
            load(MAP_GRID_ON),
            load(MAP_GRID_ON),
        ]
    )


def test_the_sortie_gate_walks_prep_to_stage_info_to_the_map():
    screen = sortie_script()

    report = entry.enter_stage(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.ok, report.trail
    assert report.trail == (
        "sortie_prep:ok",
        "stage_info:ok",
        "auto_off:ok",
        "in_map:ok",
        "auto_recheck:ok",
        "grid:ok",
    )
    assert screen.points() == [
        entry.SORTIE_TAP,
        screens.AUTO_SWITCH_TAP,
        entry.STAGE_INFO_ADVANCE_TAP,
    ]


def test_the_sortie_gate_never_taps_the_auto_deploy_button():
    """出擊 (1930,970) 與自動編制 (2001,924) 相鄰；誤點會改編成。"""
    screen = sortie_script()

    entry.enter_stage(screen.capture, screen.tap, sleep=lambda _: None)

    assert (2001, 924) not in screen.points()


def test_an_early_tap_to_next_skips_the_advance_instead_of_tapping_blind():
    screen = Screen([load(PREP), load(MAP_GRID_ON)])

    report = entry.enter_stage(screen.capture, screen.tap, sleep=lambda _: None)

    assert "stage_info:skipped" in report.trail
    assert entry.STAGE_INFO_ADVANCE_TAP not in screen.points()
    assert report.ok, report.trail


def test_a_stuck_auto_switch_stops_the_sortie_before_the_map():
    screen = Screen([load(PREP), load(STAGE_INFO_AUTO_ON)])

    report = entry.enter_stage(screen.capture, screen.tap, sleep=lambda _: None)

    assert not report.ok
    assert entry.STAGE_INFO_ADVANCE_TAP not in screen.points()


def test_the_sortie_gate_refuses_to_start_off_the_prep_page():
    screen = Screen([blank()])

    report = entry.enter_stage(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.trail == ("sortie_prep:not_on_page",)
    assert screen.taps == []


def test_the_abandon_flow_is_the_only_thing_allowed_in_the_abandon_band():
    screen = Screen([load(MAP_AUTO_OFF)])

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.ok
    assert screen.points() == [
        entry.BATTLE_MENU_TAP,
        entry.BATTLE_MENU_ABANDON_TAP,
        entry.ABANDON_CONFIRM_TAP,
    ]
    assert screen.taps[1][2] == "abandon"


def test_the_abandon_flow_refuses_when_we_are_not_on_the_map():
    screen = Screen([blank()])

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert not report.ok
    assert screen.taps == []
