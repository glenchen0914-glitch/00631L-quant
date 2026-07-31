# Falcon v1.1.1 報告校正版

本版僅修正報告呈現，不更動任何交易策略或參數：

- 實際執行時間固定使用台灣時區 `Asia/Taipei`。
- 「可執行價位」改為「條件式觀察價位」。
- 明確註記「到價不等於直接買進，仍須等待確認訊號」。

# 00631L＋00981A 短線雙標的 V17 Final

本版只服務短線操作，正式標的為：

- 00631L：台灣50正2短線反彈／落底交易
- 00981A：主動式ETF短線轉強／回檔交易

不加入009816與2330，也不做長線資產配置。

## 每日自動流程

台灣時間週一至週五14:35，GitHub Actions會：

1. 更新00631L與00981A行情。
2. 分別建立技術指標。
3. 分別執行回測與模型。
4. 產生兩份獨立決策卡。
5. LINE一次推送兩則訊息。
6. 更新兩檔歷史紀錄。

## 報告位置

### 00631L

- `reports/daily_decision.json`
- `reports/dashboard.html`
- `reports/strategy_leaderboard.csv`
- `reports/wave_tracking.csv`
- `reports/decision_history.csv`

### 00981A

- `reports/00981A/daily_decision.json`
- `reports/00981A/dashboard.html`
- `reports/00981A/strategy_leaderboard.csv`
- `reports/00981A/wave_tracking.csv`
- `reports/00981A/decision_history.csv`

## 00981A風險處理

00981A上市歷史較短，因此：

- 模型資料不足時不硬給預測。
- 回測策略不足時自動切換短線技術備援。
- 歷史少於500筆時，信心最高只到C級。
- 正式進場必須同時考慮大盤環境、MA20、MACD與量價。


## 07:00盤前自動報告

新增GitHub Actions：

`00631L + 00981A 07AM Premarket`

台灣時間週一至週五07:00自動執行，LINE會收到三則：

1. 盤前市場摘要
2. 00631L盤前決策
3. 00981A盤前決策

盤前報告使用：

- NASDAQ、SOX、S&P500、Dow、Russell 2000
- 台積電ADR
- VIX
- 美元指數
- 美國10年債殖利率
- S&P與NASDAQ期貨
- 前一交易日00631L及00981A收盤決策

注意：Yahoo Finance沒有穩定的正式台指期夜盤免費資料，因此本版不宣稱包含台指期夜盤；使用美股期貨作為方向替代參考。

## Falcon v1.1 Report Designer
07:00與14:35 LINE報告改為決策優先格式，新增操作結論、交易成熟度、可執行買點、防守線、今日執行規則、最大錯誤與AI一句話。Research Engine完成前不顯示未經回測的歷史勝率。

## Falcon v2.0.0 — Research Engine 基礎版

新增獨立 `Falcon Research Engine` workflow，每週六台灣時間08:00或手動執行。研究流程會：

1. 為00631L與00981A重新下載並建立歷史特徵。
2. 以最新市場狀態尋找過去相似日，且只使用該日期之後的報酬作為歷史標籤。
3. 統計3、5、10交易日報酬、扣估計交易成本後期望值、MAE/MFE及Bootstrap 95%區間。
4. 進行擴張視窗樣本外驗證，避免只顯示樣本內漂亮數字。
5. 將研究結果寫入 `reports/research/`；07:00與14:35報告只在研究樣本足夠時顯示歷史證據。

本版不會把歷史勝率當成未來保證，也不會因研究分數自動繞過Gate、Gap Filter或ATR風控。
