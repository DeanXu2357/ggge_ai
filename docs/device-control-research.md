# 手機控制技術研究

## 目標
透過 USB 傳輸線讓電腦端程式操作 Android 手機，用於後續自動化解 SD鋼彈G世代 手機遊戲關卡。

## 已測試環境
- 電腦：Linux，`adb` 已安裝於 `/usr/bin/adb`
- 手機：Samsung SM-G9900，Android 12（SDK 31）
- 解析度：1080x2340

## 連線步驟（三星手機的常見坑）
1. 開啟【設定 > 關於手機】連點【組建編號】7 次開啟開發者選項
2. 【設定 > 開發者選項】開啟【USB 偵錯】
3. 用傳輸線接上電腦
4. **重點**：下拉通知列點開 USB 選項，把用途從「僅充電 / 檔案傳輸(MTP)」改成「傳輸檔案」，MTP 模式下不會啟用 adb debug 介面，授權對話框也不會跳出來
5. 手機會跳出「允許 USB 偵錯」對話框，勾選「一律允許使用這台電腦進行偵錯」後按允許
6. 若對話框沒跳出，先到開發者選項執行【撤銷 USB 偵錯授權】，拔插傳輸線重試

驗證指令：
```
adb devices -l
# 應顯示 device 而非 unauthorized
```

## 控制方案比較

| 方案 | 說明 | 優點 | 缺點 |
|---|---|---|---|
| 純 ADB shell (`input tap/swipe`, `screencap`) | 直接下指令 | 最輕量，無額外依賴 | 沒有元素辨識，座標寫死，遊戲改版就失效 |
| **uiautomator2**（已選用） | Python 套件，透過 adb 推送一個常駐 agent (atx-agent) 到手機，用 HTTP API 操作 | 安裝快、不需 Java/Appium Server、支援截圖/座標點擊/元素查找 (XML hierarchy)、Python 生態好整合影像辨識 | 主要支援原生 Android View，遊戲多半是 Unity/Cocos2d 全螢幕渲染，UI 樹通常抓不到內部元素，仍需仰賴「螢幕截圖 + 樣板比對/座標點擊」 |
| Appium | 跨平台自動化框架，需另外起 Appium Server (Node) | 業界標準、支援 iOS | 較重，需要 Java + Node + Appium Server 常駐，對 Unity 遊戲一樣抓不到內部元素 |

**結論**：由於 SD鋼彈G世代 是遊戲引擎全螢幕渲染（非原生 View），uiautomator2 的元素查找對遊戲畫面用處有限，實際操作會以「screencap 截圖 → OpenCV 樣板比對 / 影像辨識找座標 → uiautomator2 送出 tap/swipe」為主要模式。uiautomator2 在此仍有價值：截圖、按鍵注入、應用啟動/切換、裝置狀態查詢都很穩定好用。

## 遊戲資訊
- 套件名稱：`com.bandainamcoent.gget_WW`（SD GUNDAM G GENERATION）
- 使用帳號：`hsupy23@gmail.com`（研究專用 Google 帳號，資訊存於 `secrets/google_account.local.json`，未進版控）

啟動 / 關閉遊戲指令：
```bash
adb shell monkey -p com.bandainamcoent.gget_WW -c android.intent.category.LAUNCHER 1
adb shell am force-stop com.bandainamcoent.gget_WW
```

## 目前進度
- [x] adb 裝置授權成功
- [x] `pip install uiautomator2` 完成
- [x] `python3 -m uiautomator2 init` 完成，成功推送 atx-agent 並可截圖/查詢狀態
- [x] 建立研究專用 Google 帳號並登入 Google Play
- [x] 安裝 SD鋼彈G世代（`com.bandainamcoent.gget_WW`）
- [ ] 遊戲畫面截圖 + 關卡棋盤/單位辨識（下一階段程式部分）
- [ ] 座標點擊操作驗證（需要先完成遊戲新手教學、進到關卡畫面）

## 常用指令備忘
```bash
# 確認裝置
adb devices -l

# Python 連線範例
python3 -c "import uiautomator2 as u2; d = u2.connect(); print(d.info)"

# 截圖
python3 -c "import uiautomator2 as u2; u2.connect().screenshot('screen.png')"
```
