# ggge_ai

研究自動化解 SD鋼彈G世代（SD GUNDAM G GENERATION，`com.bandainamcoent.gget_WW`）手機遊戲關卡。

## 目錄結構
- `docs/` — 技術研究筆記
- `secrets/` — 帳號、裝置等敏感資訊（已 `.gitignore`，不進版控），檔名 `*.local.json` 為實際資料，`*.example.json` 為格式範例
- `scripts/` — 之後開發的自動化腳本（下一階段）

## 現況
- 已透過 USB 連接 Android 手機（Samsung SM-G9900），並以 `uiautomator2` 完成連線驗證
- 已建立研究專用 Google 帳號並在手機上安裝遊戲

詳見 [docs/device-control-research.md](docs/device-control-research.md)。

## 架構

採 GOAP（Goal-Oriented Action Planning）架構，Python 3.12+。設計細節與里程碑見 [docs/architecture.md](docs/architecture.md)。
