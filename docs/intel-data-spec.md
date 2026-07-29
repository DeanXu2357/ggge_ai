# 情報資料規格（2026-07-30 定案）

沙盤（`sandbox/model.py`）輸入欄位的完整需求清單與蒐集對映。
使用者裁決：關卡內蒐集＝專門 GOAP 行動（Inspect）；關卡外蒐集＝
寫死流程讀強化頁；先定資料再設計蒐集（本檔即定案）。

## 欄位需求（每台機體）

| 組 | 欄位 | 蒐集來源 |
|---|---|---|
| 數值面板 | unit_attack／unit_defense、reaction（反応）、mobility（機動）、max_hp、en_max、move_range | 我方：強化頁機體詳情（**反応與機動確認在列**）。敵方：關卡內機體詳情 |
| 駕駛員 | pilot_attack／pilot_defense（含命中公式的能力補正來源） | 我方：角色詳情頁。敵方：關卡內機體詳情 |
| 武裝（逐把） | name、power、range_min／max、en_cost、accuracy、can_counter、map_weapon（**MAP 字樣 icon**）＋blast＋彈數、debuff 種類與量 | 武裝分頁（強化頁與關卡內詳情皆有） |
| 能力詞條 | has_shield、attack_shield、interception_reduction、skills（EN 補給等） | 能力／OP 分頁 |
| 次數類 | chance_steps_max（再動）、support_attack／defend 次數上限 | **關卡內機體詳情頁**（使用者裁定；進入路徑＝點單位→摘要卡→詳情，舊標定可參考） |
| 戰場動態 | pos、hp／en 即值、acted、debuffs、支援次數餘額 | 戰鬥中逐 tick 觀測，**永不 cache** |

關卡層級：地形補正（逐格，待標定）、增援劇本事件（攻略經驗回寫，
沙盤已支援注入）。

**延後欄位——tag（使用者 2026-07-30 預告）**：機體／駕駛員帶 tag，
組隊時能力值需要 tag 相搭配（相性加成），且永恆之路出擊限制以
tag 篩選。蒐樣時順手記 tag 顯示位置，但相性機制入規劃**延後**：
使用者裁定之後更新在 HTN 的組隊規劃（批 4 編成評估的後續）。

## 蒐集設計

- **關卡外（我方機隊）**：強化→單位→逐機詳情三類分頁；角色詳情
  補駕駛員數值。強化操作後重讀（帳本知道何時失效）。
- **關卡內（敵方＋次數類）**：GOAP 行動 **Inspect(單位)**——點單位
  →摘要卡→詳情（武裝＋能力＋次數）→關閉→寫回情報庫。符號效果
  ＝該單位 known。
- **資訊不全＝行為**：Advisor 對涉及 unknown 單位的戰鬥候選一律
  不背書（回 None），規劃器自然把 Inspect 排進計畫——偵察不用
  特殊機制。
- **解析方法**：待批 2b 實機蒐樣後裁定（模板／OCR vs 廉價 LLM；
  重點武裝與能力兩分頁）。

## 情報庫（stage/intel.py）

以單位識別為鍵，roster 側（我方，關卡外蒐集）與 stage 側（敵方，
關卡內蒐集＋跨輪累積）兩區；查詢介面供 TacticalAdvisor 組裝
BattleState。定義檔／快取只當先驗、畫面才是權威（既有裁決）。
