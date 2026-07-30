from __future__ import annotations
from dataclasses import dataclass, asdict
from itertools import product
from pathlib import Path
import json, math, sqlite3
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from .config import Config

def download_one(symbol: str, start: str) -> pd.DataFrame:
    x = yf.download(symbol, start=start, auto_adjust=False, progress=False, threads=False)
    if isinstance(x.columns, pd.MultiIndex):
        x.columns = [c[0] for c in x.columns]
    if x.empty:
        raise RuntimeError(f"{symbol} 無資料")
    if "Adj Close" not in x.columns:
        x["Adj Close"] = x["Close"]
    if "Volume" not in x.columns:
        x["Volume"] = 0
    x.index = pd.to_datetime(x.index).tz_localize(None)
    return x[["Open","High","Low","Close","Adj Close","Volume"]].dropna(subset=["Close"])

def download_all(cfg: Config) -> dict[str, pd.DataFrame]:
    data, errors = {}, {}
    for name, symbol in cfg.symbols.items():
        try:
            data[name] = download_one(symbol, cfg.start)
            print(f"✅ {name}: {len(data[name])} 筆")
        except Exception as exc:
            errors[name] = str(exc)
            print(f"⚠️ {name}: {exc}")
    if "etf" not in data:
        raise RuntimeError(f"00631L 核心資料下載失敗：{errors}")
    return data

def build_db(data: dict[str, pd.DataFrame], cfg: Config) -> None:
    Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cfg.db_path) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS prices(
            date TEXT NOT NULL, name TEXT NOT NULL, symbol TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL,
            PRIMARY KEY(date, name)
        )""")
        for name, x in data.items():
            rows = x.reset_index().rename(columns={
                "Date":"date","Open":"open","High":"high","Low":"low",
                "Close":"close","Adj Close":"adj_close","Volume":"volume"
            })
            rows["date"] = pd.to_datetime(rows["date"]).dt.strftime("%Y-%m-%d")
            rows["name"] = name
            rows["symbol"] = cfg.symbols[name]
            cols = ["date","name","symbol","open","high","low","close","adj_close","volume"]
            con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?,?,?,?,?,?)",
                            rows[cols].itertuples(index=False, name=None))

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100/(1+rs)

def stochastic_kd(high, low, close, n=9):
    ll, hh = low.rolling(n).min(), high.rolling(n).max()
    rsv = 100*(close-ll)/(hh-ll).replace(0,np.nan)
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()
    return k,d

def build_features(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = data["etf"].rename(columns=str.lower).copy()
    for n in [5,10,20,60,120,240]:
        df[f"ma{n}"] = df["close"].rolling(n).mean()
    df["rsi14"] = rsi(df["close"])
    df["k"],df["d"] = stochastic_kd(df["high"],df["low"],df["close"])
    fast = df["close"].ewm(span=12,adjust=False).mean()
    slow = df["close"].ewm(span=26,adjust=False).mean()
    df["dif"] = fast-slow
    df["dea"] = df["dif"].ewm(span=9,adjust=False).mean()
    df["macd_hist"] = df["dif"]-df["dea"]
    prev = df["close"].shift(1)
    tr = pd.concat([(df["high"]-df["low"]),(df["high"]-prev).abs(),(df["low"]-prev).abs()],axis=1).max(axis=1)
    df["atr14"] = tr.ewm(alpha=1/14,adjust=False).mean()
    mid = df["close"].rolling(20).mean()
    sd = df["close"].rolling(20).std()
    df["bb_mid"],df["bb_up"],df["bb_low"] = mid,mid+2*sd,mid-2*sd
    weekly = df[["high","low","close"]].resample("W-FRI").agg({"high":"max","low":"min","close":"last"})
    wk,wd = stochastic_kd(weekly["high"],weekly["low"],weekly["close"])
    df["week_k"] = wk.reindex(df.index, method="ffill")
    df["week_d"] = wd.reindex(df.index, method="ffill")
    for name,x in data.items():
        if name == "etf": continue
        y = x.copy()
        y[f"{name}_ma20"] = y["Adj Close"].rolling(20).mean()
        y[f"{name}_above_ma20"] = y["Adj Close"] > y[f"{name}_ma20"]
        y[f"{name}_ret1"] = y["Adj Close"].pct_change()
        df = df.join(y[[f"{name}_above_ma20",f"{name}_ret1"]], how="left")
    cols = [c for c in df.columns if "_above_ma20" in c or "_ret1" in c]
    df[cols] = df[cols].ffill()
    return df.dropna(subset=["ma240","week_k","rsi14"]).copy()


def add_ml_features(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["ret1"] = x["close"].pct_change()
    x["ret5"] = x["close"].pct_change(5)
    x["ret20"] = x["close"].pct_change(20)
    x["vol20"] = x["ret1"].rolling(20).std() * np.sqrt(252)
    x["ma5_gap"] = x["close"] / x["ma5"] - 1
    x["ma20_gap"] = x["close"] / x["ma20"] - 1
    x["ma60_gap"] = x["close"] / x["ma60"] - 1
    x["bb_pos"] = (x["close"] - x["bb_low"]) / (x["bb_up"] - x["bb_low"]).replace(0, np.nan)
    x["atr_pct"] = x["atr14"] / x["close"]
    x["kd_gap"] = x["k"] - x["d"]
    x["week_kd_gap"] = x["week_k"] - x["week_d"]

    for name in ["twii","nasdaq","sox","sp500","vix","dxy","us10y","tsm_adr"]:
        ret_col = f"{name}_ret1"
        if ret_col not in x:
            x[ret_col] = np.nan

    # 預測未來5日是否上漲超過2%，只作為輔助訊號
    x["target_5d"] = ((x["close"].shift(-5) / x["close"] - 1) > 0.02).astype(int)
    return x

ML_FEATURES = [
    "rsi14","k","d","week_k","week_d","macd_hist","ma5_gap","ma20_gap","ma60_gap",
    "bb_pos","atr_pct","ret1","ret5","ret20","vol20","kd_gap","week_kd_gap",
    "twii_ret1","nasdaq_ret1","sox_ret1","sp500_ret1","vix_ret1","dxy_ret1",
    "us10y_ret1","tsm_adr_ret1"
]

def train_ml_model(df: pd.DataFrame) -> dict:
    x = add_ml_features(df).replace([np.inf,-np.inf], np.nan)
    model_df = x.dropna(subset=ML_FEATURES + ["target_5d"]).copy()
    if len(model_df) < 500:
        return {"probability": None, "auc": None, "confidence": "不足", "note": "可用資料不足500筆"}

    X = model_df[ML_FEATURES]
    y = model_df["target_5d"].astype(int)
    tscv = TimeSeriesSplit(n_splits=5)

    aucs = []
    last_model = None
    for train_idx, test_idx in tscv.split(X):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        if y_train.nunique() < 2 or y_test.nunique() < 2:
            continue
        model = RandomForestClassifier(
            n_estimators=300, max_depth=5, min_samples_leaf=12,
            class_weight="balanced", random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)
        pred = model.predict_proba(X_test)[:,1]
        aucs.append(roc_auc_score(y_test, pred))
        last_model = model

    if last_model is None:
        return {"probability": None, "auc": None, "confidence": "不足", "note": "時間切分後類別不足"}

    last_model.fit(X, y)
    latest = x[ML_FEATURES].iloc[[-1]]
    if latest.isna().any(axis=None):
        return {"probability": None, "auc": float(np.mean(aucs)) if aucs else None,
                "confidence": "不足", "note": "最新一日仍有缺值"}

    prob = float(last_model.predict_proba(latest)[:,1][0])
    auc = float(np.mean(aucs)) if aucs else None
    if auc is None:
        confidence = "不足"
    elif auc >= 0.60:
        confidence = "中"
    elif auc >= 0.55:
        confidence = "偏低"
    else:
        confidence = "很低"

    return {
        "probability": prob,
        "auc": auc,
        "confidence": confidence,
        "note": "機器學習只作為輔助，不單獨決定交易"
    }

def market_regime_score(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    parts = {}
    weights = {"台股趨勢":20,"NASDAQ":15,"SOX":20,"S&P500":10,"台積電ADR":15,"VIX":10,"美元":5,"美債殖利率":5}

    def trend_points(name, weight):
        above = last.get(f"{name}_above_ma20", np.nan)
        ret = last.get(f"{name}_ret1", np.nan)
        if pd.isna(above):
            return None
        base = weight * (0.75 if bool(above) else 0.25)
        if pd.notna(ret):
            base += weight * (0.15 if float(ret) > 0 else -0.15)
        return int(round(max(0, min(weight, base))))

    parts["台股趨勢"] = trend_points("twii",20)
    parts["NASDAQ"] = trend_points("nasdaq",15)
    parts["SOX"] = trend_points("sox",20)
    parts["S&P500"] = trend_points("sp500",10)
    parts["台積電ADR"] = trend_points("tsm_adr",15)

    vix_ret = last.get("vix_ret1", np.nan)
    parts["VIX"] = None if pd.isna(vix_ret) else (10 if float(vix_ret) <= -0.02 else 7 if float(vix_ret) <= 0 else 4 if float(vix_ret) < 0.03 else 0)
    dxy_ret = last.get("dxy_ret1", np.nan)
    parts["美元"] = None if pd.isna(dxy_ret) else (5 if float(dxy_ret) <= 0 else 2)
    us10y_ret = last.get("us10y_ret1", np.nan)
    parts["美債殖利率"] = None if pd.isna(us10y_ret) else (5 if float(us10y_ret) <= 0 else 2)

    available = {k:v for k,v in parts.items() if v is not None}
    max_score = sum(weights[k] for k in available)
    raw = sum(available.values())
    score = int(round(100 * raw / max_score)) if max_score else 0
    label = "偏多" if score >= 75 else "中性偏多" if score >= 60 else "中性" if score >= 45 else "中性偏空" if score >= 30 else "偏空"
    return {"score": score, "label": label, "parts": parts, "max_score": max_score}

def bottom_progress_breakdown(df: pd.DataFrame, manual: dict) -> dict:
    last = df.iloc[-1]
    items = {}

    wk = float(last["week_k"])
    items["周KD"] = 100 if wk < 20 else 70 if wk < 30 else 40 if wk < 40 else 10

    rsi_v = float(last["rsi14"])
    items["RSI"] = 100 if rsi_v < 30 else 70 if rsi_v < 40 else 30 if rsi_v < 50 else 10

    items["日KD"] = 80 if float(last["k"]) > float(last["d"]) else 20
    items["MACD"] = 80 if float(last["macd_hist"]) > float(df["macd_hist"].iloc[-2]) else 20

    close = float(last["close"])
    ma20 = float(last["ma20"])
    ma60 = float(last["ma60"])
    items["均線"] = 80 if close > ma20 else 50 if close > ma60 else 20

    vol20 = float(df["close"].pct_change().rolling(20).std().iloc[-1] * np.sqrt(252))
    items["波動"] = 70 if vol20 > 0.45 else 50 if vol20 > 0.30 else 30

    margin_change = manual.get("margin_change")
    margin_available = margin_change is not None and pd.notna(margin_change)
    if margin_available:
        items["融資"] = 70 if float(margin_change) < 0 else 30
        margin_status = "已提供"
    else:
        items["融資"] = None
        margin_status = "資料未提供"

    regime = market_regime_score(df)
    items["市場環境"] = regime["score"]

    weights = {"周KD":0.18,"RSI":0.12,"日KD":0.10,"MACD":0.12,"均線":0.14,
               "波動":0.08,"融資":0.08,"市場環境":0.18}
    available = {k:v for k,v in items.items() if v is not None}
    weight_sum = sum(weights[k] for k in available)
    total = int(round(sum(available[k]*weights[k] for k in available) / weight_sum))
    return {
        "score": max(0,min(100,total)),
        "items": items,
        "data_status": {"融資": margin_status}
    }

def tiered_entry_plan(df: pd.DataFrame, levels: dict, stage: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"])
    atr = max(float(last["atr14"]), close * 0.015)
    resistance = float(levels["resistance"])
    recent_low = float(df["low"].tail(20).min())

    min_gap = max(0.50 * atr, 0.015 * close)
    first = close - 0.35 * atr
    second = min(first - min_gap, close - 0.90 * atr)
    third = min(second - min_gap, close - 1.45 * atr)

    floor_price = max(close * 0.55, 0.01)
    first = max(first, floor_price + 2 * min_gap)
    second = max(second, floor_price + min_gap)
    third = max(third, floor_price)

    if second >= first:
        second = first - min_gap
    if third >= second:
        third = second - min_gap

    stop = min(third - max(0.35 * atr, 0.01 * close),
               recent_low - 0.10 * atr)
    stop = max(0.01, stop)
    if stop >= third:
        stop = max(0.01, third - max(0.35 * atr, 0.01 * close))

    first_note = "僅觀察，尚未觸發買進" if stage == "觀察" else "第一筆試單"

    return {
        "first": float(first),
        "second": float(second),
        "third": float(third),
        "stop": float(stop),
        "first_note": first_note,
        "resistance": resistance,
        "min_gap": float(min_gap),
    }



def data_quality_report(data: dict[str, pd.DataFrame], symbols: dict[str, str]) -> dict:
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    rows = []
    required = ["etf","twii","nasdaq","sox","sp500","vix","dxy","us10y","tsm_adr"]
    for name in required:
        frame = data.get(name)
        if frame is None or frame.empty:
            rows.append({
                "name": name, "symbol": symbols.get(name), "status": "失敗",
                "latest_date": None, "delay_days": None, "rows": 0,
                "missing_close": None
            })
            continue
        latest = pd.to_datetime(frame.index.max()).tz_localize(None)
        delay = int((today - latest.normalize()).days)
        missing_close = int(frame["Close"].isna().sum()) if "Close" in frame else None
        status = "正常" if delay <= 4 else "延遲"
        rows.append({
            "name": name, "symbol": symbols.get(name), "status": status,
            "latest_date": str(latest.date()), "delay_days": delay,
            "rows": int(len(frame)), "missing_close": missing_close
        })
    complete = sum(r["status"] == "正常" for r in rows)
    score = int(round(100 * complete / len(required)))
    return {"score": score, "rows": rows}

def walk_forward_strategy_metrics(df: pd.DataFrame, s: Strategy, cfg: Config, windows: int = 4) -> dict:
    n = len(df)
    if n < 400:
        return {"windows": 0, "positive_windows": 0, "median_pf": None, "median_return": None}
    fold = max(80, n // (windows + 2))
    results = []
    for i in range(windows):
        start = max(0, n - (windows - i + 1) * fold)
        end = min(n, start + 2 * fold)
        seg = df.iloc[start:end]
        if len(seg) < 80:
            continue
        metrics, _ = backtest(seg, s, cfg)
        if metrics is not None:
            results.append(metrics)
    if not results:
        return {"windows": 0, "positive_windows": 0, "median_pf": None, "median_return": None}
    pfs = [r["profit_factor"] for r in results if np.isfinite(r["profit_factor"])]
    rets = [r["total_return"] for r in results]
    return {
        "windows": len(results),
        "positive_windows": int(sum(r > 0 for r in rets)),
        "median_pf": float(np.median(pfs)) if pfs else None,
        "median_return": float(np.median(rets)),
    }

def strategy_description(row: pd.Series) -> str:
    parts = [f"周KD<{int(row['week_k_max'])}", f"RSI<{int(row['rsi_max'])}"]
    if bool(row["require_k_cross"]): parts.append("日KD黃金交叉")
    if bool(row["require_macd_improve"]): parts.append("MACD改善")
    if bool(row["require_close_ma20"]): parts.append("站上MA20")
    if bool(row["require_twii_ma20"]): parts.append("大盤站上MA20")
    parts.append(f"停損{float(row['stop_loss']):.0%}")
    parts.append(f"停利{float(row['take_profit']):.0%}")
    parts.append(f"最長{int(row['max_hold'])}日")
    return "｜".join(parts)

def model_consensus(df: pd.DataFrame) -> dict:
    x = add_ml_features(df).replace([np.inf,-np.inf], np.nan)
    model_df = x.dropna(subset=ML_FEATURES + ["target_5d"]).copy()
    if len(model_df) < 500:
        return {"probability": None, "consensus": None, "models": [], "confidence": "不足", "note": "可用資料不足500筆"}

    X = model_df[ML_FEATURES]
    y = model_df["target_5d"].astype(int)
    latest = x[ML_FEATURES].iloc[[-1]]
    if latest.isna().any(axis=None):
        return {"probability": None, "consensus": None, "models": [], "confidence": "不足", "note": "最新資料有缺值"}

    tscv = TimeSeriesSplit(n_splits=5)
    specs = [
        ("Logistic", Pipeline([("scaler", StandardScaler()), ("model", LogisticRegression(max_iter=1500, class_weight="balanced"))])),
        ("RandomForest", RandomForestClassifier(
            n_estimators=300, max_depth=5, min_samples_leaf=12,
            class_weight="balanced", random_state=42, n_jobs=-1
        )),
    ]
    model_rows = []
    for name, model in specs:
        aucs = []
        trained = False
        for train_idx, test_idx in tscv.split(X):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            if y_train.nunique() < 2 or y_test.nunique() < 2:
                continue
            model.fit(X_train, y_train)
            pred = model.predict_proba(X_test)[:,1]
            aucs.append(roc_auc_score(y_test, pred))
            trained = True
        if not trained:
            continue
        model.fit(X, y)
        prob = float(model.predict_proba(latest)[:,1][0])
        auc = float(np.mean(aucs)) if aucs else None
        model_rows.append({"name": name, "probability": prob, "auc": auc})

    if not model_rows:
        return {"probability": None, "consensus": None, "models": [], "confidence": "不足", "note": "模型無法完成時間序列驗證"}

    valid = [m for m in model_rows if m["auc"] is not None]
    avg_prob = float(np.mean([m["probability"] for m in model_rows]))
    avg_auc = float(np.mean([m["auc"] for m in valid])) if valid else None
    consensus = float(np.mean([m["probability"] >= 0.55 for m in model_rows]))
    if avg_auc is None:
        confidence = "不足"
    elif avg_auc >= 0.62:
        confidence = "中"
    elif avg_auc >= 0.56:
        confidence = "偏低"
    else:
        confidence = "很低"
    return {
        "probability": avg_prob,
        "consensus": consensus,
        "models": model_rows,
        "auc": avg_auc,
        "confidence": confidence,
        "note": "多模型只作為輔助，不單獨決定交易"
    }

def explain_decision(decision: dict) -> dict:
    positives, negatives, missing = [], [], []
    if decision["bottom_progress_pct"] >= 60:
        positives.append("落底進度已接近布局門檻")
    else:
        negatives.append("落底進度仍不足")
    regime = decision["market_regime"]
    if regime["score"] >= 55:
        positives.append("市場環境至少中性偏多")
    else:
        negatives.append(f"市場環境為{regime['label']}")
    ensemble = decision["ensemble_signal"]["vote_ratio"]
    if ensemble >= 0.6:
        positives.append("Top 5策略多數支持")
    else:
        negatives.append("Top 5策略尚未形成多數")
    model = decision["model_consensus"]
    if model.get("probability") is not None:
        if model["probability"] >= 0.55:
            positives.append("模型共識略偏多")
        else:
            negatives.append("模型共識未達偏多門檻")
    else:
        missing.append("模型資料不足")
    if decision["data_status"].get("融資") != "已提供":
        missing.append("融資資料未提供")
    return {"positive": positives, "negative": negatives, "missing": missing}

def confidence_grade(decision: dict) -> dict:
    score = 0
    score += min(30, decision["bottom_progress_pct"] * 0.30)
    score += min(20, decision["market_regime"]["score"] * 0.20)
    score += 20 * decision["ensemble_signal"]["vote_ratio"]
    model = decision["model_consensus"]
    if model.get("probability") is not None:
        score += 15 * max(0, min(1, (model["probability"] - 0.45) / 0.20))
    score += 15 * (decision["data_quality"]["score"] / 100)
    score = int(round(score))
    grade = "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 50 else "D"
    return {"score": score, "grade": grade}


@dataclass(frozen=True)
class Strategy:
    name: str
    week_k_max: int
    rsi_max: int
    require_k_cross: bool
    require_macd_improve: bool
    require_close_ma20: bool
    require_twii_ma20: bool
    stop_loss: float
    take_profit: float
    max_hold: int

def make_strategies():
    out=[]; i=1
    for vals in product([20,30,40],[30,35,40,45],[False,True],[False,True],
                        [False,True],[False,True],[0.05,0.07,0.09],
                        [0.10,0.15,0.20],[10,20,30,40]):
        wk,rs,kx,macd,ma20,twii,sl,tp,mh = vals
        if tp <= sl: continue
        out.append(Strategy(f"S{i:05d}",wk,rs,kx,macd,ma20,twii,sl,tp,mh)); i+=1
    return out

def signal_for(x: pd.DataFrame, s: Strategy) -> pd.Series:
    sig=(x["week_k"]<s.week_k_max)&(x["rsi14"]<s.rsi_max)
    if s.require_k_cross:
        sig &= (x["k"]>x["d"])&(x["k"].shift(1)<=x["d"].shift(1))
    if s.require_macd_improve:
        sig &= x["macd_hist"]>x["macd_hist"].shift(1)
    if s.require_close_ma20:
        sig &= x["close"]>x["ma20"]
    if s.require_twii_ma20 and "twii_above_ma20" in x:
        sig &= x["twii_above_ma20"].fillna(False)
    return sig.fillna(False)

def backtest(x: pd.DataFrame, s: Strategy, cfg: Config):
    cost=(cfg.commission_rate*cfg.commission_discount+cfg.slippage_rate+
          cfg.commission_rate*cfg.commission_discount+cfg.sell_tax_rate+cfg.slippage_rate)
    sig=signal_for(x,s)
    trades=[]; i=1
    while i<len(x):
        if not bool(sig.iloc[i-1]):
            i+=1; continue
        entry_i=i; entry=float(x["open"].iloc[i])
        exit_i=min(i+s.max_hold,len(x)-1)
        exit_price=float(x["close"].iloc[exit_i]); reason="max_hold"
        for j in range(i,min(i+s.max_hold,len(x)-1)+1):
            if float(x["low"].iloc[j]) <= entry*(1-s.stop_loss):
                exit_i=j; exit_price=entry*(1-s.stop_loss); reason="stop_loss"; break
            if float(x["high"].iloc[j]) >= entry*(1+s.take_profit):
                exit_i=j; exit_price=entry*(1+s.take_profit); reason="take_profit"; break
        trades.append({"entry_date":x.index[entry_i],"exit_date":x.index[exit_i],
                       "entry":entry,"exit":exit_price,
                       "net_return":exit_price/entry-1-cost,
                       "hold_days":exit_i-entry_i+1,"reason":reason})
        i=exit_i+1
    t=pd.DataFrame(trades)
    if t.empty: return None,t
    r=t["net_return"]; eq=(1+r).cumprod(); dd=eq/eq.cummax()-1
    wins=r[r>0].sum(); losses=-r[r<0].sum()
    pf=wins/losses if losses>0 else np.inf
    years=max((t["exit_date"].iloc[-1]-t["entry_date"].iloc[0]).days/365.25,1/365.25)
    return {"trades":len(t),"win_rate":(r>0).mean(),"avg_return":r.mean(),
            "profit_factor":pf,"max_drawdown":dd.min(),
            "cagr":eq.iloc[-1]**(1/years)-1,"total_return":eq.iloc[-1]-1},t

def optimize(df: pd.DataFrame, cfg: Config):
    split=int(len(df)*cfg.train_ratio)
    train,test=df.iloc[:split],df.iloc[split:]
    rows=[]; trade_map={}
    for s in make_strategies():
        mt,_=backtest(train,s,cfg); ms,tr=backtest(test,s,cfg)
        if mt is None or ms is None: continue
        if mt["trades"]+ms["trades"]<cfg.min_total_trades or ms["trades"]<3: continue
        if not np.isfinite(mt["profit_factor"]) or not np.isfinite(ms["profit_factor"]): continue
        row=asdict(s)
        for k,v in mt.items(): row[f"{k}_train"]=v
        for k,v in ms.items(): row[f"{k}_test"]=v
        row["score"]=(2.2*min(mt["profit_factor"],ms["profit_factor"])
                      +1.5*min(ms["profit_factor"],4)
                      +2*ms["cagr"]+2*ms["max_drawdown"]
                      +0.02*min(ms["trades"],30))
        row["description"] = strategy_description(pd.Series(row))
        wf = walk_forward_strategy_metrics(x, s, cfg)
        row["wf_windows"] = wf["windows"]
        row["wf_positive_windows"] = wf["positive_windows"]
        row["wf_median_pf"] = wf["median_pf"]
        row["wf_median_return"] = wf["median_return"]
        rows.append(row); trade_map[s.name]=tr
    board=pd.DataFrame(rows)
    if board.empty: raise RuntimeError("沒有策略通過最低樣本門檻")
    board=board.sort_values(["score","profit_factor_test","max_drawdown_test"],
                            ascending=[False,False,False]).head(cfg.top_n)
    return board,{k:trade_map[k] for k in board["name"]}

def read_manual_today(path: str) -> dict:
    defaults={"foreign_futures_net_oi":None,"margin_change":None,
              "margin_maintenance_ratio":None,"tx_night_change_pct":None,
              "event_risk_score":None,"event_note":""}
    p=Path(path)
    if not p.exists(): return defaults
    x=pd.read_csv(p)
    if x.empty: return defaults
    row=x.iloc[-1].to_dict()
    defaults.update({k:row.get(k) for k in defaults})
    return defaults

def bottom_progress(df: pd.DataFrame, manual: dict) -> tuple[int,list[str]]:
    last=df.iloc[-1]; score=0; reasons=[]
    wk=float(last["week_k"])
    if wk<20: score+=25; reasons.append("周KD進入20以下布局區")
    elif wk<30: score+=16; reasons.append("周KD進入30以下觀察區")
    elif wk<40: score+=8
    distance=(float(last["close"])-float(last["bb_low"]))/max(float(last["close"]),1e-9)
    if distance<=0.02: score+=18; reasons.append("接近布林下緣支撐")
    elif distance<=0.05: score+=10
    if float(last["rsi14"])<30: score+=12; reasons.append("RSI進入超賣")
    elif float(last["rsi14"])<40: score+=7
    if float(last["k"])>float(last["d"]): score+=10; reasons.append("日KD偏多")
    if float(last["macd_hist"])>float(df["macd_hist"].iloc[-2]): score+=10; reasons.append("MACD改善")
    if bool(last.get("twii_above_ma20",False)): score+=8; reasons.append("大盤站回20日均線")
    vix_ret=float(last.get("vix_ret1",0) or 0)
    if vix_ret>0.05: score+=8; reasons.append("恐慌情緒升高")
    mc=manual.get("margin_change")
    if mc is not None and pd.notna(mc) and float(mc)<0: score+=5; reasons.append("融資下降")
    ff=manual.get("foreign_futures_net_oi")
    if ff is not None and pd.notna(ff) and float(ff)>0: score+=4; reasons.append("外資期貨淨部位偏多")
    event=manual.get("event_risk_score")
    if event is not None and pd.notna(event):
        score-=round(float(event)*0.10)
        if float(event)>=60: reasons.append("重大事件風險偏高")
    return max(0,min(100,int(round(score)))),reasons


def _nearest_levels(df: pd.DataFrame) -> dict:
    """只把目前價格下方的價位稱為支撐，上方價位稱為壓力。"""
    last = df.iloc[-1]
    close = float(last["close"])
    recent = df.tail(min(120, len(df))).copy()

    candidate_supports = {
        "10日低點": float(recent["low"].tail(10).min()),
        "20日低點": float(recent["low"].tail(20).min()),
        "60日低點": float(recent["low"].tail(60).min()),
        "MA5": float(last["ma5"]),
        "MA10": float(last["ma10"]),
        "MA20": float(last["ma20"]),
        "MA60": float(last["ma60"]),
        "布林下緣": float(last["bb_low"]),
    }
    candidate_resistances = {
        "10日高點": float(recent["high"].tail(10).max()),
        "20日高點": float(recent["high"].tail(20).max()),
        "60日高點": float(recent["high"].tail(60).max()),
        "MA5": float(last["ma5"]),
        "MA10": float(last["ma10"]),
        "MA20": float(last["ma20"]),
        "MA60": float(last["ma60"]),
        "布林中軸": float(last["bb_mid"]),
        "布林上緣": float(last["bb_up"]),
    }

    supports = [(name, value) for name, value in candidate_supports.items()
                if np.isfinite(value) and value <= close]
    resistances = [(name, value) for name, value in candidate_resistances.items()
                   if np.isfinite(value) and value >= close]

    support_name, support = (
        max(supports, key=lambda x: x[1])
        if supports else ("近期最低價", float(recent["low"].min()))
    )
    resistance_name, resistance = (
        min(resistances, key=lambda x: x[1])
        if resistances else ("近期最高價", float(recent["high"].max()))
    )

    broken_levels = sorted(
        [(name, value) for name, value in candidate_supports.items()
         if np.isfinite(value) and value > close],
        key=lambda x: x[1]
    )
    reclaim_name, reclaim = broken_levels[0] if broken_levels else (None, None)

    return {
        "support": support,
        "support_label": support_name,
        "resistance": resistance,
        "resistance_label": resistance_name,
        "reclaim_level": reclaim,
        "reclaim_label": reclaim_name,
    }

def _backtest_confidence(best: pd.Series) -> dict:
    """依樣本外交易筆數與PF穩定性標示可信度。"""
    trades = int(best["trades_test"])
    pf = float(best["profit_factor_test"])
    train_pf = float(best["profit_factor_train"])

    if trades < 5:
        level, note, score = "很低", "樣本外交易少於5筆，只能視為初步線索", 15
    elif trades < 10:
        level, note, score = "低", "樣本外交易不足10筆，PF容易被少數交易放大", 30
    elif trades < 20:
        level, note, score = "中低", "樣本外交易筆數仍偏少，需持續累積", 50
    elif trades < 40:
        level, note, score = "中", "樣本外交易筆數已有一定參考性", 70
    else:
        level, note, score = "中高", "樣本外交易筆數較充足，但仍不代表未來績效", 85

    if pf > 4:
        note += "；PF高於4，須特別防範過度擬合"
        score = max(10, score - 15)
    if abs(pf - train_pf) / max(abs(train_pf), 1e-9) > 0.75:
        note += "；樣本內外PF差異偏大"
        score = max(10, score - 15)

    return {"level": level, "score": score, "note": note, "trades": trades}



def strategy_ensemble_signal(df: pd.DataFrame, board: pd.DataFrame, top_n: int = 5) -> dict:
    top = board.head(min(top_n, len(board)))
    votes = []
    names = []
    for _, row in top.iterrows():
        s=Strategy(row["name"],int(row["week_k_max"]),int(row["rsi_max"]),
                   bool(row["require_k_cross"]),bool(row["require_macd_improve"]),
                   bool(row["require_close_ma20"]),bool(row["require_twii_ma20"]),
                   float(row["stop_loss"]),float(row["take_profit"]),int(row["max_hold"]))
        sig = bool(signal_for(df, s).iloc[-1])
        votes.append(1 if sig else 0)
        names.append({"name": s.name, "signal": sig, "score": float(row["score"])})
    ratio = sum(votes)/len(votes) if votes else 0
    return {"vote_ratio": ratio, "members": names}


def make_decision(df: pd.DataFrame, board: pd.DataFrame, manual: dict, data_quality: dict | None = None):
    best=board.iloc[0]
    s=Strategy(best["name"],int(best["week_k_max"]),int(best["rsi_max"]),
               bool(best["require_k_cross"]),bool(best["require_macd_improve"]),
               bool(best["require_close_ma20"]),bool(best["require_twii_ma20"]),
               float(best["stop_loss"]),float(best["take_profit"]),int(best["max_hold"]))

    levels=_nearest_levels(df)
    confidence=_backtest_confidence(best)
    regime=market_regime_score(df)
    breakdown=bottom_progress_breakdown(df,manual)
    ml=train_ml_model(df)
    models=model_consensus(df)
    ensemble=strategy_ensemble_signal(df,board,top_n=5)

    last=df.iloc[-1]
    close=float(last["close"])
    progress=breakdown["score"]
    k_cross=bool(last["k"]>last["d"] and df["k"].iloc[-2]<=df["d"].iloc[-2])
    macd_up=bool(last["macd_hist"]>df["macd_hist"].iloc[-2])
    above_ma20=bool(last["close"]>last["ma20"])

    ml_prob = ml["probability"] if ml["probability"] is not None else 0.5
    ensemble_ratio = ensemble["vote_ratio"]

    # V5 綜合決策：落底進度、環境、策略投票、ML輔助共同決定
    if progress >= 78 and regime["score"] >= 65 and ensemble_ratio >= 0.8 and ml_prob >= 0.60 and above_ma20:
        stage="加碼"; position=50
        action="多項訊號共振，可提高至50%持股"
    elif progress >= 70 and regime["score"] >= 55 and ensemble_ratio >= 0.6 and ml_prob >= 0.55:
        stage="布局"; position=20
        action="條件初步確認，可建立20%試單"
    elif progress >= 45:
        stage="觀察"; position=0
        action="接近布局區，但仍等待確認"
    else:
        stage="觀察"; position=0
        action="不進場，維持0%"

    plan=tiered_entry_plan(df,levels,stage)

    payload = {
        "version":"V6.0 Final",
        "data_date":str(df.index[-1].date()),
        "strategy":s.name,
        "stage":stage,
        "action":action,
        "suggested_position_pct":position,
        "bottom_progress_pct":progress,
        "bottom_breakdown":breakdown["items"],
        "data_status":breakdown["data_status"],
        "reference_close":close,
        "entry_plan":plan,
        "support":float(levels["support"]),
        "support_label":levels["support_label"],
        "resistance":float(levels["resistance"]),
        "resistance_label":levels["resistance_label"],
        "reclaim_level":None if levels["reclaim_level"] is None else float(levels["reclaim_level"]),
        "reclaim_label":levels["reclaim_label"],
        "week_k":float(last["week_k"]),
        "daily_k":float(last["k"]),
        "daily_d":float(last["d"]),
        "macd_improving":macd_up,
        "above_ma20":above_ma20,
        "market_regime":regime,
        "ml_signal":ml,
        "model_consensus":models,
        "ensemble_signal":ensemble,
        "manual_inputs":manual,
        "backtest_confidence":confidence,
        "data_quality":data_quality or {"score":0,"rows":[]},
        "out_of_sample":{
            "trades":int(best["trades_test"]),
            "win_rate":float(best["win_rate_test"]),
            "profit_factor":float(best["profit_factor_test"]),
            "avg_return":float(best["avg_return_test"]),
            "max_drawdown":float(best["max_drawdown_test"]),
            "cagr":float(best["cagr_test"])
        }
    }
    payload["decision_explanation"] = explain_decision(payload)
    payload["confidence_grade"] = confidence_grade(payload)
    return payload

def save_outputs(df, board, trades, decision, cfg: Config):
    out=Path(cfg.reports_dir); out.mkdir(parents=True, exist_ok=True)
    board.to_csv(out/"strategy_leaderboard.csv",index=False)
    for name,t in trades.items():
        t.to_csv(out/f"trades_{name}.csv",index=False)
    (out/"daily_decision.json").write_text(json.dumps(decision,ensure_ascii=False,indent=2),encoding="utf-8")
    track_path=out/"wave_tracking.csv"
    row=pd.DataFrame([{
        "date":decision["data_date"],
        "bottom_progress_pct":decision["bottom_progress_pct"],
        "stage":decision["stage"],
        "suggested_position_pct":decision["suggested_position_pct"],
        "action":decision["action"]
    }])
    if track_path.exists():
        old=pd.read_csv(track_path)
        old=old[old["date"]!=decision["data_date"]]
        row=pd.concat([old,row],ignore_index=True)
    row.to_csv(track_path,index=False)
    reclaim_text = (
        f"<p>待收復：{decision['reclaim_label']} {decision['reclaim_level']:.2f}</p>"
        if decision.get("reclaim_level") is not None else ""
    )
    confidence = decision["backtest_confidence"]
    regime = decision["market_regime"]
    models = decision["model_consensus"]
    model_rows = "".join(
        f"<li>{m['name']}：上漲機率 {m['probability']:.1%}｜AUC {m['auc']:.3f}</li>"
        for m in models.get("models", [])
    ) or "<li>資料不足</li>"
    bars = "".join(
        (
            f"<div style='margin:8px 0'><div>{k}：資料未提供</div><div style='background:#eee;border-radius:10px;height:10px'></div></div>"
            if v is None else
            f"<div style='margin:8px 0'><div>{k}：{v}%</div><div style='background:#eee;border-radius:10px;height:10px'><div style='width:{v}%;background:#555;height:10px;border-radius:10px'></div></div></div>"
        )
        for k,v in decision["bottom_breakdown"].items()
    )
    market_rows = "".join(
        f"<li>{k}：{'資料未提供' if v is None else str(v)+'分'}</li>"
        for k,v in regime["parts"].items()
    )
    explain = decision["decision_explanation"]
    pos = "".join(f"<li>{x}</li>" for x in explain["positive"]) or "<li>目前沒有明確支持理由</li>"
    neg = "".join(f"<li>{x}</li>" for x in explain["negative"]) or "<li>目前沒有主要反對理由</li>"
    missing = "".join(f"<li>{x}</li>" for x in explain["missing"]) or "<li>主要資料齊全</li>"
    plan = decision["entry_plan"]
    grade = decision["confidence_grade"]
    html=f"""<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <div style="max-width:680px;margin:20px auto;padding:22px;border-radius:18px;box-shadow:0 4px 18px #bbb;font-family:-apple-system;line-height:1.55">
    <h2>00631L 每日決策 V6.0 Final</h2><p>資料截止：{decision['data_date']}</p>
    <h1>{decision['action']}</h1>
    <p>決策信心：<b>{grade['grade']}級（{grade['score']}/100）</b>｜資料完整度：{decision['data_quality']['score']}/100</p>
    <p>落底進度：<b>{decision['bottom_progress_pct']}%</b>｜市場環境：<b>{regime['label']} {regime['score']}/100</b></p>
    <p>階段：{decision['stage']}｜建議持股：{decision['suggested_position_pct']}%</p>
    <p>參考收盤：{decision['reference_close']:.2f}</p>

    <hr><h3>分批價位與風險</h3>
    <p>第一筆：{plan['first']:.2f}（{plan['first_note']}）</p>
    <p>第二筆：{plan['second']:.2f}</p>
    <p>第三筆：{plan['third']:.2f}</p>
    <p>停止加碼／防守線：{plan['stop']:.2f}</p>
    <p>下方支撐：{decision['support_label']} {decision['support']:.2f}</p>
    <p>上方壓力：{decision['resistance_label']} {decision['resistance']:.2f}</p>
    {reclaim_text}

    <hr><h3>支持進場理由</h3><ul>{pos}</ul>
    <h3>反對進場理由</h3><ul>{neg}</ul>
    <h3>缺少的資料或確認</h3><ul>{missing}</ul>

    <hr><h3>落底進度拆解</h3>{bars}
    <hr><h3>市場環境拆解</h3><ul>{market_rows}</ul>

    <hr><h3>策略與模型共識</h3>
    <p>Top 5策略投票：{decision['ensemble_signal']['vote_ratio']:.0%}</p>
    <ul>{model_rows}</ul>
    <p>多模型平均上漲機率：{'資料不足' if models.get('probability') is None else f"{models['probability']:.1%}"}</p>
    <p>樣本外交易：{decision['out_of_sample']['trades']}筆｜勝率：{decision['out_of_sample']['win_rate']:.1%}｜PF：{decision['out_of_sample']['profit_factor']:.2f}</p>
    <p>回測可信度：<b>{confidence['level']}</b>（{confidence['score']}/100）</p>
    <p style='font-size:14px;color:#9a5a00'>{confidence['note']}</p>
    <p style='color:#777'>模型與回測只作為輔助；歷史績效不保證未來結果。</p></div>"""
    (out/"dashboard.html").write_text(html,encoding="utf-8")

def run():
    cfg=Config()
    data=download_all(cfg)
    quality=data_quality_report(data,cfg.symbols)
    build_db(data,cfg)
    feat=build_features(data)
    Path("data").mkdir(exist_ok=True)
    feat.to_parquet("data/features.parquet")
    board,trades=optimize(feat,cfg)
    manual=read_manual_today("data/manual/manual_inputs.csv")
    decision=make_decision(feat,board,manual,quality)
    save_outputs(feat,board,trades,decision,cfg)
    print(json.dumps(decision,ensure_ascii=False,indent=2))

if __name__=="__main__":
    run()