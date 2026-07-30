# 00631L Quant V4.5.1

手機版＋GitHub Actions 自動版（首次執行修正版）。

## 功能

- 自動下載 00631L、大盤與國際市場資料
- 建立 SQLite
- 自動回測大量策略
- 策略排行榜
- 每日決策卡
- 落底進度 0～100%
- 波段追蹤表
- GitHub Actions 交易日早上 07:30（台灣時間）自動執行
- Colab 手機一鍵重跑

## GitHub 上傳後

開啟：

`notebooks/00631L_Colab_V4_5.ipynb`

再按 `Open in Colab`。

Notebook 已預設 GitHub 帳號 `glenchen0914-glitch`，通常不需要再修改。

## 自動排程

`.github/workflows/daily.yml` 預設在週一至週五台灣時間 07:30 執行。

GitHub Actions 使用 UTC，因此 cron 為：

`30 23 * * 0-4`

## 手動資料

可編輯：

`data/manual/manual_inputs.csv`

欄位包含：

- 外資台指期淨未平倉
- 融資增減
- 融資維持率
- 台指夜盤漲跌幅
- 重大事件風險分數
- 重大事件備註

沒有可靠資料時可留空，系統不會假裝已取得。

## V4.5.1 修正

- 修正 Open in Colab 連結中的 `USERNAME`。
- 預設填入 GitHub 帳號。
- 修正台灣時區的 GitHub Actions 星期設定。
- 避免把 SQLite、Parquet 與 Python 快取提交到 GitHub。
- 只提交每日報告與追蹤結果。
