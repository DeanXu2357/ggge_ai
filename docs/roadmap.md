# 進度與規劃

更新日期：2026-07-24（**現行恢復點＝本檔「暫停快照（2026-07-24 委派迴圈
session 收工）」段**——委派迴圈 8 修復輪合併＋實機 8 輪＋同日 Round 1.12
離線合併、恢復點 Round 1.13（待上機）；最新里程碑＝07-24 掃描主體首度
滿分收斂（輪九）；前一里程碑＝07-23 覆蓋驅動掃描重寫日；再前＝07-21
協調者管線日）

## 暫停快照（2026-07-24 委派迴圈 session 收工，恢復點）

**本 session 戰果**：委派迴圈 8 個修復輪全數合併（Round 1／1.5～1.11，
tip `cd44e20`，**883 passed／3 xfailed、ruff 綠**，測試 810→883）；實機
8 輪（輪五~輪十二）。**已實戰驗證**：批8 回合入口自癒、identify 疊層
安全化（unit_move 機制通道）、navigator 生命週期、選取殘留防禦（一次
解除）、飢餓煞車（130 秒早停）、地形指紋 first-write-wins（輪九掃描
主體滿分：552/552、10 nudges、首擊 100%、四邊全註冊）、refused／
anchor 原生存證管線。**逐輪敗因鏈**（全部定讞、詳細證據在
live-verification-queue.md 佇列 1）：輪五 identify 盲重試→R1.5；輪六
`bring_to_view` 生命週期崩潰＋late-arrival 跳 scout→R1.6；輪七選取
殘留污染→R1.7；輪八地形 LWW 錯位死鎖→R1.8；輪九 identify 幽靈候選
→R1.9；輪十錨定零單位→R1.10；輪十一/十二掃描入口 no-lattice→省電鎖
假說（R1.11）被輪十二原生鐵證推翻，**真根因＝`read_map_lattice`
row-seed 撞 HUD 邊緣離群峰、缺 trim()（確定性、已離線復現）**。

**同日稍晚（新 session 主 session 驗證整合，純離線、未碰裝置）**：
Round 1.12（`read_map_lattice` seed 離群修剪，鏡照 `read_grid_lattice`
既有 `trim()`、閾值不動）由 opus worktree agent 依規格開工，主 session
複核 diff＋在該 worktree 重跑全套 pytest/ruff 後 fast-forward 合併
（`869114a`）：先紅後綠驗證——舊碼在鐵證幀 `hud_edge_outlier_20260724.
png`（源自輪十二 `diag_turn1_anchor_no_lattice.png`）上因頂部 HUD 邊緣
離群峰（y=71，與下峰間距 357px 違反 80-160）觸發全有全無檢查判 `None`
（紅）；補離群修剪後讀出 7 條乾淨列、pitch≈97，與同幀窄帶讀值一致
（綠）。880 passed／4 skipped（既有 skipif、與本次改動無關）／3 xfailed、
ruff 全綠，九幀標準答案表與既有 fixture 全數不受影響、閾值未動。已清
worktree。

**恢復點＝Round 1.13（輪十三，同冷探索協定，待上機）**：R1.9/1.10/1.11/
1.12 皆待首戰（R1.11 的 guard 機制已在輪十二正確觸發過一次，但因當下
無鎖是 no-op，其「真的從變暗恢復」路徑仍零實機曝光）；期望 A1 冷掃
＋A2 暖掃落袋→Round 2 GOAP 化（草案，待輪十三結果回報後由主 session
重新規劃細節，見 scan-flow-robustness-plan.md）→跨家族第二關（總計畫
與驗收 A1-A5 在 plan 檔
`~/.claude/plans/adb-adb-libusb-1-whimsical-hopper.md`）。
**紀律**：掃描主體再敗→停問使用者；省電鎖使用者已確認不可調。

**2026-07-24 再更新（Round 2 定案 session）**：戰鬥內流程層 GOAP 與
使用者逐題定案，正式規格落檔
[flow-goap-controller2.md](flow-goap-controller2.md)（BattleController2
新入口、goal=sync_initial_map、逐單位 GOAP 化、不設獨立中斷 router）。
使用者拍板 probe 優先於輪十三（現況 EX-2 IF 戰局讓給 probe，輪十三
順延其後）。**Round 2.0（flow kernel）已合併**：opus worktree 開發、
主 session 複核 diff＋worktree 重跑全套後 fast-forward（`ca99e89`），
**925 passed／4 skipped／3 xfailed、ruff 綠**（基準 880→925）；交付
`battle/flow/`（vocabulary 三值 translator、8 個 ensure 修復導航動作、
BattleController2 tick 迴圈＋flow_* ledger 事件）＋`map_view.
expand_unit_list`（collapse 位元級等價委派）；controller.py／goap/／
vision.py／settings.py 零觸碰；dimmed 偵測缺樣（值域保留、永不
emit）。複核修正一處：tick 語意定調「逐步驗證執行」（原草案「只執行
第一步」與定案 2 分流規則矛盾）。**恢復點＝Round 2.1（巨集＋逐單位
動作＋goal＋run_sync_map.py，離線）→ Round 2.2 實機 probe**。

**裝置現況**：TURN 1 our-turn hub（EX-2 IF、0/15、剩 3 回合敗北限制、
9/9 卡可行動）、乾淨無殘留、格線 off、閒置變暗中（keyguard 自解）、
`data/cache/stages/` 空（備份 stages.bak-20260723/）、adb libusb 正常、
戰局可棄退體力。孤兒 worktree `8b1b6df`（probe B）依使用者裁決續擱置。
subagent 額度 settings 已調 40（新 session 生效）。**收尾待辦**（驗收
A5 時處理）：flaky `test_not_actionable` 計時競態、name 轉錄
`FORECAST_LEFT_NAME_REGION` 跨螢幕挪用、absence-audit 清單立 issue、
`_scout_local` 觀察（歷輪皆未達 turn-2）。

## 常備提醒與殘項

- 遇到有 MAP 敵機的關卡先蒐樣本——capture 移動選格畫面（兩類威脅圖示）
  ＋該敵機武裝面板，存 PNG（silent-events.md 批D）；蒐到前批E 不開工。
- 出擊機「鈷藍環＋白VV」輔助偵測器未實作（map-scan-survey.md 07-20
  深夜段）。
- 07-21 驗證回報 minor 殘項（後續順手）：T5 prep→forecast 跨 source
  斷言、T6 run_summary 雙場加權測試、tension 出界測試。

## 里程碑沿革（摘要；全文見 archive.md「roadmap 歷史快照」）

- **07-23～24 覆蓋驅動掃描重寫＋委派迴圈**：serpentine 退役、覆蓋驅動
  掃描五批重寫＋批6-8 實機修復；委派迴圈 8 修復輪（Round 1／1.5～1.12）
  ＋實機 8 輪逐層定讞、輪九掃描主體滿分收斂。證據鏈
  live-verification-queue.md 佇列 1、規格 scan-flow-robustness-plan.md、
  掃描設計 map-scan-survey.md。
- **07-21 協調者管線日**：操作/辨識分離原則＋協調者 pipeline 正式化；
  T1-T10（盤面辨識庫、切格線、zoom 冷掃前置、HP 對帳鏈批A-C、單位
  詳情視圖、MP/激昂機制定案）；live-verification-queue.md／
  live-test-plan.md／mp-tension.md 誕生。
- **07-20 離線地圖拼接＋標準答案**：9 幀拼接管線 27/27 零漏、地圖
  23×24、schema-3 deploy_slots；FrameSource／FactionIdentifier 接縫＋
  批2 cutover（弧色陣營判定退役、tacmap 無陣營化）。詳見
  map-scan-survey.md。
- **07-19 S9d 應戰 UI**：battle-prep／stance UI 實機標定＋辨識落地＋
  controller 接線（battle-prep-ui.md）；深夜十輪實機迭代＋#25 顯示方格
  （battle-settings-ui.md）。
- **07-17～19 離線工程重構（行為不變）**：每圈單次截圖、中斷 router＋
  middleware、tick 分類/分派收攏、BattleTimeline、四層單向依賴
  battle→content→planner→sim（agent-architecture.md「套件分層」、
  battle-phase-states.md）。
- **07-14～15 pilot 離線 M1-M7＋S0-S8 批次**：BoardTracker、pilot
  executor、advise_reaction、HSV 不可分判決（逐像素色彩路線關閉）、
  S0 證據分層→S8 應戰接線（stage-definition-requirements.md）。

## 歷史

舊暫停快照（2026-07-08 ～ 07-23）、初期計畫、已完成清單、
戰鬥控制器 v2 改進項目等歷史內容已全部移至 [archive.md](archive.md)
——除了了解歷史脈絡,開發時不需要讀。
