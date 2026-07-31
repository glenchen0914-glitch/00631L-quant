from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from .models import *

class DQE:
    def __init__(self,stale_days): self.stale_days=stale_days
    def run(self,data):
        missing=[k for k,v in data.items() if v.empty or len(v)<60]
        good=[v for v in data.values() if not v.empty and len(v)>=60]
        comp=round(len(good)/max(len(data),1)*100,1)
        return Quality(comp>=75,comp,missing,[])

class MarketEngine:
    def __init__(self,s): self.s=s
    def pts(self,df,w):
        if df.empty:return 0
        r=df.iloc[-1]; c=float(r.Close)
        if c>r.SMA20>r.SMA60:return w
        if c>r.SMA20:return round(w*.7)
        if c>r.SMA60:return round(w*.45)
        return round(w*.15)
    def run(self,data,q):
        w=self.s.weights["market"]
        score=sum(self.pts(data.get(k,pd.DataFrame()),w[key]) for k,key in [
            ("TAIEX","taiex_trend"),("NASDAQ","nasdaq_trend"),("SOX","sox_trend"),("TSMC","tsmc_trend")])
        vix=data.get("VIX",pd.DataFrame()); vv=float(vix.iloc[-1].Close) if not vix.empty else 25
        score+=w["volatility"] if vv<18 else round(w["volatility"]*.5) if vv<25 else 0
        if not q.valid: score=min(score,60)
        score=max(0,min(100,int(score)))
        regime=Regime.BULL if score>=80 else Regime.UPTREND if score>=65 else Regime.RANGE if score>=45 else Regime.DOWNTREND
        risk=Risk.HIGH if not q.valid or vv>=30 or score<40 else Risk.MEDIUM if vv>=22 or score<65 else Risk.LOW
        summary={Regime.BULL:"多頭結構完整，但禁止高檔追價。",Regime.UPTREND:"市場偏多，採分批進場。",Regime.RANGE:"市場整理，等待支撐與右側確認。",Regime.DOWNTREND:"市場偏弱，優先控制風險。"}[regime]
        return Market(regime,risk,score,int(q.completeness),summary)

class SymbolEngine:
    def __init__(self,s): self.s=s
    def run(self,key,name,df,m):
        if df.empty or len(df)<60:return Decision(key,name,0,Phase.P0,Action.WAIT,0,0,0,None,None,None,"等待資料恢復","資料不足",{})
        r,p=df.iloc[-1],df.iloc[-2]; c=float(r.Close); atr=float(r.ATR14) if not pd.isna(r.ATR14) else c*.025
        sup,res=float(r.LOW20),float(r.HIGH20)
        checks={"market_ok":m.score>=55 and m.risk!=Risk.HIGH,
                "support_zone":c<=sup+atr*1.2,
                "kd_confirmation":(r.K>r.D and p.K<=p.D) or (r.K>r.D and r.K<55),
                "macd_confirmation":r.HIST>p.HIST,
                "moving_average_confirmation":c>r.SMA5 or c>r.SMA10,
                "volume_confirmation":bool(r.VOL_RATIO>=.8) if not pd.isna(r.VOL_RATIO) else False,
                "risk_ok":m.risk!=Risk.HIGH and c>sup-atr}
        ew=self.s.weights["entry"]; entry=sum(ew[k] for k,v in checks.items() if v)
        blockers=not(checks["market_ok"] and checks["support_zone"] and checks["risk_ok"])
        exit=(30 if r.K>=80 else 0)+(25 if r.HIST<p.HIST else 0)+(30 if c>=res-atr*.7 else 0)+(15 if r.VOL_RATIO>=1.8 else 0)
        s=self.s.strategy
        if exit>=s.exit_full_threshold: phase,act,pos,nxt=Phase.P5,Action.EXIT,0,"全部出場，結束交易週期"
        elif exit>=s.exit_reduce_threshold: phase,act,pos,nxt=Phase.P5,Action.REDUCE50,50,"減碼50%，觀察壓力"
        elif exit>=s.exit_watch_threshold: phase,act,pos,nxt=Phase.P5,Action.REDUCE20,80,"開始分批停利"
        elif entry>=s.add_threshold and not blockers: phase,act,pos,nxt=Phase.P3,Action.ADD,s.add_position_pct,"右側確認後加碼"
        elif entry>=s.pilot_threshold and not blockers: phase,act,pos,nxt=Phase.P2,Action.PILOT,s.pilot_position_pct,"建立試單，等待確認"
        elif entry>=55: phase,act,pos,nxt=Phase.P1,Action.WAIT,0,"等待KD、MACD及價格同步"
        else: phase,act,pos,nxt=Phase.P0,Action.WAIT,0,"維持空手，等待高報酬風險比"
        risk="高檔追價" if c>r.SMA20 and not checks["support_zone"] else "支撐跌破" if c<=sup+atr else "市場轉弱"
        return Decision(key,name,round(c,2),phase,act,pos,int(entry),min(100,int(exit)),round(sup,2),round(res,2),round(max(0,sup-atr*.6),2),nxt,risk,checks)

class Orchestrator:
    def __init__(self,s): self.s=s
    def run(self,data):
        q=DQE(self.s.strategy.stale_market_days).run(data); m=MarketEngine(self.s).run(data,q); e=SymbolEngine(self.s)
        ds=[e.run("ETF_00631L","00631L 元大台灣50正2",data.get("ETF_00631L",pd.DataFrame()),m),
            e.run("ETF_00981A","00981A 主動式ETF",data.get("ETF_00981A",pd.DataFrame()),m)]
        return Result(datetime.now(ZoneInfo(self.s.timezone)),q,m,ds)
