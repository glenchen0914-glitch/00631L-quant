# 00631L Quant V3

手機優先的 00631L（元大台灣50正2）量化研究專案。

## 手機使用方式

1. 將本專案內容上傳到 GitHub Repository。
2. 點開 `notebooks/00631L_Colab_V3.ipynb`。
3. 點 `Open in Colab`。
4. 在 Colab 選單按「執行階段」→「全部執行」。
5. 結果會顯示在 Notebook 最下方，並可存入 Google Drive。

## 功能

- 下載 00631L、台灣加權指數、NASDAQ、SOX、S&P 500、VIX、美元指數、美國10年債殖利率、台積電 ADR
- 建立本地 SQLite 資料庫
- 計算 MA、RSI、KD、周KD、MACD、ATR、布林通道
- 自動產生並回測大量策略
- 使用時間切分的樣本內／樣本外測試
- 扣除手續費、交易稅與滑價
- 輸出最佳策略排行榜
- 產生手機版每日決策卡
- 輸出 CSV、JSON 與 HTML 報告

## 重要提醒

歷史回測不保證未來績效。正式實盤前應進行 walk-forward、參數穩健性與紙上交易驗證。