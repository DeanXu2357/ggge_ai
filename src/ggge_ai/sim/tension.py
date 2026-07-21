"""MP／激昂（tension）機制假設庫的 sim 佔位模組.

依據 docs/mp-tension.md：一般機體 MP 範圍 0-12，四階段門檻與傷害加成
（§1）已由使用者核對定案，本模組把它們收錄為機制常數／純函式。

**尚未定案、未接線**：MP 增減值（命中/擊墜/被彈的轉移量，§2）沒有可信
來源，必須等 C2 打表後才建轉移模型；本模組因此只提供 stage/damage_bonus
兩個查表函式，不含任何 MP 增減邏輯。暴擊倍率表（§1）雖已收錄為常數，
但來源是單一實測貼文，C2 打表驗證項④複驗前不得接線到傷害計算路徑。
另外，激昂（MP 階段）不影響命中／迴避（§1，YouTube 命中率實測公式無
MP 項）——sim 的命中模型（formulas.hit_probability）不需要、也不應該讀
這個模組。

完整建模（MP 增減轉移、暴擊倍率接線）排入 T10 後續批次；見 §4。
"""

from __future__ import annotations

import logging
from functools import lru_cache

log = logging.getLogger(__name__)

MP_MAX = 12

# 四階段上界（含）：0-3 普通／4-7 強氣／8-11 超強氣／12 超一擊。
_STAGE_UPPER_BOUNDS = (3, 7, 11)

# 階段傷害加成：加算入增傷桶，與技能增傷、易傷 debuff 相加後，桶總和
# 才乘算基礎傷害（formulas.expected_damage 的 bonuses 引數），非獨立乘算。
DAMAGE_BONUS_BY_STAGE: tuple[float, ...] = (0.0, 0.10, 0.20, 0.30)

# 暴擊倍率表：單源實測（wikiwiki 實測帖＋altema 佐證），C2 打表驗證項④，
# 索引對應 stage() 回傳值；目前未接線到任何傷害計算路徑。
CRIT_MULTIPLIER_BY_STAGE: tuple[float, ...] = (1.1, 1.2, 1.2, 1.3)


def stage(mp: int) -> int:
    """回傳 MP 對應的四階段索引（0-3），界線見 docs/mp-tension.md §1。"""
    if not 0 <= mp <= MP_MAX:
        raise ValueError(f"mp must be within 0..{MP_MAX}, got {mp}")
    for idx, upper in enumerate(_STAGE_UPPER_BOUNDS):
        if mp <= upper:
            return idx
    return len(_STAGE_UPPER_BOUNDS)


def damage_bonus(mp: int) -> float:
    """階段傷害加成，加算入增傷桶（非獨立乘算，docs/mp-tension.md §1）。"""
    return DAMAGE_BONUS_BY_STAGE[stage(mp)]


@lru_cache(maxsize=1)
def warn_not_modeled() -> None:
    """第一次呼叫時提醒一次：傷害期望尚未接 MP/激昂。之後的呼叫是無操作。"""
    log.warning(
        "tension/MP not yet modeled in damage expectation; see docs/mp-tension.md"
    )
