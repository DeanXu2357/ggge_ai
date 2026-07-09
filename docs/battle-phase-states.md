# 戰鬥生命週期與畫面狀態（2026-07-09，2026-07-09 使用者修正版）

## 目的

`ManualBattleController.run()` 目前是一條依優先序排列的反應式檢查鏈——每次
迭代重新從畫面猜一次「現在是什麼情況」，沒有一個顯式維護的「我相信自己在
哪個狀態」信念，也沒有留下轉移歷史。歷史上的幻影回合數、modal 重開的
stall 等 bug 都源自這裡。本文盤點現有畫面狀態與偵測手段，目的是設計一個
帶歷史的顯式狀態機取代它。**本文只整理現狀，不是新設計，程式碼未變動。**

（v1 盤點版本把重點放在「有哪些畫面狀態」的分類學上，被使用者指出沒有
講到生命週期本身；本版本重寫，以下的生命週期核心模型是本文的主結構。）

## 生命週期核心模型（使用者 2026-07-09 定案）

戰鬥的生命週期只需要一個二元判斷，不需要知道現在具體是敵方回合、
第三方回合、還是別的什麼：

> **我們現在能不能做事？**——看下方單位列表有沒有可操作單位。有，就是
> **ACTIONABLE（我方可操作）**；沒有，就是 **NOT_ACTIONABLE（我方不可
> 操作）**，不管背後遊戲引擎怎麼分敵方/第三方回合，一律當同一種狀態處理。

這個框架天然涵蓋第三方友軍的兩種情形，不需要另外探測「這關第三方可不
可控」：**可控的第三方會出現在單位列表裡**，那就自然落進 ACTIONABLE、
跟操作我方單位走同一條路；**不可控就不會出現在列表裡**，那就落進
NOT_ACTIONABLE，當成自動行動的單位，我們只需要等結果。

**刻意排除的範圍**：某些關卡的敵方跟第三方敵人會互打（用來降低難度），
這是內容細節，不影響生命週期的機制設計，現階段不理會，需要時再從畫面
讀（不寫死）。

### ACTIONABLE（我方可操作）

判斷依據：`vision.unit_cards_present`——已經是全語料驗證過的訊號（#1
的殘機卡 bug、#18 的回歸測試都在測這個），不依賴顏色，比弧色判斷穩固
很多，適合當生命週期的主判斷。

進入這個相位後，才需要知道「操作到哪一步」的子狀態——這部分現有的
`MODE_LABELS`（`unit_move`／`weapon_select`／`skill`）已經覆蓋得不錯，
是 ACTIONABLE 底下的子迴圈，不是跟 ACTIONABLE 平行的頂層狀態：

```
ACTIONABLE 進入
  → 選取單位
  → UNIT_MOVE（移動或原地開武裝）
  → WEAPON_SELECT（攻擊或無目標退回移動）
  → （攻擊後：若有再動，回到 UNIT_MOVE／WEAPON_SELECT；若無，回列表）
  → 列表還有可操作單位？有 → 選下一個；沒有 → 離開 ACTIONABLE
```

### NOT_ACTIONABLE（我方不可操作）

判斷依據：`unit_cards_present == False`（ACTIONABLE 的否定，同一個
訊號，不需要另外的偵測機制）。

這個相位裡，控制器唯一該做的事只有兩件：

1. **等結果**——動畫在播就是活動中（不算逾時），純粹等畫面穩定下來、
   單位列表重新出現可操作單位，回到 ACTIONABLE。
2. **等反應畫面（應戰決策，#3）**——敵方攻擊我方單位時彈出的防禦/
   迴避/反擊選擇，是 NOT_ACTIONABLE 期間唯一需要我們輸入的例外。這是
   目前**唯一還缺偵測機制**的部分，範圍很明確：不是「判斷現在是不是
   敵方回合」，而是單純「有沒有出現這個彈窗」，跟其他 modal（隱藏戰鬥
   WARNING、單位詳情）用同一套機制（模板比對特定畫面元素）處理即可，
   不需要理解回合歸屬。

其餘目前歸類在「未建模」的東西（ENEMY_TURN、THIRD_PARTY_TURN 的獨立
判斷）**不需要做**——ACTIONABLE/NOT_ACTIONABLE 的二元判斷已經涵蓋了
控制器真正需要的資訊，硬要分清楚回合歸屬只是多做工。

## 跨相位、可能疊加在 ACTIONABLE 或 NOT_ACTIONABLE 之上的中斷狀態

這些不屬於生命週期本身，是隨時可能打斷任一相位的插曲，處理完就回到
原本在做的事：

| 狀態 | 正面偵測？ | 機制 |
|---|---|---|
| KEYGUARD_LOCKED | ✅ | `Keyguard.ensure_unlocked()`（系統鎖 dumpsys + 暗度閘控的省電鎖圖示） |
| HIDDEN_BATTLE_WARNING modal | ✅ | `vision.is_hidden_battle_warning`，模板比對 |
| UNIT_DETAIL_MODAL | ✅ | `vision.is_unit_detail_modal`，模板比對，走 `_handle_known_modal()` 表格化 escape hatch |
| MID_BATTLE_STORY（劇情，MENU 鈕左移） | ✅ | `vision.locate_story_menu`，自由位置模板比對 |
| END_TURN_DIALOG（`dlg_end_turn`） | ✅ | manifest 模板；只在我方主動點「回合結束」時出現，全單位自動耗盡動作力會直接跳過 |
| DEATH_DIALOGUE（單位死亡的內嵌對話行） | ✅ 但層級低 | `vision.locate_dialog_cursor`，目前埋在 `mode is None` fallback 分支裡，其他檢查都落空才會去試 |
| ENEMY_REACTION_POPUP（應戰決策，#3） | ❌ | **唯一還缺的偵測機制**，見上節 |

BATTLE_PREP（開場「開始戰鬥」確認畫面）是生命週期迴圈開始前的一次性
入口，不在 ACTIONABLE/NOT_ACTIONABLE 循環之內。

## 生命週期轉移圖（簡化版）

```
BATTLE_PREP ──(開始戰鬥)──▶ ACTIONABLE(turn 1)

ACTIONABLE ──(單位列表清空)──▶ NOT_ACTIONABLE
NOT_ACTIONABLE ──(單位列表重新出現)──▶ ACTIONABLE(下一 turn)
NOT_ACTIONABLE ──(應戰彈窗出現)──▶ 應戰決策 ──(選完)──▶ 回到 NOT_ACTIONABLE 繼續等
[任一相位] ──(彈窗/劇情/鎖出現)──▶ 對應中斷狀態 ──(處理完)──▶ 回到原相位
```

TURN 數字（`vision.turn_marker_changed`）只是這個迴圈的計數器，用來
確認「這次真的是新一輪，不是 modal 造成的幻影」，不影響該做什麼決策
——ACTIONABLE/NOT_ACTIONABLE 的二元狀態才是控制器行為的依據。

## 尚待查證/存疑

- **`label_battle_prep` 出現次數異常**：jsonl 統計顯示 71/13 場，均值
  >1，比「每場戰鬥開場一次」的預期高，原因未查證。
- **PHASE_START 過場橫幅**（螢幕中下方大字，跟左上角「我軍回合」常駐
  小字是不同視覺元素）跟 `unit_cards_present`／`label_our_turn` 的時間
  關係未驗證——過場當下列表是否已經可讀，未知，待實機確認。這兩點都
  不影響 ACTIONABLE/NOT_ACTIONABLE 的主判斷邏輯，只是子狀態/計數器
  層級的細節。

## 下一步

生命週期主結構已經定案（ACTIONABLE/NOT_ACTIONABLE 二元 + 現有
MODE_LABELS 子迴圈）。要落地成程式碼的話，實質工作只剩：① 把
`run()` 現有的隱式優先序檢查鏈換成讀 `unit_cards_present` 決定相位、
依相位分派的顯式結構；② 標定 ENEMY_REACTION_POPUP 的畫面錨點與
handler（待裝置）。要現在開始寫這個嗎？
