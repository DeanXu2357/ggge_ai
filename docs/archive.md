# 歷史檔案庫（archive）

**本文件存放開發時再也不需要的 domain knowledge。** 除非要了解歷史脈絡
（某個決策當初為什麼這樣做、某個問題當年長什麼樣），日常開發不需要讀
這裡。所有內容都是被新架構取代的舊定義、演變歷程、或已解決問題的原始
記錄——熱資料一律以 `docs/` 其他文件與程式碼為準。

收錄原則（2026-07-14 使用者指示）：
- 舊的定義或演變歷程從熱文件移入此處。
- 已被新架構解決的問題（如主動索敵）從熱資料移除、存放於此。

## 目錄

1. [已被新架構解決的問題](#已被新架構解決的問題)
2. [設計演變歷程](#設計演變歷程)
3. [roadmap 歷史快照（2026-07-08 ～ 07-23）與初期計畫](#roadmap-歷史快照)
4. [初版系統架構文件（2026-07-04）](#初版系統架構文件)
5. [裝置控制技術研究（2026-07-04）](#裝置控制技術研究)
6. [舊 session handoff 提示詞（2026-07-07）](#舊-session-handoff)
7. [screen-map 的帳號時代紀錄](#screen-map-的帳號時代紀錄)

---

## 已被新架構解決的問題

| 問題 | 當年的解法 | 被什麼取代 |
|---|---|---|
| **主動索敵移動**（單位不知道往哪走） | `_seek_move_target` 啟發式優先鏈：畫面內敵弧 → 威脅格質心 → 星座錨定 tacmap → 偵察方向 heading（2026-07-04 起逐步演化） | Pilot 架構（GGGE_PILOT）：solver 的 `advice.move_world` 直接給出目標格，executor 做 world→screen 換算與移動格吸附。貪婪鏈只剩無意見類 fallback |
| **威脅格質心當敵方方向代理** | 紅「!」格質心 = 敵方大致方位（hub 粉紅弧污染 tacmap 時的繞道） | 關卡定義檔（layout 入檔，見 stage-definition-requirements.md）：敵人存在與位置由定義檔決定,不再靠單次掃描猜方向 |
| **hub 敵我 HSV 誤判的閾值修法** | 期待重新校準色相/飽和度帶域（issue #5） | 2026-07-14 判決:同幀混編下 H/S/V 統計完全重疊（fixture `our_turn_hub_mixed_factions`），逐像素色彩路線關閉;改走 sig-confirmation → 未來 uid 身分制 |
| **intel 面板預算**（固定 6 → 動態上限 12） | 節流開局敵情掃描的裝置時間 | 定案拿掉（2026-07-14）:冷掃全量（掃不完=報錯）、溫 cache 校驗,見 stage-definition-requirements.md |
| **每次進關重讀全部敵情** | 感知記憶化 cache（sig-keyed kit） | 關卡定義檔（layout+conditions+events、uid 身分制） |
| **EN 耗盡只能待機**（戰鬥控制器 v2 清單） | 規劃中的技能/支援鈕掃描 | 追蹤移至 GitHub issue #12（ActionCatalog 的畫面來源）;solver 已建模 EN 經濟與技能,執行端待 pilot 整合 |

## 設計演變歷程

### battle-phase-states 的 v1 → v2 演變（2026-07-09）

v1 盤點版本把重點放在「有哪些畫面狀態」的分類學上，被使用者指出沒有
講到生命週期本身；v2 重寫為 ACTIONABLE/NOT_ACTIONABLE 二元模型。

**ACTIONABLE 判斷依據的落地修正**:原始設計把 `unit_cards_present` 設計
成頂層 ACTIONABLE 的判斷依據，但落地寫程式碼前發現:沒有任何實機證據能
確認卡片列在 `UNIT_MOVE`/`WEAPON_SELECT` 子畫面底下是否仍可見——現有
語料庫裡唯一走到 select_unit 之後的場次不是卡在同一張畫面（20260706-
233158 的 mystery A stall），就是幀是 0-byte（凍機事故截斷）。貿然假設
等於賭一個沒有證據的假設，違反「沒有新截圖證據不要動閾值/假設」紀律。
改用 `mode is not None`（`MODE_LABELS` 任一命中）完全不用賭:這是既有
handler 已在用、已跑得動的訊號;重構純粹把「`mode is None` 時做什麼」
從匿名 fallback 變成有名字的方法（`_on_not_actionable`），行為完全不變
（167 測試全過，含專門釘住等價性的回歸測試）。

BATTLE_PREP 原設想要獨立於循環之外,是基於 `unit_cards_present` 版本的
舊設計;`mode is not None` 版本直接涵蓋它。

### combat-formulas 案例 2 的修正（2026-07-13）

案例 2 原記錄為「預測顯示 M 直接擊殺 A、合格的 B 未攔截」，衍生出
「支援防禦觸發條件未知」的異例待查。2026-07-13 使用者修正:預測實際
顯示 M 的傷害被 B 防禦、擊殺 B、A 反擊——與案例 1 同型，異例不存在。
自此全部實測都是「有合格支援者即攔截」。

### 感知記憶化 cache 的三機制設計（2026-07-05，被關卡定義檔取代）

原設計（agent-architecture.md 舊節）:①cache 匯入——`data/cache/stages/`
以 sig 為 key 存敵方 kit、`data/cache/roster/` 存圖鑑;同步流程=戰術地圖
掃位置（永遠現場）→敵方詳情查 cache→未命中現場讀→寫回。②建檔腳本——
驅動同一條讀取路徑窮舉掃描,數字 OCR、本地 LLM 只轉錄文字,人工 diff 後
入庫。③校驗機制（最後做）——開局抽查摘要卡 HP 與 cache 比對,不符標記
過期整關退回現場讀取。

被取代原因（2026-07-14，全文 stage-definition-requirements.md）:sig 是
機種指紋不是單位身分（同機種不同駕駛數值不同）;且 cache 只存 kit 不存
佈局/條件/事件,solver 拿到的仍是不完整賽局。演進為:後端 uid 身分制＋
關卡定義檔（layout+conditions+events）＋冷掃全量/溫 cache 校驗。
校驗機制的精神（畫面權威、抽查、過期退回）原樣保留。

### agent-architecture 實作順序清單（2026-07-05/06 版，多數已完成）

1. 戰鬥流水帳+run-scoped 黑板〔完成 07-05〕 2. 戰術地圖 v1〔完成 07-05〕
3. HARD 探測（E1 第12關回歸→E2）〔完成〕 4. 戰後歸因 v1〔完成〕
5. cache 匯入機制〔完成,將被定義檔取代〕 6. 敵方資訊面板 OCR〔完成〕
7. 戰略迴圈〔部分〕 8. cache 建檔腳本〔跳過,直接演進〕 9. 行動掃描器
v1〔issue #12〕 10. 內層 GOAP〔以 pilot 形式實現〕 11. 戰鬥模擬器 v0
〔完成〕 12. 跨機啟動順序規劃〔pilot v1 維持第一張卡〕 13. 模擬器 v1
（格子可達性/應戰彈窗）〔格子完成,彈窗=#3〕 14. 1.5-ply 站位安全
〔被 solver 取代〕 15. 戰役目標介面〔未做〕 16. LLM 整合〔部分:advisory
screen reader〕

工程評估基準（E1-E4）:E1 第12關回歸〔07-05 達成〕、E2 HARD 探測帶流水帳
〔07-05 達成〕、E3 戰略迴圈 farm→強化→再挑戰〔未達〕、E4 HARD 1 通關零
關卡專屬資料〔07-12 達成:Gundam X HARD 1 首戰通關 17/17 含隱藏戰〕。

---

## roadmap 歷史快照

（roadmap.md 於 2026-07-14 精簡時移入，2026-07-24 二次精簡再移入
07-14 白天 ～ 07-23 的快照與 07-17～19 離線工程重構紀錄;由新到舊排列,
含 2026-07-08 ～ 07-23 的全部舊暫停快照,以及 07-04 時代的初期計畫/
已完成清單/戰鬥控制器 v2 改進項目/鎖屏防護等節。當年的「現行計畫」明載不做
自建模擬器/MCTS,後經使用者 2026-07-06 澄清並非紅線,已由 expectiminimax
solver 取代——閱讀時注意時代脈絡。）

## 舊快照（2026-07-23 覆蓋驅動掃描重寫日）

**本日（純離線、未碰實機）**：07-23 凌晨 serpentine cutover 首次實機
survey_abort，根因＝**偵測器域錯配**（弧偵測 battle-zoom 校準 vs T3 最小
zoom 工作點，#26 07-20 已登記漏接；「垂直漂移污染」原說法經流水帳複核
推翻，見 map-scan-survey.md 更正段）。據使用者定案（手勢量退出座標計算、
幀間只用相對關係＋邊界目視、掃描改覆蓋驅動、邊界只在看見時成立）以協調者
管線分五批把地圖掃描整條重寫，**serpentine 退役**。下午起三輪實機驗證
（輪二~輪四）逐層剝洋蔥又落地批6／批7，收工 tip 見文末、**810 passed／
3 xfailed、ruff 綠**：

- **批1**（`932eb4f`）視覺原語：`read_map_lattice`（全幀格線外插＋截止緣
  ＝邊界目視證據）＋`cell_fingerprints`（逐格 Lab 指紋）＋fixtures。
- **批2**（`de1b0f1`／`83a257b`）`FrameObservation`＋`CellMap`：相對定位
  （邊界硬約束＋地形投票裕度，手勢量全面退出）／integrate／frontier／
  to_tacmap；標準答案端到端 27 台／23×24。
- **批3**（`984c95e`／`bbd0960`）`CoverageScanSource` 覆蓋迴圈＋回復協定
  ＋controller cutover（含 bring_to_view 同源改造，消滅 335px 假跳）＋
  退役 `pan_leg`／`_at_edge`／`SCAN_EDGE_RATIO`／serpentine；07-23 假南
  邊界回歸鎖死。
- **批4**（`e6849e2`／`8000baf`／`2b673f9`）LLM 定位第三層接線＋護欄＋
  probe；實跑裁決**no-ship**（gemma 本機 0/8 exact、係統性回 (0,0)），
  tier 落地上鎖但生產休眠、控制器不注入 llm、迴圈與純確定性版 bit 級
  一致（見 llm-localize-probe.md）。
- **批5**（`18ee1be`＋本文件收尾）cache bounds 預載：既存定義檔的
  `map_cols/map_rows` 當覆蓋掃描規劃 hint（frontier 外插＋預算放大），
  **紅線＝hint 永不成 registered edge，邊界仍必須目視看見**；實掃見到的邊
  與 hint 矛盾即丟棄、ledger 記 `cache_bounds_dropped`、退回純探索。
  schema 增 map size 欄（來源＝覆蓋掃描落地，符合 2026-07-05 cache 例外）。

**下午實機三輪（輪二~輪四，皆 sonnet 執行、裝置每輪零損耗）**：每輪都在
覆蓋掃描主體之前的不同層陣亡、每層都是離線測不到的真 bug，逐案定讞後
落地修復批（詳細證據鏈全在 live-verification-queue.md 佇列 1）：

- **輪二**（run 20260723-145815）FAIL 於 T3 前置：`zoom_at_max` 窄帶被
  密集編隊蓋掉誤判 → **批6**（`d13b26a`..`f35b39b`）寬帶 fallback＋pinch
  中心動態選空地（使用者指示）＋zoom 序列存幀。
- **輪三**（run 20260723-154731）T3 PASS（批6 生效），FAIL 於邊界偵測：
  seed/walk 越過真實西緣在星空種幽靈格線 → north=south 偽陽性 → 0 nudge
  假完成 → **批7**（`c1bd7a7`..`fb1ed3f`）亮度濾波＋自洽 gate＋起點錨定、
  frontier 語意分離（不一致態顯式 fail）、abort 路徑無條件釋放格線；
  實機幀入 fixture `west_in_view_20260723.png`。
- **輪四**（run 20260723-165948）FAIL 於回合入口（覆蓋掃描未觸達）：
  輪三殘留的**收合單位列表**（批7 之前的 abort 不釋放）讓 `_on_our_turn`
  的 `unit_cards_present` 誤判「無可行動單位」，tap 疑似誤標的
  `END_TURN_BTN=(275,182)` 反開單位比較 modal，41 次循環零進展後依紀律
  中止。**批8 修訂版設計已與使用者定案（見佇列 1），尚未開工**。
- 另落地：測試衛生修正（`b1a46e1`，RunBlackboard 流水帳導 tmp——pytest
  汙染真 data/runs/ 的假 run 自 07-21 起即存在，鑑識定讞後修除）；
  **probe B**（`04b2d24`）單圖 LLM 選 patch vs 確定性基準三模式量測，
  裁決「作為獨立定位層皆不可行」（alias 高分同調投票擊敗多數決；
  幾何護欄 verify_offset 被反證必要），LLM tier 維持休眠。

**恢復點＝批8（修訂版，使用者已核設計、待開工）**，之後輪五重跑冷探索：
1. **觀測三值化（治本）**：新 `unit_list_state(frame) → expanded/collapsed/
   unknown` 像素探針（切換鈕位置：展開 ▽(1970,780)、收合 ▲(1970,1010)）；
   `unit_cards_present` 消費者改吃三值，「收合／unknown」永不得當語意答案
   ——與掃描定案同一認識論（absence of evidence ≠ evidence of absence）。
   連帶修 `_set_unit_list_open` 自身的同款混淆（展開但卡條真空會被誤讀成
   收合而點錯切換鈕）。
2. **handler 前提契約（防線）**：`_on_our_turn` 下「無可行動單位」結論前，
   前提不滿足先修復（展開列表）再重讀；相位分類器已把關到 phase 層
   （輪四分類正確、敗在子狀態），前提檢查用廉價像素探針不加截圖成本。
3. **END_TURN_BTN=(275,182) 離線診斷**：用輪四截圖確認實際命中元素；
   有證據才改座標，否則標 live probe。回合本會自動推進，此鈕的必要性
   一併檢視。
4. **absence-audit**：全庫掃同型觀測（哪些 vision 讀值的 False 混合了
   「前提不成立」），揪兄弟 bug。
5. 佇列 1 回寫輪四＋批8 結果。
輪五協定沿用冷探索（cache 空、`GGGE_INTEL=1 GGGE_STAGE_ID`），批7 的
三項修復與掃描主體（nudge／frontier／回復協定）仍為零實機驗證。

**裝置現況（輪四收工）**：活動關 EX-2 IF 戰鬥 TURN 1 our-turn hub、
破壞數 0/15、剩 3 回合敗北限制、一台我方已行動（輪二貪婪攻擊）；
**格線 ON 殘留＋單位列表收合殘留**（輪三 abort、批7 前行為；批8 主修會
讓輪五開場自癒，或手動點 ▲(1970,1010) 展開）；unit-detail modal 已由
sonnet 手動關閉；adb libusb 正常；`data/cache/stages/` 空（冷探索中，
備份在 `data/cache/stages.bak-20260723/`）；戰局可放棄退體力。

**同日稍晚（規劃 session，純離線、未碰裝置）**：批8 範圍擴充定案——
往前追查發現 modal 清除邏輯（`is_unit_detail_modal` 觸發時點掉重試）
已在 `controller._clear_scan_obstruction`／`live_scan.CoverageScanSource
._clear_obstruction`／`map_view.return_to_top` 三處獨立重複實作，
`UNIT_DETAIL_CLOSE` 座標常數也有兩份宣告；批8 唯一沒有這層防護的正是
輪四摔倒的 `_set_unit_list_open`。**批8 完整規格（含此擴充）已落檔
[scan-flow-robustness-plan.md](scan-flow-robustness-plan.md)**，roadmap
本節之後只保留指標，todo 以該檔為準。委派迴圈規劃：opus worktree 開發
→ 主 session 驗證合併 → sonnet 上機驗證（＝輪五）→ 回報→下一輪。已完成
worktree 清理（16 個孤兒 worktree，15 個確認合併清除，1 個未合併
`worktree-agent-a6dfce2035d900d36`/`8b1b6df` LLM probe B 產出刻意保留
待使用者決定去留）。**卡點：`Agent` 工具 subagent 派遣額度 session 內
20/20 用滿、Round 1 opus dev 尚未派出**——新 session 開工前先調高
`CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION`（memory `delegation-execution
-model` 坑④），再照 scan-flow-robustness-plan.md「Round 1」直接派工，
不需重新規劃。

**2026-07-23 深夜（委派迴圈執行 session）**：額度已調 40（新 session 生效）。
**Round 1＝批8 落地合併**（`220d40c`..`2eeed9c` fast-forward，824 passed/
3 xfailed、ruff 綠；切換鈕實為「單位列表」文字標頭帶域模板、非 ▽/▲ 座標
——三張真像素 fixture 佐證的證據驅動偏差）。**輪五冷探索：FAIL 於
identify，但為歷來最深進度**——批8 回合入口自癒 PASS、T3 PASS、**覆蓋
掃描主體首次實機收斂**（97.6%、bounds 24×23、frontier 自然收斂），
identify 2/45 後 tap 中未行動我方機進移動模式、盲目重試致
SurveyIncomplete（詳細證據鏈＝佇列 1 輪五段）。**恢復點＝Round 1.5
（identify 疊層安全化，規格在 scan-flow-robustness-plan.md，已定讞待
開工）**，之後輪六同協定重跑。裝置末態：TURN 1「單位移動＋選擇武裝」
疊層（艾格沙貝選中未確認）、格線已釋放、cache 空。既有 flaky
`test_not_actionable` 計時競態定讞非本輪引入，收尾立 issue。

**Round 1.5＝identify 疊層安全化合併**（`ba29868`/`e6a8520`，831 tests
綠；視圖閘門先於 dock、move-overlay=ALLY 機制證據通道、return_to_top
嚴格脫出；t0135 實測單右 dock 0.995 偽 ally——閘門必要性的更強證據）。
**輪六：FAIL 於 identify 前置 `bring_to_view()`（`_nudges` 未初始化、
確定性崩潰），但覆蓋掃描主體 100% 收斂**（552/552、28 nudges、首擊
71%）；並引爆既有 late-arrival 缺陷（跳過簿記與 scout 直接選卡攻擊
一次）。**恢復點＝Round 1.6（navigator 生命週期＋late-arrival 歸位，
規格在 scan-flow-robustness-plan.md）**，之後輪七同協定重跑——Round
1.5 的 unit_move 通道在輪七才真正受測。裝置：TURN 1 hub、9/10 可行動、
cache 空。

**Round 1.6 合併（`3a69ffd`，834 tests 綠）→ 輪七 FAIL 於覆蓋掃描主體
（首擊 5.4% vs 輪六 71%、110 nudges 燒預算）**。三方鑑識定讞根因＝
**敵機選取殘留態**（比較 HUD＋紅色威脅色塊自 t0005 全程在場；螢幕錨定
HUD 投 (0,0) 假票壓過低重疊外推幀；`is_unit_detail_modal` 對此全盲）＋
refused 路徑無煞車無存證。**恢復點＝Round 1.7（選取殘留偵測與空地 tap
解除鏈＋定位飢餓煞車＋refused 原生存證，規格在
scan-flow-robustness-plan.md）**，之後輪八同協定——開場殘留在場即前置
防禦首戰。裝置：TURN 1 hub、殘留在場勿手動清、9/10 可行動、cache 空。

## 舊快照（2026-07-21 協調者管線日）

**本日（純離線、未碰實機、adb no permissions 待 seat0 桌面登入）**：
使用者定調兩件工作模式：①**操作/辨識分離**入 agent-architecture.md
設計原則 5（辨識收 frame 參數可 fixture 驗證、流程拆操作/狀態確認、
每條實機流程配獨立 probe 腳本）；②**協調者 pipeline 正式化**（主
session 寫 plan → opus subagent worktree 分支開發 → fable5 subagent
針對性驗證 → 主 session 整合；網路調查產出先與使用者核對再落檔）。
十個任務全數走完 pipeline、tip 7fe8270、**706 tests/3 xfailed、ruff 綠**：

- **T1** 盤面狀態辨識庫：`map_view.classify_frame` 純函式＋表驅動偵測器
  ＋封閉詞彙、`vision.grid_pitch`/`zoom_at_max`（閾值 113=98.5/127.5
  中點）、11 fixture 幾乎全重用既有圖。
- **T2** 切格線流程：三像素探針公開化（`read_grid_setting` 等）、六步
  操作/確認交替、設定頁 ON 真圖 fixture×2（OFF 態全庫無樣本、入缺樣
  清單）、`scripts/grid_toggle_probe.py`。
- **T3** zoom 冷掃前置：`Pincher` 注入（uiautomator gesture 工廠）、
  full_scan 前置序列（退頂層→開格→拉最遠→`zoom_at_max` 驗證）、
  兩輪不過=SurveyIncomplete fail-fast（**每場首回合都會攔，錯 zoom
  掃描=垃圾**）；probe try/finally、`ensure_battle_grid` 共用。
- **T4 批A**：`UnitBelief.hp_turn` 鮮度欄（`_set_hp` 統一收斂、estimate/
  定義檔不蓋章）＋`board_belief` 每回合快照（timeline 閘門含 turn 1）。
- **T5 批B**：`battle/audit.py` 騎 `_set_hp` 覆寫前對帳、殘差記
  `unattributed_damage`（v1 容差 0 資料最大化）；`UnitBelief.uid`。
- **T6 批C**：`agent/closure.py`＋`scripts/audit_run.py`——board_belief
  錨定重建 HP 時間線、完備性分數=1−未解殘差率（隱含歸功、擊殺殘差
  另歸類、第三方只 flag 方向）、舊格式優雅降級。
- **T7** classify_frame 加 `settings` 態；驗證抓到 major：
  `is_battle_tab_selected` 單像素在 hub 淺色地形誤判（444 張掃出）→
  返修為底線幾何（線段比例＋上下護欄），複掃 9→2 僅剩真設定頁，
  回歸 fixture 釘住。
- **T8** 單位詳情「基本資訊」視圖：`classify_unit_detail`（切換鈕文字
  判別，`is_unit_detail_modal` 對 basic 視圖會誤 True）、
  `read_unit_detail_basic`（HP/EN/SP/**MP** 全欄 OCR 驗證、`basic` 字型
  =modal 複本＋slash）；單樣本過擬合風險入缺樣清單；form D（動作選單
  MP）渲染讀不出、刻意跳過。
- **T9/T9b** MP/激昂調查（`docs/mp-tension.md` 假設庫）＋使用者裁決：
  MP=激昂 0-12 滿 12 超一擊；**一般機不歸零、跨回合完整保留（使用者
  證實）**；必暴/強化超一擊=特殊機專屬；階段表（4/8/12→+10/20/30%
  加算桶）7 源一致**定案進機制層**；「出入」歸因=暴擊倍率獨立軸
  （1.1/1.2/1.2/1.3）＋加算桶；MP 增減值三源互斥=打表最高優先。
- **T10 佔位**：`sim/tension.py` 已定案常數＋`compute_damage` warn-once
  「MP 未建模」；完整建模等 C2 打表（使用者裁決）。發現 `formulas.py`
  的 CRIT_HIGH_MORALE/CRIT_SUPER 是死常數，接線時收斂單一權威。

**新文件**：`live-verification-queue.md`（實機驗證佇列＋缺樣本清單）、
`live-test-plan.md`（**run-book：場次 A 非破壞蒐樣→B 冷掃全鏈路→C 戰鬥
＋C2 MP 打表→D 機會型；BLOCKING 攔截點協定=停下請使用者操作到指定
畫面→session 截圖→探針驗收**）、`mp-tension.md`。

**恢復點**：①adb 恢復（seat0 桌面實體登入）後照 live-test-plan 逐場
執行——場次 A 含 OFF 態設定頁/基本資訊視圖第二樣本等缺樣攔截，場次 B
=cutover 冷掃全鏈路首驗（T3 後 zoom 失敗會 survey_abort，首跑留意）；
②T10 完整建模等 C2 打表定案 MP 增減值；③驗證回報的 minor 殘項：T5
prep→forecast 跨 source 斷言、T6 run_summary 雙場加權測試、tension
出界測試，後續順手。

**裝置現況**：本日未碰實機；戰局仍停活動關 TURN 1 our-turn hub（可
放棄退體力）；`data/cache/stages/` ex2if schema-3 定義檔在。

## 舊快照（2026-07-20 離線地圖拼接＋標準答案落地）

**本 session（07-19 深夜～07-20，純離線＋subagent 讀圖，未操作實機）**：
map-scan-survey.md 的實作藍圖第一階段（無陣營位置池）離線落地，issue #26。
- **fixture series** `tests/fixtures/vision/map_scan/ex2if_20260719/`：使用者
  手動平移 9 幀全幀 PNG＋manifest（順序/方向標籤）＋ground_truth v2＋
  standard_answer。
- **`vision.find_unit_density_peaks`**：最小 zoom 下弧與隊徽環合體、舊形狀閘
  全盲 → 三色帶聯集＋單位尺寸 box filter 密度峰值。整數計數（float32 平行
  分塊不確定性會翻 plateau 峰）；NMS 局部極大 31px／貪婪去重 80px 分離
  （80px 膨脹窗會讓強鄰高原吞掉弱單位）；橫幅 HUD 挖洞挖在色罩（挖密度圖
  會把峰擠到洞緣）。單幀 recall 104/104。
- **`battle/map_stitch.py` 離線拼接**：配對假設投票＋pan 方向提示閘門＋池
  支持度計分；ICP 精修（平均殘差、半徑 45<半格防 alias）；弱幀受限重定位
  （≤250px；全域 locate 曾跳 890px 對到對面星座）；靜點濾除 ≥4/9 幀（2 幀
  會誤殺螢幕位置巧合的真單位）；**phase correlation 整條移除**（格線週期
  紋理高分假鎖近零位移）。
- **標準答案（使用者定案的工作順序：先讀圖產標準答案、程式以對到它為驗收）**：
  9 個並行 subagent 各精讀一幀（4x4 分塊窮舉）→ 132 觀測 → 27 唯一單位；
  四邊界 subagent 實測（東緣其實有入鏡，pt6/8/9 互證）→ 地圖 23x24 格、
  單位絕對格座標；s20 淡綠大型機 2x2 footprint。管線交叉驗證 **27/27 零漏**，
  多出的全是大型單位多峰（測試上限 14 把關）。
- **StageUnit.footprint＋`scripts/export_stage_def.py`**：標準答案→schema-2
  定義檔（faction=unknown、status=positions_only，warm path 不採、惰性）。
- 561 tests/3 xfail、ruff 綠。工具：`scripts/replay_map_scan.py`（重放拼接
  ＋標註合成圖）。
- **業務知識**：①我方出擊編隊＝鈷藍環＋白色雙V階級徽（比弧色可靠的我方
  線索，第二階段可用）；②**佔格是內容、環幾何推不出來**——兩個大型單位
  都被環量測誤判（戰艦實為 3x2=6 格、大型機實為上緣貼齊所在列往下 2x2，
  皆使用者遊戲內確認更正），佔格權威=使用者/遊戲內驗證，候選機制=選取時
  移動範圍/阻擋實測（未實作）；「環心壓格線交叉點」只當疑似大型單位旗標；
  ③平移拼接在畫面邊緣有透視失真（東緣 pt1 極右量測 vs 中央量測差 1.5 格），
  邊界量測取近畫面中心幀。
- **07-20 續（定案 6 實作完結）**：`battle/map_grid.py` 格相對位置整合
  落地——每幀實測格線鏈（局部間距步進，無固定格距）、單位夾線落格、
  幀間整數格偏移（投票＋配對像素位移方向＋池支持度三重裁決）、邊界=
  正交線脊終止點。ex2if 驗收 25/25＋大型單位區塊內、零衝突。**管線
  抓到標準答案列原點偏一列**（舊像素÷固定格距在透視漸變 84→102px 下
  累積半格），使用者遊戲內雙向驗證（北空 5 排/南空 7 排、s26 從下數
  第 8 格）後定案修正；地圖 23 欄x24 列（欄列各有多幀互證＋迴圈閉合）。
  standard_answer/定義檔已更新；test_map_grid 3 項驗收。564 tests 綠。
- **07-20 續2（出擊機拆分＋雙V驗證，未碰實機）**：使用者指認 27 單位中
  10 台為我方出擊機（兩隊各 5 slot，順序即號位）→ **schema-3
  deploy_slots** 落地（92744bf）：格位=關卡內容可 cache、站誰=每次出擊
  永不 cache、號位→格位對應存 `DeploySlot.observed` 累積假設（編隊號位=
  未來規劃可指派變數，使用者確認遊戲自動擺位但格子固定）；ex2if 定義檔
  重匯出 17 units＋10 slots；567 tests/3 xfail 綠。subagent 幀2/幀3 互證
  雙V徽：**鈷藍環＋實心白VV=出擊機判別式 10/10 零誤判**；青綠環=特殊
  狀態（s04 勝利目標標記帶「敵軍全滅」浮字、s27 VV變體）——詳見
  map-scan-survey.md 07-20 深夜段。同步盤面流程討論定調：掃描前置補
  「zoom 拉到最遠」（現有標定即最遠 zoom，殘餘參數化降級為穩健性項）；
  流程解耦四接縫=FrameSource（可抽換取圖）/read_board（純函式）/
  inspect_unit（單一函式點開讀取）/backfill。
- **07-20 續3（FrameSource 批1＋批1.5 落地，未碰實機）**：同步盤面解耦
  開工。批1（16d4651）＝取圖/判讀接縫：`battle/frame_source.py`
  （MapFrame=image+hint+measured_shift、FrameSource Protocol、
  FixtureFrameSource manifest 重放）＋`map_grid.read_board` 純函式入口，
  replay 腳本與測試改走接縫。批1.5（9c4b538）＝integrate 逐軸多通道
  仲裁，回應使用者「單位集中一隅的地圖拼不拼得起來」：定位骨幹改為
  地圖本身——邊界絕對註冊＋格線相位解纏（實測位移准到 1/3 格距即可）
  ＋單位投票降為佐證；逐軸定位（單軸失敗的無單位幀仍當另一軸橋樑）；
  通道衝突 fail-loud。驗收含極端情境測試（單位只留末幀，全鏈無單位
  定位、offset 與密集板逐幀一致）。學到：單幀偵測有內容偏差（s24 幀9
  偏東一格）——多幀支持與第二階段點擊複驗是內容保真度的正解。
  573 tests/3 xfail 綠。**批2（controller 直接替換）發現時序耦合：舊弧色
  census 的下游（survey/敵我分流）要等第二階段 inspect_unit 才有替代品，
  cutover 應與第二階段同批落地**——順序改為批3a（LiveScanSource 離線
  搬遷）＋第二階段實作 → 一次切換。
- **07-20 續4（批3a＋第二階段離線落地，未碰實機）**：使用者定調工作
  順序=先偵查/敵我辨識、敵我辨識用介面包裝。四個 commit：
  ①批3a（61bb69d）`battle/live_scan.py` LiveScanSource——serpentine
  走法整段搬進 FrameSource 接縫（無陣營導航地標池、逐腿量測、吞滑
  動換起點、彈窗關閉；measured_shift=負鏡頭位移，_pixel_matches_hint
  釘死符號），pan/scan 常數單一來源移入、controller 回頭 import；
  ②FactionIdentifier 介面（02a7cab）`battle/faction.py`——Protocol
  ＋DockBannerIdentifier（左=敵/右=我、雙命中拒判、永不猜測），
  vision.summary_anchor_score 共用 0.88 灰階尺；
  ③右停靠標定（ff50952）**data/runs 考古取代實機取樣**：subagent 掃
  449 截圖＋1092 流水帳幀（689 幀右停靠），定案右停靠=左佈局「平移」
  非鏡像（機體+818/駕駛+1652、y 全等），RIGHT_DOCK_REGION=
  (1388,175,100,65) 沿用模板與閾值，跨四地圖 0.918-0.997；坑：
  battle_prep/weapon_select 右面板同幾何（雙卡同框 fixture 入庫當
  拒判回歸釘）；考古全樣本佐證停靠邊定案零反例；
  ④survey identify 模式（fea83ee）——survey_stage 增 identifier 注入
  （None=舊路徑，controller 未切）：左停靠→面板鏈入 layout、右停靠
  →DeploySlot.cell＋ally_indices；幽靈證據兩型（同格重複 twin＋無
  橫幅貼近已識我方）。589 tests/3 xfail 綠。
- **07-20 續5（不停頓事件討論定調＋規劃，未碰實機、與續4 平行的
  討論線）**：地圖砲等「不停下來讓我方互動」的敵方事件感知方案與
  使用者逐輪討論定案，開 issue #27＋規劃全文 `docs/silent-events.md`。
  要點：①威脅圖示（移動選格內驚嘆號=敵攻擊範圍、鎖定+驚嘆號=地圖砲
  射程，自動顯示）成為地圖砲主接縫，敵方回合即時偵測正式放棄（動畫
  夾雜各單位行動間無法定時取樣，使用者實測知識）；②戰況紀錄查無此
  功能；③**流水帳完備性標準＝離線可推導性**定調（生成模型識別、非
  軌跡重播；即時單發不逆推、離線全場脈絡歸因；暴擊靠殘差聚類樣本群
  識別），同步回答 stage-definition-requirements 開放問題 4；④敵方
  策略假設庫（SRPG 原型庫＋逐機計分＋預測準確率量尺＋min 兜底）
  可行性確認但**往後排**，process-scoped 不入檔（使用者放棄跨執行
  留存）。優先序裁決：批A 資料保存（turn-boundary 信念快照＋tracker
  HP 鮮度欄）→ 批B HP 對帳（audit，騎既有數值讀點、殘差記
  unattributed_damage、與 reconcile.py 單發歸因分工）→ 批C 帳目閉合
  檢查（離線腳本、未解殘差率=完備性分數）先行——一邊開發一邊累積
  數據；批D 樣本蒐集被動並行；批E 威脅圖示偵測器／批F sim MAP 建模
  等樣本與第二階段；地圖砲規格（只打我方/必中/無支援防禦/移動前
  限定/次數制）已錄入 silent-events.md §1。
- **常備提醒**：遇到有 MAP 敵機的關卡先蒐樣本——capture 移動選格
  畫面（兩類威脅圖示）＋該敵機武裝面板，存 PNG（silent-events.md
  批D）；蒐到前批E 不開工。
- **07-20 續5（批2 cutover 落地，未碰實機）**：使用者拍板（A）第三方
  v1 左停靠一律 enemy 可、但**敵我辨識必須有明確邊界**（介面收口，
  實作內容可慢慢改）；（B）經解釋後同意 seed 吃完整星座。一次切換：
  ①tacmap 無陣營化（`units`＋`threats` 兩池；locate/anchor 改全池
  假設）；②`identity.seed` 完整星座（layout ∪ deploy_slots，deploy
  缺席=不滿編可容忍）＋**共識錨定**取代最西北角錨（每個 (格,點)
  配對提案原點、互配對數投票，我方站極西/極西出擊格空置都不再剪切
  網格）；SeedReport 增 deploy_points；③`observe.build_battle_state`
  改統一證據階梯（resolver 身分→tracker 我方 sig→census 我方位置→
  丟棄記註），**hub_poisoned 特例整個刪除**——任何弧色都不是陣營
  判定；④controller：`_ally_points`（census 我方位置，行動後畢業到
  tracker sig）＋`faction_identifier` 注入欄位（陣營唯一出口）、
  `_ensure_stage_definition_inner` 改 identifier 模式（cold seed 連
  我方一起點名=identify 的免費交叉驗證）、warm 採 seed.deploy_points、
  `_scout` 全掃改 LiveScanSource（controller 舊 serpentine/_pan_leg
  全刪，`_navigator()` 共享 tacmap 當 bring_to_view 地標池）、
  hint/resync/sig_refresh/reinforcement 全改「已識別身分＋known ally
  過濾」。測試面 6 檔重寫/調整。
- **恢復點（實機驗證 pending）**：①cutover 後全鏈路未經實機——冷掃
  survey identify 全流程（LiveScanSource 走圖→逐台點擊分流→完整星座
  點名）需一輪實戰；裝置 adb 目前 unauthorized，需使用者在手機上
  重新授權 USB 偵錯；②出擊機「鈷藍環＋白VV」輔助偵測器未實作；
  ③#24 冷掃太空圖提早收工、#25 掃描期格線、縮放 sendevent 照舊；
  ④第三方判別=未來的 FactionIdentifier 通道（介面已收口）。
- **裝置現況**：本 session 未碰實機。戰局仍停在活動關 TURN 1 our-turn hub
  （可放棄退體力）；`data/cache/stages/` 已重建 ex2if schema-3 定義檔
  （positions_only、warm path 不採）。

## 舊快照（2026-07-19 晚 S9d 應戰 UI 辨識落地＋S0-S8 批次）

**S9d 辨識落地（2026-07-19 晚，純離線、未碰實機）**：照 `docs/battle-prep-ui.md`
§9 vision 清單全數接進程式，20 張 20260719 PNG fixture 離線驗證：
- `vision.read_reaction_stance_menu`：dodge 圖示定錨（**像素證據推翻「錨點隨武器
  數右移」——動作列是固定槽位格**，dodge (1540,940)、defend (1352,940)、武器往左
  pitch 187）、defend/shield 靠鈕圖示互斥判別（裁片相關 −0.12）、EN 黃字定武器槽
  佔用、鈕心 V≥120 判可用（**開放假設：SHORT 無確認可用樣本，V 閘門可能誤殺深色
  可用圖示，S10 實戰驗證**）。回傳 stance→tap（`ReactionStanceMenu`）。
- `read_battle_prep_forecast`：`hit_pct` 改頭像列掃描 `read_avatar_hits`（列置中
  x≈963、pitch 200、pct 白字左緣＝頭像圓心 x、專用 `hit` 字型**缺 '3'**；應戰取
  紅環、攻擊取最右藍環）；`support_defense` 標籤模板（-應戰- bool／-攻擊- None）。
- OCR 三修：hud `6_c` 修 14168→14188；中央攻/反 48px 大字是另一字體、hud 字模把
  8/9/5 誤讀成 6（163188→163168 等四例，subagent 逐位轉錄裁決）→ 專用 `attack`
  字型；hit% 字體 hud 讀不動（'0'→'1'）→ 專用 `hit` 字型。
- 標定連帶抓到 `tracker.on_battle_prep` 陣營映射 bug：舊碼假設 -攻擊- 時左面板
  是我方，實測**左面板永遠是敵方**（右我左敵、兩變體皆然）→ 改為固定映射
  （-攻擊- prep 的信念更新原本左右反貼）。
- 15 個新 fixture JSON（7 forecast 全欄位＋4 stance 選單＋4 拒讀負樣本）；
  521 tests/3 xfail、ruff 全綠。**controller/sim 未動**。

**裝置現況**：前段 session USB 全程在線健康（`R5CRC37JBYJ device`、Awake、**無凍機**，
遊戲 RANK 23、體力 95/108）。使用者選「直接跑實機」（接受凍機風險，未先做
memtest86+/platform-tools）並授權主對話直接讀圖（破 screenshot-cost-discipline、
該 session 限定，**辨識落地 session 未沿用**——目視標定/轉錄一律走 subagent）。
手機省電觸控鎖曾因對話中閒置逾時觸發一次、使用者手動解，
Keyguard 本可處理（見 [[stage-clear-loop-status]]「battery-saver touch lock」）。

**S9d 標定成果（2026-07-19 白天 session）**：應戰 stance UI 已實機標定完成。
- 產出：`docs/battle-prep-ui.md`（正式地圖）＋`tests/fixtures/vision/forecast/`
  10 張 PNG fixture＋`reaction_live_20260719.md`（逐步記錄）＋2 memory
  （[[battle-prep-ui-map]]、[[forecast-lowerbound-enemy-defense-ai]]）。
- 標定：陣營右我左敵（攻擊/應戰皆然）、is_reaction＝標題、stance 相對定位錨點策略
  （閃避最右錨/防禦次右/counter 武器往左 pitch≈170、亮度 V 分辨可用）、defend 減傷20%
  ／dodge 敵命中-20%（效果卡＋forecast delta 驗證）、命中率＝頭像上方、攻擊順序＝
  頭像①②③（動態）、支援攻擊/支援反擊順序。
- 機制知識（sim/solver 建模需求）：forecast 傷害＝保守下界（KILL 才確定擊殺、
  無 KILL≠打不死）、敵方 AI 反擊會死就防禦保命、賭暴擊/降防欺敵；「①殺主單位→
  反擊階段全取消（含支援反擊）」sim 已建模（core.py:873），此塊無需改。

**S9d controller 應戰接線（2026-07-19 晚，離線完成、待實機驗證）**：
`_choose_reaction_stance` 改消費 `read_reaction_stance_menu`，刪
`REACTION_OPTION_TAPS` 固定表。流程＝算術定位我方頭像槽
（`vision.defender_avatar_slot`：頭像列置中 963/pitch200，token 數＋盾標籤＋
奇偶約束唯一解最右槽，5/5 fixture 驗證；顏色環偵測在藍水面地圖誤判、棄用）
→ tap 開選單（已開跳過）→ 讀選單 → advise_reaction（allowed_stances=選單
集合）→ stance/武器 tap（武器假設＝spec 順序左到右）→ 行動選擇 (2042,924)
估計值 → 共用開始戰鬥。fail-fast：ungrounded/avatar_not_found/
menu_unreadable/stance_unavailable/weapon_unmapped/weapon_disabled。
533 tests/3 xfail、ruff 綠。

**2026-07-19 深夜：實機驗證第一輪暴露五問題、全數修復（活動關「最終驗證
STAGE EX-2 IF」戰局停在 TURN 1 當標定場）**：
- ① story 錨點漏 ☰ 左移變體（活動關出擊劇情卡分類）→ manifest region 加寬
  ＋screen_score fixture（c113e89）。② Keyguard 省電鎖「淡出態」盲點（圖示
  隱藏、tap 全被吃）→ 中性 poke 喚醒再驗，實戰多次自動解鎖（2589ed3）。
  ③ survey 詳情卡固定右停靠點位在左停靠關卡打空 dismiss → 雙停靠序列
  （87dc7b4）。④ #24 serpentine per-leg 流水帳（d7e4df0；收縮量測窗假設
  實測證偽——循環相關繞回，窗寬須 ≥2× 平移）。⑤ **#25 顯示方格落地**：
  戰鬥選單→設定→戰鬥籤全路徑實機標定（`docs/battle-settings-ui.md`，
  AUTO戰鬥紅線防呆）、`battle/settings.py` toggle 驅動（fail-soft）、
  `vision.read_grid_lattice`（直線 pitch≈128、橫線 108→123 縱向透視 →
  原始線位、三重閘拒假格網）＋`snap_to_lattice` 弧吸附格心、serpentine
  前開掃畢關。548 tests/3 xfail、ruff 綠。
- 標定副產物：戰鬥選單「勝利條件」鈕＝戰鬥中讀勝利條件的第二入口；
  空格點擊出現青色格子選取框＝格幾何備選信號。

**2026-07-19 深夜：十輪實機迭代收攏（全記錄見
[map-scan-survey.md](map-scan-survey.md)）**：掃描/survey 十輪未全通但每輪
確診一層——story ☰ 變體、Keyguard 淡出態、卡片停靠、per-leg 取證、角錨定、
累積基準量測、地標接力、動態空地起點、彈窗凍結（使用者目擊定案）。
**使用者兩大新定案**：① 掃描產出=完整地圖（角錨定、邊界權威）；
② **敵我辨識延後二階段——第一階段全單位無陣營入 sim，第二階段點擊看
橫幅停靠邊（左上=敵、右上=我），捨棄血條顏色判別**（同時解釋卡片換邊
之謎：停靠邊=陣營）。11 個 commit、555 tests/3 xfail 綠。

**恢復點（新 session 從這裡開始）**：① 讀 `docs/map-scan-survey.md`——
設計定案五條＋實作藍圖＋未完成清單都在裡面；首務＝**兩階段敵我辨識
實作**（tacmap 無陣營化＋橫幅停靠邊判陣營；右停靠我方橫幅需一張標定
截圖）。② 應戰四假設驗證仍排在 survey 全通之後（battle-prep-ui.md §9）。
③ 裝置：活動關戰局停在 TURN 1 hub（可放棄退體力）、stages cache 已清、
省電鎖常駐 Keyguard 自理。重跑前 `discord-notify` 通知使用者（指示不變）。

**還差的截圖情境（待使用者實機截圖）**：
1. ~~`support_defense` 畫面~~ **已於 2026-07-19 取得**（reaction_support_defense_20260719.png，
   盾圖示「支援防禦」標籤＝標定依據）。
2. ~~應戰多武裝機體選單~~ **已取得**（reaction_shield_menu：F91 5 武器、pitch~170、
   錨點隨武器數移動→須模板定位錨點）。
3. ~~`shield` 選項~~ **已取得**（reaction_shield_menu：有盾機體防禦鈕＝shield 減40%＝
   SHIELD_MULTIPLIER 0.6、非獨立選項；修正先前 defend/shield 判斷）。
4.（可選）敵方 AI 保命實例（選目標顯 KILL→進戰鬥準備敵改防禦、KILL 消失）、
   暴擊武裝 forecast 下界顯示、技能發動後流程。

**規劃定稿**：stage-definition＋uid 身分制＋M8 雙行為 observer 合併為
**S0-S10 批次**（計畫全文 `~/.claude/plans/nifty-forging-sonnet.md`；
需求 docs/stage-definition-requirements.md）。使用者三個修正定調：
①hub 誤判歸根究底是 observer 元件缺陷→**S0 元件除錯先行**，
「敵人存不存在由定義檔決定」的補償性設計拿掉（定義檔只當 turn-1
開局先驗與身分描述）；②**弧色只當第一層啟發式**，我方可控單位權威=
hub 下方可操作單位卡條；③指定截圖當 observer 端到端實測案例
（observer_board fixture 機制）。舊 Stage B/C 收編 S9/S10（B0 作廢）；
執行節奏=S1 完成後停下給使用者過目 schema。

**S0 成果（413 測試/3 xfail、ruff 綠、replay 閘門與基準一致）**：

1. **d32430f observe 證據分層**：poisoned 掃描上無敵方 sig 對位的
   紅帶弧，先對位 tracker ally 信念（卡條驅動的 activation 錨定鏈）
   →回收為未行動我方；對不上才丟棄。敵方 sig 優先權、乾淨掃描路徑
   不變。
2. **3676323 vision.count_unit_cards**：卡底藍 HP 條計數（pitch
   175px；藍條寬=剩餘 HP 比例，實測 92/66/18px 受傷條，12px 下限；
   亮度剖面會被亮地形淹沒不可用；卡條實延伸至 x≈1949，舊 900px box
   只見 5 張）。select_unit ledger 事件帶 cards 欄位；`_build_board`
   缺額 note（cards>盤面我方＝未來 M8-① resync 觸發訊號）；replay
   增 cards 對比；4 張 PNG fixture（7/6/10/0，subagent 目視 ground
   truth）＋合成測試釘閘門。
3. **ec72087 observer_board check**：真實截圖＋標注先驗（tracker
   信念/intel 位置）→斷言解析後盤面陣營數；mixed_factions（3 粉紅
   回收＋敵恰 1）與 pink_bug（9 假敵→4 回收 0 敵）兩案例釘住修復。

**S0 判定紀錄**：弧結構差異（敵弧維持紅左＋橙右雙色調 vs 未行動我方
全寬粉紅＋黃上線，`yellow_only` 欄 32 vs 0）只有 n=1 敵樣本→僅當
啟發式不當權威；相位邊界快照離線證據足（phase_start_clean 乾淨、
位置攜帶由遊戲規則保證），捕捉時機歸 S9；卡條語義實測=未行動可操作
列表（回合起點=存活數、隨啟動遞減、擊殺再動會補卡回升→單調性僅
advisory）。

**S0 未竟（歸 S9 實機）**：自機卡/敵機卡判別（已知風險①的關閉條件）、
相位邊界快照的捕捉時機標定。

**S1-S4 已落地（461 passed/3 xfail、ruff 綠）**：S1 schema v2
（e9d4064，使用者已過目放行）；S2 條件驅動 Objective（34ddcf4——
terminal 回終局值、bounds 隨附否則 Star1 不健全、預設路徑與現行為
等值有多 seed 守衛、depth-1 斬首盤打指揮官/素設定打雜兵對照）；
S3 sim events（8d88c70——**pending_events＋fired_events 兩個 tuple
都進 key()**：within_turn 視窗會「過期不觸發」，只放 pending 會讓
已觸發/已過期在 weaken 靜態值不進 key 下碰撞；拆增援口案例=solver
先殺別隻、等視窗過期再殺標記敵）；S4 IdentityResolver（ce2855f——
seed 貪婪雙射＋refresh 互斥唯一鄰居兩套配對、sig 只當候選過濾、
passthrough 模式供 replay）。

**S5 身分翻轉已落地（fdd847f，465 passed/3 xfail、ruff 綠）**：盤面
unit_id/tracker 信念鍵/SimExpectation id/executor 目標驗證全講 uid，
sig 降純證據；controller 與 tracker 共用單一 resolver（canonical 登錄
序一致）；我方永遠走 "sig:<hex>" 降級 uid（我方身分不進定義檔）；
`target_ok` 複合驗證（預期 sig 容差＋共享 sig 時 HP 信念交叉）。
replay 閘門：reader 命中率不動、tracker 一致性同基準（33 信念/1 死）；
dead-sig advisory 變多＝舊 kill_check 精確查 key 漏登記擊殺的修正。
**殘餘風險（S10 要量測）**：同機種雙機開局同滿血→HP 交叉檢查無法
分辨雙胞胎，錯鎖對象可通過驗證直到血量分歧；緩解案（錨定目標世界
位置）留 S10 實測後定。

**S6 已落地（f021ef1，466 passed/3 xfail）**：`survey_stage` 全量
fail-loud（每台開面板無 sig 去重、pilot_hint 快照、SurveyIncomplete
不寫部分檔）＋`validate_stage`（幾何普查免費＋共享 sig 組優先抽查）；
controller `_ensure_stage_definition` 取代 `_acquire_intel_once`（溫啟
採用=seeded resolver 換入 tracker＋uid specs＋開局信念；否則冷掃；
survey_abort 與 pilot_abort 同軌）；`tacmap.locate()`＋`_bring_to_view`
pan 導航（S9b 實機驗證）；GGGE_INTEL 必附 stage_id、GGGE_PILOT 必開
INTEL；IntelBudget 與 stage_cache.py 退役。

**S7 已落地（f11cec4）**：M8-①`_board_with_resync`（expected_alive
當分母、缺敵一回合一次局部重掃；pilot 空盤先 resync 再問、仍空=
`board_empty_after_resync` abort；擊殺在破壞數判決處 `register_death`
讓分母跟著降）；M8-③ 盈餘無主紅弧（已解析敵=expected 才算，缺額歸
resync、我方缺額歸卡條，避免 tap 粉紅我方）→`stage_event_observed`
＋軟性增量 survey＋發 uid 寫回定義檔 events（保守 turn_start 觸發、
原始觀測隨檔）；M8-④ `stage_sim.to_sim_state`（layout＋增援同格網
量化、增援模板留在 EventTable 不上開局盤、conditions 編譯 objective）
＋斬首關離線解到終局 smoke。

**S8 已落地（e0eccb7）**：M8-② 離線半——`vision.ReactionPopup`＋
`read_reaction_popup`（S9d 模板落地前回 None）；`solve_reaction`
**根節點枚舉限制在彈窗實際提供的選項**（樹內防禦節點不受限；空集=
無決策）；`advise_reaction(allowed_stances, allow_support_defend)`；
controller `_maybe_handle_reaction` 在 NOT_ACTIONABLE 最優先（雙名牌
ground 到 uid 否則 `reaction_ungrounded` abort；stance 座標未標定=
`reaction_taps_uncalibrated` abort，座標表 `REACTION_OPTION_TAPS`
留給 S9d；貪婪模式只記 ledger 不動手）。**（S9d 已修正接線）**：上述
`ReactionPopup`/`read_reaction_popup`/`_maybe_handle_reaction`（NOT_ACTIONABLE
路徑）已廢——應戰＝battle_prep -應戰- 變體，感知併入 `BattlePrepForecast`、
執行器改 `_choose_reaction_stance` 接進 `_on_battle_prep`。`solve_reaction`
根節點限制與 `advise_reaction` 介面不變。

**下一步（實機段進行中）**：S9 實機標定批次（memtest86+/BIOS 凍機檢查
先行）——a) stage-info 條件樣本＋片語 parser（諮詢點）b) 冷掃全量實跑
一關（`_bring_to_view` 驗證）c) pilot 對齊探測（收編舊 B1/B2/B3，uid
語義）**d) 應戰彈窗：碼面接線已整併完成（本 session），剩 stance 切換
UI 實機標定＝`REACTION_OPTION_TAPS`＋vision 讀 `available_stances`/
`support_defense`（參考幀 20260711-223704）** e) 登場演出樣本 → S10
整合戰（驗收指標見計畫；翻預設要使用者簽核）。

## 離線工程重構紀錄（2026-07-17 ～ 07-19，行為不變、非里程碑）

**2026-07-17 離線工程重構（行為不變、非里程碑）**：`ManualBattleController.run()`
兩項結構整理——① 每圈單次截圖：中斷偵測器（終局/敗北/隱藏關/modal/劇情）
共用一張 frame，相位/對話框兩讀複用為第一讀、第二讀才重截（防抖不變），
約 8→2 adb 截圖/idle tick，正對凍機嫌疑的截圖 I/O；`perception.observe/probe`
加選參 `frame=`，預設 None 照舊自截（flow.py/AgentLoop 不受影響）。② 中斷
cascade（一串 `if vision.is_*()`）收成優先序偵測表 router（`_route_interrupts`
＋`LoopStep`），相位 ACTIONABLE/NOT_ACTIONABLE 分支維持明確 fall-through。
483 tests/3 xfail、ruff 全綠；commit 13e336f。③ **sim 子套件抽取**
（a51a2b1）：純機制引擎 `sim.py→sim/core.py`＋`solver/formulas/enemy_model/
grid` 移入 `battle/sim/`（相依驗證：只 import `..state`/`..actions`+stdlib，
不碰 perception/vision/controller），`__init__` re-export 保舊路徑；
`bridge/objectives/stage_sim/advisor` 留 battle/ 當 adapter/client 層。
④ **SimAdvisor 介面型態**（b462c03）：controller 對 sim 的操作面收斂成
`SimAdvisor` Protocol（`advise`/`advise_reaction`），`DefaultAdvisor` 為預設
實作、以 `advisor: SimAdvisor` 欄位依賴反轉注入（可換 fake/替代 solver），
移除 `advisor_mod.*` 直呼。⑤ **邊界重構定案（使用者拍板三決策：升頂層／
刪 battle/planner.py／action 執行域留 battle）**，七小步 commit
（ca58ba9…8599f5a）落地四層單向依賴 `battle → content → planner → sim`
（全圖見 agent-architecture.md「套件分層」）：sim 升頂層＋擁有詞彙
（`sim/vocab.py` Faction/DecisionKind，battle 反向 re-export/別名）；
評估詞彙下沉 `sim/objective.py`（Objective/EvalWeights/EvalContext，
solver 不再被 objectives 編譯器穿透）；搜尋層抽 `planner/`（solver＋
enemy_model）；`content/` 資料綁定層（kit＝UnitSpec/UnitStats/WeaponRow/
SpecDefaults、grounding＝數值落地＋假設回報、stage_def（含 sig 距離）、
objectives、stage_sim 直建定義檔座標不經 BattleState）；`core/`→`goap/`
改名；死碼 battle/planner.py（plan_activation，production 零引用）連測試
刪除。行為不變、477 tests（483−6 刪除的 planner 測試）/3 xfail、ruff 全綠。
**裝置現況與 S9 恢復點不變，見下。**

**2026-07-18 router middleware（行為近似不變、非里程碑）**：controller 兩層
路由的 log 收成 middleware（使用者提案「既然走 router 就加 middleware 記部份
handler 的 log」）。① 中斷路由：`_handle_*` 改回傳宣告式意圖
（`LoopStep.log=(kind, extras)`／`finish=outcome`），`_dispatch_interrupt`
統一補共用幀＋執行，handler 不再直接碰 ledger；格式一致、沒 handler 能默默
漏記——`end_turn` 以前整段沒進 ledger，現自動補上。② 相位路由：抽
`_dispatch_phase`，正常結束記一筆信封 `phase`（名字＋`outcome=ok`＋
`elapsed_ms`），domain log 仍留 `_on_*` 內；兩個終止例外（PilotAbort／
SurveyIncomplete）沿用原記錄並轉 `LoopStep(done=True)` 走同一離場接縫。
純機制、流水帳只供工程分析不當先驗故改格式安全。484 tests（+7 middleware）
/3 xfail、ruff 全綠；文件見 battle-phase-states.md「路由與 middleware」。
**裝置現況與 S9 恢復點不變，見下。**

**2026-07-19 tick 收攏（行為不變、非里程碑）**：`run()` 的兩段路由（中斷
pipeline＋裸露的相位分支）收成單一「分類→分派」接縫，tick 主體＝截圖→
`_classify`→`_dispatch` 三行。討論定調：覆蓋層是 **interrupt**（每 tick 邊界
採樣的非同步外部事件）不是 exception——phase 層無法靠「失敗」發現它們
（模板穿透變暗覆蓋層會自信誤讀、無 label 又與動畫無法區分），z-order 掃描
是 label 可信的前置條件；「報錯重判」通道維持在既有 expectation 機制當
備援。實作：① `_overlay_pipeline` 一張 `(state, detect, handle)` 表，掃描
順序與配對不漂移；② `_classify` 回傳扁平 state（覆蓋層／去前綴相位／
`not_actionable`），label 簿記（`_log_state`／`_check_expectation`／
`_judge_pending`）隨 mode 讀取走，覆蓋層 tick 不燒 expectation 預算；
③ `_dispatch` 依 state 選 middleware，`LoopStep` 增 `activity` 欄餵 idle
看門狗（neutral tap 不算進展的語意上移）；④ `_dispatch_phase` 改收去前綴
phase 名。行為等價（偵測順序、短路成本、per-tick 截圖副作用、terminal
出口全保留）；491 tests（+7 classify/dispatch）/3 xfail、ruff 全綠；文件
battle-phase-states.md「分類與分派」。**裝置現況與 S9 恢復點不變，見下。**

**2026-07-19（續）BattleTimeline 三批次（行為不變、非里程碑）**：controller
的「時間記憶」拆進新物件 `battle/timeline.py`（純狀態、不截圖不點擊；與管
空間的 BoardTracker 分工），使用者定調「handler 只看當下畫面、跨 tick 記憶
歸注入物件」。① act→verify 契約搬入：UI 流程圖集中成 `TRANSITIONS` 表，
handler 改報 `acted("attack")`，`_classify` 每 tick 餵 `observe(phase)` 並執行
回傳 ledger intent，`_dispatched_mode` 廢除（來源＝畫面最後確認的 phase）；
ledger 期望事件改記去前綴相位名（流水帳僅工程分析，格式安全）。② turn
偵測搬入 `on_turn_read`（OCR 跳號防呆＋marker fallback，turn 權威 1-based
對齊 ledger/tracker），六個散裝旗標（scouted/advised/sig_refreshed/resynced/
intel_done/full_scan_done）收成 `due()`/`mark_*` 工作閘門（turn scope 翻頁
自動重上膛）。③ `_ActionState`→`timeline.activation`，被吞回滾從 on_eaten
lambda 內化成表上 `repair` 欄，`ends_activation` 取代散落的 reset。timeline
只記帳回報 divergence 永不否決分派（畫面權威紅線）；④⑤（使用者批准的
行為變更，落地順序抑制先行避免過渡態亂 nudge）：not_actionable 在契約
開啟時安靜等（不累 miss、不 nudge、不燒 LLM；垂死對話游標照答，敵方
回合無契約保留 keep-alive tap），然後刪除 `_wait_animation` 45 秒阻塞
——確認開戰後短 settle 即 return，動畫由主迴圈 NOT_ACTIONABLE tick
消化、終局由每 tick 的覆蓋層掃描接住（舊兩出口都是迴圈原生功能），
`settle_timeout_s`／`frame_diff` 依賴一併移除，全系統只剩一個迴圈
（測試套件 130s→100s，reconcile_wiring 不再空轉即為切除證據）。
503 tests/3 xfail、ruff 全綠；文件 battle-phase-states.md「期望轉移驗證」。
**裝置現況與 S9 恢復點不變，見下。**

## 舊快照（2026-07-14 白天 pilot 離線 M1-M7）

**裝置現況**（本批次純離線未碰實機）：遊戲停在主畫面（棄局後遇日期
變更彈窗已收）、體力 ~96、adb server 關。WiFi adb 已配對（poyu@fedora；
重連只需 `adb connect 192.168.50.28:<無線偵錯主頁port>`，port 每次重開
會變）。凍機硬體檢查（memtest86+/BIOS）仍最優先，見
system-freeze-investigation。

**本批次成果（396 測試/3 xfail、ruff 全綠；計畫全文
~/.claude/plans/cheerful-wibbling-umbrella.md）**：

1. **M1 advisor unit_id**（1e28dc0）：`advise(unit_id=...)` 重排 units
   釘根節點行動者（solver 零改動；`SimState.key()` 排序＝TT 順序不敏感
   有測試釘住）。
2. **M2 BoardTracker**（49ba7e6）：forecast/prep/破壞數/回合邊界四掛鉤
   的讀值不再用完即丟——sig-keyed 信念（HP/EN/生死/位置），process
   內活、絕不落地；`apply()` 回填盤面並把每筆攜帶值列為 assumption。
   observe 增 `hub_poisoned`（無 sig 對位的敵弧丟棄）。
3. **M3 寫回接線**（b264cbd）＋ **M5 sig 位置逐回合刷新**（158a7b8）：
   唯一鄰居零 tap 靜默更新、歧義才 tap（預算 6 tap/25s），修掉
   turn-1 凍結位置的身分衰減。
4. **M6 pilot**（7b984f0）：`GGGE_PILOT=1` 時 solver 驅動每次啟動
   （executor.py 純原語：anchor 辨識選中機→單機建議→移動格吸附→
   武器槽→切目標驗證）。失敗分類照使用者定案：無意見類退貪婪記
   `pilot_fallback`；對齊失敗類 `pilot_abort` 直接結束整場留現場。
   我方單位可掛 sig（隨行動增量學習）。run_manual_battle.py 旗標
   與 flow.py 對齊（GGGE_INTEL/ADVISOR/PILOT/STAGE_ID）。
5. **M7 advise_reaction**（e4a3a83）：應戰彈窗由 solver 決定（使用者
   定案，不用靜態預設）——重用 `_our_defense_node` 當根的迭代加深；
   攻擊者無 spec→None→abort。執行端偵測仍缺（#3 實機標定）。
6. **sig 抖動正規化**（099626f）：實戰語料證明同一單位 sig 跨面板
   漂移 3-5 bits——tracker/target_ok/refresh 全部改走
   `signature_distance` 容差 6；位置型目標（無 sig 可驗）降無意見。
7. **M4 HSV 判決＝不可分**（b395319）：417 張截圖三角測量＋subagent
   目視 ground truth——決定性幀 `our_turn_hub_mixed_factions`（同幀
   混編：粉紅我方 H7-8/S135/V202 vs 真敵紅 H8/S136/V204，統計完全
   重疊；人眼差異在血條黑缺損段與黃內線）。兩張新 strict-xfail PNG
   fixture 入庫；**逐像素色彩路線正式關閉，不再迭代閾值**。
   `scripts/replay_frames.py`：run 幀重播 harness（observer 改動的
   回歸閘門；基準：JPEG 幀 sig 欄位劣化最重；tracker 重播顯示實機
   sig 抖動會鏈式超出容差——6 機編成出 17 個我方信念，驗證局要盯）。
8. **M4 諮詢定案落地**（b587fe2）：`_build_board` 常態 `hub_poisoned=
   True`（盤面只收 sig 確認敵）；intel 預算動態跟隨敵機種類數（上限
   12、每面板 ~15s），顯式預算維持固定供測試。

（本批次尾聲的 M8 雙行為 observer 定案與 7/14 晚關卡定義檔定案，
已全部併入上方 S 批次計畫與 docs/stage-definition-requirements.md。）

**已知風險（實機驗證要盯，S9 對應）**：① intel 掃描會 tap 到粉紅
我方弧——tap 自己單位可能開自機摘要卡（讀進敵方 intel＝污染）或
選中單位，7/13 實戰沒炸但未系統驗證（S9 自機卡判別關閉此風險）；
② 實機 sig 抖動鏈式漂移（見上）；③ anchor 單解錯位風險（fail-fast
會抓後果）。

## 舊快照（2026-07-14 凌晨實機夜，恢復點）

**裝置現況**：遊戲停在主畫面（棄局後遇日期變更彈窗已收），體力 ~96，
adb server 已關。WiFi adb 已配對（poyu@fedora；重連只需
`adb connect 192.168.50.28:<無線偵錯主頁port>`，port 每次重開會變）。

**本夜實機成果**：① 對帳鏈首次全程實戰（data/runs/20260713-225448，
victory 14/17、4 回合、787 事件）：預測讀取 21+47 次、kill_check
20 次、期望轉移 183 met/3 miss、**3 筆真攔截塌陷樣本**（#20 語料，
幀已存）；發現並修復 detail 別名突變 bug（b5944f9）。② ledger 逐筆
串流實戰驗證（凍機 #9 只留 1 筆但沒全滅；正常場 787 筆完整）。
③ **M3b 標定完成**（9f50fcf）：摘要卡在右上 (1510,205)（舊猜值錯）、
武裝分頁/關閉鈕預設值命中、新增能力分頁 (1813,176)；沙薩比 EX 面板
全讀通。④ 凍機 #8(USB)/#9(WiFi) 同夜——傳輸無關，memtest86+/BIOS
檢查最優先。⑤ 3 筆 expectation_miss = standby→battle_prep 合法轉移
未列（待補）。

**下一步**：跑 `GGGE_INTEL=1` 模型驗證局（標定已就緒）——expectation
轉 grounded，[SIM-DIVERGE damage/kill_flip] 開始檢驗交戰結算模型；
凍機風險見 system-freeze-investigation（先做硬體檢查再長跑）。

## 舊快照（2026-07-13 晚，恢復點）

**裝置現況**：與稍早快照相同——本日未碰實機，手機停在鋼彈X 選關畫面
（HARD 1 已通關），adb server 關、tmux 清。

**本批次成果（commit 4d45691，315 測試/1 xfail、ruff 全綠）**：使用者
提供三個實機觀測案例（M 攻 A，A 有支援防禦 B／支援攻擊 C 的三種結局），
據此把模擬器的交戰結算順序改成與實機一致（全文入檔
docs/combat-formulas.md「交戰結算順序」節）：

1. **支援防禦承受制**：B 代替 A 承受 M 的一擊（傷害以 B 的數值計算、
   B 可被擊破），取代舊的「A 打折受傷」近似；B 陣亡不取消任何後續。
2. **反擊階段只看主目標（防守方）存活**：主目標活著 → 應戰反擊＋
   支援攻擊都打向攻擊方；主目標被擊破 → 反擊階段整個取消（含支援
   攻擊），攻擊方無傷——「先殺主目標消音全部回擊」是搜尋樹可利用
   的戰術（有 solver 測試釘住）。使用者當晚修正案例 2 的預測描述
   （實際顯示 B 攔截、M 擊殺 B、A 反擊，「合格支援者未攔截」異例
   不存在），並**直接確認取消規則雙向成立**：我方回合殺 A 則敵方
   C 停手；敵方回合我方 M 被擊破則我方 N 停手。敵方相位方向另有
   對稱測試釘住。
3. **DefenseResponse 拆軸**（stance × support_defend × support_attack，
   攔截與應戰不再互斥）、支援次數拆防禦/攻擊兩池（bridge 把
   SUPPORT_ATTACK 能力接上新池）、Decision 增 support_hit 機率分支。
4. **solver 我方攻擊不再免費**：EnemyModel 新增 reactions()——policy
   基線＝應戰＋一律攔截（案例 2 修正後與全部實測一致；step 對不合
   格部分自動退化 no-op）、min＝攔截與否×五種 stance 全枚舉（樣本
   仍少，保守界）；我方防禦 max 節點在有合格支援者時加倍枚舉攔截
   分支。剪枝/TT 等值性測試的隨機盤面加入雙池支援次數後仍全數等值。
5. 實測案例編成 tests/test_battle_sim.py（case1/case3＝觀測；擊殺
   取消規則含敵方相位鏡像測試），另加順序邊界案例（反擊先殺 M 則
   C 停手、無合格攔截者 fall-through 打回 A、擊破攔截者給再動、
   C 出手不看 A 的應戰選項、C 射程不足不出手）。未實測細節以保守
   假設入檔（sim.py docstring＋formulas 文件）。

**同晚逐案問答批次（案例 4-12，使用者逐題定案；全文入檔
combat-formulas.md）**：三題推翻現行實作並已改碼——**支援攻擊先於
主目標反擊結算**（支援機體帶 debuff，先上效果反擊才吃得到；M 中途
陣亡則後續不出手）、**多名支援攻擊者同時齊射**（上限 3~4 待網查，
SimParams.max_support_attackers=3）、**miss 不消耗攔截次數**。四題
確認現行假設：攔截有每相位次數（拆網打法成立）、擊破攔截者給再動
（需撐過反擊＋還有次數，step 本來就這樣檢查）、支援攻擊只看射程與
次數不看 A 能否反擊、應戰彈窗全部防守選項皆玩家可選（solver max
節點建模正確，執行端掛 #3）。特殊機制入檔：進攻盾（進攻時攔反擊，
#22）、支援防禦減傷是逐機體詞條（#20 已補留言）、現無雙職機體。
新 issue：**#21**（介面讀剩餘支援次數＋上限網查）、**#22**（進攻盾
判別＋建模）；#3、#20 補範圍留言。

**網查批次＋離線實作（使用者指示：網查→離線優先實作，commit
75795bc）**：網查定案四項——EN 自然回復（自軍相位開始回最大 EN 的
10%，敵我皆然）、攔截減傷＝承受者防禦狀態（通常 0.8／盾防 0.6，
「別枠疊算→0.48」一說與 wiki 單槽式矛盾留實機裁決）、debuff 持續
一整回合且**敵方 phase 掛的會延續到我方 phase**（下一次敵方 phase
開始才消失；同種取大覆蓋、異種並存）、支援剩餘次數顯示於**地圖
單位右下子彈狀圖示**（亮=剩餘，#21 讀取目標）；同時支援上限網查
無載（維持 3，實機數圖示定案）。離線落地四項：sim EN 自然回復
（en_regen_fraction）、攔截減傷狀態制（廢 0.5，has_shield→0.6）、
solver 齊射開關枚舉（測試釘住「單發殺廉價目標省次數、齊射留給
需要三發的目標」）、進攻盾機制半場（attack_shield 旗標攔反擊，
#22 偵測留實機）。329 測試/1 xfail、ruff 全綠。

**追加離線批次（commits 7795c51/84268dd）**：地圖炮機制入 sim＋
solver（移動前限定、必中、無交互、只傷敵、不給再動、耗彈數
weapon_ammo 進 TT key；legal_map_attacks 生成、solver 測試釘住
「一發雙殺勝過普攻」；地圖炮被禁止當普攻/反擊/支援武裝）、攔截
逐機體減傷詞條欄位（interception_reduction，#20 內容待面板）、
**武裝 debuff 機制**（SimDebuff：命中掛上、跨相位一整回合到期、
同種取大、⑨槽傷害倍率通道；測試釘住「支援先擊掛 debuff、主攻
吃加成」——齊射先結算的機制價值正式兌現）。內容（彈數/範圍/
詞條數值）全部等面板讀取。剩餘離線候選：solver Star2 probing
（7/8 遺留）。337 測試/1 xfail、ruff 全綠。

**回家實機清單（等使用者接手機）**：① M3b 敵情採集驗證（GGGE_INTEL=1
免費棄局，沿用稍早快照步驟）；② 對帳鏈實戰誘發支援防禦——順帶收
#20 裁決樣本（盾持ち攔截者的預測傷害 ÷ 公式值：0.6 或 0.48）；
③ #21 支援次數子彈圖示模板裁切＋同時上限計數；④ EN 回復進位規則
（記兩回合開頭同一單位 EN）；⑤ #22 進攻盾詞條樣本（能力分頁截圖）；
⑥ #23 敵方地圖炮行為觀察（挑有地圖炮敵機的關卡）；⑦ 蛇形掃描實機
計時（28 腿預算）。

**第四輪問答（案例 23-26）地圖炮定案＋敵 AI 校準**：地圖炮完全
無交互（不可應戰、不可攔截——唯一無視支援網的火力）、施放後強制
結束行動且不給再動（最佳打法＝多動機師普攻賺再動、最後一動放炮）、
消耗彈數非 EN（一場 1-2 發）、只傷敵不誤傷。規則入檔、建模列未來
（彈數/AoE 未建模）；**工程缺口開 issue #23**：敵方施放無應戰彈窗
流程、我方 HP 無聲變動，controller 需偵測＋戰場同步（使用者明確
要求）。敵 AI 目標選擇（案例 26）＝一般打最近但有例外、無保證——
NearestTargetPolicy baseline 合理，跨執行的關卡 AI 推斷觸及紅線
（流水帳禁當先驗），未經使用者定案不做。

**第三輪問答（案例 18-22）全數確認現行實作、零改碼**：齊射擊殺
不論誰補刀都給主攻者再動（破壞數統計可能記給實際擊殺者、依模式
而定——對帳鏈裁決留意）、再動＝完整行動重來（移動/攻擊/技能/
地圖炮）、應戰無次數限制（EN＋存活即可，「反擊誘餌」戰術成立且
搜尋樹已具備發現它的要素）、反擊只打主攻（支援射手不會被點名）、
應戰/支援皆耗武裝 EN 且可換低耗武裝（新增兩個釘住測試：同相位
連續應戰、EN 不足的武裝 fallback）。新網查項：**EN 每回合自然
回復**（疑似無詞條也回，未建模——多回合 EN 經濟現偏悲觀）、
**地圖炮機制**（存在、再動可放；範圍/應戰/攔截規則全未知、未建模）。

**第二輪問答（案例 13-17）再改碼一項、確認多項**：**進攻側支援
齊射存在**（順序同反擊＝支援先主攻後；已實作 Decision.support，
預設帶隊）且**攔截者吞下整輪齊射、第一發擊破也不打穿**（已實作：
單攔截者、整輪一次攔截次數、全 miss 不扣；測試釘住「齊射灌屍體」
與「單發燒攔截較划算」的經濟）。確認：支援資格＝駕駛特性＋機體
移動力範圍（原「近似」升格確認；偵察要讀駕駛能力欄）、單次交戰
僅一名攔截者（誰攔＝遊戲 AI）、支援武裝有獨立命中%（預測畫面可
點看；模擬器暫當必中）。新網查項：debuff 跨相位持續、支援命中%
讀取。

**新增待實機標定項**：支援防禦觸發規則的實證確認（實測皆「合格即
攔截」但樣本少；對帳鏈 battle_prep 塌陷紀錄持續蒐證）、**支援防禦
承受方倍率——使用者標記存疑，開 issue #20 追蹤**（減傷是逐機體
詞條非全域常數；實機標定＝預測顯示對 B 傷害 ÷ 公式基礎傷害，網路
查證＝wikiwiki.jp/gget 等社群實測）、同時支援上限 3 或 4（#21）、
支援次數的介面讀取位置（#21）。

**下一步**：沿用稍早快照的實機清單（M3b 驗證、對帳鏈實戰、蛇形掃描
計時）；對帳鏈實戰時順帶記錄「預測畫面顯示的承受者是誰」，累積支援
防禦觸發規則的實證樣本，同場可一併取 #20 的倍率樣本與 #21 的介面
截圖。

## 舊快照（2026-07-13 稍早，恢復點）

**裝置現況**：本日未碰實機（純離線開發），沿用 7/12 深夜狀態——手機
停在鋼彈X 選關畫面，HARD 1 已通關，adb server 已關、tmux 已清。

**本批次成果（commits 5acb129..50dddd4，305 測試/1 xfail、ruff 全綠）**，
回應使用者 7/12 的歸因需求（「內建 AI 也能通關且評價更好——我要知道
贏是演算法期望所致，還是隊伍太強隨便打都贏」）：

1. **M1 `vision/digits.py` 模板數字 OCR**：確定性、絕不亂猜（低於門檻
   回 None）。HUD 白字＋modal 深字雙字形庫（全裁自全解析度 PNG）；
   語料 15/15＋modal 24/24。關鍵規則：SQDIFF 再確認需決定性差距才准
   翻案（修 8→6、2→7 回歸）、最長連續字形串（擋表頭亮邊假 '4'）、
   斜線豁免小字形加成（半透明表頭上 '/' 只剩 0.75）。
2. **M2 遊戲預測讀取器（battle/vision.py）**：read_weapon_select_
   forecast／read_battle_prep_forecast（-應戰- 旗標、命中%）／
   read_enemy_summary／read_kill_counter（破壞數標籤錨定，TURN 章
   自動寬度會讓它浮動）＋name_signature 單位圖像簽名（tight-bbox
   dHash，位移 ±4px 距離 0、異單位 25+ bits）。v1 stub（皆有 fixture
   釘住）：武裝選擇命中%（🎯浮動在目標頭上且語料被裁切）、
   support_defense 圖示（無語料）、亮背景破壞數（回 None 重試）。
3. **M3a `battle/panels.py` 詳情面板解析**：左欄 12 數值（跨三分頁
   不變）＋武裝卡列（LV/RANGE/POWER/EN/命中/爆擊＋格鬥/射擊徽章）；
   藍色▲強化數值 12/12 直讀。to_unit_spec＋assumptions；UnitSpec 增
   pilot_shooting/pilot_melee；pilot_attack_for 依徽章選射擊值/格鬥值。
4. **M3b 敵情採集＋stage cache（離線半場）**：scout_intel 點敵→摘要
   卡（sig 去重、幻影點容忍）→開 modal→武裝分頁→解析→cache；
   IntelBudget(6 面板/90s)。stage_cache=data/cache/stages/，只存身分
   與基礎 kit（現 HP 永遠讀畫面），sig 普查不符→cache_stale→現場
   重讀。**GGGE_INTEL=1 才啟用，等實機標定**（SUMMARY_CARD_TAP／
   WEAPONS_TAB_TAP 座標、settle 時間）。
5. **M4a 對帳鏈接線**：每次攻擊先 compute_expectation（formulas 代入
   面板 spec，缺值記 assumption；quality=grounded/assumed/none）→
   讀武裝選擇 forecast 對帳→battle_prep 抓支援防禦塌陷＋命中%→
   破壞數 delta 裁決。分類：[SIM-DIVERGE damage/kill_flip/support_
   defense]、[RNG-BRANCH]（命中<100 的預期擊殺落空＝骰子問題）、
   [MODEL-DIVERGE]（命中=100 沒死＝模型錯）、[SIM-SKIP]（無 grounded
   期望＝永不記功）。attribution 新增 algorithm_credit＝grounded 且
   擊殺確認 / 出手次數，勝場 0 grounded→明示「勝利不可歸因演算法」。
   順修：battle_prep→battle_prep 列為合法轉移（消 12 筆假 retry）。
6. **M4b advisor 提案（GGGE_ADVISOR=1）**：observe.py 把 tacmap＋
   sig 位置投影成 BattleState（敵單位以 sig 為 id），每回合諮詢
   advisor.advise(3s) 記 decision 事件——只提案不執行；實際目標 ≠
   提案目標→[SIM-DIVERGE] proposal_target。
7. **回合計數修復（原任務 #9）**：TURN 數字 OCR 直讀為主（HARD 1
   的 19 張存檔幀重放：前 12 張讀 1、後 7 張讀 2，半解析度 JPEG 也
   乾淨），marker 比對降為後備；+3 以上跳躍視為誤讀拒收。
8. **tacmap v2 角落蛇形全圖掃描（原任務 #7，使用者指示）**：首回合
   相機開到西北角再蛇行到底（邊緣=相位相關量測位移趨零），南緣飽和
   後補走最後一列；模擬世界測試證明任意起點全角落覆蓋＋全單位同步；
   28 腿預算；次回合起用便宜的四向局部刷新。
9. 附帶修復：LLM reader 開機後首讀被限流吞掉（monotonic 從開機起算
   ＋預設 0.0 的組合 bug）；新增 LlmScreenReader.transcribe（名牌
   轉錄，共用限流）——首見 sig 會存名牌裁切＋LLM 轉錄人類可讀名。

**下一步（需實機／使用者在場）**：
1. **M3b 實機驗證**（免費棄局）：`GGGE_INTEL=1` 出擊 HARD 1→turn 1
   採集→棄局→驗 ledger unit_intel/cache_stale 與 data/cache/stages/；
   重跑同關驗零開面板；毀 cache 驗回退。需標定摘要卡/分頁 tap 座標。
2. **對帳鏈實戰**：一場完整 decision→forecast→kill_check jsonl，設法
   誘發支援防禦；`GGGE_ADVISOR=1` 看提案與 proposal_target。
3. 蛇形掃描實機計時（28 腿預算是否過長）；武裝選擇命中%（🎯錨定模板
   需一張未裁切語料）；support_defense 圖示語料；我方單位 modal 開法
   標定（roster 完整數值）。

**遺留缺口（7/12 快照繼承）**：勝利尾巴 unknown 卡死（SECRET CLEAR
演出）、假移動格（殘留紅框）、敵方相位 AUTO chip 撥不動（不影響防護）。

## 舊快照（2026-07-12 深夜，恢復點）

**裝置現況**：手機停在鋼彈X 選關畫面（stage_list 0.95），HARD 1 已通關
（首次獎勵已領：鑽石×50、SECRET 機體、鋼彈X Divider 入手演出走完，
獎勵尾巴以手動 tap 收回選關）。adb server 已關、tmux 已清。

**實測局結果（data/runs/20260712-192608/battle_01.jsonl，245 事件，
1044 秒，破壞數 17/17 敵軍全滅）**：

1. **勝利**：19 次選單位、12 攻擊、25 交戰確認、**11 個 move（10 個
   directional_*、7 個以威脅格導向）**——史上第一次單位真的推進，
   方向全部正確（對比前日 hint 指西）。5 standby（3 超程 2 已移動）。
   隱藏戰鬥照 policy=challenge 接下並打贏。
2. **期望轉移驗證實戰帳**：65 met / 13 retry / 1 miss / 1 expired。
   12 個 retry 全是敵方相位連續應戰彈窗（battle_prep→battle_prep，
   模型當 tap 被吞而重按開始戰鬥——重按恰好是正確處置，功能無害，
   但 log 有噪音）；1 miss＝standby 後被應戰彈窗插隊（合法轉移，
   模型未列）；1 expired＝終局動畫。**改進項：battle_prep→battle_prep
   應列為合法轉移（連續應戰）**。
3. **hub guard 故障注入成功**：戰鬥中手動把 AUTO 撥到全自動（多次
   注入，敵方相位撥不動、hub 相位其一落地），下一次 hub 訪問即
   `AUTO left on btn_auto_full at the hub, forcing manual`＋ledger
   auto_guard 事件＋LLM 診斷讀圖。force 回 absent 是因為終局動畫把
   HUD 收掉，行為正確。
4. **LLM 讀圖 6 次實戰命中**：載入畫面、戰中未知畫面（甚至建議了
   正確的武器鈕）、AUTO 診斷、勝利後 SECRET CLEAR 畫面×3（正確建議
   TAP TO NEXT，但 unknown handler 無控制權——見缺口 2）。
5. 出擊後直接進戰鬥（放棄過的關卡重出擊會跳過 stage_info 與開場
   劇情）——stage_info 閘門這次沒被經過，controller 開頭 15s 探測
   承接，AUTO 本來就是 manual。

**本場暴露的缺口（依痛度排序）**：
1. **回合計數回歸（任務 #9）**：實際 TURN 5、ledger 全程 turn=1，
   marker 比對沒觸發（7/11 同圖是好的）；_turn_scouted 因此不重置、
   偵察只跑一次。有 19 張 select_unit 幀可離線重播。
2. **勝利尾巴 unknown 卡死**：SECRET BATTLE CLEAR／機體入手演出不在
   畫面庫，agent loop 等滿 90×2s 收 FAILED（戰鬥其實已贏、ledger 已
   歸檔）。候選解：unknown handler 在 LLM 建議「tap to advance」類
   場景給受限的 neutral tap 權限，或補模板。
3. **假移動格**：t=104.8 的 cell 移動（1720,604）與目標（786,137）
   反向——weapon_select 返回後殘留的紅色攻擊範圍外框被白框遮罩誤抓
   （同因 20260712-182654 驗出 38 假格）。幀已存 ledger。
4. 敵方相位 AUTO chip 撥不動（注入實測），probe 高分照樣匹配不到
   ——chip 在該相位可能鎖定，不影響防護但注入測試要挑 hub 時機。

**新語料**：`assets/screenshots/20260712-hub-corpus-01.png`（我方
hub、全解析度 PNG，hp_arc 重校準用）、`20260712-enemy-turn-marching-
fullres.png`（敵方回合行軍、全解析度）。

## 舊快照（2026-07-12 晚間，恢復點）

**裝置現況**：手機停在「機動新世紀鋼彈X HARD STAGE 1」選關畫面（出擊
準備鈕），體力 25/104 自然回復中。驗證局用戰鬥選單收場——**放棄戰鬥
不消耗體力／挑戰次數（確認框明文實證），出擊 10 點已退回**，之後可
低成本反覆實測。adb server 已關、tmux 已清。

**本批次成果（commits 99035e1 + 後續，213 測試/1 xfail、ruff 全綠）**：

1. **LLM 讀圖輔助**（`perception/llm.py`）：ollama 讀截圖協助未知畫面
   判別，預設 gemma4:latest（實測 8B 暖機 3.6s 且輸出比 26B 乾淨）；
   接線於 controller 未知場景（neutral tap 前）、AUTO 防呆失敗診斷、
   clear-loop unknown handler。rate limit 60s、任何失敗都退化為原行為。
   **實戰命中**：載入畫面被正確讀出（5.8s）。
2. **AUTO 防呆 act→verify→retry**（`force_manual_auto`）：tap 後要求
   chip 狀態在 6s 內真的轉移，否則視為被吞重試；回傳 manual/absent/
   unconfirmed 三態。stage_info 硬閘門（unconfirmed 拒絕推進出擊）、
   controller 開頭 15s 短預算（修 60s 空燒）、hub 每次訪問複檢。
   **實戰驗證**：使用者遊玩殘留的真實全自動被閘門攔截，full→enemy→
   manual 每步驗證後才出擊，7/11 汙染場景完整重演並被擋下。
3. **期望轉移驗證機制**（使用者定案方向）：`Expectation` 契約（來源
   相位→合法目標集合），met/eaten（on_eaten 回滾 handler 旗標）/miss
   （畫面權威，只記帳）/expired（檢查次數計時）四種裁決，v1 掛在
   選單位/開武裝/攻擊/開始戰鬥/待機。見 docs/battle-phase-states.md。
4. **戰術感知修復（對「往敵人反方向」的診斷回應）**：
   - 診斷實據：兩場戰鬥 0 個 move 事件（單位從沒被下移動指令，全程
     站樁）；`find_move_cells` 白框假設在雪地歸零（白遮罩飽和成一大塊，
     9 張全解析度幀離線重現）；scout hint 指西而敵軍在北（tacmap 22 敵
     vs 實際 14——hub 弧線誤判餵毒＋雪地無特徵相位相關飄移）。
   - 修法（不動任何 HSV 閾值）：威脅格「!」不受敵我誤判污染，升為
     `_seek_move_target` 第 2 優先與 `_hint_from_map` 首選（tacmap 加
     threats 層）；抽不到格子但有方向時改「方向性點擊」fallback
     （PAN_CENTER 朝目標 260px，撞到弧線退 150px，`directional_*`
     basis 記帳）。頂帽/亮度掃描/窄飽和度萃取格子皆試過不可分，
     結論記在此，別重走。
5. 放棄戰鬥流程標定：戰鬥中右上 ☰ → 放棄 (456,850) → 確認 (1346,850)，
   回到選關畫面。已寫入 CLAUDE.md 鐵則。

**尚缺、待使用者下實機測試指令**：
1. 期望轉移驗證＋方向性移動＋威脅格導向的實戰資料（放棄免費，可多輪）。
2. hub guard 故障注入測試（戰鬥中手動撥 AUTO，驗證 hub 複檢抓回）。
3. SIGTERM 中斷時 ledger 未歸檔（20260712-182115 只有 frames 目錄，
   jsonl 沒寫出）——中斷路徑要查，或改 ledger 逐事件 append。
4. 雪地 move-cell 真正的抽取（目前用方向性點擊繞過；圓角/缺口特徵
   模板是下一個候選，需要更多樣本）。
5. hub 弧線 HSV 重校準仍缺全解析度 hub 語料（目前用威脅格繞過）。
6. （承前批次）keyguard 疑似誤報、應戰決策選項優化、roster_calibration
   接線。ensure_manual_auto 60s 空燒已由 2 修掉；stage_info 修正包的
   AdvanceStageInfo 路徑今日已實戰走通。

## 舊快照（2026-07-11 深夜，恢復點）

**裝置現況**：HARD STAGE 1 於 turn 4 **戰敗**（己方單位全滅——隊伍
低於建議戰鬥力＋單位待機不推進，屬預期結果；這場開頭本來就被殘留
AUTO 汙染，定位是活體測試場不是通關嘗試）。`is_defeat_screen` 首次
實機命中、controller 乾淨退出、ledger 歸檔 outcome=defeat（
`data/runs/20260711-225442/battle_01.jsonl`，1195 秒、四回合、13 種
事件：15 對話/13 選單位/9 待機/5 攻擊/27 應戰確認/5 neutral_tap/1
隱藏戰鬥彈窗/1 劇情跳過/4 戰術掃描/3 end_turn）。FAILED 畫面已手動
點「選擇關卡」收回，**裝置現停在鋼彈X 選擇關卡畫面（HARD 1 節點）**，
體力充足。tmux session 已清、adb server 已關（收工紀律）。

**本批次成果（commits 1cd5f38→cef76bb，179 測試/1 xfail、ruff 全綠，
全部附實機驗證證據）**：

1. **is_static 卡死正式修畢，方向為使用者定案的「可操作性優先」**：
   不再判斷「畫面是否靜止」，直接 probe 相位 label 判斷 ACTIONABLE，
   連續兩次一致才 dispatch；回合邊界改用 TURN 數字變化（`_turn_marker`
   比對），刪掉 `_phase_break`/`_none_streak` streak 邏輯；
   `ensure_manual_auto` 改雙讀一致；`_wait_animation` 改「靜止或 label
   回來」雙出口。（bd11a67）
2. **highpass 匹配修好亮背景 label 失效**：TM_CCOEFF_NORMED 對「暗圖
   校準的模板 vs 亮雪地」會掉到 gate 以下（實測 0.764 < 0.80）；模板
   可在 manifest 開 `preprocess: highpass`（減 31×31 高斯局部平均），
   雪地 0.893、暗圖 0.964+、負樣本反而更低。只開給五個相位 label。
   （b750af2，fixture 語料 mode_label/ 七案釘住）
3. **敵軍回合橫幅干擾模板**：「敵軍回合」與「我軍回合」四字共三字，
   cross-match 0.81/0.83 超過 gate——舊迴圈被 is_static 意外遮住、新
   迴圈立刻踩到（敵方回合全程狂點單位卡）。修法不是調閾值：新增
   `label_enemy_turn` 模板一起 probe，`resolve_mode()` argmax，干擾
   模板贏＝NOT_ACTIONABLE。實測 0.991 vs 0.831 分離。（3c2ada4）
4. **對話 cursor 搜尋帶加寬 130→170px**：劇情對話（立繪＋說話者橫幅
   雙行版面）的 ▼ cursor 停在 y~905-925，舊帶搆不到（帶內 0.571 vs
   全幀 0.945），run 2 因此停擺 10 分鐘。（cef76bb）
5. **neutral-tap fallback（使用者建議）**：NOT_ACTIONABLE 連續 3 輪
   什麼都認不出→頂部中央（無按鈕區）輕點一下嘗試推進；對話類畫面
   點哪都會前進，其他畫面安全忽略。每次記 `neutral_tap` ledger 事件
   ＋存幀，未知場景自動留校準素材；副作用防 3 分鐘省電鎖。（cef76bb）
6. **實機煙霧測試（HARD STAGE 1 活戰場，run 1-3）驗證清單**：雪地
   label 偵測（probe 0.86-0.87 穩定）、marker 回合邊界（turn 2-4 正確
   觸發、modal 不誤進位）、完整攻擊鏈（選單位→武裝→鎖定→確認 ×5+）、
   **#3 應戰決策彈窗首次實機捕捉**（標題「戰鬥準備 -應戰-」被
   `label_battle_prep` 以 0.948 承接，`_on_battle_prep` 的開始戰鬥
   tap 能推進不卡死；最佳應戰選項的決策是未來工作）、死亡對話推進、
   劇情對話變體推進、省電鎖 mid-run 自解、unit_detail modal 逃脫、
   隱藏戰鬥 WARNING 彈窗（policy=challenge）、MENU 左移劇情跳過、
   **`is_defeat_screen` 首次實機命中＋乾淨歸檔退出**。run 1 首次產出
   含真實戰鬥事件的完整 jsonl；run 3 打完整場（見上方裝置現況）。
7. **狀態轉換 log（使用者建議）**：主迴圈感知裁決改變時記一行
   「state: 舊 (held N checks) -> 新」含 label/信心證據，四種裁決
   （ACTIONABLE／NOT_ACTIONABLE 干擾模板／NOT_ACTIONABLE 無 label／
   TRANSITION 兩讀不一致）；standby 補記決策脈絡（move cells 數、
   tacmap 敵數、scout hint）；`GGGE_DEBUG=1` 切 DEBUG 級。（a9cd9d7）

**本批次觀察到、尚未處理**：
1. **戰術缺口（既有 v1 弱點實錄）**：武器超程時「no enemy direction
   found, standing by」頻繁出現——scout 有敵人座標但移動目標選擇失敗，
   單位原地待機不推進。對應 battle-skills-improvement 既有記憶，
   屬戰術品質非生命週期問題。
2. **keyguard 疑似誤報**：22:56:15 對話推進中（每 5 秒有輸入）觸發
   「game battery-saver lock engaged」——3 分鐘閒置條件不可能成立，
   疑似劇情畫面調暗＋中央區誤匹配鎖頭圖示；解鎖 swipe 對對話無害
   （等於推進一行）。需要抓到現場幀才能釘 fixture。
3. **ensure_manual_auto 在無 AUTO 鈕畫面燒滿 60 秒 timeout**（對話
   畫面開場時）。可考慮縮短 timeout 或加「畫面有對話 cursor 就跳過」。
4. 期望轉移驗證（act → verify → retry）尚未動工——todo #3，是下一個
   結構性投資。

**尚缺、待裝置**：
1. HARD STAGE 1 乾淨場重打（本場開頭被殘留 AUTO 汙染，見上一快照）。
2. 出擊前 AUTO 防呆自動化（stage_info 畫面上強制 AUTO 手動）——這次
   又是靠人眼攔截。
3. stage_info 修正包（5b6c811）驗證——仍未真正跑到。
4. 應戰決策的選項優化（現在照預設確認）。
5. roster_calibration 接線。

## 舊快照（2026-07-11，恢復點）

**裝置現況**：手機停在「機動新世紀鋼彈X HARD STAGE 1」戰鬥中，我軍回合
TURN 1，破壞數 4/14，畫面在鋼彈F90 的「單位移動／選擇武裝」子畫面，AUTO
已確認為關閉（灰色、非高亮）。這場戰鬥沒有結束、沒有撤退，就是單純停在
原地——`run_manual_battle.py` 已被我手動 SIGTERM 中止（`data/runs/
20260711-214453/battle_01.jsonl` 只有一筆 `finish/interrupted`，全程
437 秒零行動）。下次接手前**先截圖確認畫面沒有被系統動作（省電鎖等）
影響過**，再決定要繼續手動這場、還是撤退重打。

**本批次成果（找到 HARD 關卡並出擊，過程中發現四個獨立問題，沒有新
commit——這批純粹是實機驗證嘗試 + 即時除錯，程式碼未變動）**：

1. **確認並進入「機動新世紀鋼彈X HARD STAGE 1」**：透過關卡選單→
   MAIN STAGE→鋼彈X 系列→選擇，確認 HARD 0/1 未過，建議戰鬥力
   160,000，首次獎勵 LV50 SECRET 機體＋可奪取敵方機體。隱藏條件「2回合
   內擊敗夏基亞·佛羅斯特、歐爾巴·佛羅斯特」達成時敵方會增援。出擊準備
   帶自動編制隊伍（LV81/LV45/LV50/LV45/LV45 主力＋LV22 支援），增幅
   +4,646。

2. **重大發現①：AUTO 殘留全自動狀態，內建 AI 在人為介入前已自動出手**。
   出擊進場後 stage_info 畫面的 AUTO 開關已呈高亮（全自動）狀態，我手動
   點擊試圖切換時意外同時觸發了畫面推進，直接跳進戰鬥；戰鬥開場動畫
   期間內建 AI 已自動打死 4 隻敵人（破壞數 4/14）才被我發現並手動關閉
   AUTO。**這違反了「戰鬥必須由我們的程式操作、絕不能讓內建 AI 接手」
   的紅線**，雖然是裝置殘留狀態造成、非我方主動選擇，且已即時補救，但
   這場戰鬈的開場已被內建 AI 汙染，不能當作 controller 的乾淨驗證證據。
   根因跟先前 stage_info 修正包驗證中斷時發現的 AUTO 競態同源（出擊前
   沒有先確認/強制 AUTO 為手動）。

3. **重大發現②：主機再次硬凍機（第 5 次），這次伴隨主動 adb 操作**。
   `run_manual_battle.py` 於 21:29:51 啟動、21:30:00 左右仍在正常跑
   （log 顯示「AUTO is btn_auto_enemy, cycling toward manual」），
   `journalctl -b -1` 卻在 21:30:24 戛然而止——只有一行例行的
   `freeze-blackbox` 心跳 log，沒有任何 `systemd-shutdown` 序列，跟過去
   四次凍機同簽名。**新線索**：這次凍機發生在腳本啟動後僅 ~36 秒、且
   正值密集 adb shell／uiautomator2 呼叫期間，跟先前「adb server 常駐
   閒置三分鐘後當機」的假說不同方向，暗示主動的 USB／adb I/O 也可能是
   誘因之一，而不只是常駐本身。`system-freeze-investigation` 需要納入
   這個新資料點。

4. **重大發現③：`no permissions` 根因首次查清**。凍機重開機後
   `adb devices` 顯示 `R5CRC37JBYJ no permissions`，`getfacl` 一查發現
   USB 裝置節點的 ACL 只授權給 `gdm-greeter`（`rw-`），poyu 只有 other
   權限（`r--`，無寫入）。`loginctl seat-status seat0` 確認：重開機後
   seat0 預設由 `gdm-greeter`（登入畫面）持有，systemd-logind 把本機
   USB 裝置的 ACL 動態綁在目前持有 seat0 的 session 上；只有使用者**
   實際在實體機器登入桌面**、seat0 轉移給 poyu 的 session 後，adb 權限
   才會恢復——這正是先前快照「no permissions 已解除、原因不明」的真正
   機制。本次使用者中途實體登入後，權限確實立即恢復，驗證了這個推論。
   沒有 sudo 免密碼可以繞過，純系統層限制，不需要也不該動 udev 規則。

5. **重大發現④（本次卡住的直接原因）：`vision/motion.py` 的
   `is_static(threshold=0.015)` 在 HARD STAGE 1 這張雪地地圖上完全無法
   收斂**。即時對現場畫面連續量測 5 次，全部回傳 `False`（背景飄雪
   粒子特效／移動範圍格「!」圖示的脈動動畫／選中單位的紅圈光效，任一或
   合力造成連續幀差異持續超過閾值）。`ManualBattleController.run()`
   主迴圈在 `is_static` 為 `False` 時會直接 `continue`（視為戰鬥仍在
   播動畫），完全不會進到 mode 偵測／`_on_unit_move`／`_on_weapon_
   select` 等行動分支。結果整場戰鬈從 21:44:53 跑到我 21:52:10 手動
   SIGTERM 中止，437 秒內零行動、零有意義 log。**這是全新發現的
   controller 卡死模式，跟先前任何已知問題（AUTO 競態、hp_arc 誤判、
   ENEMY_REACTION_POPUP 缺口）都不同源**，且很可能不是這張地圖獨有——
   任何有持續動畫背景（雨、雪、粒子特效）的戰場都可能觸發同樣的卡死。

**尚缺、待裝置（更新後排序見下方「下一步」）**：
1. **`is_static` 卡死問題需要修法方向**——本次最大的技術阻礙，且動
   `vision.py`／`motion.py` 需要使用者拍板方向（遮罩掉飄雪等已知動畫
   區域再比較？放寬 threshold？連續 N 次 False 後改用備援判斷強制
   評估 mode？）＋照專案紀律走 fixture 回歸測試流程，不能貿然調閾值。
2. **AUTO 開關出擊前防呆**——這次又中招，是人眼即時攔截、不是自動化
   把關。需要在 controller 或 stage_info handler 加上出擊後第一時間
   強制檢查/確保 AUTO 為手動，而不是靠人在旁邊盯。
3. Gundam X HARD STAGE 1 本身還沒清完，卡在 Turn 1 中途（破壞數
   4/14），前段已被內建 AI 汙染，就算修完 is_static 問題後續打完，這場
   也不能當作乾淨的「全程我方 controller 操作」驗證證據——大概率需要
   放棄重打。
4. stage_info 修正包（5b6c811）——仍然是「完全未驗證」，這次也沒機會
   推進。
5. 生命週期 ACTIONABLE/NOT_ACTIONABLE 重構（516987e）的實機行為——同上，
   沒有取得完整一輪戰鬥的即時觀察證據。
6. ENEMY_REACTION_POPUP（#3）畫面錨點標定與 handler——仍未動工。
7. roster_calibration 裝置常數標定——仍未接進 controller.py。

**下一步**：跟使用者討論 `is_static` 卡死的修法方向並取得共識；方案
定案、有 fixture 證據後才動 `vision.py`／`motion.py`；同時把「出擊後
強制確認 AUTO 為手動」做成自動化防呆而非人眼盯場。兩個修好後，放棄
現在這場已被汙染的 HARD STAGE 1，重新出擊乾淨驗證一輪。

## 舊快照（2026-07-10，恢復點）

**裝置現況**：手機已接回，`adb devices` 顯示 `R5CRC37JBYJ device`（上一
快照的 `no permissions` 已解除，原因不明，未深究）。截圖確認畫面在
**選擇關卡**，游標停在關卡 12（劇情預覽「難道非得開火不可嗎！」，建議
戰鬥力 133,000，地形地面，所需 10，略過 3/3，資源 84/103），關卡
9/10/11 均顯示 CLEAR。體力/資源足夠再跑一輪。

**本批次成果（167 測試/1 xfail、ruff 全綠，沿用 commit 3029f79 之後
未變動 — 這批純粹是實機驗證嘗試 + 事後鑑識，沒有新 commit 的程式碼）**：

1. **啟動 `run_clear_loop.py` 打關卡 11**（使用者核可用任一關驗證、10
   體力不是問題）。腳本跑到 `data/runs/20260709-215050/frames/battle_01/`
   共 27 張 probe/move/attack frame，最後一張
   `t0046_turn1_move.jpg`（2026-07-09 21:56:15）。**`battle_01.jsonl`
   從未寫出**——流水帳檔完全不存在，不是「有紀錄但缺 finish 事件」。
2. **重大發現：5b6c811 stage_info 修正包這次也沒被實際跑到**。根因是
   競態：AUTO 開關在使用者先前手動遊玩後被留在「全自動」，遊戲在我們
   的腳本第一次 `perception.observe()` 之前就已經自動跳過
   stage_info（「TAP TO NEXT」）甚至更多畫面。也就是說，先前對這個
   修正包「看起來有效」的印象是誤判——它從未真正被本次流程呼叫到。
   **這修正包目前的驗證狀態退回「完全未驗證」**，且下次驗證必須先解掉
   這個競態（出擊前檢查/強制 AUTO 為手動，或提高腳本啟動後的截圖頻率
   避免被搶跑）。
3. **主機乾淨重開機，非凍機模式**：`journalctl -b -1`／`-b -2`／`-b -3`
   均可見完整 `systemd-shutdown` 序列（SIGTERM 給殘留 process、journal
   正常 stopped），跟過去四次凍結的「無日誌戛然而止」簽名不同，判斷
   跟 `system-freeze-investigation` 的凍機模式無關。07-10 當天另外還有
   13:35、14:10 兩次同簽名的乾淨重開機，同樣非凍機。
4. **未解謎團（需使用者確認）**：最後一張自動化 frame
   （07-09 21:56）到目前截圖（07-10 19:15）之間隔了近 21 小時，中間
   主機重開機三次。這段期間**沒有任何 `battle_01.jsonl` 或其他紀錄**顯示
   關卡 11 是怎麼結束的，但畫面上關卡 11 現在是 CLEAR、關卡 12 變成
   游標所在的「下一關」。最合理的推測是使用者在腳本卡住後（對應
   使用者當時問的「怎麼不會動？」）手動用手機把這場戰鬥打完，但這只是
   推測、尚未跟使用者核實。**如果是手動完成的，這場戰鬥不能算是生命
   週期模型／stage_info 修正包的實機驗證證據**，需要重跑一輪讓自動化
   腳本全程跑完才算數。

**尚缺、待裝置（更新後排序見下方「下一步」）**：
1. stage_info 修正包（5b6c811）——真正的第一次驗證，這次要先排除
   AUTO-full 競態。
2. 生命週期 ACTIONABLE/NOT_ACTIONABLE 重構（516987e）的實機行為——今天
   這次嘗試被中斷，沒有取得完整一輪戰鬥（含 NOT_ACTIONABLE 段落）下的
   即時觀察證據。
3. ENEMY_REACTION_POPUP（#3）畫面錨點標定與 handler——生命週期模型剩下
   唯一的實質缺口，仍未動工。
4. roster_calibration 裝置常數標定——已有純運算邏輯與測試，尚未接進
   controller.py、尚未量測真實列表鈕座標/鏡頭跳轉量。

**下一步**：跟使用者核實關卡 11 戰鬥是否為手動完成；接著重跑
`run_clear_loop.py`（關卡 12 現成可打），這次出擊前先截圖確認 AUTO
開關狀態，避免重蹈 stage_info 競態覆轍，順便補齊生命週期模型與
stage_info 修正包的真正實機證據。

## 舊快照（2026-07-09 更晚）

**裝置現況**：跟上一快照相同，`no permissions` 未處理，本批次全程沒碰
裝置。

**本批次成果（commits a07b05f/ecddb4f/516987e/8bba4d6，167 測試/1
xfail、ruff 全綠）**：

1. `docs/battle-phase-states.md` 從一份畫面狀態分類學（被使用者指出
   「相當空泛」）改寫成使用者定案的生命週期模型：**ACTIONABLE／
   NOT_ACTIONABLE 二元判斷**，不分敵方/第三方回合；可控第三方會自然
   出現在單位列表走 ACTIONABLE 路徑，不可控的自然落 NOT_ACTIONABLE，
   不需要額外探測第三方可控性。敵我互打降低難度這類內容細節刻意不理。
2. **落地進 `controller.py`**（516987e）：`run()` 的 `mode is None`
   fallback 從匿名分支改成有名字的 `_on_not_actionable()`，是應戰彈窗
   （#3）未來的掛載點。**沒有**照文件原稿用 `unit_cards_present` 當
   頂層判斷——落地前發現沒有實機證據能證明卡片列在 unit_move/
   weapon_select 子畫面底下還可見，貿然假設違反紅線；改用
   `mode is not None`（既有 handler 已經在用、已驗證的訊號），
   純重構、行為零改變（回歸測試釘住等價性）。文件已回頭同步這個落差
   （8bba4d6）。
3. `unit_cards_present` 用途不變——還是 `_on_our_turn()` 判斷「選下一個
   還是結束回合」，這是它本來就驗證過的場景。

**尚缺、待裝置**：ENEMY_REACTION_POPUP（應戰彈窗）畫面錨點標定與
handler，是生命週期模型剩下唯一的實質缺口。

## 舊快照（2026-07-09 晚）

**裝置現況**：跟上一快照相同（`adb devices` 顯示實體連接但 `no
permissions`，未處理，本次工作全程沒再碰 adb/裝置）。

**本批次成果（163 測試/1 xfail、ruff 全綠，commits 46a5a70/8c21883）**：

1. **#5 根因新線索（重大）**：用 #18 取樣時發現，`20260706-233847.png`
   （真實「我軍回合、選單位」hub 畫面）上 `find_ally_units` 誤判 0、
   `find_enemy_units` 誤判 9 個假陽性。深查後：現行 HSV 閾值的敵方紅
   校準來源（`20260705-170520.png`）其實是**敵方回合**畫面，跟控制器
   實際掃描發生的**我方回合單位選取 hub**畫面是不同 UI 狀態；hub 狀態
   下未行動我方單位的弧線色相跟敵方紅幾乎同色相（2026-07-09 量測皆
   中位數 hue 3-8）。也就是「閾值對錯了畫面狀態校準」，不是漏了一個
   色域，補帶反而會讓真敵方一起被 `find_ally_units` 誤收。副觀察：
   同一張圖裡已行動/未行動單位弧色不同（一藍一紅相鄰），暗示紅色
   可能是「本回合待行動」高亮而非純陣營色，待更多樣本驗證。**沒有
   修 `vision.py`**——證據不足以安全重新校準，只把此圖存成 #18 的
   xfail 回歸案例釘住現象，詳見 CLAUDE.md 視覺辨識避坑節與
   `tests/fixtures/vision/hp_arc/our_turn_hub_pink_bug.json`。
2. **#18 視覺回歸測試庫首批**（46a5a70）：`scripts/curate_fixture.py`
   （真實截圖裁切→`tests/fixtures/vision/<類別>/<案例>.{jpg,png}+json`）
   ＋ `tests/test_vision_regression.py`（回歸掃描語料庫，xfail 支援）。
   首批 10 案例涵蓋 hp_arc／unit_cards／unit_detail_modal／
   hidden_battle_warning／defeat_screen 五類，全部來自真實截圖（戰敗
   用真模板疊真背景合成，因語料庫目前沒有真正輸掉的截圖）。hp_arc 類
   改存 PNG 無損——JPEG q85/90/95 對這種像素級色彩/形狀判斷會非單調地
   翻轉 blob 分類（實測證據見 commit）。**尚缺**：screen_mode、
   template_locate（MENU 漂移/結束回合對話框）、keyguard 暗幀負例
   三類，留待下次擴充。
3. **roster_calibration 設計骨架**（8c21883）：回應使用者對顏色判斵
   可靠度的質疑，提出「單位列表點擊＋鏡頭跳轉量測」取代弧色判斷我方
   身分/位置的方案——單位列表天然只列可操控單位（含未來換邊劇情也
   成立），點擊造成的鏡頭跳轉用既有 `vision.measure_camera_shift`
   （純地形相位相關，不碰單位顏色）量測、串接成 slot→世界座標表。
   `battle/roster_calibration.py` 只含串接運算，裝置相關常數（列表鈕
   座標、列表列間距、選取單位鏡頭歸位錨點）全部注入，未硬編造值——
   這些待裝置接回才能實測校準，目前用假 capture/tap/shift 測試純運算
   邏輯（`tests/test_roster_calibration.py`）。**尚未接進
   controller.py**，屬 track 1（裝置門檻）工作。

**GitHub 同步**：#5 留言記錄根因新線索；#18 留言記錄首批完成與缺口。

**下一步（沿用 2026-07-09 稍早定案的排序，見下方舊快照）**：軌道 0
剩餘部分（#18 補三類）可以再擠一點，但主要卡點還是裝置——`no
permissions` 沒解決之前，軌道 1（驗證 5b6c811、#5/#6、advisor 影子
模式、roster_calibration 裝置常數標定）都動不了。

## 舊快照（2026-07-09 早）

**裝置現況**：`adb devices` 顯示 R5CRC37JBYJ 已實體連接但 `no permissions`
（與上一快照「手機仍拔離」不符，可能使用者已插回但尚未在裝置上重新授權
USB 偵錯，或 udev/授權狀態跑掉）——本次只用來確認連線就 `adb kill-server`
收工，未深究、未使用裝置。依凍機調查紀律（memory
`system-freeze-investigation`），adb server 只在有人盯著的工作時段開，
用完即殺。下次要用裝置前先處理這個 no permissions。

**本次完成**：把 2026-07-08 快照「Issue 分類」的結論同步成 6 則 GitHub
issue 留言（#19/#17/#13/#3/#12/#14），標明各自「本分支已解決的部分」vs
「仍待實機/正交依賴的部分」，任務清單文件與 GitHub 議題現在一致。

**任務排序定案（使用者 2026-07-09 確認）**：

軌道 0（裝置沒回來也能做，現在就做）：
1. **#18 視覺回歸測試庫**——用既有 `data/runs`/`assets/screenshots` 語料
   建，不需裝置；後續動 `vision.py`（驗證 5b6c811、修 #5/#6）都要靠它當
   回歸網，排最前面。

軌道 1（裝置接回後依序做）：
1. 驗證 `5b6c811` 修正包（含 #1 實機驗證）——程式碼已寫好，只差臨門一腳
   的實機證據。
2. #5 掃描計數修正——#6、#14、advisor 輸入品質的共同根基。
3. #6 鏡頭錨定驗證（緊接 #5）。
4. advisor 影子模式接進 controller（只記流水帳不執行、風險低，是本分支
   最大投資的變現點）。
5. #3 實機半部（應戰彈窗感知標定，跟第 4 點同一輪戰鬥順便收集）。
6. #12 感知端（ScanProvider，先做 SUPPORT/技能鈕簡化可用性判斷，不必等
   完整 OCR）。

軌道 2（維持低優先）：#9 OCR、#8/#11 cache、#13 剩餘 cache 抽查、#10
戰略迴圈——沒有理由提前。

**取捨**：嚴格依賴序會是「#5/#6 全修完才試 advisor」，拖太久看不到
solver 主線的實機反饋；用「影子模式」打破序列依賴——advisor 不影響實際
戰鬥決策，即使輸入不準也只是流水帳多一筆怪建議，不拖累通關，讓 vision
修正與 solver 整合兩條線並行推進。

**下一步**：開始實作 #18（軌道 0，不需裝置）。

## 舊快照（2026-07-08 晚）

**裝置現況**：手機仍拔離。**第四次凍結**：07-08 16:53~16:54（journal 於
16:53:03 例行訊息後戛然而止，與前三次同簽名）——發生在無裝置、無戰鬥、
近乎閒置的機器上：session 開始 4 分鐘、`adb devices` 拉起 adb daemon 約
3 分鐘後。四次凍結的軟體側共同因子收窄為「adb server 常駐」（該 boot
先前 16.5 小時無 adb 無事）；但 Fedora android-tools 的 adb 無 mDNS，
閒置 server 只剩 USB bus 掃描，而先前 USB 重度壓測是陰性——機率性硬體
嫌疑同步上升。詳見 memory `system-freeze-investigation`。**adb server
已殺掉；開機後可能有東西自動拉起（07-08 20:10 曾見一顆掛在
systemd --user 下），做無 adb 對照前先 `pgrep adb`。** memtest86+ 過夜
與 BIOS 更新檢查仍未做。

**本批次成果（離線 solver 主線；151 測試/ruff 全綠）**：
1. **solver 健全性**（1529e14）：置換表加 exact/lower/upper 界值旗標；
   Star1 一般化為 n 元期望節點（含敵方 policy 節點）；修掉 fail-soft
   界值方向寫反的剪枝不健全 bug。回歸手段＝隨機盤面上「剪枝+TT」必須
   等值於「無剪枝參考」（SolverConfig 的 use_tt/use_star1 開關）。
2. **行動生成擴充**（a3adbe6）：SimUnit 技能欄（SimSkill：uses/
   ends_turn）、legal_skills＋reposition_moves（朝各目標推進＋滿移動力
   後撤）進 _ally_decisions——「補 EN 再打」「欺近畫面外目標」「脫離
   致死圈」都由搜尋自己發現（各有行為測試）。另修 PV 決策重複前置 bug。
3. **Sim v1 幾何**（16c52cc）：battle/grid.py BFS 王步可達性——異陣營
   擋路、我方可穿不可停、SimState 選配地圖邊界；legal_attacks 接 reach
   集合做繞路落點。測試含「兩機堵咽喉→敵方對後排攻擊消失」端到端案例。
   支援防禦幾何仍為切比雪夫近似（待辦）。
4. **Bridge＋Advisor**（52be776）：battle/bridge.py 把 BattleState 量化
   成 SimState（能力注入→再動/技能/支援欄位；數值權威序＝現場 > spec
   (OCR/cache) > BridgeDefaults，每個 fallback 記名為假設供歸因）；
   battle/advisor.py 一呼叫完成 bridge→solve→控制器詞彙（世界座標移動
   目標/目標 id/武器）＋假設清單＋搜尋統計。

**Issue 分類（完成本分支可解 vs 不可解，2026-07-08 使用者要求）**：
- 本分支主體：#19（模擬器＋expectiminimax）、#17（內層 GOAP）。
- 被本分支收編：#13（1.5-ply 站位安全→多層搜尋＋葉評估取代）、#3 的
  決策端（防禦應對＝solver 的 defender-reaction max 節點；剩敵方回合
  彈窗感知/handler 是實機部分）。
- 部分解決（決策端解、感知端待裝置）：#12（ActionCatalog/技能生成已
  進搜尋；畫面掃描與 execute 接線待 #9/實機）、#14（advisor 以世界座標
  定移動目標取代全域朝向；輸入品質仍依賴 #5/#6）。
- 本分支解決不了（正交）：#5（掃描計數失準——solver 輸入品質的根基，
  最重要的正交依賴）、#6、#1、#4（實機驗證）、#9（OCR——bridge 的
  UnitSpec 就是它的消費介面）、#8/#11（cache）、#10（戰略迴圈）、
  #18（視覺回歸庫）。

**恢復步驟（手機接回後）**：① `pgrep adb` 確認對照狀態→接回→截圖
（可能鎖屏，swipe 1164 430 1164 60 350 解）→ ② 先實機驗證 5b6c811
修正包（stage_info/keyguard 暗度閘/modal 逃生）→ ③ advisor 影子模式接
進 controller（每次啟動呼叫 advise() 只記流水帳不執行，離線比對 solver
vs 現行啟發式的決策差異，controller 接線的實機驗證證據由此而來）→
④ 敵方回合應對彈窗的感知標定（#3 的實機半）。cell_size 標定：戰術地圖
格距要從實測畫面量測。

**solver 待辦（不擋接線）**：Star2 probing；支援防禦的路徑感知幾何；
敵方 policy 模型精化（現為最近目標）；第三方勢力在 solver 中仍為惰性；
SUPPORT_ATTACK 尚未模擬。

## 舊快照（2026-07-08 凌晨）

**裝置現況**：手機已再次拔離（壓測結束）。遊戲上次確認停在 **HARD 2
戰鬥中 TURN 1 我方回合 hub**。無程式在跑。注意：手機的
`svc power stayon true` 未還原，接回後先跑
`adb shell svc power stayon false`。

**恢復步驟**：接回手機 → `adb devices` → 截圖（可能鎖屏，swipe 1164 430
1164 60 350 解）→ 確認是否仍在戰鬥（可能被登出，屆時從關卡列表重進，
會多耗 10 體力並經過新的 stage_info 動作）→ tmux 跑 `run_manual_battle.py`
實機驗證修正包。

**2026-07-07 深夜凍結調查結論**：7/5–7/7 三次無日誌硬當機（journal 於
07-06 00:09、07-07 00:30、07-07 09:35 戛然而止）。腳本審查無失控模式；
重現測試全數陰性——純 CPU/熱（heavy 全核 burst 一小時、Tctl 峰值 71°C）、
USB adb 流量＋heavy 組合（一小時）、傳輸中拔線（kernel 乾淨零 xhci 錯誤）。
剩餘嫌疑：WiFi adb 路徑（mt7921，凍結 2、3 的實際傳輸方式，未測）與
機率性硬體（建議 memtest86+ 過夜、查 BIOS 更新）。壓測工具在
`data/stress-test/`（stress.py light/heavy、capture_loop.py，gitignored）。
另：09:35 凍結發生在 git commit 寫入途中，留下 4 個 0-byte object 與
斷頭 HEAD——已修復（branch 指回 5b6c8118、重建 index，工作樹無損；
證據存 data/stress-test/git-corruption-evidence.txt）。本 commit 的
roadmap 快照即當時未遂 commit 的內容。

**20260706 深夜實測結論（feat/inner-goap，commits 79fcc0c/5b6c811）**：
clear loop 兩處斷點＋戰鬥三次靜默 stall 全數診斷完畢：
- main_menu 模板是 RANK 2 徽章裁圖，升到 RANK 13 後 0.783 過不了 0.90
  gate → 已重裁成出擊 MAIN STAGE 鈕（79fcc0c，rank/日期不變量）。
- stall 鏈：keyguard 的鎖圖示模板在暗色靜止戰場誤匹配（TM_CCOEFF 深色
  均勻區坑）→ 解鎖拖曳劃在敵方鋼坦克上 → 打開單位設置詳情 modal →
  無 handler 靜默循環＋假相位斷點灌高內部回合數＋unit_cards_present
  誤報 True。
- 修正包（5b6c811）六項：stage_info 畫面動作（AUTO 改手動＋勝利條件
  幀存流水帳＋TAP TO NEXT，使用者多次重申的需求落地）、keyguard 全幀
  暗度第二訊號（語料 30 張真鎖幀 8.7–31.6 全保留，gate 40）、modal
  逃生口（偵測標題帶＋點關閉 (1176,992)；語料 452 幀全中零誤報）、
  unit_cards_present 拒斥 modal、回合數以畫面 TURN 數字變化佐證、
  select 後三幀 post_select_probe 儀器。132 測試全過、ruff 乾淨。

**已知未修/未驗**：
- **mystery A 未解**：第三次 stall 的 modal 在點 FIRST_UNIT_CARD 後約
  4 秒重開、無 keyguard 事件——post_select_probe 儀器已上線，等下次
  發生離線重放。
- main_menu→stage_list 沒有 planner 邊（從 main_menu 起步會 no plan；
  上次手動導航繞過）。
- AdvanceStageInfo 未實機驗證：AUTO chip 離線 probe 0.895@(1820,54)
  沒問題，但 ensure_manual_auto 的靜態幀 gate 可能被 TAP TO NEXT 閃爍
  拖到逾時（有 30s timeout，會 degrade 到戰內重試，不致卡死）。

**接續待辦**：① 恢復戰鬥實機驗證修正包 → ② 重啟 #18 視覺回歸庫
（新素材：RANK 過期模板案例、暗鎖幀、modal 正負樣本、
stage_info、20260706-233158 run 的 hub 幀）→ ③ LLM perception 讀單位
資訊（ollama；格式樣本已採：武裝、技能／能力、OP 兩分頁優先，見
memory llm-perception-unit-info）。

**舊快照（2026-07-06）**：停在選擇關卡（機動戰士鋼彈 HARD 2，★★☆，
SECRET 已奪取），體力 25/80。

**模擬器/expectiminimax 定案（2026-07-06 深夜，feat/inner-goap 分支）**：
使用者確認要**求關卡最佳解**，depth-1 不夠、後端模擬必建。已定案收錄
機制（相位制回合、擊殺再動每回合重置、敵方相位的我方防禦應對
{閃避/防禦/反擊} 是 max 節點、格子移動與路徑封鎖拆支援防禦網、敵人
同樣有再動/支援且受特殊能力放大、支援次數每相位重置）；敵方節點預設
策略模型、介面保留 min；搜尋＝anytime 迭代加深 expectiminimax（殘局
自動精確，離線解全關=加大預算）。傷害/命中公式已從社群 wiki 調查入檔
`docs/combat-formulas.md`（閃避修正等待實機標定）。全文見
agent-architecture.md「戰鬥模擬器與 expectiminimax」節。**v0 骨架已完成
（#19）**：`battle/sim.py`（SimState/step/相位輪換/charge 重置）、
`formulas.py`（公式全參數化）、`enemy_model.py`（policy/min 可插拔）、
`solver.py`（迭代加深＋置換表＋Star1；Star2 與 TT 界值精修留 TODO）；
105 測試全過。裁量記錄：切比雪夫距離；`dodge_hit_penalty=20`、
`support_defend_multiplier=0.5` 為待標定預設；技能尚未接進 solver
行動生成（step 已支援）。新任務 #18＝視覺回歸測試庫（截圖整理成
標註案例釘 vision 閾值）。下一步＝#19 的 v1（格子可達性/路徑封鎖、
敵方回合應對彈窗感知）與 controller 整合。

**架構討論定案（2026-07-06 晚，commits 1dfc800/357bfab/0dccad9，全文見
agent-architecture.md）**：內層戰鬥 GOAP（#17 主 issue，收編 #12/#13）——
BattleState 統一盤面、ActionCatalog＝畫面掃描∪能力注入（擊殺再動等編成
知識灌入）、啟動內鏈式規劃（判死用實際數值 HP 非弧比例）、第三方可控性
開戰探測；**MCTS/模擬器非禁令**（先前誤記為紅線，CLAUDE.md 已更正）；
前置條件即內容（體力管理=資料綁定前置的實例）；編成兩階段（先讀取同步）；
目標介面預留戰役。缺什麼之後再補。

**離線批次（2026-07-06 完成、已 push、已關 issue）**：
- **#15 流水帳決策事件配截圖**（da1bed3）：每個決策事件（select_unit/move/
  attack/standby/tactical_map/story_dialog/hidden_battle_warning/end_turn/
  finish）存一張縮圖 JPEG（長邊 1280、q85）到 `data/runs/<ts>/frames/
  battle_NN/`，存幀失敗軟性略過不中斷。61→65 測試。
- **#16 隱藏戰鬥 WARNING 彈窗辨識**（f3ead6d）：`vision.is_hidden_battle_
  warning`（彈窗 1.0、他處 ≤0.21、gate 0.6）＋控制器依 `hidden_battle_policy`
  決策（預設 challenge 挑戰；OCR 戰力門檻留待實機）。彈窗自帶 AUTO 鈕不碰。

**下一步＝實機驗證**（需使用者提供測試機）：跑一場含索敵與（若觸發）隱藏
戰鬥的戰鬥，驗證 #14 索敵重構（cd89b9f enemy_onscreen）與 #16 彈窗決策，
並讓 #15 的 frames 自然產生，作為 #5/#6/#12/#3 校準的第一手資料。

**任務改用 GitHub Issues 管理**：repo `git@github.com:DeanXu2357/ggge_ai.git`
（public、main）、看板 https://github.com/users/DeanXu2357/projects/2 。
本檔的「工作安排」細節改以 issue #3–#15 追蹤，見 [[github-repo-and-tasks]]。

**今日重大成果**：
- **HARD 2 含隱藏戰鬥由我們的程式全自動通關**（23:43，TOTAL SCORE 8,525
  NEW RECORD、破壞 14/14 含增援、6/10 存活、受損 43%）。流水帳
  `data/runs/20260705-232132/battle_01.jsonl`（outcome battle_result）。
- 四個戰術修正實機驗證：索敵重構（1ddc407，單位改朝世界座標敵群前進）、
  死亡台詞對話自動推進（bd6b132，本場自動處理 5 次無需人工救）、
  殘機單卡辨識（#1）、戰敗畫面辨識（#2，本場贏了未觸發但已上線）。
- 中斷落地流水帳（8350f60）。

**本場暴露、已開 issue 的缺陷**：
- #14（high）索敵 fallback 過粗：鏡頭錨定每次 miss（#6）→退到全域單一朝向
  →前排/側翼單位（如 GQuuuuuuX）走離最近敵人。**最該優先修的戰術缺陷。**
- #12（high）EN 歸零不會用 SKILL/SUPPORT 補能量，直接待機（實戰確認，
  行動列的 SKILL SP／SUPPORT EN 1/1 鈕被無視）。
- ~~#15 流水帳決策事件配截圖~~（已解，da1bed3）。
- ~~#16 隱藏戰鬥 WARNING 彈窗辨識與決策~~（已解，f3ead6d）。
- #5 掃描仍低估我方/第三方（我方 10 掃到 2–6、第三方恆 0）。**#14 的根因。**

**帳號現況**：RANK 11、資金 158,380、體力 25/80。隊伍戰鬥力 111,530
（遠超 HARD 2 建議 70,000——本 session 反覆確認敗因在程式非數值）。

**下一步（依 issue 優先序）**：先修戰術三本柱 #14（索敵 fallback）、#12
（EN/技能行動掃描）、#15（決策截圖）——這三個直接決定戰術品質；再回架構
主線 #7 歸因、#8 cache、#9 OCR、#10 戰略迴圈。

## 現行計畫

架構已與使用者重新定案，全文見 `docs/agent-architecture.md`。核心原則：
程式只內建「機制」不內建「內容」；不建關卡資料庫（跨執行無狀態）；
執行輸入只有目標關卡 + 可用的局外成長 action；關內動作空間完全開放。
不做自建模擬器/MCTS——戰術用遊戲內建預測值做 1-ply 貪婪，再升 1.5-ply
站位安全；戰略靠觀測式戰後歸因決定補強方向。

實作順序（詳見架構文件）：
1. 戰鬥流水帳 + run-scoped 黑板
2. HARD 1 探測（先第 12 關回歸驗證 62bef06，再 HARD 1 收戰敗流程與錨點）
3. OCR 數字讀取（戰力/資金/預期傷害）
4. 戰後歸因 v1（數值差距 vs 程式缺陷）
5. 戰略迴圈（goal + allowed actions、強化與 farming）
6. 行動掃描器 v1（SUPPORT/技能鈕，EN 補給）
7. 1.5-ply 站位安全評估

第 12 關全流程 SUCCESS 記錄（2026-07-04 23:36）：導航→戰鬥→劇情跳過→
結算→回關卡列表全自動，戰鬥中劇情與鎖屏皆自動處理。

## 已完成

### 基礎架構（M1）
- GOAP 核心：`WorldState`（不可變、可雜湊）、`Action`（前置條件/效果/execute）、A* 規劃器（`core/planner.py`）。
- Agent 迴圈（`agent/loop.py`）：sense → plan → act → verify，含信念記憶（latch 無法直接感知的效果，如 `stage_cleared`）、「有進展就重新規劃、無進展才計失敗」的容錯策略。
- 感知/致動介面：`Perception` protocol、`AdbActuator`（landscape 2340x1080 參考座標、依實際解析度縮放）。

### 視覺辨識（M2）
- OpenCV 模板比對：manifest 驅動（`assets/templates/manifest.yaml`），16 個畫面錨點 + 約 20 個元件模板，含搜尋區域限定。
- `RecognizerPipeline`：多辨識器串接、信心度短路（為未來 OCR / Ollama LLM 辨識預留）。
- 標定工具：`scripts/capture.py`、`scripts/crop.py`、`scripts/verify_match.py`。
- 動態偵測（`vision/motion.py`）：`is_static()` 以幀差分辨可操作畫面 vs 劇情/攻擊動畫。

### 通關流程（實機驗證）
- 六個 flow action：進出擊準備 → 出擊（處理首次下載彈窗）→ 跳過劇情（MENU→SKIP，含戰鬥中劇情）→ 戰鬥等待 → 關閉結算 → 排掉獎勵鏈回到關卡列表。
- 新手教學提示框（coach-mark）以 `hint_dialog` 模板偵測並排除。
- AUTO 按鈕三態偵測（青=全自動、紅=敵回合自動、無色=全手動），argmax 模板比對。
- 導航迴圈端到端可跑；第 7~9 關已通關（但 8、9 是內建 AI 打的——這正是要修正的問題）。

## 目前問題（下一步的起點）

戰鬥階段目前依賴遊戲內建全自動 AI，違反專案核心目標：**戰鬥必須由我們的程式操作**。
已確認方向：進戰鬥後將 AUTO 切到無色（全手動），戰術 v1 用簡單啟發式。

已知技術障礙：
- 黑畫面/載入轉場輪詢太粗，錯過可操作的第一幀，內建 AI（青色 AUTO 跨關卡保留）就自己開打。
- 攻擊動畫期間 AUTO 按鈕被遮擋，probe 會回 None——讀寫 AUTO 只能在 `is_static` 的畫面上做並重試。

## 下一步：手動戰鬥控制器

1. **快速接手戰鬥開始**
   - 出擊後以次秒級間隔輪詢，穿過黑畫面/載入畫面，抓到第一個可操作的 battle_map 靜止幀。
   - 立刻把 AUTO 切到無色全手動（is_static 閘控 + 重試）。AUTO 狀態跨關卡保留，之後的關卡只需驗證。
2. **戰鬥 UI 探索與標定**（手動模式下逐步截圖）
   - 我方單位選取、移動格子、選擇武裝、目標選取、攻擊確認、待機、回合結束、單位列表。
   - 單位/敵人位置偵測可能需要顏色/blob 偵測而非模板比對（單位外觀隨編成變動）。
3. **v1 戰術啟發式**
   - 每個可行動單位：移動到最近敵人 → 攻擊 → 下一單位；無可行動單位則結束回合。
   - 全手動模式下也要推進敵方回合（點擊確認敵方行動的畫面）。
4. **整合進 GOAP**
   - 以新的 `ManualBattle` action 取代 `AutoBattle`，效果不變（battle_map → battle_result + stage_cleared），戰術細節封裝在 action 內部（或後續拆成戰鬥層子規劃器）。
5. **驗收**：第 10 關起用全手動控制器實測通關。

## 鎖屏防護（2026-07-04 完成）

Samsung 閒置約 3 分鐘自動鎖屏會吞掉所有點擊，而模板仍能透過變暗的畫面比對成功，
造成長時間戰鬥（敵方回合、劇情暫停）中途卡死——第 12 關兩次全流程測試都因此失敗。
解法（`actuation/keyguard.py`）：
- 偵測：`dumpsys window policy` 的 `KeyguardStateMonitor mIsShowing`（實機驗證可靠）。
- 解鎖：KEYCODE_WAKEUP → `wm dismiss-keyguard` → 從鎖頭圖示往上拖曳（raw 座標，不隨遊戲橫向旋轉）。
- 整合：AgentLoop 每次迭代檢查；ManualBattleController 每 15 秒檢查。
- 戰鬥逾時改為活動制：總預算 60 分鐘 + 10 分鐘無活動守門（動畫算活動）。

## 戰鬥控制器 v2 改進項目

（使用者 2026-07-04 實戰觀察提出）

- **技能與支援能力運用**：v1 只會攻擊/移動/待機。實測發現單位 EN 耗盡時，
  控制器不會使用技能或支援能力補 EN，之後只能待機。單位需要知道自己可用的輔助手段：
  - 角色技能（下中 MP 圓鈕，消耗 SP，如「強勢 DAMAGE+10%」類 buff）
  - 支援能力（下中 SUPPORT 鈕，如 EN 補給 1/1、回復 HP 1/1——EN 桶/愛心圖示）
  - 機體額外技能（武裝選擇環上的「技能」鈕、變形 MANEUVER 等）
  - 決策時機：EN 不足以發動任何武裝時先補 EN；HP 低時回復；進攻前掛 buff
- 感知需求：讀取當前單位 EN/HP 數值（OCR）或至少偵測「所有武裝都因 EN 不足不可用」的狀態
  （武器輪盤圖示灰化/紅字），以及 SUPPORT/技能鈕的可用狀態（次數、SP 量表）
- ~~**主動索敵移動**~~（2026-07-04 完成）：`battle/vision.py` 的
  `find_enemy_units`/`find_ally_units` 以單位腳下的底座圓弧做敵我判斷
  （敵=紅橘弧、我=藍弧；hue + 寬扁長寬比 blob 過濾，我方紅色機體與威脅格「!」不會誤判）。
  移動模式改為：朝最近可見敵人前進（以移動範圍質心當作自身位置代理），
  偵測不到敵環才退回威脅格質心。第 12 關實機畫面驗證 6/6 敵、4/4 友、零誤判。
  尚未處理：敵人全部在鏡頭外時需要捲動地圖索敵。
- 其他既知改進：切換目標選擇最優目標（現在只吃預設）、
  武器選擇考慮傷害/EN 效率而非固定順序

## 大方向：以「完成某一關」為 GOAP 目標的全域策略層

（使用者 2026-07-04 提出；2026-07-05 細化定案於 `docs/agent-architecture.md`，
與本節出入處以架構文件為準——特別是「跨執行無狀態、不存關卡資料」原則）

GOAP 的目標設定為「完成指定關卡」，而達成手段不只遊戲內的戰鬥執行，
還包含遊戲外的資源養成。規劃器要能判斷：目前隊伍打不過這關時，
如何用遊戲外資源（強化、開發、編成調整等）改變/強化隊伍後再挑戰。

概念上是兩層 GOAP：

- **戰略層**（新增）：世界狀態含隊伍戰力、持有資源（資金、經驗值道具、
  機體/角色清單）、目標關卡難度估計。action 例如：強化機體、開發新機體、
  調整編成、重打低難度關卡賺資源、直接挑戰目標關卡。
  「挑戰失敗」是可感知的回饋，會更新戰力估計並觸發重新規劃（先養成再戰）。
- **戰術層**（現有）：關卡內的導航與手動戰鬥控制器。

前置需求：
1. 感知隊伍/資源狀態 —— 需要 OCR（讀資金、等級、戰力數值）或 LLM 辨識，
   這會把原本延期的 OCR/Ollama 辨識器變成必要項目。
2. 標定養成相關畫面：強化、開發、編成（unit_setup 深入）、機體詳情。
3. 戰力 vs 關卡難度的估計模型（可先用「推薦戰力/敵方等級」等遊戲內顯示值）。
4. 失敗偵測：戰敗結算畫面的錨點與處理流程。

**HARD 1 實測計畫**（使用者 2026-07-04 指示）：以現有控制器挑戰 HARD 1
（建議 65,000 vs 我方約 33,000，預期失敗），觀察戰敗流程並盤點缺口。
期望方向再次確認：關卡內戰鬥真的完成不了時，要能從局外成長
（強化/開發/刷資源）想辦法完成關卡——即戰略層是硬需求，不是可選項。

## 之後（延期項目）

- Ollama 多模態 LLM 辨識器、OCR 辨識器、`recognition.yaml` 執行期組態。
- 「略過」掃蕩機制解鎖後的快速重複通關路徑。
- 更聰明的戰術（地形、射程、屬性相剋）。

---

## 初版系統架構文件

（原 docs/architecture.md,2026-07-04;GOAP 分層/Recognizer pipeline/
目錄結構仍與現況大致相符,但正式架構文件是 agent-architecture.md;
里程碑 M1-M6 已全數完成或被 roadmap 取代;recognition.yaml 執行期
組態從未實作。）

# 專案架構設計

## 目標

自動通關 SD鋼彈G世代（`com.bandainamcoent.gget_WW`）。核心採用 GOAP（Goal-Oriented Action Planning）：給定 goal，規劃器自動從已定義的 action 集合中搜索出達成路徑，而非撰寫寫死的流程腳本。

## 語言：Python 3.12+

- perception 依賴（uiautomator2、OpenCV、OCR）皆為 Python 生態，已驗證可用
- 回合制遊戲規劃頻率低，無效能壓力；GOAP 核心只是 A* 搜索
- 主要開發時間花在調整樣板圖與 action 定義，Python 迭代最快

## 分層架構

```
┌─────────────────────────────────────────────┐
│  Agent Loop（sense → plan → act → verify）  │
├─────────────────────────────────────────────┤
│  GOAP Core                                  │
│  WorldState / Action / Goal / Planner(A*)   │
├──────────────────────┬──────────────────────┤
│  Domain（遊戲知識）   │                      │
│  screens / actions / │                      │
│  goals 定義          │                      │
├──────────────────────┴──────────────────────┤
│  Perception（介面）   │  Actuation（介面）    │
│  → GameState         │  ← tap/swipe/key     │
├──────────────────────┼──────────────────────┤
│  AdbPerception       │  AdbActuator         │
│  (uiautomator2 截圖   │  (uiautomator2       │
│   + OpenCV/OCR)      │   tap/swipe)         │
│  未來：其他實作…      │  未來：其他實作…      │
└──────────────────────┴──────────────────────┘
```

### 設計原則

1. **GOAP 覆蓋全域**：選單導航也是 GOAP action（前提 `current_screen=main_menu`、效果 `current_screen=stage_select`）。新增畫面只需補 action 定義，規劃器自動探索路徑。
2. **Perception 介面定在語意層**：回傳結構化 `GameState`（目前畫面、單位、HP、可點擊元素），影像辨識細節封裝在 ADB 實作內。未來換成封包側錄、模擬器記憶體讀取等方式時，GOAP 層不動。
3. **戰鬥智能先簡後繁**：第一版用啟發式（派最近單位、攻擊最近敵人）打通整條迴圈，之後再迭代戰術規劃。

## GOAP Core

```python
WorldState = dict[str, Value]      # 符號化事實，如 {"screen": "battle_map", "my_turn": True}

class Action(Protocol):
    name: str
    cost: float
    def preconditions_met(self, state: WorldState) -> bool
    def apply_effects(self, state: WorldState) -> WorldState   # 規劃期模擬
    def execute(self, actuator, perception) -> bool            # 實際執行

class Goal(Protocol):
    def is_satisfied(self, state: WorldState) -> bool
    def heuristic(self, state: WorldState) -> float

class Planner:
    def plan(self, state: WorldState, goal: Goal, actions: list[Action]) -> list[Action] | None
```

- 規劃器用 A*，以 action cost 總和為代價、goal heuristic 為引導
- **執行後驗證**：每個 action 執行完重新 perceive，比對實際狀態與預期效果；不符即重新規劃（replan），這是對抗遊戲彈窗、網路延遲、辨識失誤的主要手段
- 同一 action 連續失敗 N 次即中止並留下截圖與狀態 dump，供除錯

## Perception 介面

```python
class Perception(Protocol):
    def observe(self) -> GameState

@dataclass
class GameState:
    screen: ScreenId                 # 目前畫面的分類結果
    elements: list[UiElement]        # 可互動元素（id、bbox、信心值）
    battle: BattleState | None       # 戰鬥中才有：單位列表、位置、HP、行動狀態
    raw_screenshot: Path             # 原始截圖留檔，供除錯
```

`GameState → WorldState` 由一個轉換層負責（例如 `battle.enemies_alive == 0` 轉成 `{"all_enemies_defeated": True}`），讓 GOAP 只面對符號化事實。

### AdbPerception（第一個實作）

- 截圖：uiautomator2 `screenshot()`
- 辨識：交由 Vision 辨識層（見下節），AdbPerception 只負責取得影像並組裝 `GameState`
- 戰鬥棋盤解析：格子座標系標定 + 單位圖示比對

## Vision 辨識層（多辨識器架構）

辨識不綁定單一技術，定義統一的 `Recognizer` 介面，多個實作可依設定組合使用：

```python
class Recognizer(Protocol):
    name: str
    def classify_screen(self, img: Image) -> list[ScreenCandidate]        # 畫面分類
    def detect_elements(self, img: Image, query: Query) -> list[UiElement]  # 元素偵測
    def read_text(self, img: Image, region: Bbox | None) -> list[TextResult]  # 文字讀取
```

三種能力皆回傳附信心值（confidence）的結果，未支援的能力可回傳空集合。

### 實作一：TemplateRecognizer（OpenCV 樣板比對）

- 錨點樣板比對做畫面分類、按鈕定位（`assets/templates/`）
- 快（毫秒級）、座標精準、結果穩定可重現
- 弱點：樣板要人工裁切維護，遊戲改版或未見過的彈窗就失效

### 實作二：OcrRecognizer

- 讀取 HP、傷害數字、關卡名稱等文字（候選：PaddleOCR，中日文較佳）
- 只實作 `read_text`，其餘能力回傳空

### 實作三：LlmRecognizer（Ollama 多模態模型）

- 透過 Ollama API 把截圖丟給多模態模型，以 JSON schema 約束輸出（Ollama 支援 structured outputs）
- 本機已可用模型：`gemma4:31b` / `gemma4:26b` / `gemma3:27b`（皆支援影像輸入）
- 強項：
  - 零樣板成本理解任意畫面——處理沒見過的彈窗、活動公告、錯誤訊息特別有用
  - 語意層面的判斷（「哪顆按鈕是出擊」「目前是誰的回合」）
  - 遊戲風格化字體的閱讀常比傳統 OCR 穩
- 弱點與對策：
  - **座標定位不準**：一般多模態模型輸出的 bbox 不可靠。對策：(a) 讓 LLM 從樣板比對已找到的候選元素中「挑選」而非自行給座標；(b) 需要 LLM 獨立定位時，在截圖上疊加編號網格，讓它回答格號再換算座標
  - **延遲高**（秒級、31B 模型更久）：只放在 fallback 與低頻決策，不進高頻迴圈
  - **輸出不穩定**：temperature 設 0、JSON schema 約束、結果一律帶信心值進融合層裁決

### 融合策略（RecognizerPipeline）

執行時可依設定檔選擇啟用哪些辨識器與組合方式：

```yaml
# config/recognition.yaml 示意
screen_classify:
  - recognizer: template
    accept_above: 0.90        # 信心值達標直接採用
  - recognizer: llm           # 前者不達標才 fallback
    model: gemma4:26b
element_detect:
  - recognizer: template
  - recognizer: llm
    mode: arbitrate           # 樣板結果模糊時由 LLM 在候選中裁決
text_read:
  - recognizer: ocr
  - recognizer: llm
    mode: fallback
```

- **fallback 鏈**：依序嘗試，信心值達門檻即採用——常態走快速便宜的樣板比對，異常畫面才升級到 LLM
- **arbitrate**：多個候選難分高下時，把候選連同截圖交給 LLM 裁決
- **未知畫面兜底**：所有辨識器都無法分類時，由 LLM 描述畫面並建議脫困動作（例如關閉彈窗），這是 agent 異常恢復（M5）的關鍵能力
- 所有辨識結果統一落地 log（輸入截圖、各辨識器輸出、最終採用），供離線回歸與調參

## Actuation 介面

```python
class Actuator(Protocol):
    def tap(self, x: int, y: int) -> None
    def swipe(self, x1, y1, x2, y2, duration_ms: int) -> None
    def key(self, keycode: str) -> None
```

第一個實作 `AdbActuator` 包 uiautomator2。遊戲為橫向運行，座標一律以 2340x1080 基準定義，實作層在每次操作時查詢當前螢幕尺寸換算，避免裝置旋轉造成座標錯位。

## Domain（遊戲知識層）

遊戲相關定義全部集中在這層，與引擎解耦：

- `screens.py` — ScreenId 列舉與各畫面的錨點樣板對應
- `actions/navigation.py` — 選單導航 action（點擊某按鈕 → 畫面轉移）
- `actions/battle.py` — 戰鬥 action（選單位、移動、攻擊、待機、結束回合）
- `goals.py` — 如 `StageCleared(stage_id)`、`ReachScreen(screen_id)`

## 專案目錄結構

```
ggge_ai/
├── pyproject.toml
├── src/ggge_ai/
│   ├── core/                # GOAP 引擎（不含任何遊戲知識）
│   │   ├── state.py         # WorldState
│   │   ├── action.py        # Action / Goal 介面
│   │   └── planner.py       # A* 規劃器
│   ├── domain/              # 遊戲知識
│   │   ├── screens.py
│   │   ├── goals.py
│   │   └── actions/
│   ├── perception/
│   │   ├── base.py          # Perception 介面 + GameState 資料類
│   │   └── adb/             # uiautomator2 + OpenCV 實作
│   ├── actuation/
│   │   ├── base.py
│   │   └── adb.py
│   ├── agent/
│   │   └── loop.py          # sense-plan-act-verify 主迴圈、replan、失敗處理
│   └── vision/
│       ├── base.py          # Recognizer 介面、共用資料類
│       ├── pipeline.py      # 融合策略（fallback / arbitrate）
│       ├── template.py      # OpenCV 樣板比對
│       ├── ocr.py           # OCR
│       ├── llm.py           # Ollama 多模態模型
│       └── geometry.py      # 座標換算、網格疊加等工具
├── config/                  # recognition.yaml 等執行期設定
├── assets/templates/        # 各畫面錨點與按鈕的裁切樣板圖
├── tests/                   # core 規劃器可純單元測試；vision 用存檔截圖做回歸測試
├── scripts/                 # 輔助工具：截圖標定、樣板裁切等
├── docs/
└── secrets/                 # gitignored
```

## 工具鏈

- 套件管理：`uv`（lockfile、虛擬環境一體）
- 測試：`pytest`——GOAP core 與 GameState→WorldState 轉換為純函式，易測；vision 部分以既存截圖做離線回歸測試，不依賴實機
- Lint/format：`ruff`
- 主要依賴：`uiautomator2`、`opencv-python`、`numpy`、`ollama`（官方 Python client）；OCR 需要時再加

## 里程碑

1. **M1 — 骨架與 GOAP core**：規劃器 + 單元測試，不碰實機 ✅（uv 專案、core/planner A*、Recognizer 介面與 pipeline、AgentLoop、AdbActuator/AdbPerception 骨架、17 個測試通過）
2. **M2 — 畫面辨識最小集**：Recognizer 介面與 pipeline、樣板比對實作、LLM 辨識實作（Ollama）、截圖標定工具、3–5 個核心畫面的分類與按鈕偵測
   - 標定工具已完成 ✅：`scripts/capture.py`（實機截圖）、`scripts/crop.py`（裁切樣板並登記 manifest，支援 GUI 框選與 `--box` 直接給座標）、`scripts/verify_match.py`（離線驗證分類/偵測，可輸出標註圖）；樣板統一登記於 `assets/templates/manifest.yaml`（`vision/manifest.py`）
   - 實機驗證：截圖成功，遊戲為橫向 2340x1080、繁中介面
   - 待做：蒐集各核心畫面截圖並裁切錨點樣板、LLM/OCR recognizer 實作
3. **M3 — 導航打通**：從遊戲啟動 GOAP 導航到任一關卡的出擊畫面
4. **M4 — 戰鬥迴圈**：啟發式戰鬥決策，自動打完一場簡單關卡
5. **M5 — 完整通關迴圈**：戰後結算 → 回選單 → 下一關，含異常恢復（彈窗、斷線）
6. **M6+**：戰術強化、其他 perception 實作

---

## 裝置控制技術研究

（原 docs/device-control-research.md,2026-07-04。uiautomator2 選型
定案沿用至今;三星 USB 偵錯連線步驟在裝置重置時或許還用得上;
遊戲套件名 com.bandainamcoent.gget_WW 與啟動指令仍有效,但日常
連線走 src/ggge_ai/app.py 的 connect()。）

# 手機控制技術研究

## 目標
透過 USB 傳輸線讓電腦端程式操作 Android 手機，用於後續自動化解 SD鋼彈G世代 手機遊戲關卡。

## 已測試環境
- 電腦：Linux，`adb` 已安裝於 `/usr/bin/adb`
- 手機：Samsung SM-G9900，Android 12（SDK 31）
- 解析度：1080x2340

## 連線步驟（三星手機的常見坑）
1. 開啟【設定 > 關於手機】連點【組建編號】7 次開啟開發者選項
2. 【設定 > 開發者選項】開啟【USB 偵錯】
3. 用傳輸線接上電腦
4. **重點**：下拉通知列點開 USB 選項，把用途從「僅充電 / 檔案傳輸(MTP)」改成「傳輸檔案」，MTP 模式下不會啟用 adb debug 介面，授權對話框也不會跳出來
5. 手機會跳出「允許 USB 偵錯」對話框，勾選「一律允許使用這台電腦進行偵錯」後按允許
6. 若對話框沒跳出，先到開發者選項執行【撤銷 USB 偵錯授權】，拔插傳輸線重試

驗證指令：
```
adb devices -l
# 應顯示 device 而非 unauthorized
```

## 控制方案比較

| 方案 | 說明 | 優點 | 缺點 |
|---|---|---|---|
| 純 ADB shell (`input tap/swipe`, `screencap`) | 直接下指令 | 最輕量，無額外依賴 | 沒有元素辨識，座標寫死，遊戲改版就失效 |
| **uiautomator2**（已選用） | Python 套件，透過 adb 推送一個常駐 agent (atx-agent) 到手機，用 HTTP API 操作 | 安裝快、不需 Java/Appium Server、支援截圖/座標點擊/元素查找 (XML hierarchy)、Python 生態好整合影像辨識 | 主要支援原生 Android View，遊戲多半是 Unity/Cocos2d 全螢幕渲染，UI 樹通常抓不到內部元素，仍需仰賴「螢幕截圖 + 樣板比對/座標點擊」 |
| Appium | 跨平台自動化框架，需另外起 Appium Server (Node) | 業界標準、支援 iOS | 較重，需要 Java + Node + Appium Server 常駐，對 Unity 遊戲一樣抓不到內部元素 |

**結論**：由於 SD鋼彈G世代 是遊戲引擎全螢幕渲染（非原生 View），uiautomator2 的元素查找對遊戲畫面用處有限，實際操作會以「screencap 截圖 → OpenCV 樣板比對 / 影像辨識找座標 → uiautomator2 送出 tap/swipe」為主要模式。uiautomator2 在此仍有價值：截圖、按鍵注入、應用啟動/切換、裝置狀態查詢都很穩定好用。

## 遊戲資訊
- 套件名稱：`com.bandainamcoent.gget_WW`（SD GUNDAM G GENERATION）
- 使用帳號：`hsupy23@gmail.com`（研究專用 Google 帳號，資訊存於 `secrets/google_account.local.json`，未進版控）

啟動 / 關閉遊戲指令：
```bash
adb shell monkey -p com.bandainamcoent.gget_WW -c android.intent.category.LAUNCHER 1
adb shell am force-stop com.bandainamcoent.gget_WW
```

## 目前進度
- [x] adb 裝置授權成功
- [x] `pip install uiautomator2` 完成
- [x] `python3 -m uiautomator2 init` 完成，成功推送 atx-agent 並可截圖/查詢狀態
- [x] 建立研究專用 Google 帳號並登入 Google Play
- [x] 安裝 SD鋼彈G世代（`com.bandainamcoent.gget_WW`）
- [ ] 遊戲畫面截圖 + 關卡棋盤/單位辨識（下一階段程式部分）
- [ ] 座標點擊操作驗證（需要先完成遊戲新手教學、進到關卡畫面）

## 常用指令備忘
```bash
# 確認裝置
adb devices -l

# Python 連線範例
python3 -c "import uiautomator2 as u2; d = u2.connect(); print(d.info)"

# 截圖
python3 -c "import uiautomator2 as u2; u2.connect().screenshot('screen.png')"
```

---

## 舊 session handoff

（原 docs/handoff-next-session.md,2026-07-07 的一次性開工提示詞;
HARD 2 早已通關,內容全數過時,僅存流程風格參考。）

# 下次工作提示詞（HARD 2 實測起點）

把下面整段貼給 Claude Code 當第一則訊息即可。

任務：恢復 HARD 2 探測（E2），實戰驗證戰術地圖 v1，收集戰敗流程資料。

先讀 CLAUDE.md、docs/roadmap.md 的暫停快照、docs/agent-architecture.md，
然後嚴格照以下流程執行。每個實機動作後都要截圖看圖確認，不確定就停下來問我。

## 第 0 步：確認裝置與遊戲狀態

1. `adb devices` 確認 R5CRC37JBYJ 在線。
2. 截圖判斷目前畫面：
   - 還在 HARD 2 戰鬥中（TURN 1 我軍回合）→ 直接第 1 步。
   - 被鎖（畫面變暗或鎖頭圖示）→ 先隨便點一下喚亮，再
     `adb shell input swipe 1164 430 1164 60 350` 解鎖，截圖確認後繼續。
   - 遊戲被登出/回到主畫面 → 重新進場：關卡(1230,1050) → 主要關卡 →
     初鋼系列 → 選擇(1989,889) → 點 HARD 2 節點 → 出擊準備(1989,891) →
     出擊(2040,1030)，有下載彈窗按確認(1369,851)，簡報畫面點中央跳過。

## 第 1 步：啟動控制器（tmux 背景）

```
tmux new-session -d -s e2 "uv run python scripts/run_manual_battle.py 2>&1 | tee /tmp/e2_run.log"
```
掛 watcher（背景 bash，每 30 秒檢查一次，命中就結束並輸出 log 尾段）：
結束訊號=「controller finished」；異常訊號=「Traceback」；tmux session
消失也要視為結束。

## 第 2 步：驗證戰術地圖（看 log，前 5 分鐘內就有結論）

必須看到的訊號：
- `scout: tactical map has N enemies / M allies / K third-party`
  —— N 應該接近 10（這關敵軍 10 台）。N=0 或只有 1-2 → 掃描有問題，
  截圖對照實際畫面，檢查相位相關的 response 與座標合併。
- `tactical-map enemy at (...) (screen), camera offset (...)`
  —— 星座錨定命中，畫面外敵人成為移動目標。整場一次都沒出現的話，
  記錄下來（錨定條件可能太嚴），但不要中途改碼，先讓這場打完。
- `new turn detected (turn N)` —— 回合邊界偵測，N 應隨戰局遞增。

異常處理：controller crash → 看 Traceback 修（小修，pytest 過再重啟
tmux）；重啟後遊戲仍在戰鬥中，控制器會自己接手。

## 第 3 步：戰敗流程收集（本場的主要目的，預期會輸）

我方全滅時控制器多半不認得戰敗畫面，會走到 idle timeout（最長 10 分鐘）
才退出——這是預期行為，不是 bug。在那之前：
1. watcher 回報結束或 log 安靜下來後，立刻截圖。
2. 把戰敗結算的完整畫面序列截下來（戰敗動畫→結算→點掉後回到哪個畫面），
   每點一步截一張。
3. 從戰敗結算截圖裁出穩定錨點（畫面上固定的「戰敗/LOSE」字樣區域），
   存 assets/templates/screens/ 候選，用 scripts/verify_match.py 驗證
   對戰敗幀高分、對其他畫面低分。

## 第 4 步：流水帳分析與收尾

1. 檢查 `data/runs/<時間戳>/battle_01.jsonl`：
   - `turns` 應 >1（相位斷點修正的實戰驗證）
   - 有 `tactical_map` 事件、`move` 事件的 basis 分布
     （enemy_arc/tacmap/threat_centroid/scout_hint 各佔多少）
   - `factions` 快照的 allies 數應隨戰局遞減（被打死）
2. 用流水帳做第一次戰後歸因（人工版）：我方在第幾回合開始減員、
   擊殺了幾台、standby 原因分布——寫成簡短結論。
3. 更新 docs/roadmap.md 暫停快照（裝置現況＋下一步），commit。

## 本場之後的既定順序（別跳步）

1. 戰後歸因 v1 程式化：先只分「數值差距 vs 程式缺陷」兩類。
2. cache 匯入機制（見 agent-architecture.md「內容 cache」節）：
   schema＋載入器＋黑板匯入＋未命中回退；試點 cache 用 HARD 2 面板
   截圖手抄（assets/screenshots/20260705-1538*.png、-154019.png）。
   注意：我方機體受養成影響，cache 只記身分/基礎資料，實數現場讀。
3. 敵方資訊面板 OCR：現場讀取→黑板→寫回 cache 的完整路徑；
   OCR 數字（戰力/資金/預期傷害）共用機制。
4. 戰略迴圈（強化＋farming）→ cache 建檔腳本（本地 LLM 只轉錄文字，
   數字一律 OCR）→ 最後才做 cache 校驗。

## 紅線提醒（違反=返工）

- 結束回合對話框永遠選左「待機並結束」，絕不選右邊自動戰鬥。
- 不寫任何關卡專屬資料進程式碼；跨執行不留關卡記憶。
- vision.py 的 HSV 閾值沒有截圖證據不准動。
- 連續兩次修不好同一個問題就停下來問使用者。


---

## screen-map 的帳號時代紀錄

（2026-07-14 精簡時自 screen-map.md 移入:2026-07-04 探索當時的帳號
進度快照與首次通關實證。帳號現況以 roadmap 快照為準——RANK 9+、
HARD 已解鎖、鋼彈X 系列進行中,下表的鎖定清單多已解鎖。）

### 鎖定中的功能（RANK 2 時代）


| 功能 | 位置 | 解鎖條件 |
|---|---|---|
| MASTER LEAGUE | 關卡類型選擇 | 玩家 RANK 5 |
| UPGRADE STAGES（強化培育） | 關卡類型選擇 | 完成機動戰士鋼彈關卡 9 |
| ETERNAL ROAD（永恆之路） | 關卡類型選擇 | 完成機動戰士鋼彈關卡 14 |
| CHALLENGE（挑戰） | 系列選擇左下 | 未顯示條件，鎖頭圖示 |
| 略過（掃蕩） | 關卡列表右側 | 鎖定，顯示剩餘 3/3 |
| Z鋼彈 / SEED 系列 | 系列選擇 | 前置系列進度 |
| 個人基地部分設施 | 個人基地 | ??? 區域，鎖頭圖示 |
| 使命側欄部分項目 | 使命畫面左側 | 鎖頭圖示 |

### 自動化上的意義（RANK 2 時代的分析）


- 通往戰鬥的最短路徑是 `main_menu → btn_sortie_main`，兩步即到關卡列表
- 目前帳號可自動化的迴圈：第 7 關起的主線推進（NORMAL 6/14 → 14/14），過程會自然解鎖 UPGRADE STAGES（關卡 9）與 ETERNAL ROAD（關卡 14）
- 「略過」解鎖後可對已 3 星關卡掃蕩，屆時自動化重複刷關會改走該路徑
- 機體補給有免費 10 連未領，建議手動處理（轉蛋選擇涉及帳號價值判斷，不納入自動化）

### 完整通關迴圈首次實證（2026-07-04 第 7 關）


```
stage_list ─出擊準備─▶ unit_setup ─出擊─▶ [下載彈窗(首次)] ─▶ story ─MENU→SKIP─▶
battle_map（切 AUTO 全自動，等待結束）─▶ battle_result ─繼續─▶ reward(EXP) ─繼續─▶
[解放招募等彈窗，TAP TO NEXT] ─▶ reward(清單) ─故事─▶ story ─MENU→SKIP─▶ Loading ─▶
stage_list（下一關 NEXT，迴圈閉合）
```

實測結果：TOTAL SCORE 11,466（3 條件全達成）、殲敵 12/12、存活 7/8、受損 19%、耗時約 4 分鐘。
第 8 關（哀・戰士，建議戰鬥力 21,000，水陸地形）已解鎖為 NEXT。

戰後畫面錨點：`battle_result`（TOTAL SCORE 字樣）、`reward`（REWARD 標題）、`story`（MENU 鈕）。
戰後鏈的按鈕位置固定：繼續/故事鈕都在右下 (2024,1024)，彈窗 TAP TO NEXT 點畫面中央即可。

備註：story 錨點刻意只框 MENU 鈕——AUTO 鈕有發光脈動動畫，含入會使信心值不穩（1.000 → 0.805）。

