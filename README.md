# Falcon Trading OS v1 (MVP)

為 **00631L** 與 **00981A** 建立的短線波段交易作業系統。

## 已完成
- yfinance 行情下載與 SQLite 儲存
- SMA、MACD、KD、ATR、量能比
- Data Quality、Market、Entry、Position、Exit、Trade Phase、Checklist
- LINE Command Card、Decision Journal
- GitHub Actions 台灣時間交易日 07:00 執行
- 基本單元測試

## 執行
```bash
pip install -r requirements.txt
python main.py --no-line
pytest -q
```

## LINE Secrets
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_USER_ID`

正式使用前須先回測與模擬交易。yfinance 適合個人研究，正式交易宜更換授權行情來源。
