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
