# 戰鬥準備 UI 家族地圖與戰鬥機制

實機標定（R5CRC37JBYJ，橫向 2340x1080）的「戰鬥準備」畫面家族——forecast、
應戰 stance 選單、支援攻擊、技能——以及 forecast 傷害語意、敵方 AI 應戰決策等
戰鬥機制。來源＝2026-07-19 實機探測（使用者手動操作到各畫面、主對話讀圖標定）。

- 座標一律**原圖像素**；證據截圖見 `tests/fixtures/vision/forecast/`（§8 對照表）。
- 座標多為視覺估計，標「待像素精量」者接程式前需以像素定位收斂。
- 機制知識（§7）為使用者口述並經確認，屬 sim/solver 建模需求，非畫面標定。

## 1. 畫面家族與識別

| 標題 | 觸發 | is_reaction | 說明 |
|---|---|---|---|
| 戰鬥準備 **-攻擊-** | 我方主動攻擊 | False | 我方選攻擊，敵方反擊 |
| 戰鬥準備 **-應戰-** | 敵方主動攻擊我方 | True | 敵方攻，我方選應戰 stance |
| **技能** | 攻擊/應戰中點技能按鈕 | — | 額外行動（buff/特殊），sim 未建模 |

`is_reaction` 判斷來源＝標題 -攻擊- vs -應戰-（`vision.is_battle_prep_reaction`）。

## 2. 陣營與 forecast 佈局（-攻擊-/-應戰- 通用）

- **陣營固定：右面板＝我方、左面板＝敵方**（與機種背景無關，攻擊與應戰皆然，
  已用 EN 消耗＋傷害 delta 交叉驗證）。
  - vision `attacker`＝左面板＝**敵方**、`defender`＝右面板＝**我方**。
  - controller `_choose_reaction_stance` 把 `attacker_name_sig` 當 enemy、
    `defender_name_sig` 當 "ally" 解析 → **方向正確**。
- **中央攻擊/反擊數值**：上排＝主動方傷害、下排＝被動反擊方傷害（位置固定）。
  - **顏色＝陣營色（藍＝我方動作、紅＝敵方動作），不固定於攻擊/反擊**：
    -攻擊- 時藍「攻擊」(我)＋紅「反擊」(敵)；-應戰- 時紅「攻擊」(敵)＋藍「反擊」(我)。
    **不可靠顏色分辨攻擊 vs 反擊，只能靠位置（上/下）與陣營（左/右面板）**。
- `read_battle_prep_forecast` 現況（reaction_live 離線驗證）：attack_value/
  defense_value/attacker·defender HP·EN·hp_delta 皆正確；`hit_pct=None`（region
  未對到，見 §3）；defender_hp 偶有 OCR 誤讀（14168→14188，digit 模板待查）。
- **KILL 標記**：致死傷害在面板 delta 後顯示「KILL」（語意見 §7）。
- **點頂部單位橫幅 → 單位設置詳情**（攻擊/反擊雙方皆可）＝**戰鬥中 intel 來源**
  （關卡外只能點敵人，戰鬥準備可看敵我雙方）。左欄＝機體＋駕駛員數值（**±標記＝
  受能力影響**）；三 tab：**組合資訊**(修正效果 buff＋標籤＋系列，buff 欄右「i」看詳細)／
  **武裝、技能**(機體武裝＋機體/駕駛員技能，**顯示持有≠可用**、限制武裝不顯示剩餘次數)／
  **能力、OP**(能力＋選擇性零件，**數值影響已反映左欄**)。詳見 unit_detail_combined
  fixture 與 memory `llm-perception-unit-info`。

## 3. 底部頭像列：攻擊順序＋命中率

- **攻擊順序＝頭像上的數字 ①②③**（動態，隨參戰單位增減編號）。例：支援攻擊
  參戰時 ①支援攻擊 → ②主攻 → ③敵反擊；無支援時只 ①攻擊 → ②反擊。
- 各頭像**上方白字＝該階段武裝命中率**（各自獨立，如 85/100/55）；
  **下方字＝行動類型**（攻擊/反擊/支援攻擊/不參加/閃避…）。
- **藍框＝我方、紅框＝敵方**。
- **頭像列隨參戰數變長 → 命中率/順序必須相對定位**（從右端往左數），不可固定座標。
- 命中率 region（原圖估計，待精量）：反擊態紅①（敵攻我）~(813,819)、藍②(我)~(930,819)；
  digit 比機體數字小。`hit_pct` 應讀主動攻擊方那格（-應戰- 讀紅①敵攻命中率）。

### 支援攻擊
- 支援候選頭像排在主攻①/反擊②的**左側**；系統自動判參加與否、**無手動選擇 UI**
  （顯示「不參加」或參戰編號）。場上支援單位頭頂標「不參加」/武裝名。
- 同時最多 3 個支援攻擊（本例 3 候選），佐證 `sim` `max_support_attackers=3`。
- 攻擊值隨支援疊加（例 163188 無支援 → 169729 +1 支援）。

### 支援反擊（應戰時）
應戰情境我方也可有支援單位反擊：頭像順序＝①敵攻 → ②**支援反擊**（我方支援機）
→ ③被攻擊單位反擊（reaction_support_counter，命中 100/100/82）。頭像②行動類型
標「支援反擊」（攻擊時的對應是「支援攻擊」）。支援機不列入頂部兩面板（只主交戰雙方）。
**注意：支援反擊＝友軍多反擊一次（對應 sim 防守方 support_attack pool），
≠ `support_defense`（友軍替被攻擊者擋傷）——後者仍未取得畫面。**

**但書：反擊階段觸發依賴被攻擊主單位存活**——①敵攻若擊殺③主單位，整個反擊階段
取消、②支援反擊也不觸發（雖②結算在③前）。**sim 已正確建模**（`core.py:873`
`if response is not None and target.alive:` 把 ②support_attack 齊射與 ③COUNTER 都圈在
target 存活條件內，target 死則全跳過；core.py:38-43 註解 confirmed），此塊無需改。
對 solver：我方主單位會被①秒時 counter 無效，應改防禦/閃避保命。

### 支援防禦 support_defense（reaction_support_defense）
應戰時我方友軍（interceptor）替被攻擊主單位**擋傷**（≠支援反擊的多打一次）。
視覺信號：主單位面板出現**盾圖示「支援防禦」**標籤、右側疊第二個 interceptor 面板、
底部頭像列有「支援防禦」頭像（盾圖示、**無攻擊序號**，插在①敵攻與②主單位反擊之間）、
場上 interceptor 標「支援防禦」。→ vision 偵測盾圖示「支援防禦」標籤即 `support_defense=True`。
機制吻合 sim interceptor（`core.py:842-846`，`struck=interceptor`）；interceptor 承受傷害
是否已含 shield/defend 減免待與 sim 對照。順序：①敵攻 → 支援防禦(擋傷、主單位免傷) → ②主單位反擊。

**互斥規則（使用者口述）**：被攻擊單位選 **defend/shield 時不能**接受支援防禦（自己擋）；
只有選 **dodge/counter** 才能疊 support_defend。→ solver 枚舉須據此排除無效組合（見 §9）。

## 4. 應戰 stance UI（S9d 核心）

### 入口與流程
點我方（藍框，應戰時＝②）駕駛員頭像 → 展開應戰動作選單。
完整執行流程：**點我方頭像 → 選 stance 鈕 → 「行動選擇」確認回主畫面 → 「開始戰鬥」**。

### 動作選單佈局（reaction_menu）
```
[武器N]…[武器2][武器1][防禦][閃避]   ← 右起：閃避、防禦為固定錨點
  └── 反擊武器往左、數量不定、等間距 pitch≈170
```
- `DefenseKind`（`sim/core.py:108`，＝`available_stances` 值域＝`REACTION_OPTION_TAPS` key）：
  `none / dodge / defend / shield / counter`。
- 選單各鈕 → stance 對應：
  - 閃避 → **dodge**（動作列最右錨點）
  - 防禦 → **defend**（無盾機體）或 **shield**（有盾機體，鈕標「防禦（盾牌）」），閃避左一格錨點；見下效果
  - 各反擊武器 → **counter** + weapon（防禦往左第 k 格，pitch 固定）

### 相對定位標定策略（使用者定案）
機體武裝數不定 → **不列舉絕對武器座標**，用右側 dodge/defend 錨點 + pitch 相對定位：
- 用閃避/防禦圖示模板定錨 → 往左數圓鈕算武器數 → 得 `available_stances`。
- `REACTION_OPTION_TAPS` 改「錨點 + pitch 相對定位」，非固定 stance→tap。
- **可用/不可用靠鈕中心亮度 V**：disabled（射程外等）暗淡 V≈62、可用 V>105
  （support_weapon_menu 實測，SHORT 短程超距灰色 V=61.7）。vision 用 V 排除灰鈕。

### 座標（原圖估計，待像素精量）
| 元素 | 座標 | 備註 |
|---|---|---|
| 閃避 dodge（最右錨） | ~(1533,918) | 準星圖示 |
| 防禦 defend（錨） | ~(1351,918) | 盾圖示 |
| counter 武器（LONG/SHORT 例） | ~(1144,918)/~(969,918) | 往左 pitch≈170 |
| 行動選擇（確認） | ~(2042,924) | 大鈕 |
| 返回 | ~(1802,930) | |
| 我方頭像（切換入口，應戰②） | ~(924,848) | |

pitch 實測 172/169/174 ≈ **170**（support_weapon_menu 多武器樣本）。**上表絕對座標僅
2 武器例**；動作列不右對齊，**錨點絕對位置隨武器數右移**（閃避 2 武器~1533、5 武器~1854，
見 reaction_shield_menu）→ **必須用閃避/防禦圖示模板定位錨點、勿寫固定座標**。

### 選中態與效果卡
- 選中鈕亮藍高亮外框、其餘變暗 → vision 可讀當前 stance。
- 右上「效果說明卡」（原圖 x~1439-2188, y~339-538）顯示選中 stance 標題＋效果文字，
  為讀當前 stance 的第二來源。
- forecast HP delta **隨選定 stance 即時重算**（見下效果驗證）。

### 各 stance 效果（實機驗證）
- **defend / shield**：防禦鈕的 stance **依機體有無盾**（同一鈕位，非獨立選項）：
  - 無盾 → **defend**：效果卡「受到的損傷減少20%」＝`DEFEND_MULTIPLIER 0.8`
    （加布斯雷例，選後 HP delta -10364→-8292 驗證）。
  - 有盾 → **shield**：鈕標「防禦（盾牌）」、效果卡「受到的損傷減少40%」＝
    `SHIELD_MULTIPLIER 0.6`（F91 例，reaction_shield_menu）。
  vision 靠效果卡減傷%（20 vs 40）或鈕標籤（防禦 vs 防禦（盾牌））區分。
- **dodge**：效果卡「敵方命中率減少20%。※超過100%時可能不會減少」＝`dodge_hit_penalty 20.0`。
  選閃避後 HP delta 不變（減命中率非傷害）；命中率 100→90（原>100 封頂，-20 後 90，
  印證「超過100%可能不減」）。確認後中央標籤「反擊 6164」→「閃避 0」（不反擊、對敵 0 傷）。
- **counter**：用武器反擊，選中態同 reaction_menu 圖 LONG。

## 5. 支援攻擊武裝選單（support_weapon_menu）

我方主動攻擊時點進支援攻擊角色的武裝選單：
```
[SHORT][LONG][LONG][不參加X]   ← 右錨＝不參加X（≠ 應戰的防禦/閃避）
```
- 等間距 pitch≈170（x 969/1141/1310/1484）。
- 灰色 disabled ＝ SHORT（短程超距不可用），靠亮度 V 分辨（見 §4）。
- **不同情境動作列右錨不同**：-攻擊-支援＝不參加X、-應戰-＝防禦/閃避 → 相對定位須先辨情境。

## 6. 技能選擇畫面（skill_menu）

- 入口＝攻擊/應戰畫面右側「行動選擇」正上方的**技能按鈕**（雙上箭頭⌃⌃＋「技能」，
  ~(1714,714)），角色有行動機會（MP 足）時亮起。
- 標題變「技能」；底部技能槽等間距 pitch~170（同武器/stance 選單，相對定位通用）。
  空槽＝灰斜線。
- 每技能：圖示＋SP 消耗；右上效果卡（例「攻擊爆裂 LV2：對敵損傷+10%（1回合）」）；
  底部「SKILL SP」資源條；右下綠色「發動」鈕（~2042,924）。
- 技能＝額外行動（buff/特殊），**sim 尚未建模**，未來擴充。

## 7. 戰鬥機制與策略（sim/solver 建模需求，使用者口述並確認）

### forecast 傷害是保守下界（實際結算 ≥ 預覽）
- **各階段獨立計算、不串聯前階段 debuff**：支援攻擊①若降敵防禦，forecast 的主攻②
  仍按**未降防**算（偏低）；實際 ①先降防 → ②打更高傷害 → **可能預覽敵殘血存活、
  實機卻擊殺**。
- **暴擊**：非 100% 必暴時 forecast 用**非暴擊值**；只有必暴武裝才算暴擊傷害、可能顯示 KILL。
- **KILL 字樣＝確定擊殺（可信）；無 KILL ≠ 打不死**。
- 對 sim：KILL 可信；無 KILL 的殘血敵**不可判「打不死」**；sim 要自己串聯降防/暴擊；
  reconcile 遇「sim 預測擊殺 vs forecast 殘血」＝forecast 保守，非 sim 錯。

### 敵方 AI 應戰決策（保命邏輯）
- 我方攻擊敵方、敵方選應戰時，若「反擊會死、防禦能活」→ 敵方**選防禦保命** → 打不死。
  現象：選目標時預覽顯示 KILL（假設反擊），進戰鬥準備後敵方改防禦、KILL 消失。
- **敵方 AI 依 forecast 下界判斷是否防禦** → 欺敵手段：
  - **賭暴擊**：用「下界不死、上界(暴擊)死」的武裝，敵方看下界判安全→選反擊→暴擊擊殺。
  - **支援降防**：敵方看未串聯降防的預覽判安全→選反擊→降防串聯後擊殺。
- 對 solver：`enemy_model` 要建模敵方防禦決策；`solver` 選攻擊＝博弈——下界就 KILL
  反而逼敵防禦（可能打不死），刻意選「下界不 KILL、上界/降防才 KILL」騙敵反擊再擊殺。
  sim 要能表達「下界 vs 上界傷害」與敵方 policy 的互動（不只單一期望傷害）。

### 先攻（先發攻擊）
部分機體（**主要防禦型**）的武裝有**先攻特性**：在原結算順序外**額外一個先攻 queue**，
帶先攻武裝排最前結算；雙方都有先攻則都入先攻 queue，無先攻的照原順序（①②③）。
視覺標記＝頭像**上方橘色「先發攻擊」標籤**（reaction_first_strike，本例①支援反擊帶先攻
被排到最前）。戰術：先攻搶殺敵方攻擊者 → 敵攻不觸發（連上「①殺主單位取消反擊」）。
**sim 缺口**：`core.py` 結算順序（攻擊方→反擊方，core.py:24-43）**無先攻 queue** 概念
（core.py:28 的「first strike」是 interception 第一擊、非此），改程式要加。先攻＝武裝內容。

> 紅線提醒：降防效果的有無/數值、暴擊率是**內容**，須從武裝面板讀（見
> memory `llm-perception-unit-info`），不可寫死。

## 8. fixture 對照表（`tests/fixtures/vision/forecast/`）

| fixture | 畫面 | 標定重點 |
|---|---|---|
| `reaction_live_20260719` | -應戰- 主畫面（反擊態） | 陣營、數值、命中率 100/87、read_forecast 驗證 |
| `reaction_menu_20260719` | 應戰動作選單（LONG 選中） | stance 四鈕、DefenseKind、佈局 |
| `reaction_defend_20260719` | 防禦選中 | defend −20%傷、HP delta -8292、效果卡 |
| `reaction_dodge_20260719` | 閃避選中 | dodge −20%命中、效果卡 |
| `reaction_dodge_confirmed_20260719` | dodge 確認後主畫面 | 命中率 region、閃避 0、機制驗證 |
| `attack_support_20260719` | -攻擊- ＋支援不參加 | is_reaction 來源、陣營驗證、支援佈局 |
| `attack_support_active_20260719` | -攻擊- ＋支援參戰 | 攻擊順序①②③、命中率相對定位 |
| `reaction_support_counter_20260719` | -應戰- ＋支援反擊 | 應戰順序①敵攻②支援反擊③反擊 |
| `reaction_support_defense_20260719` | -應戰- ＋支援防禦 | interceptor 擋傷、盾圖示「支援防禦」標籤 |
| `reaction_shield_menu_20260719` | -應戰- 有盾機體多武器選單 | shield＝防禦(盾牌)減40%、5 武器 pitch~170、錨點隨武器數移動 |
| `reaction_first_strike_20260719` | -應戰- 先攻多階段 | 先攻＝橘色「先發攻擊」標籤、帶先攻武裝排最前、sim 缺口 |
| `unit_detail_combined_20260719` | 點橫幅→單位設置詳情（組合資訊 tab） | 三 tab 語意、±標記＝受能力影響、buff 在組合資訊 |
| `our_turn_unit_list_20260719` | 我方回合 hub 單位列表-打開 | 9 卡條、啟動順序自由（非 UI 順序） |
| `our_turn_list_collapsed_20260719` | 我方回合 hub 單位列表-關閉 | ▲單位列表鈕(~1970,1010)、無卡條；count 前須先開 |
| `support_weapon_menu_20260719` | 支援武裝選單 | pitch≈170、灰色 disabled、不參加右錨 |
| `skill_menu_20260719` | 技能選擇 | 技能槽 pitch170、SP、發動鈕 |

原始探測逐步記錄見同目錄 `reaction_live_20260719.md`。

## 9. 待標定 / 待接程式

**vision**
- `available_stances`：閃避/防禦錨點模板定錨 → 往左數圓鈕（亮度 V 排除灰鈕）。
- `REACTION_OPTION_TAPS`：改錨點 + pitch 相對定位（非固定表）。
- `hit_pct` region 重定到底部頭像上方；defender_hp OCR 修正。
- `support_defense`：**已取得畫面**（reaction_support_defense）→ 偵測盾圖示「支援防禦」
  標籤標定 True，取代 stub None；interceptor 承受傷害的減免語意待與 sim 對照。
- 各鈕座標像素精量。

**sim/solver**
- forecast 保守下界語意接進擊殺判定（KILL 可信、無 KILL 不可判打不死）。
- `enemy_model` 建模敵方防禦保命決策。
- `solver` 下界/上界博弈選攻擊（欺敵）。
- 降防串聯、暴擊上界建模；降防/暴擊率從武裝面板當內容讀。
- **support_defend 枚舉修正**：`solver.py:110-112`／`enemy_model.py:128-132` 對每個 stance
  都配 `support_defend=True` → 須排除 defend/shield（互斥，只配 dodge/counter；none 待確認）。
- **先攻 queue 建模**：帶先攻特性的武裝優先於一般順序結算（雙方先攻同入先攻 queue）；
  sim 目前無此概念（core.py:24-43）。先攻＝武裝內容、從面板讀。
- 單位啟動順序：hub 可選**任意**可行動單位（非 UI 左到右）→ solver 規劃啟動序列、
  controller 直接點對應卡條（對照現 pilot advise+list reorder，可省 reorder）。
- 單位詳細資料入口（點頂部橫幅）＝戰鬥中 intel 來源，可接進感知（buff/能力/武裝，敵我雙方）。
- 技能為未來擴充。
