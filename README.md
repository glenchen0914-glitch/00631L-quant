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
