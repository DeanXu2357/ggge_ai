# 決策備案

使用者授權（2026-07-30）：決策分支由 Claude 自行裁決、普遍採保守
選項、逐筆在此備案。使用者隨時可回查與推翻；被推翻的決策劃線保留
不刪除。格式：日期｜情境｜選項｜採用與理由。

## 2026-08-01

- **v2.6 四件套設計決定 16 條整批接受＋一偏離裁決（27f6e12 合併）**
  ｜opus worktree 交付四 commit、主 session 親審＋主 repo 閘門
  1587 passed／ruff 綠。**74 幀實幀重放對照**（run 20260801-
  080213）：7/74 裁決改變且全數為目標——t11/t12「停滯」實為
  +220/+199px 真滑動改判 BROKEN(phase)（西旗錯釘元兇）、t24
  幽靈星座票 (−18,−192) 被拒；**零誤殺真移動**（t3-t7/t10/
  t15/t16/t33-35 不變）；邊界目擊 west t3-t20／north t7,t14／
  south t30／east t34-37，零假邊。**偏離裁決接受**：整區
  mean-abs-diff 被星空稀釋不可用（t15/t16/t24 真移動全被判原
  地，實測比分在案）→改**逐精靈窗**投票；四裁決含 NULL_BLIND
  （<2 窗＝裁判缺席維持舊行為）與 NULL_UNCLEAR（看了都不合＝
  票作廢）之分；<40px 位移兩假設不可分＝BLIND 短路（合法零合
  併不誤拒，主 session 親驗）。其餘要點：Island.lost 跨島沿用
  累加（局部原點不換）；merge 兩閘只否決不修正；edge_mismatch
  兩不改（旗與 offset 當場不可裁）＋幀隔離；EMPTY 毯要格線背
  書、目擊只要 readable（雙口徑明文）；一條既有測試契約改變
  （900px 側跳改拒收→誠實重開世界）。爭點留檔：台數需第 6 輪
  實機定讞（重放不能重規劃）；世界重開 0→2 盯 islands.reset；
  measure_pan 格線通道仍只讀全幀帶＝v2.7 候選。
- **使用者追問定調架構缺口＋裁示併入 v2.6（0801 上午續）**｜使用
  者兩問釘死缺口：①「左上角圖片左與上都空，內部座標怎會把這麼
  多張當可拼接」——答：內部轉換純航位推算，影像內容對「我在哪」
  無投票權；邊緣證據唯一消費點是撞邊事件（推論制，且旗寫在可能
  已錯的 offset 上）＝偏離 7/23「邊界只目視永不推論」教義；
  ②「狀態只有有無物體/有無更新，沒判斷是不是格子？」——答：
  正是，且更糟：covered() 純幾何不看像素，星空被蓋 EMPTY 章；
  read_lattice 讀得到格線範圍但只拿去驗相位。**裁示：v2.6 擴充
  第四件**（已 SendMessage 併入執行中批次）：(a) 幀內可見格線
  範圍＝covered() 遮罩，格線外一律 UNKNOWN、全失讀幀零 EMPTY
  章（單位目擊照收）；(b) 格線終止＝邊界目擊——旗未定目視定旗
  （回歸目視教義，撞邊路徑留作第二來源）、旗已定差超過半格＝
  該幀拒收進島＋telemetry，**不自動改旗**（旗錯 vs offset 錯
  當場不可裁，保守隔離留資料）。與批 7 星空假邊界教訓對接：
  亮度不支持的終止不出邊證言、只縮遮罩。
- **使用者一手診斷解除停工＋v2.6 裁決（0801 上午）**｜使用者親看
  run 20260801-080213 幀定調：「前面 tick 擷取的盤面，後面以為
  有移動但實際沒有，截了 n 張一樣的圖導致盤面膨脹；t8-12 與
  frames/ 目錄同況，縮放或些微移動被判為不同區域」。主 session
  核驗結果：①同場景多 offset 重複吸收確認（藍 52 vs 實 10）；
  ②修正一處——格距全程 91-94 穩定，縮放本身未漂移，「判為不
  同區」的機轉是**邊緣區全幀 GRID_REGION 帶 read_lattice 回
  None（格線其實在畫面下半，右下窗讀得到 pitch 92.9-94.5）→
  相位閘停擺→星座票在同型編隊（幀內縱距 90/93/96 週期陣列）上
  的 alias 幽靈位移長驅直入**；③待機動畫使 frame_difference
  5.8-12.5 恆高於 2.5，原地幀進不了 STILL 而落 unmeasurable 進
  島，relocalise 同樣 alias 脆弱；④裁判驗證——直接影像比對可
  分辨真移動與幽靈（t6→t7 真移動：平移假設 14.32 勝原地
  19.11）。**v2.6 批**（取代原 A/B/C 選單，含蓋 A＋B 精神）：
  ①影像複驗閘——星座票與島嶼合併 delta 必須以 margin 勝過
  「原地假設」，原地勝出＝確定沒動走 STALLED 正軌（同時解待機
  動畫堵 STILL 缺口）②邊帶格線 fallback（象限子窗）補相位閘
  邊緣死區③merge delta 包絡閘（島存活期斷腿 expected 推上界）。
  加閘不改量測值；量測鏈其餘不動。
- **複驗輪第 5 輪判定＋台數軸停工（依紀律，已由使用者裁示解除）**｜
  第 5 輪（run 20260801-080213，6.2 分、EN 零耗）：**W1 PASS**
  （cells≡census＝80、無界外殘留、北旗改判 −12→−7 的裁剪正確
  生效）＝v2.5 機制本身有效；W3 PASS（merge 遙測 7/7 對帳）；
  W5 discarded=0；**W2 FAIL：80 台（藍 52 紅 28）vs 期望 28，
  界內膨脹比第 4 輪 census 55 更甚**。台數軸連續兩次針對性修正
  （v2.3 滯後→修漏記、v2.5 邊界一致→修界外鬼影）後主症狀仍
  在——**依紀律停工，live-tester 已 discord-notify 使用者**，
  不做第三次自主修正。**鑑識線索**（決策材料）：①merge delta
  +273（≈3 欄）重複 4/7 次、另一筆 (546,−670.3)（y 偏 8 列）
  幾乎必為錯誤重錨；②最終邊界跨 48 欄×10 列（west−11..east36）
  遠超真實地圖尺寸＝錯誤重錨把邊界旗釘在不同座標系上、矩形被
  撐大，故 W1 過而鬼影全在「界內」；③藍 52 格 vs 我方實 10 台
  ＝同一星座在多個錯位座標系下被重複吸收，UNIT 滯後保住全部；
  ④水平 broken 0→6（多為 unmeasurable 誠實拒收，island 自癒，
  但每次自癒都靠 relocalise＝把信任壓在同一個可疑環節）。**根
  因假說（待裁）**：薩克編隊＝格對齊的同型單位週期陣列，星座
  匹配與相位相關一樣有 alias 歧義——relocalise 的眾數票可以
  「錯一個編隊間距但票數十足」，錯誤 delta 整批寫入。**候選
  方向（供使用者選）**：(A) merge delta 包絡閘——島嶼存活期間
  斷掉那幾腿的指令行程可推出 delta 上下界，(546,−670) 這類立即
  拒收，超界改走丟棄重掃（誠實有界）；(B) relocalise 加眾數
  邊際要求（次高票不得貼近最高票）＋提高支持門檻；(C) 重錨不
  確定時整島丟棄不合併（成本＝更多全掃）。主 session 傾向
  A＋B 併行、C 作為兜底，但**不在裁示前動工**。
- **v2.5 單位帳一致性批設計決定 10 條整批接受（d056004 合併）**｜
  opus worktree 交付四 commit、主 session 親審（含 _trim 對未定
  旗方向不裁的行為親驗）＋主 repo 閘門 1571 passed／ruff 綠；
  判別性 6/7 未修碼 FAIL 實測。導覽 docs/reviews/
  scan-v2_5-review.md。要點裁決：裁剪含 charted（frontier 種子，
  線外「看過」是假的）；**absorb 寫值側不加界內過濾**（保守
  正確——邊界旗可能錯，寫值側過濾＝錯旗靜默吃掉真觀測；裁剪
  只在旗被新證據改寫那一刻）；`_inside` 以四旗全定為前提；
  last_merge 掛 Survey 不塞 Reading（層次歸屬）。爭點留檔：
  本批只保證 journal cells ≡ 界內 census，界內膨脹責任歸重錨
  delta＋UNIT 滯後組合，第 5 輪憑 merge 遙測定讞；若第 5 輪仍
  見界外 cells 而旗只定案一次＝存在第三條路徑（absorb 旗定後
  仍收線外格，設計決定 2 刻意保留）；`_agrees` 因 sightings 界
  內化變嚴，實機盯 islands.discarded。
- **複驗輪第 4 輪判定：水平斷鏈決勝過關＋台數第二軸缺陷定位＋
  v2.5 裁決**｜第 4 輪（run 20260801-071055，5.7 分、EN 零耗、
  游標未飄）：**V1 PASS——東西向 broken 18→0**（僅 2 次垂直
  unmeasurable 誠實隔離）；V2 PASS 有保留（lattice:constellation
  ×4 實機接通、無 lattice:commanded；但 9/13 水平腿退回舊路徑、
  lattice:phase 證人零出現＝接通率偏低，列觀察）；V3 PASS 增益
  0.44→0.75 爬升非死鎖；V4 資訊性 34 腿未降。停工條款未觸發，
  **v2.4 修正定讞有效**。**V5 FAIL 且機制定位**：journal cells
  84（藍 52 紅 32）vs 界內 census 55 vs 期望 28；29 筆整段在
  最終東界外＝邊界定案/重錨後 marks 從不裁剪的舊座標系殘留
  （fix_boundary/absorb/expire 只動 state）；界內膨脹指向重錨
  delta 寫錯整批鬼影被 UNIT 滯後保住（本輪兩次 merge delta
  (455,186.9)/(0,164.3) 可疑但無法從遙測定讞）。**v2.5 裁決**
  （自裁：不讓 2e 帶著 3 倍鬼影單位表起步）：①fix_boundary 定
  案/改判時裁剪線外 state/marks/charted/unreachable ②units/
  sightings 在 bounded 時只回界內（含 relocalise 比對標的去鬼
  影）③重錨 delta 入遙測（界內膨脹若第 5 輪仍在，憑此＋全幀
  傾印鑑識）；_reanchor/_solve/量測鏈零改動——重錨寫錯的根治
  等資料定讞，不猜。
- **v2.4 量測鏈修正批入庫＋兩偏離裁決（55cac00 合併）**｜opus
  worktree 交付、主 session 親審 diff＋主 repo 閘門親跑 1564
  passed／ruff 綠；離線以 18 對實幀重放驗證：14 對量對（與星座
  證人 ±1.5px）、3 對誠實拒收（證人矛盾/無證人）、1 對 lattice
  不可讀退回現行路徑。導覽 docs/reviews/scan-v2_4-review.md。
  機制：`measure_pan` 格線相位通道（小數＝兩幀欄線絕對距離配對
  ＋環狀中位數；通道閘控嚴格，無指令/無 x 分量/lattice 缺/欄距
  漂移 >10% 全退回現行路徑＝precheck 與靜止閘零改變）＋整數欄
  三重裁決＋`_snap`/`rephase` 全線中位數殘差。**兩偏離規格處均
  裁決接受**：(1) 獨立證人（星座 vs 相關器）各選候選且不同格→
  誠實回 None 而非星座優先——t11/t13 實據星座眾數整欄錯且該錯
  值通過下游所有閘門（相位殘差由構造為零）＝量錯寫入路徑，不准
  存在；(2) 指令兜底要求包絡窗內唯一候選——增益未收斂時
  expected 為真值 2.5×、窗含 11 候選，「取最近」自信錯兩欄。
  加項 `_correlator_credible`（畫面實變卻報沒動的相關器不得作
  證）接受——否則 t17/t20 選 +39 候選判 STALLED、連兩次會把邊
  界旗永久釘錯在圖中央。agent 自首鑑識工具修正一筆（弧色遮罩
  NCC 帶靜態 HUD 拉零＝該估計器作廢）備查於導覽 §1。
- **複驗輪第 3 輪判讀＋水平斷鏈根因主 session 離線鑑識定讞＋v2.4
  裁決**｜第 3 輪（run 20260801-060433，5.7 分收工、EN 零耗、存證
  R4 PASS＝18 對 broken 幀＋66 張全幀）：R1 部分過——垂直增益
  0.33→0.83 收斂（v2.3 修正生效）、**水平恆 0.31＝第二死鎖**
  （東西腿幾乎全 BROKEN，BROKEN 不入帳教學＝雞生蛋）；R2 FAIL
  33 腿>29（水平斷鏈燒預算抵銷垂直增益收益）；R3 FAIL 翻向多記
  （51-68 台 vs 期望 28，紅 31 藍 37）＝座標漂移鬼影被 UNIT 滯後
  保住，鬼影源頭歸水平里程計。**鑑識定讞**（主 session 親跑星座
  對位逐對驗 18 幀對）：①東向 7 腿量測凍值 −108.0±0.3 vs 星座
  真值 −97～−140 波動＝相關器回穩定假值（誤差 3-30px 正是相位閘
  攔下的東西）②t17/27/28/30 量測 ~0 vs 真值 −108～−140＝
  **phaseCorrelate 靜態峰鎖死全損**（response 0.13-0.47 仍過門
  檻、星座 fallback 未觸發）③逐幀欄距 90.2-91.3 穩定＝橫向透視
  假說出局、pitch 累積為次要（_snap 逐幀吸附自癒）④垂直軸健康
  （南北 BROKEN=0）。機制＝直欄格線 90px 週期給水平相關天生
  ±90k 歧義峰＋靜態成分搶峰；**7/20 map_stitch 同款教訓**（alias
  高分假鎖整條移除）。**v2.4 裁決**：水平位移改格線相位權威
  （線對位中位數給小數）＋整數欄三重裁決（星座＞相關器＞指令
  包絡，無一致證人誠實回不知道＝0719 紅線）；_snap/rephase 殘差
  改全線中位數；y 通道與 envelope 不動。斷鏈問題第二次針對性
  修正——**第 4 輪同款簽名再敗＝停下 discord-notify 使用者**。
- **v2.3 批設計決定 20 條整批接受＋六爭點裁決（fb2f806 合併）**｜
  opus worktree 交付五 commit、主 session 親審 diff（coverage.py
  確認只動 absorb/_learn_gain）＋主 repo 閘門親跑 1547 passed／
  ruff 綠；判別性未修碼 4 條 FAIL 實測（含 A6 先漲後跌簽名
  [4,3,1,3,4,0,…]）；增益合成收斂 0.33→1.00 六腿內、起手值與實
  機遙測逐位吻合。全文 docs/reviews/scan-v2_3-review.md。**主
  session 裁決**：(決定 2) UNIT 滯後不加「連兩幀才升」反制——
  漏記比多記貴、expire 逐代自清、複驗輪對帳台數監控，接受；
  (決定 12) 存證用 cv2.imencode 重編 PNG（像素逐點同、位元組
  不同）——離線重放要的是像素，接受，不改 Camera 介面；(爭點 2)
  第 3 輪驗收**不含斷鏈率**（本批未修量測鏈，37 次照發生是預
  期）；(爭點 3) 台數地面真相＝遊戲畫面破壞數計數器（敵 18）＋
  我方出擊 10（兩隊各 5）→期望 UNIT≈28、紅方 ≥16 為過，不另派
  人工普查；(爭點 4) --dump-survey-frames 第 3 輪＝鑑識輪打開
  一次收全資料（gitignored），成本接受；(爭點 6) 待驗項併佇列。
- **掃描複驗輪第 2 輪判讀＋主 session 鑑識＋v2.3 裁決**｜Phase A
  （data/runs/20260801-042733）：A1 PASS（29 腿 synced，遠低於 80）
  ＋A4 PASS（四旗全定，西=-11 補上）＝上輪兩大缺口關閉，連兩輪
  停止條件未觸發；A2 部分未達（斷鏈 14→11 僅降 21%）；A3 關鍵
  發現＝settle.waits 100%=1、quiet 全真——**靜止閘從未等待，
  滑行假說出局**，v2.2 的閘保留當保險但非斷鏈解方。Phase B
  （20260801-044436-phaseB）：expire() 語意實機驗證（legs 歸零、
  UNIT→STALE 9、EMPTY→UNKNOWN 351、幾何保留）＝v2.1 缺陷①修
  正 live 確認；**結束回合鈕三座標實 tap 正式標定**（(300,185)
  開窗、(997,562) 待機並結束、(1365,850) 執行；自動戰鬥紅線未
  觸碰）；敵回合 18 次應戰彈窗預設 stance 全數正確應答（副作用
  破壞數 0→15/18，棄戰未落地）；卡條換回合不彈回定讞；回合 2
  同 Survey 續掃 13 腿 synced、islands 跨代累加正確。**主 session
  離線鑑識三定讞**：(a) A6 漏記（最終 10 台 vs 目標 18 敵＋我
  10）＝**簿記層**——親跑 find_sightings 於 survey:start 幀得
  23 目擊，absorb() 無條件 EMPTY 重置＋marks.pop 抹掉先前 UNIT；
  (b) **增益學習死鎖**——遙測 9 腿 measured/expected 恆 0.33
  （最小縮放真實增益 ~0.76 vs 預設 2.3），_learn_gain 的
  0.5×wanted 撞邊保護恆真擋學習；(c) 東緣**橡皮筋回彈**（東向
  指令量到 +39/+40px 反向）由 STALL 路徑正常吸收，不修。**水平
  向斷鏈根因未定**（兩輪 37 次幾乎全 east/west；候選＝量測欠讀
  〔靜態 HUD 混窗拉峰〕vs 相位參考漂移）——不猜不修，v2.3 補
  BROKEN 幀原生存證＋--dump-survey-frames 讓第 3 輪資料可離線
  定讞。**v2.3 批**＝absorb 同代 UNIT 滯後（無目擊≠離開證據，
  我方回合敵不動）＋增益入帳改 ACCEPTED 且 ≥EDGE_SHIFT_PX＋
  BROKEN 存證＋synced 提前結束；量測鏈零改動。跨回合邊界旗不穩
  （35×9→24×5，伴隨 15/18 敵亡劇變）單樣本不下結論，觀察留檔。
- **v2.2 靜止閘＋遙測批設計決定 16 條整批接受（94fa54a 合併）**｜
  opus worktree 交付（API 過濾誤殺中斷於最終閘門前，主 session 接
  手補 commit 導覽＋親跑閘門 1525 passed／ruff 綠）｜全文
  docs/reviews/scan-quiescence-v2_2-review.md 第五節。要點：靜止
  判準 measure_shift 非 frame_difference；常數落 stage/survey.py
  （取幀策略歸執行器，board.py 保持純像素機制）；QUIET_PX=3.0
  （0.5px 零位移偏差 6× 裕度、相位閘容差 7.5× 安全距）；重試盡
  照收＋quiet 旗分開記；遙測走注入 callback（無緩衝所有權問題、
  失敗單點隔離）；islands 計數器逐筆記（斷鏈歸因到 precheck/leg）；
  survey_tick kind 名歸 Runner 端。**五爭點裁決**：(1) 驗收標準
  ＝斷鏈率降到個位數非零，接受；(2) QUIET_PX/ROUNDS 未實機標定
  →下輪首要看 settle.waits 分佈；(3) 截圖成本翻倍→實測牆鐘再
  議，PAN_SETTLE_S 本批不動（單變因紀律）；(4) Odometer.feed
  BROKEN 不推進 previous 之疑→主 session 親追呼叫鏈**裁決非缺
  陷**：observe 遇 BROKEN 一律 _isolate，新島 odometer 以斷鏈幀
  為 previous 重新播種，「同 odometer 連續兩次 BROKEN 用舊基準」
  情境不存在，量測層不補規則；(5) 實機驗證項併入複驗輪第 2 輪
  （unlocalised/isolated 對照 14/14、settle.waits 分佈、逐腿
  shift.magnitude、西旗 80 tick 內能否定）。
- **掃描複驗輪第 1 輪判讀＋v2.2 小批決策（主 session 診斷定讞）**｜
  UC HARD 1 Phase A FAIL（run data/runs/20260801-033746）：40 tick
  打滿 synced=false、西邊界未定（3/4 旗）、cells=16（9 藍 7 紅 vs
  畫面破壞數 0/18）、14 次 BROKEN(phase) 斷鏈＝36% 腿數、islands
  isolated14/merged8/discarded6、unlocalised=14；unreachable=0（退
  休機制無異常）。Phase B 依規格跳過。**機制鏈定讞**：重錨修正量
  全為整欄（180/270/360px＝pitch90 的 2-4 欄）＝被拒那腿的行程，
  恢復機制照設計運作；根因是斷鏈頻率——pan 慣性滑行拖過 1.5s
  settle，前置複核幀（expected=None，envelope 只擋 >40px）量到
  22.5–40px 無指令殘餘位移剛好落進相位閘窗口（PHASE_TOLERANCE
  0.25×90=22.5）＝0731 快照「緩動殘餘 vs 無指令 40px 閘」疑點
  實證。**v2.2 三件套裁決**：①掃描取幀靜止閘——連拍兩幀以
  measure_shift 量全域位移judge靜止（**不用 frame_difference**：
  單位待機動畫會讓它永不安靜；滑行是全域同調位移相位相關量得
  到），有界重試用盡照收（閘只降污染率）；②逐 tick 遙測入
  journal（verdict/reason/shift/offset/island 態/重試數）補 A5
  儀器化缺口；③dry_run SURVEY_TICKS 預設 40→80（步數帳 41+ 無
  裕度；LEG_BUDGET 200 不動）。coverage.py 本批零改動（v2.1 剛
  過審避免多變因）。斷鏈同款簽名若下一輪複驗再敗＝連兩輪，停下
  問使用者。
- **複驗輪附帶實機觀察**｜(a) 結束回合鈕目視標定約中心 (300,185)
  （原生 2340×1080，範圍 x172-431/y156-214）——與舊疑誤標
  (275,182) 同一鈕面，懸案傾向解除，但未實際 tap＋彈窗確認，
  不升級「已標定」，Phase B 首次點擊時覆核；(b) 棄戰零資源消耗
  三度實證（EN/資金/鑽/RANK 前後全同）；(c) 複驗輪執行面教訓：
  長時裝置委派任務要有收尾檢查點——本輪子代理 Phase A 跑完後
  失聯，戰局懸空由協調端接手收尾（棄戰＋對帳＋導航），未造成
  資源損失。(d) 資源基準漂移（EN 161→211、資金 1,255,000→
  1,307,500、鑽 2,600→4,200）＝session 間非本程式活動，僅記錄。
- **v2.1 六缺陷修正批設計決定 15 條整批接受（42d8f77 合併）**｜opus
  worktree 交付、主 session 親審 diff＋測試＋導覽（全文
  docs/reviews/coverage-v2_1-fix-review.md 第四節）｜要點：`expire()`
  legs 歸零放 `chart is None` 早退前；`_abandon()` 不歸零 legs 但清
  clamps；`_whole_cells` 更名 `_whole_columns`（名實相符）；島嶼停滯
  計數掛 `Island.stalls` 隨島滅；`_agrees` 容差逐軸半格、門檻
  RELOCATE_MIN_SUPPORT 不放寬（稀疏島寧走 `_abandon` 全掃也不讓一台
  單位背書重錨）、權威圖零目擊同視為無可矛盾；pins 複驗失敗 fall
  through 到 relocalise 不直接 None；`_nearest` 格空間歐氏＋字典序
  tie-break、一次退休一格；去重半徑 0.5×min(pitch)、每簇留字典序最
  小點、無格網退 CONSTELLATION_TOLERANCE。閘門主 repo 親跑 1521
  passed／ruff 綠；未修碼判別性 10/11 條 FAIL 實測。
- **v2.1 三爭點裁決（主 session 自裁）**｜(1) repro2_ydrift 非缺陷 2
  判別性證據（修正前後都 ok，合成世界造不出穩定半列島偏移）→接受
  現狀：判別性證據以 repro3a＋迴歸測試為準，不為此擴 fixture；半列
  情境的端到端驗證歸掃描複驗輪實機收（敵回合過場天然產生）。(2) 稀
  疏盤面重錨變嚴（pins 被 `_agrees` 擋下→ISLAND_BUDGET 耗盡→
  `_abandon` 全掃）→接受「誠實但貴」，符合「量錯寫入不准存在」紅
  線；成本實機量測後再議是否調整。(3) 實機驗證三項（多回合 legs 歸
  零＋board_synced、重錨成功率 vs 修正前流水帳、y 夾死逐格退休）併
  入掃描複驗輪清單（roadmap 佇列，live-verification-queue.md 已隨
  83fce1e 清洗刪除不重建）。
- **v2.1 修正批先於掃描複驗輪**（0731 快照留白的先後裁決）｜選項：
  複驗輪先跑收未修碼實機資料 vs 先修再驗｜採先修再驗：①一輪實機
  同時驗六缺陷修正與量測疑點（SURVEY_TICKS、0.5px/腿偏差、重錨、
  緩動殘餘），複驗先跑則修完仍得再跑一輪＝雙倍裝置時間；②實機
  session 有凍機風險前科（7/5–7/13 九次），輪數愈少愈保守；③島嶼
  合併 −50px、釘軸繞複驗屬「量錯寫入」路徑，未修先驗收的格座標
  資料可信度存疑。緩動疑點不因後驗而失真——修正批不碰量測層。
  使用者可推翻（複驗輪腳本與停點設計不受先後影響）。

## 2026-07-31

- **0731 深夜重審定讞（使用者指示：入庫後 re-review 今日兩批）**｜
  主 session 親審（coverage/zoom 全文、board/survey/entry/dry_run
  diff、座標約定逐處交叉推導）＋對抗性 reviewer 獨立掃
  `0c31161..HEAD` 雙軌，四支復現腳本親跑證實（存
  data/review-repros-20260731/）｜無問題的部分：座標與符號約定
  全數互洽、邊界旗語意四處一致無 off-by-one、GridProbe 呼叫端
  乾淨（凍結層 battle/settings.py 是獨立 bool 版未波及）、合成
  世界測試無恆真斷言。**coverage.py 六缺陷（4 high）**：
  (1) `legs` 保險絲跨代不歸零——每回合衰效後全圖重掃累積（復現
  11 回合 106 腿），燒斷後 `board_synced` 永達不成、整關 STUCK；
  (2) 島嶼合併 `_whole_cells` 把 y 捨入整列——y 軸無 rephase 也
  無相位閘，復現真值 (0,50) 解成 (0,0)、整批 −50px 併入權威圖
  且主里程計繼承該誤差永不修正；(3) 島嶼 `_pin` 單次 STALLED 即
  釘軸（主圖 D6 要 STALL_CONFIRM=2），兩軸 pins 齊時 `_solve`
  繞過 relocalise 的支持數複驗＝「量錯寫入」路徑；(4) 多格
  pocket 退休只退質心且質心可落在 pocket 外（L 形復現）——每
  tick 空轉退同一格、當下 EMPTY 的質心格誤入 unreachable 跨代
  排除＝「無聲丟失」路徑；最小縮放下地圖高（12 列×86px≈1032
  <1080）y 軸雙向夾死是常態，前提不難湊齊；(5) `clamps` 不隨
  reset()/_abandon() 清除，跨世界殘留誤真實證；(6) relocalise
  支持數門檻被島嶼重疊 view 的重複目擊灌水（「3 台實體」實質
  退化為 2 台）。另兩筆實機待驗觀察：緩動殘餘 vs 無指令 40px
  閘（每 tick 前置複核幀可能誤開島嶼）、星空假邊界後果從單輪
  升級為永久。裁決：**掃描複驗輪可照跑**——40 tick 上限＋
  expect 失敗即停＋棄戰收尾，上述缺陷在該情境至多浪費一輪不會
  失控，且緩動疑點正需實機資料；**2e 首戰前六條必修**（v2.1
  小批，範圍全在 coverage.py）。修正批派工與複驗輪先後待使用者
  裁示。
- **2c-2d review 使用者裁定**｜四項爭點（docs/reviews/2c-2d-review.md
  尾節）｜(1) `top_right_confirm` 危險帶疑問→引出勘誤（見下條）；
  (2) 自動編制不給按的原則接受；(3) accuracy＝命中%−100 暫用假設
  接受，forecast 對帳前有效；(4) **end_turn 反射否決**——「永遠選左」
  是行為決策，不歸反射層；已拆除該反射，標定座標遷 stage/gestures.py
  停放，應答歸未來按下結束回合鈕的行動自己收。
- **勘誤：自動編制位置 0730 標定錯誤（使用者一手記憶抓出）**｜舊記錄
  稱自動編制在出擊鈕右上 (2001,924)，危險帶 `top_right_confirm` 據此
  劃設；使用者指出自動編制實在出擊鈕左邊、行動選擇在右下角｜像素
  定讞（2b2_02／step8 兩幀 bbox 完全一致）：下緣按鈕列＝替換部隊／
  變更配屬／全部編制／自動編制，自動編制中心 (1496,1010)、
  (2001,924) 實為出擊鈕上緣外空星空；行動選擇實測 (2037,930) 右下角
  大圓鈕（舊估計在鈕內仍有效）｜修正：新增 `auto_deploy` 帶
  (1360-1635, 965-1055) **無任何 intent 放行**；原帶改名
  `bottom_right_confirm`（幾何不變，罩行動選擇確認）。附帶裁決：
  帶頂取 970（bbox 頂 973 上留 3px）而非 965——舊武裝選擇槽位列
  y=965（battle/controller.py WEAPON_SLOTS）貼帶外 5px，未來武裝
  選擇搬上 LiveDevice 時不至於被誤擋。殘留風險三筆：(a) 全部編制
  (~1208,1010) 與對話框通用關閉鈕位 (~1170,993) 重疊無法設帶，
  暫不設防；(b) 隱藏關「挑戰」鈕 (1404,977) 落在自動編制鈕面內，
  跨畫面固有重疊，該流程搬上 LiveDevice 時再裁（帶目前無 intent
  可放行）；(c) 帶只罩視覺 bbox＋數px，遊戲觸控 padding 若超出
  視覺框仍可能觸發，實戰觀察。
- **覆蓋模型 v2 設計決定 18 條整批接受（2df6e04 合併）**｜opus
  worktree 交付、主 session 審驗（規格 14 條逐一對落點、符號層
  零改動宣稱屬實、swept 無讀者 grep 驗證、閘門親跑 1506 passed）
  ｜全文 docs/reviews/survey-coverage-v2-review.md。**D1 swept
  淘汰請使用者確認**：欄位無任何 applicable/progressed/goal 讀者，
  覆蓋數字改走 evidence["survey"]；備選（改義／覆蓋率整數）都
  污染搜尋鍵，故採淘汰——介面縮小，使用者可推翻（git 可復原）。
  其餘要點備查：(D4) 包絡閘三段 ok/repeat/refused 解規格 1.5×
  與 2× 條文牴觸；(D5) 相位閘只驗直線軸（橫線透視遞增非不變
  量）；(D8) unreachable 退休集——HUD 壓角格明寫退休出聲，不
  悄悄當掃完；(D9) 島嶼重錨失敗＝丟棄重開世界（steering 未實
  作，成本有界）；(D12) 停滯位移取準確 0（phaseCorrelate +0.5px
  系統偏差實測 80 tick 漂一列）；(D17/18) 格距帶 ((60,105),
  (90,160)) 細帶先試、read_lattice 加 bands 參數不開新讀取器。
  煙測三發現全數處置（多尺度＋grid_on 從根修＋煙測幀入 fixture）。
  SURVEY_TICKS 未動——腿數變多是否夠用歸掃描複驗輪實測。
- **pinch 煙測重跑 PASS（0731 傍晚，使用者授權 adb 點擊恢復後）**
  ｜恢復路徑：返回標題→登入（含 154MB 資料下載、登入獎勵 DAY 6
  道具、公告關閉）→主頁→關卡 hub→UC 輪播（停留位正確）→系列
  資訊→關卡列表，全程照 ui-navigation-map 標定座標｜煙測
  （--survey-ticks 3，run data/runs/20260731-170423）：七次 pinch
  幀差 47.7→0.18 收斂、格距 127.5→約 64px 視野加倍、全流程
  select→…→survey→棄戰 ok、EN 161/111 前後一致零消耗。**縮放
  可用定讞**｜新發現三筆（已轉 v2 開發中 agent）：(a) 最小縮放
  pitch ~64 低於 GRID_MIN_SPACING=90，read_lattice 全程 None 退
  幀差；且 _ridges 間距下限在滿格幅幀會隔行取線把 64 誤讀成
  128（混疊翻倍），v2 格線相位層兩模式都要處理；(b) grid_on
  信念隨之翻 False（after_survey 實測），長跑會讓 SurveyBoard
  前置中途看似失效，v2 交付需提案；(c) 地圖邊緣半幅虛空破壞
  間距均勻性閘＋星空帶 unlocalised（r=0.001 fail-soft 正確）。
- **pinch 煙測遭遊戲錯誤 300 中斷＋恢復點擊被權限系統攔截**｜煙測
  （dry_run_entry --survey-ticks 3）進關途中 sortie→stage_info 段，
  遊戲彈「錯誤代碼：300 工作階段錯誤。將返回標題。」唯一鈕對話框；
  zoom 本體未驗到（唯一收穫＝zoom_backend available=true，
  uiautomator2 接線通）。run：data/runs/20260731-163732｜(a) 停手
  等使用者、(b) 裁決點「返回標題」恢復＋依標定文件導航重試｜先裁
  (b)（唯一官方恢復鈕、不耗資源），但執行遭權限分類器兩路攔截
  （臨時 tap 腳本＋原始 adb input tap）——live-tester 依「兩次失敗
  停下」紀律停手正確，且查證 run_manual_battle.py 是 0730 使用者
  指示刪除（無手動導航正式入口是刻意狀態），權限攔截與之相印證。
  升級使用者裁決（discord 已通知），裝置停在對話框未被誤操作。
  附記：同時段 tmux server 意外死亡一筆（日誌完整保留、是否同源
  未深究）。EN 是否受中斷流程影響待恢復後對帳（基準 161/111）。
- **驗證輪修正批設計決定整批接受**（opus worktree 交付，主 session
  審後合併；閘門雙跑全綠 1466 passed＋合併後複跑）｜11 條全文在
  docs/reviews/fix-batch-review.md，要點備查：(D1) zoom_out_max 量測
  單讀器 `board.read_lattice`＋幀差 fail-soft——不為凍結層的兩段式
  憑空造未實測的寬區常數；(D3) 不搬 obstruction 彈窗參數——彈窗歸
  反射組，代價是縮放中彈窗會讓該輪提早收斂；(D5) 幀源統一採
  「Camera 實作 screenshot() 當 device 餵 Perceiver」——單一幀源是
  結構保證非呼叫紀律；(D8) `advisory` 入 ACCEPTED_OUTCOMES 當第三
  等級（記錄不裁定），僅 grid_setting 使用；(D4) pinch 注入繞過
  tap 白名單，出手前四落點自過 check_tap。審驗確認：凍結層
  pinch.py 一字未動、show_grid bool→str 唯一消費端只記流水帳不
  裁定、pinch 落點區（y≤650）與同日勘誤新增的 auto_deploy 帶
  （y≥970）無重疊。

## 2026-07-30

- **舊 `sim/`、`planner/` 延後刪除**｜批 1b 搬遷完成後照政策應刪，
  但舊 `battle/`、`content/`（參考材料）仍 import 它們｜(a) 立即刪
  並連鎖清理、(b) 延後到批 2/3 搬完 battle/content 一起刪｜採 (b)：
  保守——參考材料在批 2d 搬遷期間仍有對照價值，現在斷鏈風險大於
  留置成本。
- **批 1b 設計決定整批接受**（Phase 併入 Faction、chance_steps 命名、
  單一 BFS 幾何、objective 歸 search、MP 不搬留加算桶接線點、命名
  全面遊戲術語化）｜在派工規格授權範圍內，機制語意有 95 條測試
  釘住｜已入庫 bc47690，使用者可逐條推翻。
- **批 2a 設計決定接受**｜(1) learn／assume 分離：畫面讀到的才記
  known、快取先驗只給數據不給 known——「快取當先驗、畫面是權威」
  的型別化；(2) 盤面級不背書：缺任一台情報整盤不計價，Inspect 因此
  自然入計畫；(3) KILL 三重保守判準（無攔截者＋迴避後命中達門檻＋
  最強減傷下傷害仍過殘 HP）｜已入庫，實機 forecast 於批 2d 成為
  權威、公式版降後備。
- **批 2d 血量接縫預決**｜2a 組盤面時 HP/EN 暫以滿值假設（對 KILL
  保守、對我方存活樂觀）｜(a) 觀測值進 StageState、(b) 觀測值經
  Intelligence.unit(hp=, en=) 注入｜採 (b)：符號狀態保持純淨（它是
  A* 搜尋鍵），動態數值走情報庫通道。
- **冷快取首進關的終局語意**｜無先驗時內層會規劃出 Inspect 序列後
  誠實停止（STUCK）｜這是偵察輪的預期產出不是失敗——批 3 外層
  把「STUCK＋情報增量非空」視為偵察成功，重估後再戰。
- **駕駛員攻擊值拆分的沙盤對映**｜遊戲拆射擊值／格鬥值（＋覺醒值），
  沙盤 Unit 只有單一 pilot_attack｜(a) 沙盤改型別、(b) 情報庫兩值
  都存、組裝時依武裝類別選用對應值｜採 (b) 保守：不動已測穩的
  沙盤型別，對映在組裝層；與實機 forecast 的對賬（批 2d）驗證
  這個選法，不符再改型別。
- **重連後 USB 資料存取彈窗按「拒絕」**｜開機重連跳「允許存取手機
  資料嗎？」系統彈窗（MTP 檔案存取授權，與 adb 無關——adb 已能
  截圖）｜(a) 允許、(b) 拒絕｜採 (b) 最小權限：作業只靠 adb，不需
  檔案存取；若之後每次重連都跳窗再改允許。
- **5 秒鎖屏處理走程式解法，不改系統設定**｜lock_screen_lock_after_
  timeout=5000 會吞 tap，roadmap 列兩路：接 keyguard.py 或請使用者
  調長 timeout｜(a) 改系統設定（調 timeout 或 stay_on_while_plugged_
  in）、(b) 新增 scripts/ensure_unlocked.py 入口（包既成
  Keyguard.ensure_unlocked），偵察輪每段互動前呼叫｜採 (b) 保守：
  不動使用者手機系統設定；解鎖路徑是既成已實戰的程式。
- **2c 解析方法裁定：混合式**｜2b 樣本定讞——面板版面固定、數字
  字體單一高對比（stage_panels＋roster_panels 共 30+ 張）｜(a) 全
  視覺 LLM（使用者原方向：ollama 廉價解析）、(b) 全模板＋OCR、
  (c) 混合：錨點定位＋數值欄數字字模模板匹配、自由文字欄（武裝
  名／能力詞條／特效說明）本地視覺 LLM（gemma3:27b 起手）＋型錄
  白名單對齊、固定詞彙徽章小模板分類｜採 (c)：數值直餵沙盤與
  KILL 判準，LLM 幻讀數字會無聲毒化且 CI 無法離線釘住；模板路徑
  確定性、fixtures 可 pytest 回歸。LLM 保留在其擅長的 CJK 自由
  文字且輸出過白名單。相對使用者原方向是保守收窄，可推翻。
  ——0730 使用者核可並補充定向：LLM 輸出綁封閉 schema（沙盤已
  實作機制的枚舉，MCP 式契約）、schema 外新機制標 unsupported
  待改碼，不猜不入庫（已落 intel-data-spec.md）。
- **批 2c 設計決定整批接受**（b24543e 合併；驗證：worktree 閘門
  綠＋獨角獸武裝頁數值逐欄對 ground truth 全中＋LLM 契約確認為
  約束解碼非 prompt 拜託）。要點備查：(1) 組裝落 stage/
  intel_panels.py——runtime 不得 import stage，型別住 stage；
  (2) **accuracy＝命中%−100**（沙盤加法項對映）待批 2d 實機
  forecast 對帳；(3) pilot_attack 不預填，三值存 pilot_offence
  由呼叫端依武裝類別選；(4) 武裝類別是集合（一把可掛多枚徽章，
  實樣佐證）；(5) 無特效說明的卡 schema 縮成只問名稱（實測留欄
  會誘發模型腦補）；(6) 戰鬥力／總戰鬥力描邊漸層字放棄解析（與
  舊碼同判）。舊 battle/panels.py 實測有無聲讀錯 bug（digit_height
  24 應為 22＋固定卡距錯位）——搬遷以新 runtime 實作為準。
- **面板 LLM 預設模型改 gemma4:31b**｜規格原指名 gemma3:27b
  （裁定當時的知識），交付實測：gemma3:27b 武裝名 0/3 且吐簡體、
  gemma4:31b 收窄後 8/8 全對齊｜(a) 留 gemma3 照規格、(b) 改
  gemma4:31b｜採 (b)：證據一面倒，簡體輸出另違專案紅線；
  GGGE_PANEL_LLM_MODEL 可覆寫。能力整區通道仍不可信（截斷、
  誤映各一例），列 2d 待驗。
- **2b-2 站位掃描精度接受**｜重跑輪人工掃描產出：四邊界截證齊、
  單位普查 12–15/18（南東角未逐格掃）、格座標 ±1 行不確定（透視
  ＋貼圖高度）｜(a) 再派一輪補到像素級全覆蓋、(b) 接受為蒐樣級
  成果收批，權威站位由批 2d 程式版盤面全覽掃描接手｜採 (b)：2b
  定位是蒐樣非情報生產，程式版本來就要重做這件事；再跑一輪人工
  只是重複折舊。
- **批 2d 設計決定整批接受**（合併入庫；驗證：worktree 閘門綠、
  grid_on 前置與覆蓋簿記雙層落點親讀確認、危險帶白名單語意親讀、
  唯讀探針實機通過原生幀直通）。要點備查：(1) 反射吐 ScreenFix
  不進行動詞彙——收彈窗不是規劃決策；(2) 危險帶白名單制（帶
  intent 才放行；AUTO 三選一帶**無任何 intent 可放行**）；(3) 掃描
  產出不帶陣營，弧色只當 Layer-0 線索，陣營解析歸 2e 證據分層；
  (4) swept 入 StageState 但搜尋側 apply 不動它——規劃一步到底，
  分段進度是感知側事實；(5) Keyguard 複本入 runtime（凍結的
  actuation 版未刪，舊工具還在用，刪 battle/ 時一併收）；(6) HP
  弧 HSV 帶域現有兩份相同副本（runtime/board 與 battle/vision），
  同上時機收斂。
- **最小縮放（pinch）延後**｜掃描規格「最小縮放＋平移」，pinch
  需多點觸控 sendevent（裝置特定 /dev/input/event7）未搬｜(a) 立
  刻搬＋實機驗、(b) 掃描先在當前縮放跑（zoom_out 注入點留白記
  skipped），pinch 另立小批搬遷＋實機驗證後接上｜~~採 (b) 保守：
  sendevent 直寫輸入裝置的風險高於效益，當前縮放下掃描功能完整
  只是腿數變多。~~ **0730 晚間實機驗證推翻改採 (a)**：UC HARD 1
  實測 20 tick 掃出 0 cell——東西兩向各燒滿 8 腿預算仍未到邊、
  合併從未觸發（data/runs/20260730-140043）。「功能完整只是腿多」
  被證偽；且 pinch 是舊架構在同一台裝置上實戰用過的碼（zoom_
  probe），風險論據弱於原判。搬遷入驗證輪修正批。
- **掃描前收卡條＝比照 grid_on 建模（0730 使用者核可定案）**｜
  可行動單位卡條遮掃描帶（y~1020），掃前需收合（舊碼 collapse_
  unit_list (1970,780)）｜(a) 執行器內嵌收合 tap、(b) 比照格線
  定向：符號行動供給 roster_collapsed，SurveyBoard 前置條件再加
  一條｜採 (b)：同一原則——會改 UI 狀態的行為進符號層。實作
  入 2d 收尾小批。
- **2d 收尾小批設計決定整批接受**（合併入庫；驗證：閘門綠 1454
  ＋roster_collapsed 感知權威落地親讀＋簽名判別依據審閱）。要點
  備查：(1) enter_stage 拆四段入 runtime（分段停點做在可測層，
  script 保持薄）；(2) 公告簽名取「公告」標題帶不取關閉鈕——
  全語料 1002 張實測關閉鈕帶誤命中 100 張、標題僅 4 張；(3)
  Inspect.apply 作廢 roster_collapsed（點單位彈回卡條），Move／
  Attack 的同款效果留待 2e 接手勢 plan 時一併補；(4) LiveExecutor
  把 driver 微步驟名記進流水帳；(5) 新增 stage_list 簽名（group
  末位只吃 unknown 幀）；(6) roster_collapsed=感知權威、None 永不
  折成收合（0723 輪四 41 次空轉的教訓條文化）。
- **關卡節點與放棄危險帶重疊＝保留危險帶不縮**｜UC HARD 1 節點
  平台 (544,872) 落在放棄帶（x0-900,y825-905），程式點選會
  TapRefused｜(a) 縮帶、(b) 加 stage_select intent、(c) 保留帶，
  節點改點編號／星列（y~667）或人工先選關｜採 (c) 保守：帶保護
  的是戰鬥內誤觸放棄，收益大於選關便利；批 3 外層選關 UI 操作
  落地時再議帶的畫面感知化。
- **scripts 清理（0730 使用者指派）**｜留 10 支（capture／crop／
  verify_match／curate_fixture／ensure_unlocked／parse_panel／
  extract_glyphs／extract_panel_templates／probe_live_channel／
  dry_run_entry）；刪 11 支＋孤兒測試：attribute_battle、
  audit_run（掛凍結 agent/）、grid_toggle_probe（runtime entry
  取代）、llm_localize_probe(_b)（定位堆疊未搬遷）、replay_
  frames、replay_map_scan（舊 battle/ 回放）、run_clear_loop、
  run_manual_battle（駕駛凍結架構，操作需求由裸 adb 與 dry_run_
  entry 承接）、zoom_probe（pinch 延後）、export_stage_def（舊
  content 管線）。CLAUDE.md 常用指令同步。注意：ensure_unlocked
  仍 import 凍結 actuation/keyguard——過渡容忍，刪 battle/ 時
  轉 runtime.keyguard。
- **修正批改用主 session 模型（單批偏離 opus 慣例）**｜opus 池
  持續 529 過載，修正批三次派工全數早夭（兩次原實例＋一次全新
  重派），主迴圈同時段請求正常｜(a) 繼續等 opus、(b) 本批改用
  主 session 同款模型｜採 (b)：五項修正規格明確偏機械性，模型
  降轉風險低於無限期停擺；delegation pipeline 的 opus 慣例不變，
  僅此批例外。
- **里程碑「高評價」解讀**｜使用者設定「二輪後以高評價完成獨角獸
  全系列 HARD」，未定義星數｜(a) 三星 COMPLETE（評分 10000，解鎖
  略過）、(b) 四星（另含隱藏戰鬥）｜採 (a)：保守——隱藏與評分
  天然衝突（觸發拖分），先以可略過為準；隱藏由 goal 的 hidden
  項目另行指定。待使用者確認或推翻。
