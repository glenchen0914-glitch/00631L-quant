from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import pandas as pd
import yfinance as yf

UNIVERSE = {
    "00631L": "00631L.TW",
    "00675L": "00675L.TW",
    "0050": "0050.TW",
    "2330": "2330.TW",
    "00673R": "00673R.TW",
    "00981A": "00981A.TW",
    "00982A": "00982A.TW",
}

def _score_one(symbol: str) -> dict:
    x = yf.download(symbol, period="2y", auto_adjust=False, progress=False, threads=False)
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = [c[0] for c in x.columns]
    if x.empty or len(x) < 80:
        return {"status": "資料不足", "score": None}
    close = x["Close"].dropna()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ret20 = close.pct_change(20)
    vol20 = close.pct_change().rolling(20).std() * np.sqrt(252)
    score = 50
    score += 15 if close.iloc[-1] > ma20.iloc[-1] else -15
    score += 15 if ma20.iloc[-1] > ma60.iloc[-1] else -15
    score += 10 if ret20.iloc[-1] > 0 else -10
    score -= min(10, max(0, (vol20.iloc[-1] - 0.25) * 30))
    return {
        "status": "正常",
        "score": int(round(max(0, min(100, score)))),
        "close": float(close.iloc[-1]),
        "ret20": float(ret20.iloc[-1]),
        "vol20": float(vol20.iloc[-1]),
    }

def scan_universe(output: str = "reports/universe_ranking.csv") -> pd.DataFrame:
    rows = []
    for name, symbol in UNIVERSE.items():
        try:
            row = _score_one(symbol)
        except Exception as exc:
            row = {"status": f"失敗：{exc}", "score": None}
        row.update({"name": name, "symbol": symbol})
        rows.append(row)
    df = pd.DataFrame(rows)
    if "score" in df:
        df = df.sort_values("score", ascending=False, na_position="last")
    p = Path(output)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    return df

if __name__ == "__main__":
    print(scan_universe())
