"""進戰鬥檢查閘門：AUTO 主動確認、格線地面真相、入圖複核、陷阱防呆。"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

import cv2

from ggge_ai.runtime import entry, screens
from ggge_ai.runtime.device import DANGER_BANDS, TapRefused, check_tap
from tests.fixtures.frames import load, path_of

MAP_GRID_ON = "grid/hub_grid_on_20260719"
MAP_GRIDLESS = "grid/hub_gridless_20260719"
STAGE_INFO_AUTO_ON = "stage_panels/stage_info_conditions"
MAP_AUTO_OFF = "stage_panels/battle_map_turn1_r2"
MAP_AUTO_ACTIVE = "stage_panels/battle_map_turn1"
PREP = "stage_panels/prep_screen"
SETTINGS_GRID_ON = "settings/grid_on_20260706"
STAGE_LIST = "popups/stage_list_dim_20260719"
STAGE_LIST_HARD_1 = "popups/stage_list_uc_hard_1_20260805"
STAGE_LIST_HARD_2 = "popups/stage_list_uc_hard_2_20260805"
DOWNLOAD_DIALOG = "popups/download_dialog_20260805"
ABANDON_CONFIRM = "popups/abandon_confirm_20260804"
BATTLE_MENU = "popups/battle_menu_20260804"


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


def test_the_settings_probe_is_advisory_and_never_fails_the_gate():
    """0730 兩輪滑塊讀成未驗證、地圖格線複驗皆過（疑截圖早於 UI 動畫）：
    探針只留紀錄，判準單獨歸地圖像素。"""
    screen = Screen([load(MAP_GRIDLESS), blank(), load(MAP_GRID_ON)])
    report = entry.GateReport()

    step = entry.confirm_grid(screen.capture, screen.tap, report, attempts=2, sleep=lambda _: None)

    advisory = [line for line in report.steps if line.gate == "grid_setting"]
    assert [line.outcome for line in advisory] == [entry.ADVISORY]
    assert all(line.ok for line in advisory)  # advisory 不擋流程
    assert entry.GRID_PROBE_GUARDED in advisory[0].detail  # 空白幀讀不到分頁＝不亂翻
    assert step.ok and report.ok


def test_the_settings_probe_never_touches_a_toggle_it_cannot_confirm():
    screen = Screen([blank()])

    probe = entry.set_battle_grid(screen.capture, screen.tap, True, sleep=lambda _: None)

    assert probe.outcome == entry.GRID_PROBE_GUARDED
    assert screens.GRID_TOGGLE_TAP not in screen.points()


def test_the_settings_probe_reports_a_slider_already_where_it_should_be():
    screen = Screen([load(SETTINGS_GRID_ON)])

    probe = entry.set_battle_grid(screen.capture, screen.tap, True, sleep=lambda _: None)

    assert probe.outcome == entry.GRID_PROBE_ALREADY
    assert probe.before == probe.after == "on"
    assert screens.GRID_TOGGLE_TAP not in screen.points()


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


@dataclass
class FakeClock:
    """假時鐘：sleep 只推進時間，不真的睡。"""

    t: float = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def test_expect_screen_keeps_polling_until_the_wall_clock_floor():
    """attempts 的時間窗靠 adb 每張 ~2.4s 撐著；串流幀源 11ms 會塌縮，所以等轉場
    要看壁鐘（0808 實機：出擊→關卡資訊頁 ~15s 運鏡）。"""
    clock = FakeClock()
    frames = [blank()] * 12 + [load(STAGE_INFO_AUTO_ON)]
    screen = Screen(frames)

    name, _ = entry.expect_screen(
        screen.capture,
        (screens.STAGE_INFO,),
        attempts=3,
        sleep=clock.sleep,
        settle_s=1.0,
        min_wait_s=30.0,
        now=clock.now,
    )

    assert name == screens.STAGE_INFO
    assert screen.looks == 13


def test_expect_screen_gives_up_when_the_wall_clock_floor_is_reached():
    clock = FakeClock()
    screen = Screen([blank()])

    name, _ = entry.expect_screen(
        screen.capture,
        (screens.STAGE_INFO,),
        attempts=3,
        sleep=clock.sleep,
        settle_s=1.0,
        min_wait_s=10.0,
        now=clock.now,
    )

    assert name == screens.UNKNOWN
    assert clock.t >= 10.0
    assert screen.looks == 11


def test_expect_screen_without_a_floor_stops_at_the_attempt_count():
    clock = FakeClock()
    screen = Screen([blank()])

    name, _ = entry.expect_screen(
        screen.capture, (screens.STAGE_INFO,), attempts=3, sleep=clock.sleep, now=clock.now
    )

    assert name == screens.UNKNOWN
    assert screen.looks == 3
    assert clock.t == 2.0


def test_selecting_a_stage_taps_nothing_when_no_node_is_supplied():
    """哪一關的節點落在哪個像素是關卡內容（還隨節點軸捲動位置變），runtime 不猜。"""
    screen = Screen([load(STAGE_LIST)])

    report = entry.select_stage(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.ok, report.trail
    assert report.trail == ("stage_list:ok",)
    assert screen.taps == []


def test_selecting_a_stage_taps_the_node_the_caller_supplied():
    screen = Screen([load(STAGE_LIST), load(STAGE_LIST)])

    report = entry.select_stage(
        screen.capture, screen.tap, node=(544, 667), expect_title=None, sleep=lambda _: None
    )

    assert report.ok, report.trail
    assert screen.points() == [(544, 667)]
    assert "stage_node:ok" in report.trail


def test_a_stage_node_inside_the_abandon_band_is_refused_not_quietly_tapped():
    """關卡列表的節點平台落在 y≈872，正好撞上戰鬥選單「放棄」的危險帶——裝置層看
    不到畫面名，所以整帶一律拒點。節點要改點編號／星列那一列（y 較高）。"""
    screen = Screen([load(STAGE_LIST)])

    with pytest.raises(TapRefused):
        entry.select_stage(
            screen.capture, screen.tap, node=(544, 872), expect_title=None, sleep=lambda _: None
        )


def test_selecting_a_stage_refuses_to_tap_when_we_are_not_on_the_list():
    screen = Screen([blank()])

    report = entry.select_stage(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.trail == ("stage_list:not_on_page",)
    assert screen.taps == []


def test_the_prep_page_step_reaches_the_prep_screen_without_spending_anything():
    screen = Screen([load(STAGE_LIST), load(PREP)])

    report = entry.open_sortie_prep(
        screen.capture, screen.tap, entry.GateReport(), sleep=lambda _: None
    )

    assert report.ok, report.trail
    assert report.trail == ("sortie_prep_page:ok",)
    assert screen.points() == [entry.STAGE_LIST_PREP_TAP]


def test_the_prep_page_is_not_claimed_when_the_tap_did_not_land():
    screen = Screen([load(STAGE_LIST), blank()])

    report = entry.open_sortie_prep(
        screen.capture, screen.tap, entry.GateReport(), sleep=lambda _: None
    )

    assert not report.ok
    assert "sortie_prep_page:not_reached" in report.trail


def test_the_sortie_step_stops_on_the_stage_info_page_without_advancing():
    """分段停點：出擊＋AUTO 閘門過了，TAP TO NEXT 還沒點——乾跑要在這裡停得住。"""
    screen = Screen([load(PREP), stage_info_with_auto("off")])

    report = entry.sortie(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.ok, report.trail
    assert report.trail == ("sortie_prep:ok", "stage_info:ok", "auto_off:ok")
    assert screen.points() == [entry.SORTIE_TAP]


def sortie_script() -> Screen:
    """AUTO 從 ON 關成 OFF 之後還會被重新確認一次所在頁（推進前的複核），所以
    OFF 態的關卡資訊頁在腳本裡出現兩次。出擊那一下之後另有一幀是下載彈窗探針吃掉
    的（彈窗不在場）。"""
    return Screen(
        [
            load(PREP),
            stage_info_with_auto("on"),
            stage_info_with_auto("on"),
            stage_info_with_auto("on"),
            stage_info_with_auto("off"),
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
    """自動編制 (1496,1010) 在出擊準備下緣按鈕列；誤點會覆蓋排好的編成。"""
    band = next(b for b in DANGER_BANDS if b.name == "auto_deploy")
    screen = sortie_script()

    entry.enter_stage(screen.capture, screen.tap, sleep=lambda _: None)

    for x, y in screen.points():
        assert not band.contains(x, y), (x, y)


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
    screen = Screen([load(MAP_AUTO_OFF), load(ABANDON_CONFIRM), load(STAGE_LIST)])
    seen: list[tuple[str, tuple[int, int]]] = []

    report = entry.abandon_battle(
        screen.capture, screen.tap, sleep=lambda _: None, on_tap=lambda *row: seen.append(row)
    )

    assert report.ok
    assert screen.points() == [
        entry.BATTLE_MENU_TAP,
        entry.BATTLE_MENU_ABANDON_TAP,
        entry.ABANDON_CONFIRM_TAP,
    ]
    assert screen.taps[1][2] == "abandon"
    assert [label for label, _ in seen] == ["menu", "abandon", "confirm"]


def test_the_confirm_tap_shares_its_row_with_the_battle_menu_help_button():
    """確認鈕與「幫助」同列（0719 標定 幫助 1327／設定 1604／使命 1887，鈕距 277-283）。
    彈窗沒出來時這一下就落在幫助的鈕格內——所以棄戰不准盲點盲報。"""
    x, y = entry.ABANDON_CONFIRM_TAP
    half = (1604 - 1327) / 2

    assert y == 865
    assert 1327 - half < x < 1327 + half


def test_an_abandon_that_never_reaches_the_stage_list_closes_the_panel_and_says_so():
    screen = Screen([load(MAP_AUTO_OFF)])

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert not report.ok
    assert report.trail[-1] == "abandon:unconfirmed"
    # 每一輪收尾都關掉手上停著的面板（誤點開的幫助頁與戰鬥選單關閉鈕同位）
    assert screen.points().count(entry.BATTLE_MENU_CLOSE_TAP) == 2
    # 彈窗從沒出現過，確認鈕一次都不准按——那一下會落在「幫助」的鈕格裡
    assert screen.points().count(entry.ABANDON_CONFIRM_TAP) == 0


def test_the_confirm_tap_waits_for_the_dialog_instead_of_firing_into_the_battle_menu():
    screen = Screen([load(MAP_AUTO_OFF), load(BATTLE_MENU), load(ABANDON_CONFIRM), load(STAGE_LIST)])

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.ok
    assert screen.points().count(entry.ABANDON_CONFIRM_TAP) == 1


def test_the_settle_check_polls_through_the_transition_instead_of_judging_once():
    """0804：最後一下之後 3.3 秒就判畫面，轉場中讀成 unknown 而誤報失敗。"""
    frames = [load(MAP_AUTO_OFF), load(ABANDON_CONFIRM)]
    frames += [blank()] * 4 + [load(STAGE_LIST)]
    screen = Screen(frames)

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.ok
    assert entry.ABANDON_SETTLE_ATTEMPTS * entry.ABANDON_SETTLE_INTERVAL_S >= 15.0


def test_the_abandon_flow_refuses_when_we_are_not_on_the_map():
    screen = Screen([blank()])

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert not report.ok
    assert screen.taps == []


STAGE_TYPE_SELECT = "popups/stage_type_select_20260805"


def _screen_of(signature_screen: str) -> np.ndarray:
    """把該畫面的簽名模板貼回它的搜尋區——回程路上兩張中繼畫面沒有實幀樣本，
    測的是接線與座標，不是視覺門檻（門檻由模板本身固定）。"""
    signature = next(sig for sig in screens.SIGNATURES if sig.screen == signature_screen)
    template = cv2.imread(str(screens.TEMPLATE_ROOT / signature.template))
    frame = blank()
    x, y, _, _ = signature.region
    frame[y : y + template.shape[0], x : x + template.shape[1]] = template
    return frame


def test_an_abandon_that_lands_on_the_mode_page_navigates_back_to_the_stage_list():
    """0805 兩輪：棄戰成功但落在關卡模式選擇頁，收尾驗收報 unconfirmed。"""
    screen = Screen(
        [
            load(MAP_AUTO_OFF),
            load(ABANDON_CONFIRM),
            load(STAGE_TYPE_SELECT),
            _screen_of(screens.SERIES_SELECT),
            _screen_of(screens.SERIES_CONFIRM),
            load(STAGE_LIST),
        ]
    )

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert report.ok, report.trail
    assert screen.points()[-3:] == [
        entry.MAIN_STAGE_TAP,
        entry.SERIES_FOCUSED_TAP,
        entry.SERIES_SELECT_TAP,
    ]


def test_a_navigation_that_stalls_stops_instead_of_tapping_on_blind():
    screen = Screen(
        [load(MAP_AUTO_OFF), load(ABANDON_CONFIRM), load(STAGE_TYPE_SELECT), blank()]
    )

    report = entry.abandon_battle(screen.capture, screen.tap, sleep=lambda _: None)

    assert not report.ok
    assert report.trail[-1] == "abandon:unconfirmed"
    assert screen.points()[-1] == entry.MAIN_STAGE_TAP
    assert entry.BATTLE_MENU_CLOSE_TAP not in screen.points()


TITLE_BOX = (1400, 100, 720, 100)


def stage_list_showing(case: str) -> np.ndarray:
    """關卡列表 + 指定關卡的右欄標題。0805 的標題樣本是右欄裁片，貼回既有的列表
    整幀才同時滿足「畫面名＝關卡列表」與「標題讀得出來」兩件事。"""
    frame = load(STAGE_LIST).copy()
    x, y, w, h = TITLE_BOX
    frame[y : y + h, x : x + w] = load(case)[y : y + h, x : x + w]
    return frame


def test_the_right_panel_title_names_the_stage_that_is_actually_selected():
    """整條標題的模板在 STAGE 1／STAGE 2 之間 raw 1.000 對 0.996 分不開；尾碼
    數字單獨比才有 0.982 對 0.399（0805 實幀量測）。"""
    assert screens.read_stage_title(load(STAGE_LIST_HARD_1)) == "uc_hard_1"
    assert screens.read_stage_title(load(STAGE_LIST_HARD_2)) == "uc_hard_2"


def test_an_unreadable_title_is_never_guessed_into_a_stage():
    assert screens.read_stage_title(blank()) is None
    assert screens.read_stage_title(load(MAP_GRID_ON)) is None


def test_selecting_a_stage_confirms_the_title_before_moving_on():
    titled = stage_list_showing(STAGE_LIST_HARD_1)
    screen = Screen([load(STAGE_LIST), titled])

    report = entry.select_stage(
        screen.capture, screen.tap, node=(544, 667), sleep=lambda _: None
    )

    assert report.ok, report.trail
    assert report.trail == ("stage_list:ok", "stage_title:ok", "stage_node:ok")
    assert screen.points() == [(544, 667)]


def test_a_drifted_cursor_gets_one_retry_then_halts_instead_of_fighting_hard_2():
    """0805 第 13 輪：(544,667) 因游標飄移實際選中 HARD 2，整輪打錯關。"""
    wrong = stage_list_showing(STAGE_LIST_HARD_2)
    screen = Screen([load(STAGE_LIST), wrong])

    report = entry.select_stage(
        screen.capture, screen.tap, node=(544, 667), sleep=lambda _: None
    )

    assert not report.ok
    assert "stage_title:wrong_stage" in report.trail
    assert "stage_node:ok" not in report.trail
    assert screen.points() == [(544, 667), (544, 667)]


def test_a_title_that_comes_right_on_the_second_tap_is_accepted():
    screen = Screen(
        [
            load(STAGE_LIST),
            stage_list_showing(STAGE_LIST_HARD_2),
            stage_list_showing(STAGE_LIST_HARD_2),
            stage_list_showing(STAGE_LIST_HARD_2),
            stage_list_showing(STAGE_LIST_HARD_1),
            stage_list_showing(STAGE_LIST_HARD_1),
        ]
    )

    report = entry.select_stage(
        screen.capture, screen.tap, node=(544, 667), sleep=lambda _: None
    )

    assert report.ok, report.trail
    assert screen.points() == [(544, 667), (544, 667)]


def test_the_download_dialog_is_recognised_and_nothing_else_is():
    assert screens.is_download_dialog(load(DOWNLOAD_DIALOG))
    for other in (blank(), load(PREP), load(STAGE_LIST), load(ABANDON_CONFIRM)):
        assert not screens.is_download_dialog(other)


def test_the_download_dialog_is_confirmed_and_waited_out():
    screen = Screen([load(DOWNLOAD_DIALOG), load(DOWNLOAD_DIALOG), load(PREP)])
    report = entry.GateReport()

    step = entry.clear_download_dialog(
        screen.capture, screen.tap, report, sleep=lambda _: None, now=lambda: 0.0
    )

    assert step is not None and step.ok
    assert screen.points() == [screens.DOWNLOAD_CONFIRM_TAP]


def test_no_download_dialog_means_not_a_single_tap():
    """(1372,848) 在出擊準備頁上是別的東西——彈窗不在場就完全不點。"""
    screen = Screen([load(PREP)])
    report = entry.GateReport()

    step = entry.clear_download_dialog(
        screen.capture, screen.tap, report, sleep=lambda _: None, now=lambda: 0.0
    )

    assert step is None
    assert screen.taps == []
    assert report.steps == []


def test_a_download_that_never_finishes_is_reported_not_ignored():
    clock = iter([0.0, 0.0, 10.0, 99.0])
    screen = Screen([load(DOWNLOAD_DIALOG)])
    report = entry.GateReport()

    step = entry.clear_download_dialog(
        screen.capture, screen.tap, report, wait_s=60.0, sleep=lambda _: None, now=lambda: next(clock)
    )

    assert step is not None and not step.ok
    assert step.outcome == "stuck"
