# 戰鬥畫面狀態盤點（2026-07-09）

## 目的

`ManualBattleController.run()` 目前是一條依優先序排列的反應式檢查鏈——每次
迭代重新從畫面猜一次「現在是什麼情況」，沒有一個顯式維護的「我相信自己在
哪個狀態」信念，也沒有留下轉移歷史。這在畫面訊號模糊時（`mode is None`
可以代表五六種完全不同的情況）沒辦法消歧義，事後也沒辦法回放診斷（幻影
回合數、modal 重開的 stall 等歷史 bug 都源自這裡）。

本文盤點目前所有已知的戰鬥內畫面狀態，標出「有沒有正面辨識訊號」與已知
缺口，作為之後設計一個帶歷史的顯式狀態機的骨架。**本文只整理現狀，不是
新設計，程式碼未變動**——盤點依據是 `battle/controller.py`／`battle/
vision.py` 在 commit 231998e 當下的內容，加上 `data/runs/*/battle_*.jsonl`
的實際事件分布。

## 狀態盤點表

### 終局狀態（結束 `run()`）

| 狀態 | 正面偵測？ | 機制 | 備註 |
|---|---|---|---|
| BATTLE_RESULT / REWARD | ✅ | `perception.observe()` 畫面分類器，信心 ≥0.9 | manifest 驅動，跟戰鬥外的畫面共用同一套分類器 |
| DEFEAT（FAILED） | ✅ | `vision.is_defeat_screen`，模板比對 FAILED 橫幅 | 分數差距寬（正例~1.0 / 負例≤0.18） |
| BATTLE_TIMEOUT / IDLE_TIMEOUT | 不是畫面狀態 | 純時間門檻 | 逾時就當作卡死放棄，跟畫面內容無關 |

### 彈窗／中斷狀態（可能疊加在任何其他狀態上）

| 狀態 | 正面偵測？ | 機制 | 備註 |
|---|---|---|---|
| KEYGUARD_LOCKED | ✅ | `Keyguard.ensure_unlocked()`（dumpsys 系統鎖 + 暗度閘控的省電鎖圖示） | 兩種鎖分開判斷，每次迭代都會檢查（`lock_check_interval_s`） |
| HIDDEN_BATTLE_WARNING modal | ✅ | `vision.is_hidden_battle_warning`，模板比對 | 分數差距寬（1.0 / ≤0.21），`run()` 頂層檢查 |
| UNIT_DETAIL_MODAL | ✅ | `vision.is_unit_detail_modal`，模板比對 | 走 `_handle_known_modal()` 的表格化 escape hatch，目前表裡只有這一個 modal，設計上可擴充 |
| MID_BATTLE_STORY（劇情，MENU 鈕左移） | ✅ | `vision.locate_story_menu`，自由位置模板比對 | 不依賴畫面分類器，因為劇情中畫面會被誤分類 |
| END_TURN_DIALOG（`dlg_end_turn`） | ✅ | manifest 模板 | **只在我方主動點「回合結束」時出現**；全單位自動耗盡動作力時遊戲直接跳過此對話框，不是不可靠，是設計上只有一條路徑會經過 |
| DEATH_DIALOGUE（單位死亡的 MENU-less 內嵌對話行） | ✅ 但層級低 | `vision.locate_dialog_cursor`，自由位置模板比對 | 只在 `mode is None` 分支內、其他檢查都落空後才會去試——結構上是「兜底猜測」而非跟其他中斷狀態同層級的頂層檢查 |

### 我方回合行動狀態（`MODE_LABELS` 驅動，互斥）

| 狀態 | 正面偵測？ | 機制 | 備註 |
|---|---|---|---|
| OUR_TURN_HUB（label_our_turn） | ✅ | 模板裁自「我軍回合」橫幅文字本身（左上角常駐小字） | 內部再靠 `unit_cards_present`（顏色/亮度）分岔成「有可操作單位」vs「無，該結束回合」，這個子判斷不是同一套機制，且有 1.2s 二次確認的 timing 依賴（卡片列會延遲動畫出現） |
| UNIT_MOVE（label_unit_move） | ✅ | 模板比對 | 內部再靠 `_action` 這個**不是從畫面讀出來、是控制器自己記的**旗標（`tried_in_place`/`moved`）決定要不要重試 |
| WEAPON_SELECT（label_weapon_select） | ✅ | 模板比對 | 內部再靠 `attack_enabled`（顏色）判斷是否鎖定目標 |
| SKILL（label_skill） | ✅ | 模板比對 | v1 沒有處理內容，偵測到就直接退出（技能空間留給 #12/#17） |
| BATTLE_PREP（label_battle_prep） | ✅ | 模板比對 | 戰鬥開場「開始戰鬥」確認畫面；jsonl 統計顯示 `engagement_confirm` 出現 71 次／13 場 run，均值 >1，比「每場戰鬥出現一次」的預期高——**原因未查證**，可能是重試/斷線造成的多次進場，也可能有除了開場外的其他時機也會誤判成這個模式，待後續用帶歷史的狀態機交叉比對 |

### 曖昧／未建模狀態（目前系統的實質缺口）

| 狀態 | 正面偵測？ | 現況 | 風險 |
|---|---|---|---|
| ANIMATION_IN_PROGRESS | 部分 | `is_static()==False` 只說「有東西在動」，不分辨是誰的動畫（我方攻擊/敵方攻擊/開場演出/單位移動） | 每次都要多等一輪才能繼續判斷，且完全不知道動畫內容 |
| ENEMY_TURN | ❌ | **完全靠負面推論**：連續兩張「靜止＋沒有任何 MODE_LABELS 命中＋沒有對話游標」的畫面，猜測「大概離開我方回合了」（`_none_streak >= 2` → `_phase_break = True`） | 這個推論在敵方回合、第三方回合、甚至我方回合內某個尚未加標籤的畫面上都會觸發，三者現在完全無法區分 |
| THIRD_PARTY_TURN | ❌ | 沒有任何獨立判斷；`find_third_party_units` 存在但只用於記錄/戰術地圖，從未進到 `run()` 的判斷分支 | 跟 ENEMY_TURN 混在一起，且 `state.py` 已經定義 `ThirdPartyControl.CONTROLLABLE` 但 controller 從未探測/使用 |
| ENEMY_REACTION_POPUP（應戰決策，#3） | ❌ | 完全沒有偵測，沒有 handler | 目前會被當成普通的「靜止、沒命中」畫面吞掉，等同於没有應戰決策——這是 #3 卡住的直接原因 |
| PHASE_START 過場橫幅（螢幕中下方大字「PHASE START／我軍回合／敵軍回合」，跟左上角常駐小字是不同的視覺元素） | ❌ | 沒有專門偵測；跟 `label_our_turn`（左上角小字）的時間關係未驗證——過場當下小字是否已經同時可讀，未知 | 過場期間的畫面分類完全未知會落在哪一類 |
| TURN_BOUNDARY（信念：剛發生了換回合） | 部分，且是唯一的歷史追蹤 | `_phase_break` + `vision.turn_marker_changed`（比對畫面上 TURN 數字有沒有真的變） | 這是全系統唯一會「回頭驗證」的機制，說明帶驗證的信念確實比純推論可靠（歷史上擋下過 modal 造成的幻影回合數）；但只追蹤「回合數」，不追蹤「我在哪個相位」 |

## 已知轉移路徑（依現有程式碼行為整理，非全部驗證過）

```
STAGE_INFO ──(導覽層，本文件範圍外)──▶ BATTLE_PREP
BATTLE_PREP ──(tap 開始戰鬥 + 等待演出)──▶ OUR_TURN_HUB(turn 1)          [PHASE_START 過場是否插在中間：未驗證]

OUR_TURN_HUB(有卡) ──(選取單位)──▶ UNIT_MOVE
UNIT_MOVE ──(原地開武裝)──▶ WEAPON_SELECT
UNIT_MOVE ──(移動到格子)──▶ UNIT_MOVE(重新判斷，_action.moved=True)
UNIT_MOVE ──(無目標)──▶ standby ──(隱式，靠遊戲自己收selection)──▶ OUR_TURN_HUB
WEAPON_SELECT ──(攻擊)──▶ 攻擊動畫 ──(隱式)──▶ OUR_TURN_HUB 或 UNIT_MOVE/WEAPON_SELECT(若有再動)
WEAPON_SELECT ──(無目標，尚未移動)──▶ RETURN_BTN ──▶ UNIT_MOVE
WEAPON_SELECT ──(無目標，已移動)──▶ standby ──▶ OUR_TURN_HUB
SKILL ──(RETURN_BTN，v1不使用)──▶ 來源畫面(UNIT_MOVE或WEAPON_SELECT，未區分)

OUR_TURN_HUB(無卡，二次確認) ──(tap 回合結束)──▶ phase_break=True ──▶ [ENEMY_TURN 或 END_TURN_DIALOG，未定]
END_TURN_DIALOG ──(待機並結束+執行)──▶ phase_break=True ──▶ ENEMY_TURN(未建模) ──▶ ... ──▶ OUR_TURN_HUB(下一回合，靠 turn_marker 驗證)

[任何狀態] ──(彈窗/劇情/鎖出現)──▶ 對應中斷狀態 ──(處理完)──▶ 回到迴圈重新判斷(不保證回到原狀態，只是重新猜)
```

## 缺口優先序（我的判斷，供討論）

1. **ENEMY_TURN 沒有正面訊號**——是目前最大的空白，#3（應戰彈窗）完全卡在
   這裡，且跟 THIRD_PARTY_TURN 混淆不清。
2. **ENEMY_REACTION_POPUP 完全未建模**——即使先解決了「知道現在是敵方
   回合」，彈窗本身還是要另外標定。
3. **PHASE_START 過場橫幅的時序未知**——會影響任何以它為基準設計的
   狀態轉移判斷。
4. **BATTLE_PREP 出現次數異常（71/13場）未查證**——可能暗示現有模板
   判斷比想像中更容易在非開場畫面誤判，值得在有歷史記錄的狀態機上
   交叉驗證。

## 下一步

這只是盤點，不是新設計。建議下一步是根據這張表，設計一個明確的狀態機
結構（狀態列舉、每個狀態的正面判斷來源、合法轉移表、歷史記錄），把
`run()` 現在的隱式優先序檢查鏈，換成顯式的「讀畫面 → 更新信念 → 依信念
分派」。要現在就設計嗎？
