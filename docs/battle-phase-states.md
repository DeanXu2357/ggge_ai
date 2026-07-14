# 戰鬥生命週期與畫面狀態

`ManualBattleController.run()` 的生命週期模型（已落地，commit 516987e）。
設計演變歷程（v1 分類學版本、`unit_cards_present` 頂層判斷的放棄理由）
見 [archive.md](archive.md)「設計演變歷程」。

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

判斷依據：`_current_mode() is not None`——`MODE_LABELS` 五個模板
（`our_turn`／`unit_move`／`weapon_select`／`skill`／`battle_prep`）
任一命中。

進入這個相位後，才需要知道「操作到哪一步」的子狀態——這部分現有的
`MODE_LABELS` 子迴圈已經覆蓋得不錯：

```
ACTIONABLE 進入
  → 選取單位
  → UNIT_MOVE（移動或原地開武裝）
  → WEAPON_SELECT（攻擊或無目標退回移動）
  → （攻擊後：若有再動，回到 UNIT_MOVE／WEAPON_SELECT；若無，回列表）
  → 列表還有可操作單位？有 → 選下一個；沒有 → 離開 ACTIONABLE
```

`vision.unit_cards_present` 用在 `_on_our_turn()` 內部判斷「列表裡
還有沒有可操作單位、該選下一個還是結束回合」——這是它已被全語料
驗證過的用途;它**不是**頂層 ACTIONABLE 的判斷依據（放棄理由見
archive.md）。

### NOT_ACTIONABLE（我方不可操作）

判斷依據：`_current_mode() is None`（ACTIONABLE 的否定，同一個
訊號，不需要另外的偵測機制）。已實作於 `controller.py` 的
`_on_not_actionable()`。

2026-07-11 補充（雪地圖卡死事故後）：這個判斷**不能**再前置任何
「等畫面靜止」的 gate——有常駐環境動畫的地圖（飄雪實測閒置 frame_diff
0.016-0.024）永遠不會靜止，靜止 gate 會讓控制器整場零行動。label probe
本身就是可操作性的判斷，配合「連續兩次讀到同一個 label 才 dispatch」
擋掉轉場殘影的誤匹配；回合邊界改用 `_on_our_turn()` 比對畫面上 TURN
數字的變化（`turn_marker`），不再數「連續無 label 的靜止幀」（攻擊動畫
期間同樣會出現無 label 段落，舊 streak 法會誤報相位斷點）。

這個相位裡，控制器唯一該做的事只有兩件：

1. **等結果**——純粹等相位 label 重新命中（單位列表重新出現可操作
   單位），回到 ACTIONABLE。
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
| DEATH_DIALOGUE（單位死亡的內嵌對話行） | ✅ | `vision.locate_dialog_cursor`，已實作於 `_on_not_actionable()`（NOT_ACTIONABLE 的第一個檢查項，不再是匿名 fallback） |
| ENEMY_REACTION_POPUP（應戰決策，#3） | ❌ | **唯一還缺的偵測機制**，`_on_not_actionable()` 已留好註解標明擴充點，見上節 |

BATTLE_PREP（開場「開始戰鬥」確認畫面）用的是 `label_battle_prep`
模板，跟其他四個 `MODE_LABELS` 同層級，自然歸在 ACTIONABLE 的第一個
子狀態，不需要額外的特例判斷。

## 生命週期轉移圖（簡化版）

```
ACTIONABLE(battle_prep) ──(開始戰鬥)──▶ ACTIONABLE(turn 1)

ACTIONABLE ──(MODE_LABELS 不再命中)──▶ NOT_ACTIONABLE
NOT_ACTIONABLE ──(MODE_LABELS 重新命中)──▶ ACTIONABLE(下一 turn)
NOT_ACTIONABLE ──(應戰彈窗出現，未實作)──▶ 應戰決策 ──(選完)──▶ 回到 NOT_ACTIONABLE 繼續等
[任一相位] ──(彈窗/劇情/鎖出現)──▶ 對應中斷狀態 ──(處理完)──▶ 回到原相位
```

TURN 數字（`vision.turn_marker_changed`）只是這個迴圈的計數器，用來
確認「這次真的是新一輪，不是 modal 造成的幻影」，不影響該做什麼決策
——ACTIONABLE/NOT_ACTIONABLE 的二元狀態才是控制器行為的依據。

## 期望轉移驗證（2026-07-12 落地，使用者定案的 act → verify → retry）

控制器不再只是被動感知：每個關鍵動作發出後登記一份轉移契約
（`Expectation`：來源相位 → 合法目標相位集合），主迴圈每次確認到
mode 時對帳：

- **命中目標**：轉移驗證成功（`expectation_met`）。
- **觀測 == 來源**：tap 被吞（省電鎖、動畫中 UI）——`on_eaten` 回滾
  該動作已設的 handler 旗標（如 `tried_in_place`），讓反應式分派
  自然重試；預算一次，再犯記 `expectation_expired`。
- **觀測是其他真實相位**：miss——**畫面永遠是權威**，接受現實照常
  分派，只記 `expectation_miss`（附幀）當作「我們的遊戲流程模型
  哪裡錯了」的證據。
- **無 label**：中性（動畫/中斷長這樣），以「檢查次數」計預算而非
  牆鐘時間，中斷處理與長動畫不會燒掉契約。

v1 登記的動作：選單位、開武裝選擇、攻擊、開始戰鬥（含應戰）、待機。
移動（tap 格子）尚未登記——移動前後 label 同為 unit_move，需要位置
驗證才能分辨成功與被吞，待實機資料。

## 尚待查證/存疑

- **`label_battle_prep` 出現次數異常**：jsonl 統計顯示 71/13 場，均值
  >1，比「每場戰鬥開場一次」的預期高，原因未查證。
- **PHASE_START 過場橫幅**（螢幕中下方大字，跟左上角「我軍回合」常駐
  小字是不同視覺元素）跟 `unit_cards_present`／`label_our_turn` 的時間
  關係未驗證——過場當下列表是否已經可讀，未知，待實機確認。這兩點都
  不影響 ACTIONABLE/NOT_ACTIONABLE 的主判斷邏輯，只是子狀態/計數器
  層級的細節。

## 下一步

生命週期主結構已落地（commit 516987e）：`run()` 依 `mode is None`
分派到 `_on_not_actionable()`（NOT_ACTIONABLE）或既有 `_on_*` handler
（ACTIONABLE），行為與重構前完全等價（167 測試全過）。剩下的實質
工作只有一項：**標定 ENEMY_REACTION_POPUP 的畫面錨點與 handler**——
待裝置。
