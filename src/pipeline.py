from __future__ import annotations
from dataclasses import dataclass, asdict
from itertools import product
from pathlib import Path
import json, math, sqlite3
import numpy as np
import pandas as pd
import yfinance as yf
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

def make_decision(df: pd.DataFrame, board: pd.DataFrame, manual: dict):
    best=board.iloc[0]
    s=Strategy(best["name"],int(best["week_k_max"]),int(best["rsi_max"]),
               bool(best["require_k_cross"]),bool(best["require_macd_improve"]),
               bool(best["require_close_ma20"]),bool(best["require_twii_ma20"]),
               float(best["stop_loss"]),float(best["take_profit"]),int(best["max_hold"]))
    sig=signal_for(df,s); last=df.iloc[-1]
    progress,reasons=bottom_progress(df,manual)
    k_cross=bool(last["k"]>last["d"] and df["k"].iloc[-2]<=df["d"].iloc[-2])
    macd_up=bool(last["macd_hist"]>df["macd_hist"].iloc[-2])
    above_ma20=bool(last["close"]>last["ma20"])
    if bool(sig.iloc[-1]):
        stage="布局"; position=20; action="下一交易日開盤建立20%部位"
    elif progress>=75 and k_cross and macd_up and above_ma20:
        stage="加碼"; position=50; action="可提高至50%持股"
    elif progress>=45:
        stage="觀察"; position=0; action="不進場，等待確認"
    else:
        stage="觀察"; position=0; action="不進場，維持0%"
    return {
        "data_date":str(df.index[-1].date()),
        "strategy":s.name,"stage":stage,"action":action,
        "suggested_position_pct":position,
        "bottom_progress_pct":progress,
        "progress_reasons":reasons,
        "reference_close":float(last["close"]),
        "entry_range_low":float(last["bb_low"]),
        "entry_range_high":float(last["ma20"]),
        "support":float(last["bb_low"]),
        "resistance":float(last["bb_up"]),
        "week_k":float(last["week_k"]),
        "daily_k":float(last["k"]),"daily_d":float(last["d"]),
        "macd_improving":macd_up,"above_ma20":above_ma20,
        "manual_inputs":manual,
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
    html=f"""<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <div style="max-width:560px;margin:20px auto;padding:20px;border-radius:18px;box-shadow:0 4px 18px #bbb;font-family:-apple-system">
    <h2>00631L 每日決策</h2><p>資料截止：{decision['data_date']}</p>
    <h1>{decision['action']}</h1>
    <p>落底進度：<b>{decision['bottom_progress_pct']}%</b></p>
    <p>階段：{decision['stage']}｜建議持股：{decision['suggested_position_pct']}%</p>
    <p>參考收盤：{decision['reference_close']:.2f}</p>
    <p>進場區間：{decision['entry_range_low']:.2f}～{decision['entry_range_high']:.2f}</p>
    <p>支撐：{decision['support']:.2f}｜壓力：{decision['resistance']:.2f}</p>
    <p>周KD：{decision['week_k']:.1f}｜日K/D：{decision['daily_k']:.1f}/{decision['daily_d']:.1f}</p>
    <p>樣本外勝率：{decision['out_of_sample']['win_rate']:.1%}｜PF：{decision['out_of_sample']['profit_factor']:.2f}</p>
    <p style='color:#777'>歷史回測不保證未來績效。</p></div>"""
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