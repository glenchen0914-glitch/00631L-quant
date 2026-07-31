# Falcon v1.0.2 修正說明

## 修正項目

14:35 `daily.yml` 原本只產生、驗證、上傳與提交報告，沒有呼叫 LINE 通知模組，因此 GitHub Actions 顯示成功但手機不會收到訊息。

本版在輸出驗證完成後新增：

- `Push LINE close report`
- 使用既有 `src.notify` 發送 00631L 與 00981A 兩則收盤決策
- `LINE_PUSH_REQUIRED=true`，若 Secrets 缺失或 LINE API 發送失敗，workflow 會明確失敗，避免假成功

## 未變更項目

- 07:00 盤前流程
- Falcon 策略核心
- 14:35 分析與報告內容
- 既有 GitHub 排程
