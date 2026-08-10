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
    """部隊資訊面板的狀態機：戰場→戰鬥選單→部隊資訊→詳情各分頁。"""

    ally: int = 10
    enemy: int = 18
    screen: str = screens.BATTLE_MAP
    panel: PanelKind = PanelKind.UNKNOWN
    faction: str = ALLY
    now: float = 0.0
    taps: list[tuple[int, int, str]] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    def grab(self) -> np.ndarray:
        return np.zeros((4, 4, 3), np.uint8)

    def keep(self, label: str) -> str:
        self.kept.append(label)
        return f"frames/{len(self.kept):05d}.png"

    def sleep(self, seconds: float) -> None:
        self.now += seconds

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
                self.screen, self.panel = screens.UNIT_DETAIL, PanelKind.STAGE_BASIC
        elif point in roster_capture.DETAIL_TAB_TAPS and self.panel is not PanelKind.UNKNOWN:
            self.panel = TAB_KINDS[roster_capture.DETAIL_TAB_TAPS.index(point)]
        elif point == roster_capture.DETAIL_CLOSE_TAP and self.panel is not PanelKind.UNKNOWN:
            self.screen, self.panel = screens.TROOP_INFO, PanelKind.UNKNOWN
        elif point == roster_capture.TROOP_INFO_CLOSE_TAP:
            if self.screen == screens.TROOP_INFO:
                self.screen = screens.BATTLE_MENU
            elif self.screen == screens.BATTLE_MENU:
                self.screen = screens.BATTLE_MAP


def _capture(game: FakeGame, tmp_path) -> roster_capture.RosterCapture:
    return roster_capture.RosterCapture(
        grab=game.grab,
        keep=game.keep,
        tap=game.tap,
        journal=Journal(tmp_path / "roster.jsonl"),
        sleep=game.sleep,
        clock=game.clock,
        screen_of=game.screen_of,
        panel_of=game.panel_of,
    )


def _sentinels_pass(monkeypatch, *, basic=None, tabs=None) -> None:
    """哨兵讀的是真幀，假幀一律讀不出值——這裡把它們換成受測案例要的答案。"""
    monkeypatch.setattr(roster_capture, "_basic_ok", basic or (lambda frame, kind: True))
    monkeypatch.setattr(
        roster_capture,
        "DETAIL_TAB_SENTINELS",
        tabs or tuple(lambda frame, kind: True for _ in TAB_KINDS),
    )


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
