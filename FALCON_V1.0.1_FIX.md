# Falcon v1.0.1 架構修正版

## 修正目的

07:00 盤前流程不再依賴前一日 14:35 產生的 `features_*.parquet`。

## 主要修正

1. 新增 `src/falcon_data.py`：
   - 特徵檔存在且完整時直接讀取。
   - 缺檔、空檔、損壞或欄位不完整時，自動下載行情、重算指標並寫回 parquet。
   - 00631L 與 00981A 各自獨立修復。
2. 新增 `falcon_doctor.py`：執行前檢查 Python、套件、資料夾寫入權限與 LINE Secrets。
3. 修正盤前輸出路徑，與 workflow 驗收一致：
   - `reports/morning/morning_summary.json`
   - `reports/morning/00631L_morning.json`
   - `reports/morning/00981A_morning.json`
   - `reports/morning/line_messages.json`
4. 保留舊報告路徑，維持向後相容。
5. 本版不改變 Gate、Scoring、Position、Risk 等交易策略規則。

## 部署

打開壓縮檔內的 `Falcon-v1.0.1`，將內部全部內容覆蓋到 GitHub 專案根目錄，Commit 並 Push。之後手動執行 `00631L + 00981A 07AM Premarket`。
