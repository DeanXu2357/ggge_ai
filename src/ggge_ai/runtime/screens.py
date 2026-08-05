"""畫面辨識：純函式，吃一張幀吐名字與讀值，永不截圖也永不操作。

分類走**同組 argmax**而不是逐一門檻：敵方回合橫幅與我軍回合橫幅共用四個字模中
的三個，raw 0.83／highpass 0.76 都在任何合理門檻之上（0711 實機），所以幹擾樣本
一起進同一組比大小，幹擾贏了就是「不是我方回合」。門檻只用來擋整組都沒中的幀。

疊層優先：系統彈窗、詳情面板、對話框這類覆蓋物先判，因為它們蓋在地圖上時底下的
相位橫幅還在原地照樣比中。

AUTO 開關 (1815,52) 的三態不看單點——那顆像素落在白色「AUTO」字上，三態全是
(255,255,254) 級的白。看整片開關底色的中位數：暗＝OFF、青＝ON 待機、紅＝ON
執行中（0730 標定，fixtures stage_panels/stage_info_auto_{off,on}.png 與
battle_auto_active_red.png 量得 medBGR (53,42,34)／(148,120,48)／(64,61,183)）。
"""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "assets" / "templates"

Region = tuple[int, int, int, int]

UNKNOWN = "unknown"
BATTLE_MAP = "battle_map"
BATTLE_MAP_ENEMY = "battle_map_enemy"
BATTLE_UNIT_MOVE = "battle_unit_move"
BATTLE_WEAPON_SELECT = "battle_weapon_select"
BATTLE_SKILL = "battle_skill"
BATTLE_PREP = "battle_prep"
BATTLE_PREP_REACTION = "battle_prep_reaction"
UNIT_DETAIL = "unit_detail"
BATTLE_MENU = "battle_menu"
TROOP_INFO = "troop_info"
END_TURN_DIALOG = "end_turn_dialog"
BATTLE_SETTINGS = "battle_settings"
STAGE_INFO = "stage_info"
SORTIE_PREP = "sortie_prep"
BATTLE_RESULT = "battle_result"
BATTLE_DEFEAT = "battle_defeat"
STAGE_LIST = "stage_list"
STAGE_TYPE_SELECT = "stage_type_select"
SERIES_SELECT = "series_select"
SERIES_CONFIRM = "series_confirm"

LOGIN_BONUS = "login_bonus"
NOTICE = "notice"
DATE_CHANGED = "date_changed"

MAP_SCREENS = (
    BATTLE_MAP,
    BATTLE_MAP_ENEMY,
    BATTLE_UNIT_MOVE,
    BATTLE_WEAPON_SELECT,
    BATTLE_SKILL,
)
# 地圖上有東西擋著、或人在子模式：都不是穩態，反射組要把它收乾。
MAP_SUBSTATES = (BATTLE_UNIT_MOVE, BATTLE_WEAPON_SELECT, BATTLE_SKILL)

AUTO_OFF = "off"
AUTO_ON = "on"
AUTO_ACTIVE = "active"

AUTO_SWITCH_TAP = (1815, 52)
AUTO_SWITCH_REGION: Region = (1770, 15, 190, 75)

GRID_TOGGLE_TAP = (1898, 591)
GRID_PROBE = (1963, 591)
ROSTER_TOGGLE_TAP = (1970, 780)
AUTO_BATTLE_OFF_PROBE = (1179, 295)
ABANDON_DIALOG_BODY: Region = (800, 300, 800, 80)
ABANDON_DIALOG_CONFIRM: Region = (1390, 855, 21, 21)
_ABANDON_BODY_MIN = 170.0
_ABANDON_BODY_FLAT_MAX = 8.0
DOWNLOAD_DIALOG_TITLE: Region = (1020, 200, 300, 80)
DOWNLOAD_DIALOG_BODY: Region = (700, 292, 940, 60)
DOWNLOAD_DIALOG_TEMPLATE = "elements/dlg_download.png"
DOWNLOAD_DIALOG_MIN = 0.80
_DOWNLOAD_BODY_MIN = 170.0
_DOWNLOAD_BODY_FLAT_MAX = 10.0
DOWNLOAD_CONFIRM_TAP = (1372, 848)

# 關卡列表右欄的標題帶。系列＋難度的字串與尾碼數字分開讀：整條標題的模板在
# 「STAGE 1」與「STAGE 2」之間只差一個字元，raw 分數 1.000 對 0.996——**分不開**
# （0805 實幀量測）。數字單獨切出來再比才有 0.982 對 0.399 的差距。
STAGE_TITLE_REGION: Region = (1440, 118, 660, 60)
STAGE_TITLE_NUMBER_REGION: Region = (2005, 118, 75, 60)
STAGE_TITLE_MIN = 0.85
STAGE_NUMBER_MIN = 0.70
STAGE_TITLE_SERIES: dict[str, str] = {"uc_hard": "elements/stage_title_uc_hard.png"}
# 尾碼數字是定寬字模比對，只認得標定過的個位數。兩位數（STAGE 10）會讓置中的標題
# 整條左移，數字帶要重新標定才能加。
STAGE_TITLE_NUMBERS: dict[str, str] = {
    "1": "elements/stage_number_1.png",
    "2": "elements/stage_number_2.png",
}

BATTLE_TAB_UNDERLINE = (1613, 201)
BATTLE_TAB_UNDERLINE_SPAN = (1605, 1651)
BATTLE_TAB_UNDERLINE_GUARDS = (14, 18)
BATTLE_TAB_UNDERLINE_EDGES = (1600, 1669)
_UNDERLINE_EDGE_TOL = 6
_UNDERLINE_LINE_MIN = 0.85
_UNDERLINE_GUARD_MAX = 0.25


@dataclass(frozen=True)
class Signature:
    """一個畫面的模板簽名。同 group 比 argmax，門檻只用來擋整組都沒中。"""

    screen: str
    template: str
    region: Region
    group: int
    threshold: float
    highpass: bool = False


# 相位橫幅共用一個帶域，六個字模一起比 argmax（沿用舊 controller 的
# MODE_LABELS＋DISTRACTOR_LABELS 決策，換成宣告式）。
PHASE_LABEL_REGION: Region = (110, 0, 310, 135)

# group 由小到大＝疊層由上到下：系統彈窗蓋住一切，再是覆蓋物與戰鬥準備家族，
# 最後才是地圖相位與外層畫面。同 group 內比分數。
UNIT_DETAIL_SIGNATURE = Signature(
    UNIT_DETAIL, "elements/unit_detail_modal.png", (1000, 50, 380, 100), 1, 0.75
)

# 戰鬥選單／部隊資訊：兩張全螢幕面板，標題都畫在同一條標題帶上（0806 六幀量測
# y 75-110 逐幀一致）。互比最高只到 0.34，門檻拉到 0.85 仍留很寬的餘裕。與
# 「單位設置詳情」同 group——三張都是蓋住地圖的面板，同層比 argmax。
PANEL_TITLE_REGION: Region = (1040, 65, 290, 58)

SIGNATURES: tuple[Signature, ...] = (
    # 三個彈窗的簽名都取「一定畫得出來的元素」而不是內容：公告有近 1.5 秒的載入
    # 空窗（內容出現前畫面近全黑），標題列與關閉鈕在空窗前後都在。空窗連框都還沒
    # 畫的那幾幀一律 UNKNOWN——猜錯畫面比說不知道貴。
    Signature(LOGIN_BONUS, "elements/label_login_bonus.png", (1380, 150, 640, 110), 0, 0.80),
    Signature(NOTICE, "elements/label_notice.png", (1110, 50, 180, 90), 0, 0.80),
    # 日期變更取「前往主畫面」鈕而不是「更新資料」標題：標題是所有維護對話框共用
    # 的，按鈕文字既是這張對話框的識別、也正是反射要點的那一顆。
    Signature(DATE_CHANGED, "elements/btn_to_main_screen.png", (1050, 810, 275, 90), 0, 0.80),
    UNIT_DETAIL_SIGNATURE,
    Signature(BATTLE_MENU, "elements/label_battle_menu.png", PANEL_TITLE_REGION, 1, 0.85),
    Signature(TROOP_INFO, "elements/label_troop_info.png", PANEL_TITLE_REGION, 1, 0.85),
    Signature(END_TURN_DIALOG, "elements/dlg_end_turn.png", (990, 165, 370, 135), 2, 0.75),
    Signature(
        BATTLE_PREP_REACTION, "elements/label_prep_reaction.png", (250, 0, 450, 100), 3, 0.80
    ),
    Signature(BATTLE_MAP, "elements/label_our_turn.png", PHASE_LABEL_REGION, 4, 0.80, True),
    Signature(
        BATTLE_MAP_ENEMY, "elements/label_enemy_turn.png", PHASE_LABEL_REGION, 4, 0.80, True
    ),
    Signature(
        BATTLE_UNIT_MOVE, "elements/label_unit_move.png", PHASE_LABEL_REGION, 4, 0.80, True
    ),
    Signature(
        BATTLE_WEAPON_SELECT,
        "elements/label_weapon_select.png",
        PHASE_LABEL_REGION,
        4,
        0.80,
        True,
    ),
    Signature(BATTLE_SKILL, "elements/label_skill.png", PHASE_LABEL_REGION, 4, 0.80, True),
    Signature(BATTLE_PREP, "elements/label_battle_prep.png", PHASE_LABEL_REGION, 4, 0.80, True),
    Signature(SORTIE_PREP, "elements/btn_launch.png", (1915, 935, 255, 145), 5, 0.80, True),
    Signature(STAGE_INFO, "screens/stage_info.png", (335, 288, 250, 128), 6, 0.80),
    Signature(BATTLE_RESULT, "screens/battle_result.png", (160, 300, 290, 125), 7, 0.75),
    Signature(BATTLE_DEFEAT, "screens/battle_failed.png", (980, 0, 400, 175), 8, 0.60),
    # 「選擇關卡」標頭。NORMAL 與 HARD 節點在同一條軸上（難度不是分頁），所以這個
    # 名字只說「人在關卡列表」；選了哪一關要另外走 read_stage_title 讀右欄標題。
    Signature(STAGE_LIST, "screens/stage_list.png", (310, 0, 340, 140), 9, 0.85),
    # 棄戰會落在關卡模式選擇頁而不是關卡列表（0805 兩輪實證），回列表的路要認得出
    # 這三張中繼畫面才走得下去。
    Signature(STAGE_TYPE_SELECT, "screens/stage_type_select.png", (135, 0, 210, 140), 9, 0.85),
    Signature(SERIES_SELECT, "screens/series_select.png", (495, 835, 420, 160), 9, 0.85),
    Signature(SERIES_CONFIRM, "screens/series_confirm.png", (1775, 820, 425, 155), 9, 0.85),
)


@functools.cache
def _template(name: str) -> np.ndarray | None:
    return cv2.imread(str(TEMPLATE_ROOT / name))


def _highpass(image: np.ndarray) -> np.ndarray:
    """去局部均值：留筆畫、丟背景亮度。亮地圖上比對暗處拍的字模就靠這個
    （亮度本身是語意的模板不可用——例如省電鎖圖示）。"""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    blur = cv2.GaussianBlur(gray, (31, 31), 0)
    return np.clip(gray - blur + 128, 0, 255).astype(np.uint8)


def crop(frame: np.ndarray, region: Region) -> np.ndarray:
    x, y, w, h = region
    return frame[y : y + h, x : x + w]


def match(frame: np.ndarray, template_name: str, region: Region, highpass: bool = False) -> float:
    template = _template(template_name)
    if template is None or frame is None:
        return 0.0
    patch = crop(frame, region)
    if patch.size == 0:
        return 0.0
    if highpass:
        patch, template = _highpass(patch), _highpass(template)
    else:
        patch = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    if patch.shape[0] < template.shape[0] or patch.shape[1] < template.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED).max())


def score(frame: np.ndarray, signature: Signature) -> float:
    return match(frame, signature.template, signature.region, signature.highpass)


def scores(frame: np.ndarray) -> dict[str, float]:
    return {signature.screen: score(frame, signature) for signature in SIGNATURES}


def classify(frame: np.ndarray) -> str:
    """畫面名，判不出來就是 UNKNOWN——絕不猜成最像的那個。"""
    if frame is None:
        return UNKNOWN
    measured = [(signature, score(frame, signature)) for signature in SIGNATURES]
    for group in sorted({signature.group for signature, _ in measured}):
        contenders = [(sig, value) for sig, value in measured if sig.group == group]
        best, value = max(contenders, key=lambda item: item[1])
        if value < best.threshold:
            continue
        return best.screen
    if is_battle_tab_selected(frame):
        return BATTLE_SETTINGS
    return UNKNOWN


def _pixel(frame: np.ndarray, xy: tuple[int, int]) -> tuple[int, int, int] | None:
    x, y = xy
    if frame is None or frame.shape[0] <= y or frame.shape[1] <= x:
        return None
    b, g, r = (int(v) for v in frame[y, x])
    return b, g, r


def read_auto_switch(frame: np.ndarray) -> str | None:
    """AUTO 開關三態，開關不在畫面上就 None。

    **暗＝OFF，不要點**——0730 踩雷定則：狀態沿用上次設定，「不碰」不是安全
    策略，但碰錯方向會親手打開自動戰鬥。
    """
    if frame is None:
        return None
    patch = crop(frame, AUTO_SWITCH_REGION)
    if patch.size == 0:
        return None
    b, g, r = (float(v) for v in np.median(patch.reshape(-1, 3), axis=0))
    if r > 140 and r > b + 60:
        return AUTO_ACTIVE
    if b > 110 and b > r + 60:
        return AUTO_ON
    # 暗底＝OFF，但「一片全黑」也是暗底：過場黑幀與被裁掉的區域都會冒充 OFF，
    # 而 OFF 是唯一「不要動它」的答案，誤讀在這裡最貴。要求白色 AUTO 字還在。
    if max(b, g, r) < 90 and _bright_fraction(patch) >= AUTO_GLYPH_MIN:
        return AUTO_OFF
    return None


AUTO_GLYPH_MIN = 0.02


def _bright_fraction(patch: np.ndarray) -> float:
    return float((cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY) > 200).mean())


def read_grid_setting(frame: np.ndarray) -> str | None:
    """顯示方格開關的滑塊像素：青綠＝on、深灰＝off、都不像＝不在設定頁。"""
    px = _pixel(frame, GRID_PROBE)
    if px is None:
        return None
    b, g, r = px
    if g > 160 and b > 160 and r < 150:
        return "on"
    if r < 120 and g < 120 and b < 120:
        return "off"
    return None


ROSTER_HEADER_TEMPLATE = "elements/unit_list_header.png"
ROSTER_HEADER_EXPANDED_REGION: Region = (1855, 740, 220, 92)
ROSTER_HEADER_COLLAPSED_REGION: Region = (1855, 960, 220, 92)
ROSTER_HEADER_MIN = 0.6

ROSTER_EXPANDED = "expanded"
ROSTER_COLLAPSED = "collapsed"


def is_unit_detail_modal(frame: np.ndarray) -> bool:
    return score(frame, UNIT_DETAIL_SIGNATURE) >= UNIT_DETAIL_SIGNATURE.threshold


def read_roster_strip(frame: np.ndarray) -> str | None:
    """可行動單位卡條的狀態就是它的標頭在哪：條帶頂＝展開、降到底＝收合。

    None ＝ 讀不出來（詳情彈窗蓋著、兩帶都命中、或兩帶都不中），**永遠不可以當
    成收合**——舊碼把「被遮住」與「收合」混成同一個 False，實機上換來 41 次空轉
    循環（0723 輪四）。搬自 battle/vision.unit_list_state，帶域與 0.6 門檻沿用
    當時實測（命中 0.88-1.0、空帶 <=0.25、彈窗 <=0.10）。
    """
    if frame is None or is_unit_detail_modal(frame):
        return None
    top = match(frame, ROSTER_HEADER_TEMPLATE, ROSTER_HEADER_EXPANDED_REGION)
    bottom = match(frame, ROSTER_HEADER_TEMPLATE, ROSTER_HEADER_COLLAPSED_REGION)
    if top >= ROSTER_HEADER_MIN and bottom < ROSTER_HEADER_MIN:
        return ROSTER_EXPANDED
    if bottom >= ROSTER_HEADER_MIN and top < ROSTER_HEADER_MIN:
        return ROSTER_COLLAPSED
    return None


def is_auto_battle_off(frame: np.ndarray) -> bool:
    """設定頁 AUTO戰鬥 三選一的 OFF 六角維持實心青＝OFF 選著。"""
    px = _pixel(frame, AUTO_BATTLE_OFF_PROBE)
    if px is None:
        return False
    b, g, r = px
    return g > 180 and b > 180


def is_abandon_confirm_dialog(frame: np.ndarray) -> bool:
    """「確認放棄」彈窗在不在場。棄戰確認鈕 (1400,865) 與戰鬥選單的「幫助」同列
    同格，彈窗不在場時按下去就是開幫助頁（0804 實機），所以這一下必須先過探針。

    戰鬥選單本身也是白面板（本體區亮度 206），只有平坦度與確認鈕的藍分得開：
    彈窗本體是無字純白（std 0.1 對選單的 24.1）、確認鈕實心藍（B255 對 214/199/193）。
    """
    if frame is None:
        return False
    body = crop(frame, ABANDON_DIALOG_BODY)
    button = crop(frame, ABANDON_DIALOG_CONFIRM)
    if body.size == 0 or button.size == 0:
        return False
    gray = cv2.cvtColor(body, cv2.COLOR_BGR2GRAY)
    if gray.mean() < _ABANDON_BODY_MIN or gray.std() > _ABANDON_BODY_FLAT_MAX:
        return False
    b, _, r = (float(v) for v in np.median(button.reshape(-1, 3), axis=0))
    return b > 200 and b - r > 80


def is_download_dialog(frame: np.ndarray) -> bool:
    """「下載關卡資料」彈窗在不在場。

    標題字模＋白底本體兩道都過才算。這個判定會授權去按「下載」鈕，按錯位置的代價
    落在出擊準備頁的其他按鈕上，所以寧可漏判。
    """
    if frame is None:
        return False
    if match(frame, DOWNLOAD_DIALOG_TEMPLATE, DOWNLOAD_DIALOG_TITLE) < DOWNLOAD_DIALOG_MIN:
        return False
    body = crop(frame, DOWNLOAD_DIALOG_BODY)
    if body.size == 0:
        return False
    gray = cv2.cvtColor(body, cv2.COLOR_BGR2GRAY)
    return gray.mean() >= _DOWNLOAD_BODY_MIN and gray.std() <= _DOWNLOAD_BODY_FLAT_MAX


def read_stage_title(frame: np.ndarray) -> str | None:
    """關卡列表右欄選中的是哪一關，回 "<系列>_<編號>"（例 "uc_hard_1"）；讀不出來回 None。

    系列用門檻、編號用同組 argmax——兩者都標定過才回值，任一段落空就是不知道。
    """
    if frame is None:
        return None
    series = max(
        STAGE_TITLE_SERIES,
        key=lambda key: match(frame, STAGE_TITLE_SERIES[key], STAGE_TITLE_REGION),
    )
    if match(frame, STAGE_TITLE_SERIES[series], STAGE_TITLE_REGION) < STAGE_TITLE_MIN:
        return None
    measured = {
        digit: match(frame, template, STAGE_TITLE_NUMBER_REGION, True)
        for digit, template in STAGE_TITLE_NUMBERS.items()
    }
    digit = max(measured, key=lambda key: measured[key])
    if measured[digit] < STAGE_NUMBER_MIN:
        return None
    return f"{series}_{digit}"


def _is_salmon(bgr: tuple[int, int, int]) -> bool:
    b, _, r = bgr
    return r > 190 and r > b + 30


def _row_salmon_fraction(frame: np.ndarray, y: int, x0: int, x1: int) -> float:
    if frame is None or y < 0 or y >= frame.shape[0]:
        return 0.0
    xs = [x for x in range(x0, x1 + 1) if 0 <= x < frame.shape[1]]
    if not xs:
        return 0.0
    hits = sum(_is_salmon(tuple(int(v) for v in frame[y, x])) for x in xs)
    return hits / len(xs)


def _salmon_run(frame: np.ndarray, y: int, x: int) -> tuple[int, int] | None:
    if frame is None or y < 0 or y >= frame.shape[0] or x >= frame.shape[1]:
        return None
    if not _is_salmon(tuple(int(v) for v in frame[y, x])):
        return None
    left = right = x
    while left - 1 >= 0 and _is_salmon(tuple(int(v) for v in frame[y, left - 1])):
        left -= 1
    while right + 1 < frame.shape[1] and _is_salmon(tuple(int(v) for v in frame[y, right + 1])):
        right += 1
    return left, right


def is_battle_tab_selected(frame: np.ndarray) -> bool:
    """設定頁的「戰鬥」籤選中底線。底線是一塊有邊界的色塊，不是一點也不只是
    一條列：單點探針會被鮭色地形斑點誤命中（0721 收斂），只驗列＋上下護欄還會
    被戰鬥地圖的紅色攻擊範圍塊誤命中（格線剛好讓護欄列乾淨，0805 南緣讀卡），
    所以再要求這條鮭色連續段的左右端點就落在籤本身的寬度上。"""
    x0, x1 = BATTLE_TAB_UNDERLINE_SPAN
    y = BATTLE_TAB_UNDERLINE[1]
    if _row_salmon_fraction(frame, y, x0, x1) < _UNDERLINE_LINE_MIN:
        return False
    run = _salmon_run(frame, y, BATTLE_TAB_UNDERLINE[0])
    if run is None:
        return False
    if any(abs(got - want) > _UNDERLINE_EDGE_TOL
           for got, want in zip(run, BATTLE_TAB_UNDERLINE_EDGES, strict=True)):
        return False
    above_dy, below_dy = BATTLE_TAB_UNDERLINE_GUARDS
    above = _row_salmon_fraction(frame, y - above_dy, x0, x1)
    below = _row_salmon_fraction(frame, y + below_dy, x0, x1)
    return above <= _UNDERLINE_GUARD_MAX and below <= _UNDERLINE_GUARD_MAX


FRAME_SIGNATURE_GRID = 16
FRAME_SIGNATURE_LEVELS = 32


def frame_signature(frame: np.ndarray) -> str:
    """粗糙的整幀指紋：16x16 灰階降採樣量化成 32 階再雜湊。

    給前景卡死看門狗用——它要問的是「畫面完全沒動」，逐位元組比對會被一根
    動畫像素否決，而降採樣＋量化之後單位待機動畫仍會改值、真凍住才不動。
    格子再粗下去兩張不同的畫面會撞同一指紋（＝誤觸復原），所以停在 16x16。
    """
    if frame is None:
        return ""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(
        gray, (FRAME_SIGNATURE_GRID, FRAME_SIGNATURE_GRID), interpolation=cv2.INTER_AREA
    )
    quantized = (small.astype(np.uint16) * FRAME_SIGNATURE_LEVELS // 256).astype(np.uint8)
    return hashlib.sha1(quantized.tobytes()).hexdigest()[:16]
