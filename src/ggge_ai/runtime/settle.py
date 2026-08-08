"""感知節奏原語：幀差量測與「等畫面收斂再取樣」。

只依賴 cv2/numpy，沒有任何畫面語意——誰要判定就誰來呼叫，判定幀一律取收斂之後
的那一張。舊 screencap 路徑每張 ~2.4s，天然跨過大多數 UI 動畫；串流取幀只要
11ms，沒有這一層就會定案在動畫中間幀（0808 選關標題滑入中被讀成 None）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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
#
# poll 間隔 0809 由 0.5s 降到 0.15s：run 20260809-011740 的 settle 事件裡，同一組
# 門檻下 nav 路（poll 0.5s）813 次只有 49% 收斂、平均等 2.89s、全程燒掉 39.2 分，
# 而 feedback 路（poll 0.15s）97% 收斂、平均 0.57s——等不到不是畫面真的一直在動，
# 是取樣太疏把緩動尾巴切在門檻外。
SETTLE_WAIT_S = 4.0
SETTLE_POLL_S = 0.15
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


@dataclass(frozen=True)
class SettleReport:
    """一次收斂等待的耗時量測。`motion` 是最後一次量到的幀差比例。

    `converged` 是「湊滿 confirm 對連續靜止」，不是「最後一對靜止」。
    """

    waited_s: float
    polls: int
    converged: bool
    motion: float


def await_still(
    grab: Callable[[], np.ndarray],
    *,
    clock: Callable[[], float],
    sleep: Callable[[float], None],
    deadline: float,
    poll: float,
    stable: float = SETTLE_STABLE_DIFF,
    confirm: int = 1,
    observe: Callable[[SettleReport], None] | None = None,
) -> np.ndarray:
    """幀差收斂：連續 `confirm` 對相鄰取樣幀都在 `stable` 內才收，等到 deadline 就放行。

    放行的那一張是「等不到靜止」的最佳可得，語意不是靜止保證。

    中途任何一對超標就把計數歸零重數：0.15s 取樣間隔下推鏡的減速尾巴會有瞬間低於
    門檻、鏡頭其實還在滑的低谷，連續兩對才分得開瞬間低谷與真停。點擊回饋那條路後面
    還有 classify 的語意閘擋著，不必付這筆錢，所以預設留 1。

    `observe` 只是耗時量測的出口，回傳前呼叫一次；這一層不認得任何語意，要落帳的
    人自己包。
    """
    started = clock()
    before = grab()
    polls = 0
    still = 0
    while True:
        sleep(poll)
        frame = grab()
        polls += 1
        motion = frame_motion(before, frame)
        still = still + 1 if motion < stable else 0
        converged = still >= confirm
        if converged or clock() >= deadline:
            if observe is not None:
                observe(SettleReport(clock() - started, polls, converged, motion))
            return frame
        before = frame
