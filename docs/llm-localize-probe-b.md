# LLM 定位 probe B 報告（弱版 patch 選擇器 vs 確定性基準，#26 批4後續）

產出：`scripts/llm_localize_probe_b.py`，2026-07-23 06:53Z，ollama @ http://localhost:11434，temperature 0、90s timeout。**本批只量測，不接生產線。**

## 背景與 probe A 對照

probe A 測最難形式（兩圖同訊息、要 LLM 回跨幀絕對格座標），本機 gemma 系統性回 (0,0)、無位移訊號→裁決 no-ship。使用者質疑成立：那不能證明「單圖分開問＋程式組合」不可行，且多圖同訊息本身是方法學混淆。probe B 量測使用者提的形式——LLM 只當 patch 選擇器（弱版），精度由程式的 TM_CCOEFF_NORMED 模板搜尋承載；另加不用 LLM 的確定性基準線（auto）與單位遮罩缺口情境（gap）。

## 方法

- 素材：`tests/fixtures/vision/map_scan/ex2if_20260719/` 九幀，批2 真值偏移鏈。
- **llm**：逐幀單圖單訊息要 LLM 列最多 3 個顯著地標＋百分比位置；每地標在 A 幀裁 170px patch（避開格線週期），於 B 幀全幅 TM_CCOEFF_NORMED 搜尋，多地標投票取偏移共識。LLM 輸入走生產編碼（長邊 1280＋JPEG q85）、搜尋用全解析原圖。
- **auto**：程式在候選網格上以 變異×幀內唯一性 計分選 top-3 patch，同一搜尋＋投票，不用 LLM——量測「patch 搜尋層本身」。
- **gap**：以真值單位位置遮罩（塗成幀中位色）後重跑 llm/auto，量測純地形能否扛定位。
- 護欄沿用生產值：patch std 下限 10.0（平坦拒判）、匹配分數下限 0.55。偏移＝各幀 lattice 格索引差（同 probe A 語意）。

## 結果矩陣

| 模式 | 模型 | 摘要 |
|---|---|---|
| auto | （無） | correct 0/8 (wrong 7, no-consensus 1, no-data 0), 平均 px 誤差 474 |
| gap-auto | （無） | correct 0/8 (wrong 7, no-consensus 1, no-data 0), 平均 px 誤差 447 |
| llm | gemma4:latest | correct 1/8 (wrong 5, no-consensus 2, no-data 0), 平均 px 誤差 441 |
| llm | gemma3:27b | correct 0/8 (wrong 5, no-consensus 3, no-data 0), 平均 px 誤差 415 |
| gap-llm | gemma4:latest | correct 0/8 (wrong 1, no-consensus 7, no-data 0), 平均 px 誤差 547 |
| gap-llm | gemma3:27b | correct 1/8 (wrong 1, no-consensus 6, no-data 0), 平均 px 誤差 251 |

## 逐對明細

### auto（確定性基準線，無 LLM）

| 幀對 | 真值 | 偏移 | 誤差 | px誤差 | 分數 | 票數 | 判定 |
|---|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | (1, 0) | (0, 5) | 455 | 0.71 | 2/2 | wrong |
| pt2→pt3 | (0, -5) | None | None | - | 0.74 | 1/2 | no_consensus |
| pt3→pt4 | (-1, -5) | (0, 1) | (1, 6) | 555 | 0.93 | 1/1 | wrong |
| pt4→pt5 | (0, -2) | (0, 0) | (0, 2) | 187 | 0.93 | 2/2 | wrong |
| pt5→pt6 | (5, 0) | (0, 0) | (-5, 0) | 502 | 0.95 | 2/3 | wrong |
| pt6→pt7 | (0, 6) | (0, -1) | (0, -7) | 686 | 0.81 | 2/3 | wrong |
| pt7→pt8 | (0, 5) | (0, 1) | (0, -4) | 368 | 0.71 | 2/3 | wrong |
| pt8→pt9 | (-1, 5) | (0, -1) | (1, -6) | 561 | 0.70 | 2/2 | wrong |

### gap-auto（單位遮罩）

| 幀對 | 真值 | 偏移 | 誤差 | px誤差 | 分數 | 票數 | 判定 |
|---|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | (1, 0) | (0, 5) | 455 | 0.87 | 1/1 | wrong |
| pt2→pt3 | (0, -5) | (0, -1) | (0, 4) | 372 | 0.80 | 2/2 | wrong |
| pt3→pt4 | (-1, -5) | None | None | - | 0.87 | 1/2 | no_consensus |
| pt4→pt5 | (0, -2) | (0, 0) | (0, 2) | 187 | 0.88 | 3/3 | wrong |
| pt5→pt6 | (5, 0) | (0, 0) | (-5, 0) | 502 | 1.00 | 3/3 | wrong |
| pt6→pt7 | (0, 6) | (0, -1) | (0, -7) | 686 | 0.85 | 3/3 | wrong |
| pt7→pt8 | (0, 5) | (0, 1) | (0, -4) | 368 | 0.70 | 2/3 | wrong |
| pt8→pt9 | (-1, 5) | (0, -1) | (1, -6) | 561 | 0.70 | 2/2 | wrong |

### llm — gemma4:latest

| 幀對 | 真值 | 偏移 | 誤差 | 分數 | 票數 | 延遲 | 判定 | 地標 |
|---|---|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | (1, 0) | (0, 5) | 0.98 | 2/3 | 7.6s | wrong | Blue Gundam unit (left side); Green Gundam unit (center); Blue Gundam unit (right side) |
| pt2→pt3 | (0, -5) | None | None | 0.92 | 1/3 | 5.1s | no_consensus | Large green mechanical unit (Gundam); Small blue and red unit (Gundam); Green submarine/ship unit |
| pt3→pt4 | (-1, -5) | (-4, 0) | (-3, 5) | 0.59 | 1/1 | 4.4s | wrong | Large green Gundam unit in the center; Blue Gundam unit to the right of the lar; Red/blue Gundam unit on the far left |
| pt4→pt5 | (0, -2) | (0, -2) | (0, 0) | 0.81 | 2/3 | 4.4s | correct | A blue and red mobile suit unit in the c; A green and blue mobile suit unit in the; A red and blue mobile suit unit in the b |
| pt5→pt6 | (5, 0) | None | None | 0.84 | 1/2 | 4.8s | no_consensus | Blue and white mobile suit unit (center-; Dark blue and red mobile suit unit (righ; Unit selection indicator/icon (bottom ri |
| pt6→pt7 | (0, 6) | (2, -1) | (2, -7) | 0.77 | 2/3 | 3.8s | wrong | Blue Gundam unit (left); Red Gundam unit (center); Blue Gundam unit (right) |
| pt7→pt8 | (0, 5) | (0, 1) | (0, -4) | 0.85 | 2/3 | 4.7s | wrong | Large green/blue mechanical unit (Gundam; Blue mechanical unit (Gundam) in the top; Blue mechanical unit (Gundam) in the bot |
| pt8→pt9 | (-1, 5) | (0, -1) | (1, -6) | 0.98 | 3/3 | 4.9s | wrong | A large green mechanical unit (Gundam); A blue and red mechanical unit (Gundam); A small blue mechanical unit (Gundam) ne |

### llm — gemma3:27b

| 幀對 | 真值 | 偏移 | 誤差 | 分數 | 票數 | 延遲 | 判定 | 地標 |
|---|---|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | (1, 0) | (0, 5) | 0.93 | 2/3 | 8.0s | wrong | Blue Gundam unit with a rifle; Red Gundam unit with a shield; Bright green terrain feature (looks like |
| pt2→pt3 | (0, -5) | None | None | 0.96 | 1/3 | 2.5s | no_consensus | Red Gundam unit with a sword; Blue Gundam unit with a shield; Yellow Gundam unit with a beam rifle |
| pt3→pt4 | (-1, -5) | None | None | 0.81 | 1/3 | 2.4s | no_consensus | Bright red Gundam unit; Large blue Gundam unit with a cannon; Yellow warning icon |
| pt4→pt5 | (0, -2) | (0, 0) | (0, 2) | 0.93 | 3/3 | 2.2s | wrong | Yellow warning sign; Red mobile suit; Blue mobile suit with wings |
| pt5→pt6 | (5, 0) | (0, 0) | (-5, 0) | 0.99 | 2/3 | 2.4s | wrong | Red mobile suit with a large beam rifle; Blue mobile suit with a shield; Yellow warning triangle icon |
| pt6→pt7 | (0, 6) | None | None | 0.93 | 1/3 | 2.2s | no_consensus | Red Gundam unit; Blue Gundam unit; Yellow warning marker |
| pt7→pt8 | (0, 5) | (0, 1) | (0, -4) | 0.94 | 2/3 | 2.5s | wrong | Large red Gundam unit; Green Gundam unit with a large claw; Blue Gundam unit with wing-like structur |
| pt8→pt9 | (-1, 5) | (0, -1) | (1, -6) | 0.89 | 2/3 | 2.6s | wrong | Large green mobile suit with a wing-like; Cluster of red mobile suits forming a li; Blue mobile suit with a distinctive ante |

### gap-llm — gemma4:latest

| 幀對 | 真值 | 偏移 | 誤差 | 分數 | 票數 | 延遲 | 判定 | 地標 |
|---|---|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | None | None | 0.92 | 1/3 | 5.4s | no_consensus | Orange unit icon (likely a mobile unit); Blue unit icon (likely a mobile unit); Small white directional arrow/marker nea |
| pt2→pt3 | (0, -5) | None | None | 0.89 | 1/3 | 4.9s | no_consensus | Orange and white marked unit (likely a c; Orange and white marked unit (likely a c; Blue and white marked unit (likely a cha |
| pt3→pt4 | (-1, -5) | (2, 0) | (3, 5) | 0.97 | 1/1 | 4.9s | wrong | Large red and white mobile suit (Gundam); Small green mobile suit in the center; Small blue mobile suit near the center-r |
| pt4→pt5 | (0, -2) | None | None | 0.75 | 1/2 | 4.8s | no_consensus | Blue and white mobile suit unit (center); Orange warning triangle marker (left-cen; Blue and white mobile suit unit (bottom- |
| pt5→pt6 | (5, 0) | None | None | 0.90 | 1/3 | 4.2s | no_consensus | Blue unit (Gundam) in the center-bottom ; Orange warning triangle icon near the bl; The 'AUTO' button in the top right corne |
| pt6→pt7 | (0, 6) | None | None | 0.72 | 1/3 | 5.2s | no_consensus | Blue and white mobile suit unit (center-; Small orange/yellow unit (left-center); Dark blue/black unit (right-center) |
| pt7→pt8 | (0, 5) | None | None | 0.74 | 1/2 | 5.0s | no_consensus | A blue and white mobile suit unit (Gunda; A red and white mobile suit unit (Gundam; A blue and white mobile suit unit (Gunda |
| pt8→pt9 | (-1, 5) | None | None | 0.78 | 1/2 | 4.9s | no_consensus | A blue and white mobile suit unit (Gunda; A red and white mobile suit unit (Gundam; A blue and white mobile suit unit (Gunda |

### gap-llm — gemma3:27b

| 幀對 | 真值 | 偏移 | 誤差 | 分數 | 票數 | 延遲 | 判定 | 地標 |
|---|---|---|---|---|---|---|---|---|
| pt1→pt2 | (1, -5) | None | None | 0.98 | 1/2 | 2.2s | no_consensus | Yellow Unit; Blue Unit; Red Unit |
| pt2→pt3 | (0, -5) | None | None | 0.71 | 1/3 | 2.3s | no_consensus | Red Gundam unit; Yellow triangular terrain feature; Blue Gundam unit with wings |
| pt3→pt4 | (-1, -5) | None | None | 0.77 | 1/2 | 2.2s | no_consensus | Red Gundam unit; Large blue structure; Yellow warning icon |
| pt4→pt5 | (0, -2) | None | None | 0.89 | 1/2 | 2.3s | no_consensus | Yellow exclamation mark icon; Blue mobile suit unit; Blue mobile suit unit |
| pt5→pt6 | (5, 0) | (0, 0) | (-5, 0) | 0.99 | 2/3 | 2.3s | wrong | Blue mobile suit with wings; Red mobile suit; Yellow warning icon |
| pt6→pt7 | (0, 6) | None | None | 0.95 | 1/3 | 2.3s | no_consensus | Blue Gundam unit; Red Gundam unit; Yellow warning icon |
| pt7→pt8 | (0, 5) | (0, 5) | (0, 0) | 0.77 | 2/3 | 2.3s | correct | Blue Gundam unit; Large rectangular structure; Small blue terrain feature |
| pt8→pt9 | (-1, 5) | None | None | 0.93 | 1/2 | 2.3s | no_consensus | Blue Gundam unit; Large blue terrain square; Red Gundam unit |

## 分析

### 機制本身是對的（先驗證再談失敗）

在下任何「不可行」結論前先確認 crop-A→search-B→格索引差這條管線沒有算錯：
手挑一個真正跨幀共通地標（pt1 (1716,100)「暗紅重裝格林砲」→ pt2 附近），
patch 在 pt2 全幅 TM_CCOEFF_NORMED 命中 (1733,573)（px 漂移 (1,18)，遠小於一格），
還原偏移 **(1,-5) 完全等於真值**（分數 0.64）。**模板機制與偏移數學都正確**——
給它一個真的共通地標，它就精準還原。失敗不在機制，在「選到的 patch 是不是真共通」。

### 兩種系統性失敗（都不是隨機噪音）

1. **含單位時＝高分假對位（alias-to-low-offset）**：最小 zoom 下同陣營機體互相
   高度神似，A 幀 patch 在 B 幀常匹配到「附近螢幕位置的另一台像的機體」而非本體，
   偏移於是塌向同排／同列（row 誤差普遍 ≈0），且**分數常 0.7–1.0**（錯對位照樣高分，
   正是 CLAUDE.md 對 TM_CCOEFF 的警告）。更糟：多個 patch **一致地**朝同一個錯偏移
   （多半近 (0,0)）投票，把少數真對位的票蓋過——**多數決共識被系統性 alias 擊敗**
   （auto/llm 的 wrong 幾乎都是 2–3/3 高票錯值）。
2. **遮單位（gap）＝純地形無共識**：把單位塗掉後，LLM 只能指地形，地形 patch 不是
   過不了 std 平坦下限（被拒），就是在星空亂點各自匹配到不同處→彼此不合→no_consensus
   佔壓倒多數（gap-llm 兩模型 13/16 對 no_consensus）。**最小 zoom 的裸地形扛不住定位**，
   偶爾一對（gap-llm gemma3 pt7→pt8）湊巧 correct，屬個案非能力。

根因驅動是**重疊帶未知**：本 series 平移達 5–6 格，落在 A∩B 重疊帶外的 patch 根本
沒有真對應，只能 alias。auto 的變異挑選與 LLM 的百分比指認**都不知道重疊帶在哪**，
於是照樣從無對應區裁 patch。

### auto 基準線 vs llm 增量：LLM 沒有加值

- auto **0/8**、gap-auto **0/8**。
- 最佳 LLM 配置也只有 **1/8**（llm gemma4 命中 pt4→pt5＝最小平移／最大重疊那一對；
  gap-llm gemma3 命中 pt7→pt8 一對），gemma3 llm **0/8**。
- **1/8 對 0/8 落在噪音內**：LLM 的語意挑地標能力（probe A 已確認有效、本輪描述也多半
  合理，gemma3 甚至會挑「structure／terrain feature」）**無法轉成定位增量**——因為
  (a) 百分比指認不精準（幾 % ＝數十至上百 px），(b) 它挑的「顯著機體」仍是別台機體的
  近複製品，照樣 alias。**LLM 相對確定性 patch 選擇器沒有可衡量的優勢。**

## 結論建議：**三選一之「皆不可行」（作為獨立定位層）**——但機制可留待正確接法

- **不採「弱版接縫」**：最佳 1/8、對確定性無增量；接上去只會餵進「高分但錯」的 alias
   偏移。生產 `_llm_assist` 的 `verify_offset`（邊界幾何）會擋掉多數，但這一層在本素材上
   **不提供任何正定位價值**，徒增一次 LLM 呼叫。→ **批4「生產休眠、僅留接縫」的決定維持不變。**
- **不採「純確定性 patch 搜尋層」作為自主定位器**：auto 同樣 0/8。變異×唯一性選點在
   單位近複製＋重疊帶未知下，選不出抗 alias 的共通 patch。
- **裁決＝皆不可行**（在此最小 zoom 全圖掃描素材上，作為獨立定位層）。**但保留一個
   關鍵限定**：模板機制本身已驗證正確，瓶頸是「重疊帶感知 + 抗 alias 的 patch 選擇 +
   幾何一致共識」，這三者受測的任一選擇器都不具備。

## 給後續接線批次的備註（若未來要重評）

1. **重疊帶不是未知的——實機迴圈知道 nudge 方向**。本 probe 的先天劣勢（跨無對應區裁
   patch）在真實 `CoverageScanSource` 裡不存在：每次 nudge 的方向已知，重疊帶＝尾隨側
   那條帶。若要做「確定性 overlap-band patch 搜尋」，**只從已知重疊帶裁 patch**，不要
   全幅亂挑——這會直接消掉本輪最大的失敗來源，值得單獨再 probe（用小步 nudge 的 series，
   非本 series 的大平移）。
2. **接受偏移只能靠幾何一致、不能靠分數多數決**：alias 是高分且同調投票，分數/多數決
   分不開真假；唯一能分的是 `CellMap.verify_offset`（覆蓋格不得越過可見邊界）與 edge pin。
   生產 `_llm_assist` 已用 verify_offset 收口——本輪證實這道護欄是必要的，不是保險。
3. **LLM 不必進這條路**：語意挑地標有效但轉不成定位增量；換更強的視覺 LLM 前，先把
   確定性 overlap-band 搜尋＋verify_offset 做起來評估，別預設 LLM 是必要件。
4. 換模型再評估的門檻沿用 probe A：某模型能在本工具 `--modes llm` ≥6/8 exact 才值得考慮
   接 `controller._navigator`；本輪兩個 responsive 模型（gemma4:latest、gemma3:27b）皆遠不及。

