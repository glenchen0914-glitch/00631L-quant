# Falcon v1.0 實作說明

本版由既有 V18 專案升級，保留舊報告作為對照，但新增獨立的 Falcon 決策層，避免直接破壞既有穩定流程。

## 新增檔案

- `src/falcon_engine.py`：Gate、三因子評分、階梯倉位、Gap 執行規則、ATR 風控。
- `src/falcon_runner.py`：先執行既有雙標的資料流程，再產生 Falcon 報告。
- `run_falcon_close.py`：Falcon 收盤入口。
- `tests/test_falcon_engine.py`：一票否決、Gap、階梯倉位、ATR 測試。
- `FALCON_ARCHITECTURE_FREEZE.md`：架構凍結與變更管理。

## 輸出

- `reports/falcon_decision.json`（00631L）
- `reports/00981A/falcon_decision.json`
- `reports/falcon_summary.json`

## 可選環境變數

- `FALCON_EVENTS=CPI,FOMC`
- `FALCON_VIX_LEVEL=23.5`
- `FALCON_VIX_CHANGE_PCT=9.2`
- `FALCON_00631L_GAP_PCT=2.8`
- `FALCON_00981A_GAP_PCT=1.6`

重大事件日若尚未接上自動經濟日曆，可先在 GitHub Actions 手動輸入或透過 repository variable 設定。
