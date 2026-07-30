from __future__ import annotations
from dataclasses import dataclass, asdict
from itertools import product
from pathlib import Path
import json, math, sqlite3
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
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
    parts["台股趨勢"] = 20 if bool(last.get("twii_above_ma20", False)) else 0
    parts["NASDAQ"] = 15 if bool(last.get("nasdaq_above_ma20", False)) else 0
    parts["SOX"] = 20 if bool(last.get("sox_above_ma20", False)) else 0
    parts["S&P500"] = 10 if bool(last.get("sp500_above_ma20", False)) else 0
    parts["台積電ADR"] = 15 if bool(last.get("tsm_adr_above_ma20", False)) else 0

    vix_ret = float(last.get("vix_ret1", 0) or 0)
    parts["VIX"] = 10 if vix_ret <= 0 else (5 if vix_ret < 0.03 else 0)

    dxy_ret = float(last.get("dxy_ret1", 0) or 0)
    parts["美元"] = 5 if dxy_ret <= 0 else 0

    us10y_ret = float(last.get("us10y_ret1", 0) or 0)
    parts["美債殖利率"] = 5 if us10y_ret <= 0 else 0

    score = int(sum(parts.values()))
    if score >= 75:
        label = "偏多"
    elif score >= 55:
        label = "中性偏多"
    elif score >= 40:
        label = "中性"
    elif score >= 25:
        label = "中性偏空"
    else:
        label = "偏空"
    return {"score": score, "label": label, "parts": parts}

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
    items["融資"] = 70 if margin_change is not None and pd.notna(margin_change) and float(margin_change) < 0 else 30

    regime = market_regime_score(df)
    items["市場環境"] = regime["score"]

    weights = {"周KD":0.18,"RSI":0.12,"日KD":0.10,"MACD":0.12,"均線":0.14,
               "波動":0.08,"融資":0.08,"市場環境":0.18}
    total = int(round(sum(items[k]*weights[k] for k in items)))
    return {"score": max(0,min(100,total)), "items": items}

def tiered_entry_plan(df: pd.DataFrame, levels: dict, stage: str) -> dict:
    last = df.iloc[-1]
    close = float(last["close"])
    atr = float(last["atr14"])
    support = float(levels["support"])
    resistance = float(levels["resistance"])

    first = min(close, max(support, close - 0.35*atr))
    second = max(support, close - 0.80*atr)
    third = max(float(df["low"].tail(20).min()), close - 1.30*atr)
    stop = min(third - 0.35*atr, float(df["low"].tail(20).min()) - 0.10*atr)

    if stage == "觀察":
        first_note = "僅觀察，尚未觸發買進"
    else:
        first_note = "第一筆試單"

    return {
        "first": float(first),
        "second": float(second),
        "third": float(third),
        "stop": float(stop),
        "first_note": first_note,
        "resistance": resistance,
    }


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


def make_decision(df: pd.DataFrame, board: pd.DataFrame, manual: dict):
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
    if progress >= 70 and regime["score"] >= 55 and ensemble_ratio >= 0.6 and ml_prob >= 0.55:
        stage="布局"; position=20
        action="條件初步確認，可建立20%試單"
    elif progress >= 78 and regime["score"] >= 65 and ensemble_ratio >= 0.8 and ml_prob >= 0.60 and above_ma20:
        stage="加碼"; position=50
        action="多項訊號共振，可提高至50%持股"
    elif progress >= 45:
        stage="觀察"; position=0
        action="接近布局區，但仍等待確認"
    else:
        stage="觀察"; position=0
        action="不進場，維持0%"

    plan=tiered_entry_plan(df,levels,stage)

    return {
        "version":"V5.0",
        "data_date":str(df.index[-1].date()),
        "strategy":s.name,
        "stage":stage,
        "action":action,
        "suggested_position_pct":position,
        "bottom_progress_pct":progress,
        "bottom_breakdown":breakdown["items"],
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
        "ensemble_signal":ensemble,
        "manual_inputs":manual,
        "backtest_confidence":confidence,
        "out_of_sample":{
            "trades":int(best["trades_test"]),
            "win_rate":float(best["win_rate_test"]),
            "profit_factor":float(best["profit_factor_test"]),
            "avg_return":float(best["avg_return_test"]),
            "max_drawdown":float(best["max_drawdown_test"]),
            "cagr":float(best["cagr_test"])
        }
    }

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
    ml = decision["ml_signal"]
    ml_text = (
        f"{ml['probability']:.1%}｜AUC {ml['auc']:.3f}｜可信度 {ml['confidence']}"
        if ml.get("probability") is not None and ml.get("auc") is not None
        else "資料不足"
    )
    bars = "".join(
        f"<div style='margin:8px 0'><div>{k}：{v}%</div><div style='background:#eee;border-radius:10px;height:10px'><div style='width:{v}%;background:#555;height:10px;border-radius:10px'></div></div></div>"
        for k,v in decision["bottom_breakdown"].items()
    )
    plan = decision["entry_plan"]
    html=f"""<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <div style="max-width:620px;margin:20px auto;padding:22px;border-radius:18px;box-shadow:0 4px 18px #bbb;font-family:-apple-system;line-height:1.55">
    <h2>00631L 每日決策 V5.0</h2><p>資料截止：{decision['data_date']}</p>
    <h1>{decision['action']}</h1>
    <p>落底進度：<b>{decision['bottom_progress_pct']}%</b>｜市場環境：<b>{regime['label']} {regime['score']}/100</b></p>
    <p>階段：{decision['stage']}｜建議持股：{decision['suggested_position_pct']}%</p>
    <p>參考收盤：{decision['reference_close']:.2f}</p>
    <hr><h3>分批價位</h3>
    <p>第一筆：{plan['first']:.2f}（{plan['first_note']}）</p>
    <p>第二筆：{plan['second']:.2f}</p>
    <p>第三筆：{plan['third']:.2f}</p>
    <p>停止加碼／風險線：{plan['stop']:.2f}</p>
    <p>下方支撐：{decision['support_label']} {decision['support']:.2f}</p>
    <p>上方壓力：{decision['resistance_label']} {decision['resistance']:.2f}</p>
    {reclaim_text}
    <hr><h3>落底進度拆解</h3>{bars}
    <hr><h3>策略與模型</h3>
    <p>Top 5策略投票：{decision['ensemble_signal']['vote_ratio']:.0%}</p>
    <p>ML未來5日上漲機率：{ml_text}</p>
    <p>樣本外交易：{decision['out_of_sample']['trades']}筆｜勝率：{decision['out_of_sample']['win_rate']:.1%}｜PF：{decision['out_of_sample']['profit_factor']:.2f}</p>
    <p>回測可信度：<b>{confidence['level']}</b>（{confidence['score']}/100）</p>
    <p style='font-size:14px;color:#9a5a00'>{confidence['note']}</p>
    <p style='color:#777'>機器學習與回測只作為輔助；歷史績效不保證未來結果。</p></div>"""
    (out/"dashboard.html").write_text(html,encoding="utf-8")

def run():
    cfg=Config()
    data=download_all(cfg)
    build_db(data,cfg)
    feat=build_features(data)
    Path("data").mkdir(exist_ok=True)
    feat.to_parquet("data/features.parquet")
    board,trades=optimize(feat,cfg)
    manual=read_manual_today("data/manual/manual_inputs.csv")
    decision=make_decision(feat,board,manual)
    save_outputs(feat,board,trades,decision,cfg)
    print(json.dumps(decision,ensure_ascii=False,indent=2))

if __name__=="__main__":
    run()