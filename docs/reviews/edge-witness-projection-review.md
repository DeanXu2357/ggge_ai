# 終止邊投影校正批（0803 晚）review 導覽

commit `c9a04a0`。把 `read_span` 的終止邊判定從「三閘錨在最外偵測格線」
換成「投影校正空間裡的脊列終點三分裁決」。起點是使用者在第 9 輪 t21 幀
上的除錯追問，設計判準（「截斷處有多條被切的格線、邊界外是平整虛空」）
與取樣規格（單一大窗）均為使用者裁定。

## 呼叫鏈

```
coverage.Survey._view
└─ board.read_span                     # lattice 逐帶邏輯不動，只換邊界來源
   ├─ board.read_lattice(…)            # 框（box）照舊來自取樣帶
   └─ board.scan_edges(frame)          # 邊界目擊，新
      ├─ _highpass(crop(EDGE_SCAN_REGION))
      ├─ _column_space                  # 縱線軸：校正／原樣自證擇優
      │  └─ rectify_columns             # x_rect = XV + (x−XV)/(1+K(y−Y_REF))
      ├─ _axis_edges(縱線軸)            # west/east
      ├─ _highpass(frame[:, x0:x0+w])   # 橫線軸讀全幀高度
      └─ _axis_edges(橫線軸)            # north/south
         └─ _ridge_run → _extend_line → _judge_side → _banded_void
```

下游：`GridSpan.borders`（新欄位，`edges` 變 property）→
`FrameView.borders` → `screen_border`／`sighted_border`（定位與地標）、
`covered()`（EMPTY 毯裁剪線改用邊界位置——框與邊界從此是兩回事，
實測框東緣 1680、邊界 1763）。

## 執行順序（單側裁決）

1. **種子**：細帶 `_ridges` 取窗內脊，間距均勻的最長連續段（<3 條該軸缺席）。
2. **短繩延伸**：往外一格一格找「預期位置 ±GRID_GAP_RANGE、峰高 ≥0.3×中位峰」
   的線；縱線軸繩長 0（校正空間有效範圍即是界）、橫線軸放窗外一個格距
   （撿回貼窗上緣的終止線 307，搆不到回合橫幅）。
3. **截斷判準**：終端離取樣範圍邊 <0.8 格距 → `truncated`（地圖沒看完）。
4. **分帶 void**：外側 0.25–1.25 格距的檢驗帶沿線向切 4 帶，各自過
   mean/max 相對門檻；≥3/4 帶過且無單帶超硬帽 → `EDGE`，否則 `blocked`。

## 標定事實（常數出處）

0803 兩輪 14 幀、多鏡頭位置擬合：縱線斜率場 slope(x)=K·(x−XV)，
XV=1166（IQR 1164~1171）、K=1.10e-4（±5%）、逐幀 rms≤0.006；橫線平行、
列距均勻 87-88。故僅縱線需校正，且映射在 Y_REF=650 上恆等——位置回報
即參考列上的螢幕 x。

## 驗證證據

- 259 幀語料迴歸（r8 158＋r9 101，`data/runs/20260803-{075745,091231}`）：
  對 v2.1 原型同判 341 側次、位置漂移中位 0px／p95 5px／max 9px；
  v3 獨有 42（西 12＋東 30＝斜邊界家族由校正撿回）。
- 對舊三閘證言：141/144 保住；丟的 3 筆（t64/t69/t70 西）為貼幀邊斜西界
  的保守棄權（truncated），主 session 親看定性非誤判。
- 六幀 fixtures（`tests/fixtures/vision/map_scan/edges_20260803/`）：
  t21 角落 west+north（第 9 輪錨定死因的解）、t58 north@307（W1 窗上緣
  外撿回）、t1-precheck 假邊迴歸鎖（見爭點 1）、t16 邊界在框外 83px。
- 閘門：pytest 1608 passed／4 xfailed，ruff 全過。

## 爭點（review 時值得盯的）

1. **t1-precheck 西 @667 翻案**：主 session 原判假邊，code-editor 以三重
   證據推翻（橫線終止量測 1.3 對 116、跨幀剛性 667→915→1162 吻合單位
   位移、與 t2 已證真邊同一實體）；放大親看定讞（艦體桁架誤讀為格線）。
   fixtures manifest `contested` 欄位留底。
2. **`_column_space` 自證擇優**（規格偏離，經核可）：校正／原樣各讀一次
   取脊峰高者。合成世界無透視、硬套校正位置抖 ±10px；副作用＝投影常數
   失準時自動退回原樣。若日後標定縮放檔位，這裡是接入點。
3. **亮度閘退場**：舊三閘的「安靜＋暗」換成「外面還有沒有格線」。舊測試
   `bright_strip_beyond…` 改寫為 `map_that_still_has_gridlines_outside…`
   ——分野在格線不在亮度。批 7 星空假邊界的防線改由分帶 void 承擔。
4. **t15 east @1943 是行為快照非地面真相**（斜東界，與 t16 的 1771 差
   172px＝該把實測東推 178px 的內容位移），測試註解已標明。
5. **v2.1 有 v3 沒的 5 筆**全部轉 `truncated`（校正空間有效範圍比原樣窄
   ~41px，貼邊證言改棄權）——保守方向的損失，非誤判。

## 已知未了

- 實機未驗（本批純離線）：角落幀 `_anchor` 能否真的錨住、`covered()` 用
  邊界裁剪後 EMPTY 毯是否誤蓋 HUD 壓角、斜西界繞邊全程穩定性。
- HUD 遮罩未做：按鈕帶靠 3/4 多數決吸收（north 證言的固定失敗帶）。
- 標定剩餘：縮放檔位（0731 pinch run）、跨更多 run 複驗；predict-and-score
  全模型列後續候選（見 decisions 0803 晚）。
