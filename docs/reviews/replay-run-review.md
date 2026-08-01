# Review 導覽：流水帳回放網頁工具（2026-08-02）

使用者交辦：新腳本回放指定過去 run 的 tick record，網頁逐筆重現並顯示留存幀；
兩種模式（投影片前後翻＋條漫直欄全列）。硬性約束＝**不動到既有進度**：本批
只新增兩個檔案，零既有檔案修改（含 `runtime/journal.py` 只作唯讀參考）。

> **先看第三節**。回放的「一筆」是流水帳 entry（seq 順序），不是 tick 分組——
> 這是本批最大的自裁決策，理由與備選在第三節與 decisions.md 0802 條。

---

## Commit 全景

| commit | 內容 |
| --- | --- |
| （程式批） | `scripts/replay_run.py`（535 行，stdlib-only server＋內嵌單頁前端）＋ `tests/test_replay_run.py`（18 條純函式測試） |
| （本檔） | 本導覽＋decisions.md＋roadmap 快照 |

閘門（主 repo 親跑）：`1621 passed, 4 xfailed`／ruff `All checks passed!`。
基底 1603 passed，本批 **+18**，全數來自新測試模組，既有測試零變動。

---

## 一、呼叫鏈與執行順序

```
main()
 ├─ parse_args()                    run（位置參數，可省）／--host／--port／--journal
 ├─ resolve_run(arg, RUNS_ROOT)     四分支：目錄路徑→原地用；.tar.gz 路徑→_extract；
 │    │                             純名稱→先目錄後壓縮檔；省略→_latest_run 取字典序最新
 │    │                             未壓縮目錄（時間戳命名＝字典序即時間序）
 │    └─ _extract(archive)          解到 mkdtemp("ggge-replay-")，atexit 清理；
 │                                  tarfile filter="data" 防壓縮檔內 traversal；
 │                                  要求恰一個頂層目錄
 ├─ find_journal(run_dir, override) 恰一個 *.jsonl 自動選；零／多個 SystemExit（多個列名）
 ├─ load_entries(journal_path)      壞行（斷電殘行、非 dict）計數跳過，stderr 一行警告
 ├─ payload 序列化一次              ★快照語意：server 起來後 jsonl 再長不會反映（爭點 2）
 └─ ThreadingHTTPServer + build_handler(run_dir, payload)
      └─ ReplayHandler.do_GET
           ├─ /          → PAGE_HTML（內嵌，無外部資源）
           ├─ /api/run   → {"name", "journal", "entries": [...]}（原樣 dict）
           ├─ /frames/…  → safe_frame_path 通過才回 image/png
           │               （resolve 後 is_relative_to 比對，%2e%2e／../ 都 404）
           └─ 其餘        → 404
```

前端（單頁 JS，資料只來自 `fetch("/api/run")`）：

```
state = { entries, index, mode, framesOnly }
投影片  renderSlide()   自帶 frame 顯示；無則向前找最近幀壓暗＋「沿用 seq X 的幀」；
                        全場無幀顯示「尚無畫面」；←/→＝step(±1)；
                        「只停在有幀的紀錄」勾選時 step 跳過無幀 entry
條漫    buildComic()    首次切換才建 DOM；<img loading="lazy">（幀是 2MB 級 PNG）；
                        點卡片 → setMode("slide", pinned=true) 停在該筆
模式切換                投影片→條漫 scrollIntoView 到當前筆；
                        條漫→投影片 nearestCardIndex()（視窗頂+80px 啟發式）
tick 顯示               從幀檔名 regex -tick(\d+)\.png$ 推導，推不出就不顯示
```

## 二、測試佈局

`tests/test_replay_run.py` 全程 tmp_path 假 run，不 bind port、不碰 adb：
resolve_run 四分支＋預設最新＋全壓縮報錯；find_journal 恰一／零／多／override；
load_entries 正常／空行／殘行容忍；safe_frame_path 正常／`../`／`%2e%2e`／不存在。
前端無自動化測試（爭點 3），以 headless Chrome 互動探針佐證（見下）。

## 三、爭點

1. **「一筆」＝流水帳 entry，不是 tick**。流水帳只有 seq/t/kind，tick 只存在於
   幀檔名；同一 tick 可對多幀（00013/00014 同 tick0345）、多數 entry 無 tick。
   tick 分組會把 gate/perform 等無幀紀錄硬塞進某個 tick 桶。採 entry 逐筆＝
   與寫入端（`Journal.record` 逐筆寫穿）同構；tick 號降級為顯示欄位。
2. **payload 啟動時序列化一次**：正在寫入中的 run 要看到新 entry 得重啟 server。
   回放定位是「過去的 run」，即時尾隨不在需求內；要做是 SSE/輪詢級的加法。
3. **前端零自動化測試**：pytest 只鎖純函式。開發批以 headless Chrome 探針驗過
   （鍵盤翻頁／沿用幀／只停有幀跳躍／條漫 lazy／點卡回跳／巢狀欄位 pre），
   並在探針中抓到一個真 bug（條漫點卡片被捲動回推索引蓋掉→pinned 參數修正）。
4. **`/frames/../dry_run.jsonl` 會以 image/png 之名回 jsonl**：safe_frame_path
   只保證不逃出 run 目錄，未再收斂到 frames/ 子樹。本機唯讀檢視器，資訊洩漏
   面＝run 目錄自身，暫不加鎖。
5. **未壓縮「最新」＝目錄名字典序**，非 mtime——時間戳命名下兩者等價，且
   rotate_runs 保證任一時刻至多一個未壓縮目錄，分支幾乎不會用到。

## 四、實 run 抽驗證據

`20260801-212645`（282 筆、17 幀）：`/` 200 10918B、`/api/run` 282 筆原樣、
主幀與 `frames/survey/t1-precheck.png` 均 200 image/png、
`--path-as-is /frames/../../../../etc/hostname` → 404。

## 五、補修（同日，使用者實測回饋）

首版只認 `frame` 欄位，使用者實測條漫「太多沒圖」點破兩個漏洞，補修批
（`de07f0a`，閘門 1625 passed／4 xfailed）：

1. **`survey_broken` 的 `prev`／`curr` 欄位漏顯**（20 筆×前後幀對，指
   `frames/broken/`）。前端改收 entry 頂層**所有**符合 `^frames/.+\.png$`
   的字串欄位（順序 frame→prev→curr→其餘鍵序，標籤=欄位名）。
2. **`frames/survey/` 側傾印流水帳零參照**：`--dump-survey-frames` 只寫檔
   不記帳，`t{tick}-{probe}.png` 命名慣例（`SurveyFrames._dump`）是唯一連
   結。伺服器端新增 `collect_attachments()` 按 `kind=="survey_tick"`＋
   `tick`＋`probe` 掛回（實 run 107 筆↔107 張一一對應），payload 增
   `attachments`（鍵=entries 索引字串），entries 保持原樣不注入欄位。

版面同步：條漫有圖卡片改雙欄（文字左、圖右直疊，<900px 退單欄）、投影片
一筆多圖直疊帶標籤、沿用邏輯改「最近一筆有任何圖」整疊壓暗、勾選框改
「只停在有圖的紀錄」、tick 顯示 entry 自帶欄位優先。修正後有圖紀錄
17→144/282（frame 17＋survey_tick 107＋survey_broken 20），純文字的
gate／stage／perform 本來就不留幀。爭點追加：投影片同組圖不重建 DOM
（避免翻頁重抓 2MB 級 PNG）、`/frames/` 刻意不加 Cache-Control（同 port
換 run 會吃到舊位元組）。

**附帶發現（未修，與本批無關）**：`tests/test_not_actionable.py::
test_run_updates_last_activity_only_when_not_actionable_returns_true` 先天
flaky——`idle_timeout_s=0.0` 靠相鄰兩次 `time.time()` 嚴格遞增才早退，本機
71% 機率同值，走進迴圈就撞假件 `_P.observe` 不收 `frame` 參數的
TypeError（`battle/controller.py:479`）。全套 5 跑 1 失敗、隔離 60 跑 0
失敗；移除本批兩檔重跑仍過＝與本批無因果。修法在該測試（假件補參數或
`idle_timeout_s` 給非零），屬既有檔案，待使用者裁示。
