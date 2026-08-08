"""感知節奏原語：幀差量測與「等畫面收斂再取樣」。

只依賴 cv2/numpy，沒有任何畫面語意——誰要判定就誰來呼叫，判定幀一律取收斂之後
的那一張。舊 screencap 路徑每張 ~2.4s，天然跨過大多數 UI 動畫；串流取幀只要
11ms，沒有這一層就會定案在動畫中間幀（0808 選關標題滑入中被讀成 None）。
"""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

# 推鏡後的緩動等待：兩幀逐像素比到穩定才收，等滿 SETTLE_WAIT_S 就放行（語意仍是
# 「盡力靜置」，不是靜止保證，所以上限到了不 Halt）。
#
# 判準不准用整區灰階均值（0803 第 10 輪定讞：整區灰階讀到的是不隨鏡頭動的星空
# 層，鏡頭在滑它也不動）。這裡問的是逐像素 absdiff：星空層靜止但單位、UI、格線
# 動畫都會在自己的位置上變色，鏡頭滑動更是全畫面位移，逐像素差都吃得到。
#
# 但地圖有常駐微動畫（單位待機、水面），幀差永遠不會是零，所以量的不是差多大而是
# 「差得夠明顯的像素佔多少」：>SETTLE_DIFF_NOISE 的像素比例。雜訊閾 8/255 濾掉編碼
# 抖動與呼吸式明暗；比例門檻 0.5% 的取法是——待機動畫只佔盤面上少數精靈的少數像素
# （2340x1080 的 0.5% 還有 ~12600 px 的餘裕），而鏡頭滑動是整幅位移、有紋理處全部
# 變色，比例會衝到幾十個百分點，兩者差了兩個數量級。兩個常數都放模組層，日後拿實機
# 流水帳校準時只改這裡。
SETTLE_WAIT_S = 4.0
SETTLE_POLL_S = 0.5
SETTLE_DIFF_NOISE = 8
SETTLE_STABLE_DIFF = 0.005


def frame_motion(before: np.ndarray, after: np.ndarray) -> float:
    """兩幀之間「明顯變了」的像素比例（0～1），見 SETTLE_STABLE_DIFF 的取法。

    形狀不同就當作全動：串流換解析度的那一幀本來就不能拿來判靜止。
    """
    if before.shape != after.shape:
        return 1.0
    diff = cv2.absdiff(
        cv2.cvtColor(before, cv2.COLOR_BGR2GRAY), cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
    )
    return float(np.count_nonzero(diff > SETTLE_DIFF_NOISE)) / diff.size


def await_still(
    grab: Callable[[], np.ndarray],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    deadline: float,
    poll: float,
    stable: float = SETTLE_STABLE_DIFF,
) -> np.ndarray:
    """幀差收斂：連兩幀差在 `stable` 內就收，等到 deadline 就放行。

    放行的那一張是「等不到靜止」的最佳可得，語意不是靜止保證。
    """
    before = grab()
    while True:
        sleep(poll)
        frame = grab()
        if frame_motion(before, frame) < stable or clock() >= deadline:
            return frame
        before = frame
