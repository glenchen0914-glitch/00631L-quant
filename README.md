# 00631L Quant V10 Auto Final

這是全自動最終版。

## 日常使用

完成首次設定後：

- 不需要每天開桌機
- 不需要每天進入 GitHub
- 不需要每天執行 Colab
- GitHub Actions 會在台灣時間週一至週五 14:35 自動執行
- 成功後更新 Repository 的報告
- 設定 LINE Secrets 後會自動推播

## 自動流程

1. 安裝套件
2. 語法檢查
3. 離線煙霧測試
4. 多市場情境測試
5. 完整最佳化器測試
6. 下載真實行情
7. 執行回測、Walk-forward 與模型
8. 產生每日決策
9. 更新決策歷史
10. LINE 推播
11. 驗證輸出
12. 上傳 Artifact
13. 只有全部成功才 Commit 報告

## 主要報告

- `reports/README.md`
- `reports/dashboard.html`
- `reports/daily_decision.json`
- `reports/strategy_leaderboard.csv`
- `reports/wave_tracking.csv`
- `reports/decision_history.csv`

## 手動版本

`notebooks/00631L_Colab_V10_Auto_Final.ipynb`

## LINE Secrets

- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_USER_ID`

沒有設定 LINE Secrets 時，自動分析仍會正常執行，只跳過 LINE 推播。
