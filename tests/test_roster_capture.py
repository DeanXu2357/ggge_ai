"""名冊採集：走訪順序、列表盡頭、哨兵重拍、危險帶白名單、例外圍堵。

全部打樁——假幀是 4x4 的黑圖，畫面名與面板種類由假遊戲的狀態機回答，所以這裡驗的是
走位與落帳紀律，不是視覺。假遊戲的每一下 tap 都真的過一次 `device.check_tap`：採集
流程踩到危險帶要在離線就爆，不能等上機。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest

from ggge_ai.runtime import device, panels, roster_capture, screens
from ggge_ai.runtime.journal import Journal
from ggge_ai.runtime.panels import PanelKind

ALLY = roster_capture.ALLY
ENEMY = roster_capture.ENEMY
TAB_KINDS = (PanelKind.STAGE_COMBO, PanelKind.STAGE_WEAPONS, PanelKind.STAGE_ABILITIES)
PAGES_PER_UNIT = 1 + len(roster_capture.DETAIL_TAB_PAGES)


@dataclass
class FakeGame:
    """部隊資訊面板的狀態機：戰場→戰鬥選單→部隊資訊→詳情各分頁。

    `view`／`tab` 是實機的全域視圖記憶：詳情關掉再開，落回的是上一台看到最後的視圖
    與分頁，跨單位跨陣營共享。
    """

    ally: int = 10
    enemy: int = 18
    screen: str = screens.BATTLE_MAP
    panel: PanelKind = PanelKind.UNKNOWN
    view: PanelKind = PanelKind.STAGE_BASIC
    tab: PanelKind = PanelKind.STAGE_COMBO
    faction: str = ALLY
    now: float = 0.0
    open_delay: float = 0.0
    pending_open_at: float | None = None
    reveal_screen: str | None = None
    reveal_at: float = 0.0
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    swipes: list[tuple[int, int, int, int, float]] = field(default_factory=list)
    slept: list[float] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    def grab(self) -> np.ndarray:
        if self.pending_open_at is not None and self.now >= self.pending_open_at:
            self.screen, self.panel = screens.UNIT_DETAIL, self.view
            self.pending_open_at = None
        if self.reveal_screen is not None and self.now >= self.reveal_at:
            self.screen, self.reveal_screen = self.reveal_screen, None
        return np.zeros((4, 4, 3), np.uint8)

    def keep(self, label: str) -> str:
        self.kept.append(label)
        return f"frames/{len(self.kept):05d}.png"

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        self.swipes.append((x1, y1, x2, y2, duration))

    def clock(self) -> float:
        return self.now

    def screen_of(self, frame: np.ndarray) -> str:
        return self.screen

    def panel_of(self, frame: np.ndarray) -> PanelKind:
        return self.panel

    def units(self, faction: str) -> int:
        return self.ally if faction == ALLY else self.enemy

    def tap(self, x: int, y: int, intent: str = "") -> None:
        device.check_tap(x, y, intent)
        self.taps.append((x, y, intent))
        point = (x, y)
        cells = roster_capture.cell_taps(self.faction)
        if point == roster_capture.BATTLE_MENU_TAP and self.screen in screens.MAP_SCREENS:
            self.screen = screens.BATTLE_MENU
        elif point == roster_capture.BATTLE_MENU_TROOP_INFO_TAP:
            if self.screen == screens.BATTLE_MENU:
                self.screen = screens.TROOP_INFO
        elif point in roster_capture.TAB_TAPS.values():
            self.faction = ALLY if point == roster_capture.TAB_TAPS[ALLY] else ENEMY
        elif point in cells and self.screen == screens.TROOP_INFO:
            if cells.index(point) < self.units(self.faction):
                self.pending_open_at = self.now + self.open_delay
        elif point in roster_capture.DETAIL_TAB_TAPS and self.panel is not PanelKind.UNKNOWN:
            self.tab = TAB_KINDS[roster_capture.DETAIL_TAB_TAPS.index(point)]
            self.panel = self.view = self.tab
        elif point == roster_capture.BASIC_VIEW_TAP and self.panel is not PanelKind.UNKNOWN:
            self.panel = self.tab if self.panel in panels.BASIC_KINDS else PanelKind.STAGE_BASIC
            self.view = self.panel
        elif point == roster_capture.DETAIL_CLOSE_TAP and self.panel is not PanelKind.UNKNOWN:
            self.screen, self.panel = screens.TROOP_INFO, PanelKind.UNKNOWN
        elif point == roster_capture.TROOP_INFO_CLOSE_TAP:
            if self.screen == screens.TROOP_INFO:
                self.screen = screens.BATTLE_MENU
            elif self.screen == screens.BATTLE_MENU:
                self.screen = screens.BATTLE_MAP


def _capture(game: FakeGame, tmp_path, *, swipe=None) -> roster_capture.RosterCapture:
    return roster_capture.RosterCapture(
        grab=game.grab,
        keep=game.keep,
        tap=game.tap,
        journal=Journal(tmp_path / "roster.jsonl"),
        swipe=swipe,
        sleep=game.sleep,
        clock=game.clock,
        screen_of=game.screen_of,
        panel_of=game.panel_of,
    )


def _sentinels_pass(monkeypatch, *, basic=None, tabs=None) -> None:
    """哨兵讀的是真幀，假幀一律讀不出值——這裡把它們換成受測案例要的答案。"""
    monkeypatch.setattr(roster_capture, "_basic_ok", basic or (lambda frame, kind: True))
    monkeypatch.setattr(roster_capture, "_weapons_ok", lambda frame, kind: True)
    monkeypatch.setattr(
        roster_capture,
        "DETAIL_TAB_SENTINELS",
        tabs or tuple(lambda frame, kind: True for _ in TAB_KINDS),
    )


def _view_taps(game: FakeGame) -> list[tuple[int, int, str]]:
    return [tap for tap in game.taps if tap[:2] == roster_capture.BASIC_VIEW_TAP]


def _kinds(entries: list[dict], kind: str) -> list[dict]:
    return [entry for entry in entries if entry["kind"] == kind]


def test_a_full_walk_covers_every_cell_of_both_factions(tmp_path, monkeypatch):
    _sentinels_pass(monkeypatch)
    game = FakeGame()
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(shots) == (game.ally + game.enemy) * PAGES_PER_UNIT
    assert all(shot.ok for shot in shots)
    assert [shot.faction for shot in shots[:PAGES_PER_UNIT]] == [ALLY] * PAGES_PER_UNIT
    assert [shot.page for shot in shots[:PAGES_PER_UNIT]] == [
        roster_capture.PAGE_BASIC,
        *roster_capture.DETAIL_TAB_PAGES,
    ]
    assert [shot.index for shot in shots[:: PAGES_PER_UNIT]] == (
        list(range(game.ally)) + list(range(game.enemy))
    )
    assert shots[-1].faction == ENEMY and shots[-1].index == game.enemy - 1
    assert all(shot.frame is not None for shot in shots)

    entries = capture.journal.entries()
    assert len(_kinds(entries, "roster_capture")) == len(shots)
    assert [entry["count"] for entry in _kinds(entries, "roster_list_end")] == [
        game.ally,
        game.enemy,
    ]
    summary = _kinds(entries, "roster_capture_summary")[0]
    assert (summary["shots"], summary["ok"], summary["failed"]) == (len(shots), len(shots), 0)
    first = _kinds(entries, "roster_capture")[0]
    assert first["faction"] == ALLY
    assert first["index"] == 0
    assert first["page"] == roster_capture.PAGE_BASIC
    assert first["panel_kind"] == PanelKind.STAGE_BASIC
    assert first["ok"] is True
    assert first["reason"] is None
    assert game.screen in screens.MAP_SCREENS
    assert game.taps[-2:] == [
        (*roster_capture.TROOP_INFO_CLOSE_TAP, ""),
        (*roster_capture.BATTLE_MENU_CLOSE_TAP, ""),
    ]


def test_the_end_of_the_enemy_list_stops_the_scan_without_a_shot(tmp_path, monkeypatch):
    """敵軍四列二十格，末列不滿：第 19 格點下去畫面不動，那一格之後不再掃。"""
    _sentinels_pass(monkeypatch)
    game = FakeGame(ally=10, enemy=18)
    capture = _capture(game, tmp_path)

    shots = capture.run()

    enemy = [shot for shot in shots if shot.faction == ENEMY]
    assert max(shot.index for shot in enemy) == 17
    entries = capture.journal.entries()
    edge = _kinds(entries, "roster_list_edge")
    assert [(entry["faction"], entry["index"]) for entry in edge] == [(ENEMY, 18)]
    assert (19, "") not in [(x, intent) for x, _, intent in game.taps]


def test_open_detail_waits_out_the_open_animation_before_deciding(tmp_path):
    """開詳情動畫 ~2.5s，畫面在閾值內轉出詳情：判 True，不誤記盡頭。"""
    game = FakeGame(ally=1, enemy=0, screen=screens.TROOP_INFO, open_delay=2.5)
    capture = _capture(game, tmp_path)

    assert capture.open_detail(ALLY, 0) is True
    assert game.now >= 2.5
    assert _kinds(capture.journal.entries(), "roster_list_edge") == []


def test_open_detail_calls_the_empty_last_cell_a_list_edge(tmp_path):
    """末列空格：點下去畫面全程 troop_info，熬滿 DETAIL_OPEN_WAIT_S 才判盡頭。"""
    game = FakeGame(ally=1, enemy=0, screen=screens.TROOP_INFO)
    capture = _capture(game, tmp_path)

    assert capture.open_detail(ALLY, 1) is False
    assert game.now >= roster_capture.DETAIL_OPEN_WAIT_S
    edge = _kinds(capture.journal.entries(), "roster_list_edge")
    assert [(entry["faction"], entry["index"]) for entry in edge] == [(ALLY, 1)]


def test_open_detail_that_opens_past_the_threshold_is_missed(tmp_path):
    """閾值上界：開啟動畫超過 DETAIL_OPEN_WAIT_S 才轉出，會被判成盡頭。"""
    game = FakeGame(
        ally=1,
        enemy=0,
        screen=screens.TROOP_INFO,
        open_delay=roster_capture.DETAIL_OPEN_WAIT_S + 1.0,
    )
    capture = _capture(game, tmp_path)

    assert capture.open_detail(ALLY, 0) is False
    edge = _kinds(capture.journal.entries(), "roster_list_edge")
    assert [(entry["faction"], entry["index"]) for entry in edge] == [(ALLY, 0)]


def test_a_delayed_full_walk_still_covers_every_cell_and_ends_on_an_edge(tmp_path, monkeypatch):
    """詳情延遲開啟（~2.5s）下仍採滿兩陣營，敵軍末列空格熬滿閾值判盡頭。"""
    _sentinels_pass(monkeypatch)
    game = FakeGame(ally=10, enemy=18, open_delay=2.5)
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(shots) == (game.ally + game.enemy) * PAGES_PER_UNIT
    assert all(shot.ok for shot in shots)
    entries = capture.journal.entries()
    assert [entry["count"] for entry in _kinds(entries, "roster_list_end")] == [
        game.ally,
        game.enemy,
    ]
    edge = _kinds(entries, "roster_list_edge")
    assert [(entry["faction"], entry["index"]) for entry in edge] == [(ENEMY, 18)]
    assert game.screen in screens.MAP_SCREENS


def test_close_to_map_heals_from_a_residual_detail_page(tmp_path):
    """非預期殘留：起點是半開詳情，仍逐層 detail→troop_info→battle_menu→map 收回。"""
    game = FakeGame(
        screen=screens.UNIT_DETAIL, panel=PanelKind.STAGE_BASIC, view=PanelKind.STAGE_BASIC
    )
    capture = _capture(game, tmp_path)

    assert capture.close_to_map() is True
    assert game.screen in screens.MAP_SCREENS
    assert [tap[:2] for tap in game.taps] == [
        roster_capture.DETAIL_CLOSE_TAP,
        roster_capture.TROOP_INFO_CLOSE_TAP,
        roster_capture.BATTLE_MENU_CLOSE_TAP,
    ]
    closed = _kinds(capture.journal.entries(), "roster_closed")[-1]
    assert closed["ok"] is True


def test_close_to_map_from_a_clean_troop_info_start(tmp_path):
    """正常收尾：末格採完乾淨回 troop_info，兩層關回地圖。"""
    game = FakeGame(screen=screens.TROOP_INFO)
    capture = _capture(game, tmp_path)

    assert capture.close_to_map() is True
    assert game.screen in screens.MAP_SCREENS
    assert [tap[:2] for tap in game.taps] == [
        roster_capture.TROOP_INFO_CLOSE_TAP,
        roster_capture.BATTLE_MENU_CLOSE_TAP,
    ]


def test_close_to_map_waits_out_an_unrecognized_screen_instead_of_blind_tapping(tmp_path):
    """認不出畫面（開啟動畫中）不盲點：先等一小段，畫面現形成 troop_info 再照層關。"""
    game = FakeGame(
        screen=screens.UNKNOWN,
        reveal_screen=screens.TROOP_INFO,
        reveal_at=roster_capture.PANEL_POLL_S,
    )
    capture = _capture(game, tmp_path)

    assert capture.close_to_map() is True
    assert game.screen in screens.MAP_SCREENS
    assert game.taps[0][:2] == roster_capture.TROOP_INFO_CLOSE_TAP


def test_a_detail_that_opens_on_the_basic_view_only_switches_once(tmp_path, monkeypatch):
    """開場就在基本資訊：拍完基本資訊切一次進詳情，不多繞一趟。"""
    _sentinels_pass(monkeypatch)
    game = FakeGame(ally=1, enemy=0, view=PanelKind.STAGE_BASIC)
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(_view_taps(game)) == 1
    assert shots[0].page == roster_capture.PAGE_BASIC
    assert shots[0].panel_kind == PanelKind.STAGE_BASIC
    assert all(shot.ok for shot in shots)


def test_a_detail_that_opens_on_a_remembered_tab_walks_back_to_the_basic_view(
    tmp_path, monkeypatch
):
    """視圖是全域記憶：開場落在詳情分頁，要先切回基本資訊拍完再切回詳情。"""
    _sentinels_pass(monkeypatch)
    game = FakeGame(
        ally=1, enemy=0, view=PanelKind.STAGE_WEAPONS, tab=PanelKind.STAGE_WEAPONS
    )
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(_view_taps(game)) == 2
    basic = [shot for shot in shots if shot.page == roster_capture.PAGE_BASIC]
    assert len(basic) == 1
    assert basic[0].panel_kind == PanelKind.STAGE_BASIC
    assert basic[0].ok is True
    assert basic[0].frame is not None
    assert [shot.page for shot in shots[1:]] == list(roster_capture.DETAIL_TAB_PAGES)
    assert all(shot.ok for shot in shots)


def test_the_second_unit_inherits_the_view_left_behind_by_the_first(tmp_path, monkeypatch):
    """跨單位共享記憶：第一台停在最後一個分頁，第二台就得走兩次切換那條路。"""
    _sentinels_pass(monkeypatch)
    game = FakeGame(ally=2, enemy=0)
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(_view_taps(game)) == 3
    assert [shot.panel_kind for shot in shots if shot.page == roster_capture.PAGE_BASIC] == [
        PanelKind.STAGE_BASIC,
        PanelKind.STAGE_BASIC,
    ]
    assert all(shot.ok for shot in shots)


def test_the_weapons_page_gets_a_slow_scroll_and_a_second_shot(tmp_path, monkeypatch):
    """武裝分頁捲一次再補一張：慢滑參數照 WEAPON_SCROLL 展開發出去。"""
    _sentinels_pass(monkeypatch)
    game = FakeGame(ally=1, enemy=0)
    capture = _capture(game, tmp_path, swipe=game.swipe)

    shots = capture.run()

    (start, end, duration) = roster_capture.WEAPON_SCROLL
    assert game.swipes == [(*start, *end, duration)]
    assert [shot.page for shot in shots] == [
        roster_capture.PAGE_BASIC,
        "stats0",
        roster_capture.PAGE_WEAPONS,
        roster_capture.PAGE_WEAPONS_MORE,
        roster_capture.PAGE_ABILITIES,
    ]
    more = shots[3]
    assert more.panel_kind == PanelKind.STAGE_WEAPONS
    assert (more.ok, more.frame is not None) == (True, True)


def test_a_capture_without_a_swipe_channel_skips_the_scrolled_page(tmp_path, monkeypatch):
    _sentinels_pass(monkeypatch)
    game = FakeGame(ally=1, enemy=0)

    shots = _capture(game, tmp_path).run()

    assert game.swipes == []
    assert roster_capture.PAGE_WEAPONS_MORE not in [shot.page for shot in shots]


def test_the_retry_between_shots_waits_out_the_bonus_flip(tmp_path, monkeypatch):
    """重拍間隔要跨得過左欄絕對值↔加成值的輪替，不能用面板輪詢的 0.3s。"""
    _sentinels_pass(monkeypatch, basic=lambda frame, kind: False)
    game = FakeGame(ally=1, enemy=0)
    capture = _capture(game, tmp_path)

    capture.run()

    retries = [seconds for seconds in game.slept if seconds == roster_capture.SHOT_RETRY_SLEEP_S]
    assert len(retries) == roster_capture.SHOT_RETRIES
    assert roster_capture.SHOT_RETRY_SLEEP_S > roster_capture.PANEL_POLL_S


def test_a_sentinel_that_comes_good_on_the_third_look_is_kept(tmp_path, monkeypatch):
    looks: list[int] = []

    def flaky(frame, kind):
        looks.append(kind)
        return len(looks) >= 3

    _sentinels_pass(monkeypatch, basic=flaky)
    game = FakeGame(ally=1, enemy=0)
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(looks) == 3
    assert shots[0].page == roster_capture.PAGE_BASIC
    assert shots[0].ok is True
    assert shots[0].reason is None


def test_a_sentinel_that_never_comes_good_is_logged_and_the_walk_goes_on(tmp_path, monkeypatch):
    looks: list[int] = []

    def never(frame, kind):
        looks.append(kind)
        return False

    _sentinels_pass(monkeypatch, basic=never)
    game = FakeGame(ally=1, enemy=0)
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(looks) == roster_capture.SHOT_RETRIES + 1
    assert (shots[0].ok, shots[0].reason) == (False, "sentinel")
    assert shots[0].frame is not None
    assert [shot.page for shot in shots[1:]] == list(roster_capture.DETAIL_TAB_PAGES)
    assert all(shot.ok for shot in shots[1:])
    summary = _kinds(capture.journal.entries(), "roster_capture_summary")[0]
    assert (summary["ok"], summary["failed"]) == (len(shots) - 1, 1)


@pytest.mark.parametrize("point", [(1564, 267), (1843, 267), (729, 847)])
def test_the_overlapping_cells_pass_only_with_the_roster_cell_intent(point):
    """名冊面板蓋著 AUTO戰鬥 三選一與棄戰鈕；那三格只有面板已開的流程點得到。"""
    assert point in roster_capture.cell_taps(ALLY) + roster_capture.cell_taps(ENEMY)

    device.check_tap(*point, intent=device.ROSTER_CELL_INTENT)
    with pytest.raises(device.TapRefused):
        device.check_tap(*point)
    with pytest.raises(device.TapRefused):
        device.check_tap(*point, intent="auto_switch")


def test_a_blow_up_mid_walk_is_contained_and_the_panels_still_get_closed(tmp_path, monkeypatch):
    _sentinels_pass(monkeypatch)
    original = roster_capture.RosterCapture.capture_unit

    def flaky(self, faction, index):
        if index == 2:
            raise RuntimeError("panel vanished")
        return original(self, faction, index)

    monkeypatch.setattr(roster_capture.RosterCapture, "capture_unit", flaky)
    game = FakeGame()
    capture = _capture(game, tmp_path)

    shots = capture.run()

    assert len(shots) == 2 * PAGES_PER_UNIT
    failure = _kinds(capture.journal.entries(), "roster_stage_failed")
    assert len(failure) == 1
    assert "panel vanished" in failure[0]["error"]
    assert capture.closed is True
    assert game.screen in screens.MAP_SCREENS


def test_the_cell_grid_matches_the_measured_pitch():
    ally, enemy = roster_capture.cell_taps(ALLY), roster_capture.cell_taps(ENEMY)

    assert len(ally) == roster_capture.ALLY_ROWS * roster_capture.CELLS_PER_ROW
    assert len(enemy) == roster_capture.ENEMY_ROWS * roster_capture.CELLS_PER_ROW
    assert ally[0] == (729, 267)
    assert ally[4] == (1843, 267)
    assert ally[5] == (729, 513)
    assert enemy[15] == (729, 847)
    assert roster_capture.DETAIL_TAB_TAPS == tuple(
        (x + w // 2, y + h // 2) for x, y, w, h in panels.TAB_BANDS
    )
