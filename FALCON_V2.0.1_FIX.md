# Falcon v2.0.1 修正說明

本版修正兩項部署問題：

1. requirements.txt 補入 pytest，確保 GitHub Actions 離線測試可執行。
2. 特徵資料不再以 MA240 作為全表硬性裁切條件。新上市標的會保留 MA20、週 KD、RSI、ATR 已成熟後的歷史列，避免 00981A 雖有約 297 筆行情，卻只剩 58 筆特徵資料。

策略、Gate、倉位與風控規則均未變更。
