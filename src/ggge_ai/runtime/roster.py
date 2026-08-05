"""名冊感知：戰鬥選單「部隊資訊」的列表格座標，與「單位設置詳情」頁的讀值。

純函式，不截圖也不點擊。列表順序穩定，所以「第幾格」就是這一輪的身分鍵；世界座標
由 jumpscan 那一層掛回去。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ggge_ai.runtime import glyphs

Point = tuple[int, int]
Region = tuple[int, int, int, int]

ALLY = "ally"
ENEMY = "enemy"

BATTLE_MENU_TROOP_INFO_TAP: Point = (753, 508)
TROOP_INFO_CLOSE_TAP: Point = (1172, 992)
TROOP_INFO_ALLY_TAB_TAP: Point = (460, 440)
TROOP_INFO_ENEMY_TAB_TAP: Point = (460, 600)
DETAIL_SELECT_TAP: Point = (1372, 995)
DETAIL_CLOSE_TAP: Point = (994, 995)

TAB_TAPS: dict[str, Point] = {ALLY: TROOP_INFO_ALLY_TAB_TAP, ENEMY: TROOP_INFO_ENEMY_TAB_TAP}

# 列表格距（0806 兩張列表幀的圖示中心量測）。我軍是「部隊1／部隊2」兩列，每列多一
# 條 GET SCORE 帶所以列距較大；敵軍四列連排。單位圖示與駕駛圖示成對，點的是單位那半。
CELL_X0 = 729
CELL_X_PITCH = 278.5
CELL_Y0 = 267
CELLS_PER_ROW = 5
ALLY_ROW_PITCH = 245.7
ALLY_ROWS = 2
ENEMY_ROW_PITCH = 193.4
ENEMY_ROWS = 4

# 陣營帶（我軍藍／敵軍紅）。兩種佈局的帶子縱向差一列，所以區域一次涵蓋兩個位置，
# 誰的顏色佔比大就是誰——這同時也就是佈局判別，不必另外數 LV 列。
FACTION_BAND_REGION: Region = (1125, 325, 165, 115)
FACTION_BAND_MIN = 0.10

# 詳情頁數值欄（0806 兩張詳情幀逐帶量測）。深字淺底，走 glyphs 的 panel 字模。
# 移動力那一列的區域必須從 x=1250 起算：標籤「移動力」右緣壓到 1205。
ENEMY_REGIONS: dict[str, Region] = {
    "hp": (1180, 149, 155, 34),
    "en": (1180, 213, 155, 32),
    "mobility": (1250, 285, 85, 35),
}
ALLY_REGIONS: dict[str, Region] = {
    "lv": (1180, 158, 155, 35),
    "hp": (1180, 217, 155, 32),
    "en": (1180, 280, 155, 33),
    "mobility": (1250, 352, 85, 35),
}
REGIONS: dict[str, dict[str, Region]] = {ALLY: ALLY_REGIONS, ENEMY: ENEMY_REGIONS}


@dataclass(frozen=True)
class RosterEntry:
    faction: str
    index: int
    hp: int | None
    en: int | None
    mobility: int | None
    lv: int | None = None

    @property
    def complete(self) -> bool:
        return None not in (self.hp, self.en, self.mobility)


def rows_of(faction: str) -> int:
    return ALLY_ROWS if faction == ALLY else ENEMY_ROWS


def row_pitch_of(faction: str) -> float:
    return ALLY_ROW_PITCH if faction == ALLY else ENEMY_ROW_PITCH


def cell_taps(faction: str) -> tuple[Point, ...]:
    """名冊順序的逐格點擊位置（列優先，左到右）。

    最後一列不見得滿格，而格數在點開之前看不出來——多出來的點交給呼叫端試點：點不
    出詳情頁就是列表盡頭。
    """
    pitch = row_pitch_of(faction)
    return tuple(
        (
            int(round(CELL_X0 + CELL_X_PITCH * column)),
            int(round(CELL_Y0 + pitch * row)),
        )
        for row in range(rows_of(faction))
        for column in range(CELLS_PER_ROW)
    )


def read_faction(frame: np.ndarray | None) -> str | None:
    """詳情頁中央的陣營帶：紅＝敵軍、藍＝我軍，都不像就 None（不在詳情頁）。"""
    if frame is None:
        return None
    x, y, w, h = FACTION_BAND_REGION
    patch = frame[y : y + h, x : x + w]
    if patch.size == 0:
        return None
    pixels = patch.reshape(-1, 3).astype(np.float32)
    blue, green, red = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    red_fraction = float(((red > 110) & (red > blue + 40) & (red > green + 40)).mean())
    blue_fraction = float(((blue > 110) & (blue > red + 40) & (blue > green + 20)).mean())
    if max(red_fraction, blue_fraction) < FACTION_BAND_MIN:
        return None
    return ENEMY if red_fraction > blue_fraction else ALLY


def read_detail(frame: np.ndarray | None, index: int) -> RosterEntry | None:
    """一張「單位設置詳情」幀 → 一筆名冊。陣營帶讀不出來就不是詳情頁，回 None。"""
    faction = read_faction(frame)
    if faction is None:
        return None
    regions = REGIONS[faction]

    def value(field: str) -> int | None:
        region = regions.get(field)
        if region is None:
            return None
        return glyphs.read_int(frame, region, ink=glyphs.Ink.DARK)

    return RosterEntry(
        faction=faction,
        index=index,
        hp=value("hp"),
        en=value("en"),
        mobility=value("mobility"),
        lv=value("lv"),
    )
