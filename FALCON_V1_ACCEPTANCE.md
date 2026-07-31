# Falcon v1.0 驗收結果

## 已完成

- Gate 一票否決與倉位上限：完成。
- Trend／Pullback／Momentum 三因子評分：完成。
- 0／20／60／100 階梯倉位與遲滯：完成。
- Gap 防追價規則：完成。
- ATR 初始停損與移動停利：完成。
- 14:35 流程改由 `run_falcon_close.py` 執行：完成。
- 07:00 流程改由 `run_falcon_morning.py` 執行並保留 LINE 推播：完成。
- 舊 V18 決策保留作對照，避免破壞既有系統：完成。

## 測試

通過：

- Falcon 一票否決、黑天鵝封鎖、Gap等待、階梯倉位、ATR風控。
- 原 V18 盤前核心測試。
- 原雙標的核心測試。

集中測試結果：`4 passed`。

完整舊測試套件因包含較重的最佳化測試，在本次執行環境超過時間限制；未宣稱完整套件全部通過。GitHub Actions 上線後仍應手動 Run workflow 做一次正式驗收。

## 尚未包含

- 自動經濟日曆；目前可用 `FALCON_EVENTS` 輸入重大事件。
- 09:00～13:30 Event Engine；排定 Falcon v1.1。
- 參數最佳化、樣本外與 Walk-forward；排定 Falcon v2.0。
- 券商即時行情；排定 Falcon v3.0。
