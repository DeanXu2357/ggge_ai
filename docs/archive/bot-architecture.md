
## 延後清單（記錄保留實作彈性，v1 不做）

1. **期望判別**：需要動作歷程供分類結果判斷「非預期中斷 vs 正常
   流程」——保障 robustness，但前提是基礎實作正確，v1 不碰。
2. 反射表「適用 view 集合」掛載欄位（metrics 見誤判再加）。
3. 分類器去抖 wrapper（metrics 的 replan 原因統計再回頭）。
4. 熔斷器（metrics 先行，規則見上）。
5. 固定 sleep→短輪詢升級（逐 handler、依 metrics）。
6. back 反射（v1 由 replan＋導航 action 承接，見反射表節）。
7. 觀察動作的 pre 形狀（`view: unknown` vs 空集＋cost）到真
   catalog／R2 與實機一起定；v1 mock 用前者。
