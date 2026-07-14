# 進度與規劃

更新日期：2026-07-14（**Pilot 離線批次 M1-M7 全落地**：solver 接管
駕駛的 executor/observer/tracker 鏈完成、預設關閉在 GGGE_PILOT 後面；
hub 粉紅弧 HSV 判決＝不可分，sig-confirmation 成為正式盤面過濾）

## 暫停快照（2026-07-14 pilot 離線批次，恢復點）

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

**使用者新定案（雙行為 observer，待規劃＝M8）**：①完整同步模式——
我方 phase 盤面空/缺敵時 observer 自行重掃補齊（pilot 空盤先 resync
再判對齊失敗）；②反應動作模式——從截圖辨識當下可操作項（應戰選項、
支援有無）回饋 solver；③演出階段辨識（事件插入/新敵機登場＝等待）；
④關卡事件可資料插入（純模擬版預備）。

**7/14 晚追加定案（需求全文 docs/stage-definition-requirements.md，
與 M8 合併重新規劃；使用者將清理對話後另開規劃 session）**：關卡
定義檔（layout＋conditions＋events）＝solver 的賽局完整描述；後端
uid 身分制取代 sig 主鍵（同機種不同駕駛數值不同，sig 降關聯證據、
建檔每台開面板）；冷掃全量（掃不完＝報錯，minimax 要完整賽局）／
溫 cache 開局校驗（畫面權威）；**intel 動態預算上限 12（b587fe2）
確定拿掉**；solver 條件驅動 terminal/evaluator＋step() 套 events
（斬首/護衛/限時關目標函數不同）；紅線邊界＝腳本事件可入檔、敵 AI
傾向不可（另簽核）。

**已知風險（實機驗證要盯）**：① intel 掃描會 tap 到粉紅我方弧——
tap 自己單位可能開自機摘要卡（讀進敵方 intel＝污染）或選中單位，
7/13 實戰沒炸但未系統驗證；② 實機 sig 抖動鏈式漂移（見上）；
③ anchor 單解錯位風險（fail-fast 會抓後果）。

**下一步**：M8 雙行為 observer 規劃；實機批次＝計畫 Stage B 探測
B0-B5（identify 探測、btn_switch_target 標定、sig 刷新、per-activation
影子、應戰彈窗捕捉）→ Stage C 整合戰（GGGE_PILOT=1 GGGE_INTEL=1，
已通關低難度關卡免費棄局）。凍機硬體檢查先行。

## 歷史

舊暫停快照（2026-07-08 ～ 07-14 凌晨）、初期計畫、已完成清單、
戰鬥控制器 v2 改進項目等歷史內容已全部移至 [archive.md](archive.md)
——除了了解歷史脈絡,開發時不需要讀。
