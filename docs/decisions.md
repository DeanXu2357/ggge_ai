# 決策備案

使用者授權（2026-07-30）：決策分支由 Claude 自行裁決、普遍採保守
選項、逐筆在此備案。使用者隨時可回查與推翻；被推翻的決策劃線保留
不刪除。格式：日期｜情境｜選項｜採用與理由。

## 2026-07-31

- **2c-2d review 使用者裁定**｜四項爭點（docs/reviews/2c-2d-review.md
  尾節）｜(1) `top_right_confirm` 危險帶疑問已釐清：右上 y≈924 同一
  槽位在出擊準備畫面是「自動編制」(2001,924)、在應戰 stance 選單是
  「行動選擇」確認鈕 (2042,924)——後者出自 0719 使用者口述流程
  （battle-prep-ui.md §4，座標未精量）；(2) 自動編制遮罩（帶 intent
  才放行）接受；(3) accuracy＝命中%−100 暫用假設接受，forecast 對帳
  前有效；(4) **end_turn 反射否決**——「永遠選左」是行為決策，不歸
  反射層；已拆除該反射，標定座標遷 stage/gestures.py 停放，應答歸
  未來按下結束回合鈕的行動自己收。

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
