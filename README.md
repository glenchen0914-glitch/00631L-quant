# 00631L Quant V4.5

手機版＋GitHub Actions 自動版。

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

第一次使用 Colab，要把第一格的 `GITHUB_USER` 改成你的 GitHub 帳號。

## 自動排程

`.github/workflows/daily.yml` 預設在週一至週五台灣時間 07:30 執行。

GitHub Actions 使用 UTC，因此 cron 為：

`30 23 * * 1-5`

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