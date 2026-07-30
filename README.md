# 00631L Quant V16 Unified Final

這是將 V11～V16 合併後的統一版本，不再拆成多個小版本。

## 已整合

- GitHub Actions 全自動更新
- LINE 推播
- 決策歷史
- 部位狀態與手動交易紀錄
- 多商品掃描與排名
- 策略研究歷史
- 多模型決策
- Walk-forward 驗證
- Colab 備援

## 每天使用

完成 GitHub Actions 與 LINE Secrets 設定後，不需要開桌機。

系統會在台灣時間週一至週五 14:35 自動執行。

## 交易狀態

在 `data/manual/trades.csv` 填入真實成交：

```csv
trade_id,date,side,shares,price,note
1,2026-07-30,BUY,1000,28.00,第一筆
```

系統會更新：

- `reports/position_state.json`
- 未實現損益
- 已實現損益
- 平均成本
- 目前股數

## 多商品排名

自動輸出：

`reports/universe_ranking.csv`

目前包含：

- 00631L
- 00675L
- 0050
- 2330
- 00673R
- 00981A
- 00982A

## 策略研究

每日保留前 20 名策略至：

`reports/strategy_research_log.csv`
