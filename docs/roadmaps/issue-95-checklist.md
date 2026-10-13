# #95 收尾檢查清單

> Type: working—#95 的執行清單；以 WIP 提交保存（`b25c932`），合併前刪除

下文的「replan」指 `docs/roadmaps/replan-main-loop.md`，「情境清單」指
`docs/roadmaps/main-loop-scenarios.md`。標記沿用 replan：［確認］＝使用者
明確確認；［提案］＝Claude 提出，等使用者裁定。已放棄的做法不留在本清單，
經過記在 replan、提交訊息與 ledger（`.superpowers/sdd/issue-95-checklist/progress.md`）。

## 1. #95 的結束條件

- ［確認，2026-10-13］三件工作完成就結束（replan §5.12.12）：
  1. 定出 UI shift planner、map sync planner、battle planner 的合約形狀，
     以及信念需要的欄位（第 7 節 C2、C3、C11、C5）。
  2. `DefaultPlanController.think` 依信念把情境交給對應的合約（第 7 節 C12）。
  3. 每個情境有一個用假物件寫的測試。
- ［確認，2026-10-13］啟發式的選擇與領域 planner 的邏輯不在 #95 定案。防止
  執行沒有進度的規則移出 #95，改由 #104 追蹤。
- ［確認］`src/ggge_ai_2` 的 pyright strict 零錯誤；不在實機上驗證（replan
  §5.12.13）。
- ［確認］#95 的票面依 replan 同步（replan §5.12.13）。
- ［確認］收尾見第 8 節。

## 2. 基線（2026-10-13，HEAD `b25c932`）

- `uv run pytest tests/ggge_ai_2 -q`：42 個測試通過。
- `uv run pyright src/ggge_ai_2 tests/ggge_ai_2`：0 個錯誤。
- 封存分支 `issue-95-agent-planner-draft`（`e1a6869`）只當參考，不合併。

## 3. 每個改動都遵守的規則

- 一個提交只有一個職責。提交訊息用 `/commit-message`，給使用者確認後提交。
- 合約在實作 `think` 的過程中確定（replan §5.12.12、§5.12.18）。
- 每個物件定義自己的結構；結構之間的轉換寫在編排的一方（replan §5.12.10）。
- 不加檢查 import 方向的測試或 lint（replan §5.8）。
- 註解只寫 why 與 warning 兩種（CLAUDE.md 的 Code comments 一節）。
- 測試的分類與位置依 replan §5.12.8。
- 每個改動結束時：`uv run pytest tests/ggge_ai_2 -q` 全部通過；`uv run pyright`
  在 `src/ggge_ai_2` 與 `tests/ggge_ai_2` 都是零錯誤。
- 牽涉時序、轉場、手勢的假設一律標成假說，向使用者確認。
- Claude 自己想加的結構（模組、型別、協定、測試、註解），先在對話中
  提出，經使用者裁定才寫。
- 寫給使用者讀的文字：每句都有主詞；代名詞與指代對象相距三句話內；
  項目代號要寫出所在文件與名稱。

## 4. 已完成

- 主迴圈：`2028181`、`2909b00`、`be01487`、`3d92679`（replan §5.12.18）。
- `Step` 由計畫提供預期、省電鎖由 reflex 解開：`90ff3a3`、`7e0d73c`、`234169d`。
  情境清單 3.1 完成。
- 隱藏戰鬥與體力不足的做法記入紀錄：`282bf3d`。
- #95 票面於 2026-10-11 依 `3d92679` 改寫（issuecomment-6107361184）；分支已推送。

## 5. 進行中

- [x] #95 同步到 `837cebe`：［確認，2026-10-13］標題與內文不改，以留言記錄
  （issuecomment-6140642049）。

## 6. 待討論

| 編號 | 題目 | 出處 | 擋住的改動 |
|---|---|---|---|
| T3 | `think` 怎麼選 | replan §5.3.3、§5.12.18 | C12 |
| T4 | 戰鬥情境 | replan §8 第 7 項 | C11 |
| T6 | map sync planner 的合約：注入的物件與流程、回傳的資料格式；點格三種結果怎麼寫進預期 | replan §8 第 9 項；情境清單第 5 節 1.6 | C3 |
| T8 | 隱藏戰鬥提早觸發時，重新規劃或 reflex | replan §8 第 10 項 | C12 |
| T7 | 新文件的路徑與文件類型 | replan §5.12.13 | 第 8 節 |

## 7. 改動清單

每個改動一個職責，附上處理的情境的假物件測試。plan controller 與它產出的
計畫只讀信念（replan §5.12.18）。

### C2. UI shift planner 的合約

- 職責：在 `agent/plan_controller.py` 定義 UI shift planner 的合約：從目前
  的 UI 狀態走向目標 UI 狀態的下一個 step。實作屬於 replan §7 的 S3。
- 情境清單：2.6、3.8 的進場與離場、4.3。

### C3. map sync planner 的合約

- 職責：在 `agent/plan_controller.py` 定義 map sync planner 的合約。實作屬於
  replan §7 的 S5。
- 擋住：T6。
- 情境清單：1.6、2.4、3.6、4.1、4.4；1.5、3.4、3.5 是實作細節。

### C11. battle planner 的合約

- 職責：在 `agent/plan_controller.py` 定義 battle planner 的合約。實作屬於
  replan §7 的 S7。
- 擋住：T4。
- 情境清單：2.1、2.3、2.5、3.7、3.8 的戰鬥部分。

### C5. 信念的欄位

- 職責：interpreter 與 uisim 各自加上自動的三種狀態（舊版
  `src/ggge_ai/runtime/screens.py` 的 off、on、active）與 '顯示方格' 是否
  開啟；信念加上隱藏戰鬥的三個屬性（情境清單第 5 節 3.2）；轉換與轉換測試
  跟著改。情境清單 4.2、4.3 的「隔線」就是設定頁的 '顯示方格'。
- 與讀這些欄位的 C12 相鄰提交，避免沒有讀者的欄位留在分支上。
- 情境清單：3.2、4.2、4.3。

### C12. `think` 的分派

- 職責：`DefaultPlanController` 的 `goal_reached` 與 `think` 依信念把情境交給
  C2、C3、C11 的合約，並包上 reflex。
- 擋住：T3、T8。需要 C2、C3、C5、C11。
- 情境清單：2.4、2.6、3.2、3.8、4.1、4.2、4.3。

## 8. 收尾

擋住：T7。

- [ ] 依 T7 的結論，把 replan 已定案的內容寫成 `ggge_ai_2` 自己的新文件。
- [ ] 經使用者同意，刪除 replan 與情境清單。
- [ ] 刪除本清單：用刪除提交拿掉，或把 `b25c932` 從分支上移除。
- [ ] 整個分支的 review。
- [ ] 合併到 dev，關閉 #95。推送與否由使用者決定。

## 9. 情境與改動的對照

每個情境的歸屬記在情境清單第 5 節。「已完成」的情境由主迴圈（`be01487`）
或 reflex（`234169d`）處理完畢。

| 情境清單編號 | 改動 |
|---|---|
| 1.1、1.4、1.7、2.2、3.3、3.9 | 已完成 |
| 1.3 | 不需改動 |
| 1.2、2.7 | 已完成；沒有進度的規則見 #104 |
| 3.1 | 已完成 |
| 1.5、3.4、3.5 | C3（實作細節） |
| 1.6、3.6、4.4 | C3 |
| 2.4、4.1 | C3、C12 |
| 2.1、2.3、2.5、3.7 | C11 |
| 2.6 | C2、C12 |
| 3.2 | C5、C12 |
| 3.8 | C2、C11、C12 |
| 4.2 | C5、C12 |
| 4.3 | C2、C5、C12 |
