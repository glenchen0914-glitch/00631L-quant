# 00631L Quant V6.0 Final

這是凍結規格的最終版。除非發現實際錯誤或資料來源失效，不再以小版本持續改動。

## 核心功能

- 00631L、台股與國際市場資料品質檢查
- 技術面、落底進度與市場環境評分
- Top 5 策略投票
- Logistic Regression＋Random Forest 多模型共識
- 樣本內、樣本外與 Walk-forward 檢查
- 三段價位、停止加碼與防守線
- 支持進場、反對進場與缺少確認訊號
- 決策信心等級 A／B／C／D
- 手機版 HTML 儀表板
- GitHub Actions 自動執行
- 執行正式流程前先跑離線測試

## 最終 Notebook

`notebooks/00631L_Colab_V6_0_Final.ipynb`

## 已知限制

- Yahoo Finance 可能有延遲、缺漏或暫時無法下載。
- 外資期貨、融資維持率、夜盤及重大事件若沒有可靠來源，必須手動補入。
- 模型與回測只能作為決策輔助，不保證未來績效。

## 最終驗收修正

- 修正 `optimize()` 中誤用未定義變數 `x` 的錯誤。
- Walk-forward 改為只對候選策略執行，避免每日執行時間不合理增加。
- Colab 現在會顯示 `run_pipeline.py` 真正的 stdout／stderr。
- 新增完整策略最佳化測試，實際執行策略產生、回測、排名及 Walk-forward。
