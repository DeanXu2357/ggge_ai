# 實機驗證佇列

2026-07-21 使用者定調：**需要實機的驗證工作一律記錄在此，不阻塞離線架構
與實作**。adb 恢復後由主 session 依優先序排程，裝置任務序列化（同時間只
允許一個 agent 操作裝置）。每項完成後把結論回寫 roadmap／相關文件，並從
本佇列移除。

**執行順序與現場操作腳本（含 BLOCKING 攔截點）見
[live-test-plan.md](live-test-plan.md)**——本檔是案例登記簿，那份是 run-book。

## 前置：裝置連線恢復

- 2026-07-21 檢查：`adb devices` 顯示 `no permissions`——依經驗為重開機後
  seat0 ACL 歸屬問題，桌面實體登入一次即解（不是 udev 問題）；roadmap
  07-20 另記過一筆手機端 unauthorized，若登入後仍不通，需在手機上重新
  授權 USB 偵錯。
- 恢復後先 `uv run python scripts/capture.py` 確認截圖鏈路，再開始排程。
- 重跑戰鬥前 `discord-notify` 通知使用者（roadmap 既有指示不變）。

## 佇列（依優先序）

### 1. #26 覆蓋驅動掃描 survey identify 全鏈路實戰輪（重寫後）

- 內容：`CoverageScanSource` 覆蓋驅動走圖 → 逐台點擊分流（FactionIdentifier
  停靠邊判陣營）→ 完整星座點名 → 定義檔匯出。整條鏈路重寫後未經實機。
- 成功判準：survey_complete；陣營判定零猜測（雙命中拒判有紀錄）；
  `identity.seed` 完整星座點名成功；戰局可正常接續或放棄。
- 場地：活動關戰局仍停 TURN 1 our-turn hub（可放棄退體力）。
- **2026-07-23 凌晨第一輪（serpentine cutover）結果：survey_abort（未過）**
  ——根因＝偵測器域錯配（弧偵測 battle-zoom 校準 vs T3 最小 zoom 工作點，
  #26 07-20 已登記漏接），非「垂直漂移污染」（該說法已被流水帳複核推翻，
  見 [map-scan-survey.md](map-scan-survey.md) 更正段）。**修復已落地：
  覆蓋驅動重寫（批1~批5，serpentine 退役、min-zoom `find_unit_density_peaks`
  注入、cache bounds 預載）**，見 [coverage-scan-plan.md](coverage-scan-plan.md)。
- **本輪要驗的點（重寫後全新，全部離線挑值待實機校準）**：
  1. **手勢方向推動有效性**：nudge 只推鏡頭不量測，卡頓/掉包只損時間；
     實機確認保守短推（`NUDGE_HALF` 250×170、700ms、settle 1.5s）真能
     推走鏡頭且下一幀可定位。
  2. **覆蓋收斂 nudges 數**：`coverage_report` 的 nudges／覆蓋率；對照
     `SCAN_MAX_NUDGES=48`（有 cache hint 時依尺寸放大）是否夠。
  3. **四邊目視偵測**：`read_map_lattice` 的截止緣四邊全中（太空圖家族
     校準，本關即太空圖）；`frame_localized` 的 `edges` 逐邊落點合理。
  4. **survey 接續 identify**：走完 → `bring_to_view`（constellation 重錨、
     無 335px 假跳）→ 停靠邊分流 → 定義檔匯出。
  5. **nudge 預算常數實機調校**：`ANCHOR_MAX_NUDGES=8`／`SCAN_MAX_NUDGES=48`／
     `RELOC_MAX_NUDGES=6`／`STUCK_LIMIT=3`／`BRING_MAX_NUDGES=8` **皆離線
     挑值**，實機依收斂表現調整。
  6. **cache bounds 預載實戰**：第二輪同關重掃時 `_navigator` 應讀到上一輪
     寫入定義檔的 `map_cols/map_rows` 當 hint（`cache_bounds_dropped` 不應
     出現＝hint 與實掃一致）。
- **附帶確認**：`_scout_local`（turn-2+ 局部掃描）的實際 zoom 狀態——若
  遊戲停留最小 zoom，local scout 用的弧偵測有同款域錯配（既存疑問，非
  本輪引入）；順手記一筆 turn-2 hub 的 zoom。
- 附帶：批A/批B（對帳資料保存）落地後，本輪同時開始累積對帳數據。

### 2. 縮放地圖獨立驗證（定案 4）

- 工具：`scripts/zoom_probe.py`（已完成：回頂層 → 開方格 → pinch 迭代
  → pitch 序列 → 關方格）。
- 已驗：GesturePincher 單次 pinch 可縮放（07-20 實機）。
- 待驗：`zoom_out_max` 收斂（連兩次 pitch 不縮判停）；方格開關往返復原；
  `map_view.ensure_max_view` 從各子狀態（選中單位／modal／卡條展開）退回
  hub；`zoom_at_max`（T1 產出的單幀辨識）與收斂迴圈結論一致。
- 成功判準：pitch 序列單調收斂到穩定值；結束時方格恢復 OFF、畫面停在
  hub；過程無誤觸單位行動。

### 3. 切格線流程獨立驗證

- 工具：T2 產出的獨立驗證腳本（讀設定 toggle 狀態 → 切換 → 地圖格線
  確認 → 復原設定）。
- 成功判準：toggle 狀態辨識與地圖格線出現/消失一致；往返後設定復原；
  誤入選單時 fail-soft 能退出。

### 4. 應戰四假設（battle-prep-ui.md §9）

- 頭像槽算術定位 tap／行動選擇 (2042,924) 估計值／武器鈕順序=spec 順序／
  SHORT 深色可用圖示 V 閘門；hit 字型缺 '3' 補樣本。
- 排程：survey 全通（佇列 1）之後，roadmap 既定順序。

### 5. 出擊機雙V偵測器 turn-1 實機輪

- 前置：偵測器離線完成（鈷藍環＋實心白VV 判別式，幀2/幀3 已 10/10）。
- 只在 turn-1 滿血未行動窗口有效（VV=可操作提示會消失、環色=HP 弧會
  變色）；陣營權威仍是停靠邊。

### 6. MAP 砲樣本蒐集（常備、被動）

- 遇有 MAP 敵機關卡：capture 移動選格畫面（兩類威脅圖示）＋該敵機武裝
  面板，存 PNG（silent-events.md 批D）。蒐到前批E 不開工。

### 7. #24／#25 殘餘

- #24 冷掃太空圖提早收工複驗；#25 掃描期格線後續（縱向透視 row 模型、
  定義檔 cells 以格線量測為權威）。

### 8. 佔格候選機制（遠期）

- 大型單位佔格＝選取時移動範圍/阻擋實測；「環心壓格線交叉點」只當疑似
  旗標。佔格權威=使用者/遊戲內驗證。

## 缺樣本清單（實機順手補拍）

- 戰鬥設定選單「顯示方格」**toggle OFF 態**截圖（T2 已掃全庫 451 張確認
  缺：ON 態兩張已入 fixture，OFF 態僅合成測試覆蓋；補拍後用
  `scripts/curate_fixture.py` 裁四探針外接框入 `vision/settings/`，PNG）。
- zoom 拉近（非最遠）且格線開啟的地圖幀（`zoom_at_max` 負樣本，若庫存
  沒有）。
- SHORT 武器「深色但可用」圖示樣本（應戰 V 閘門開放假設）。
- hit 字型含 '3' 的命中率樣本。
