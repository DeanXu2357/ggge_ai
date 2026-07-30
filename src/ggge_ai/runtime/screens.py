"""畫面辨識：純函式，吃一張幀吐名字與讀值，永不截圖也永不操作。

分類走**同組 argmax**而不是逐一門檻：敵方回合橫幅與我軍回合橫幅共用四個字模中
的三個，raw 0.83／highpass 0.76 都在任何合理門檻之上（0711 實機），所以幹擾樣本
一起進同一組比大小，幹擾贏了就是「不是我方回合」。門檻只用來擋整組都沒中的幀。

疊層優先：詳情面板、對話框這類覆蓋物先判，因為它們蓋在地圖上時底下的相位橫幅
還在原地照樣比中。

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
END_TURN_DIALOG = "end_turn_dialog"
BATTLE_SETTINGS = "battle_settings"
STAGE_INFO = "stage_info"
SORTIE_PREP = "sortie_prep"
BATTLE_RESULT = "battle_result"
BATTLE_DEFEAT = "battle_defeat"

# 進場閘門與棄戰流程需要的畫面，模板尚未取樣（0729 只留 gitignored 截圖）。
# 名字先立起來讓反射組接得上，簽名待 live-tester 補樣（回報的實機驗證清單）。
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
AUTO_BATTLE_OFF_PROBE = (1179, 295)
BATTLE_TAB_UNDERLINE = (1613, 201)
BATTLE_TAB_UNDERLINE_SPAN = (1605, 1651)
BATTLE_TAB_UNDERLINE_GUARDS = (14, 18)
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

# group 由小到大＝疊層由上到下：先判覆蓋物，再判戰鬥準備家族，最後才是地圖相位
# 與外層畫面。同 group 內比分數。
SIGNATURES: tuple[Signature, ...] = (
    Signature(UNIT_DETAIL, "elements/unit_detail_modal.png", (1000, 50, 380, 100), 0, 0.75),
    Signature(END_TURN_DIALOG, "elements/dlg_end_turn.png", (990, 165, 370, 135), 1, 0.75),
    Signature(
        BATTLE_PREP_REACTION, "elements/label_prep_reaction.png", (250, 0, 450, 100), 2, 0.80
    ),
    Signature(BATTLE_MAP, "elements/label_our_turn.png", PHASE_LABEL_REGION, 3, 0.80, True),
    Signature(
        BATTLE_MAP_ENEMY, "elements/label_enemy_turn.png", PHASE_LABEL_REGION, 3, 0.80, True
    ),
    Signature(
        BATTLE_UNIT_MOVE, "elements/label_unit_move.png", PHASE_LABEL_REGION, 3, 0.80, True
    ),
    Signature(
        BATTLE_WEAPON_SELECT,
        "elements/label_weapon_select.png",
        PHASE_LABEL_REGION,
        3,
        0.80,
        True,
    ),
    Signature(BATTLE_SKILL, "elements/label_skill.png", PHASE_LABEL_REGION, 3, 0.80, True),
    Signature(BATTLE_PREP, "elements/label_battle_prep.png", PHASE_LABEL_REGION, 3, 0.80, True),
    Signature(SORTIE_PREP, "elements/btn_launch.png", (1915, 935, 255, 145), 4, 0.80, True),
    Signature(STAGE_INFO, "screens/stage_info.png", (335, 288, 250, 128), 5, 0.80),
    Signature(BATTLE_RESULT, "screens/battle_result.png", (160, 300, 290, 125), 6, 0.75),
    Signature(BATTLE_DEFEAT, "screens/battle_failed.png", (980, 0, 400, 175), 7, 0.60),
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


def score(frame: np.ndarray, signature: Signature) -> float:
    template = _template(signature.template)
    if template is None or frame is None:
        return 0.0
    patch = crop(frame, signature.region)
    if patch.size == 0:
        return 0.0
    if signature.highpass:
        patch, template = _highpass(patch), _highpass(template)
    else:
        patch = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    if patch.shape[0] < template.shape[0] or patch.shape[1] < template.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED).max())


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


def is_auto_battle_off(frame: np.ndarray) -> bool:
    """設定頁 AUTO戰鬥 三選一的 OFF 六角維持實心青＝OFF 選著。"""
    px = _pixel(frame, AUTO_BATTLE_OFF_PROBE)
    if px is None:
        return False
    b, g, r = px
    return g > 180 and b > 180


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


def is_battle_tab_selected(frame: np.ndarray) -> bool:
    """設定頁的「戰鬥」籤選中底線。底線是一條線不是一點：單點探針會被鮭色
    地形斑點與實心紅 UI 誤命中（0721 收斂），所以要求整列鮭色而上下護欄列
    不鮭色。"""
    x0, x1 = BATTLE_TAB_UNDERLINE_SPAN
    y = BATTLE_TAB_UNDERLINE[1]
    if _row_salmon_fraction(frame, y, x0, x1) < _UNDERLINE_LINE_MIN:
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
