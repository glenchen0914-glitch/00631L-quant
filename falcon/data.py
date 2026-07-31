import logging,sqlite3
from pathlib import Path
import pandas as pd
import yfinance as yf
from .indicators import enrich
log=logging.getLogger(__name__)

class Repository:
    def __init__(self,path): self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
    def save(self,name,df):
        if df.empty:return
        with sqlite3.connect(self.path) as c:
            df.reset_index().to_sql("prices_"+name.lower(),c,if_exists="replace",index=False)

class Provider:
    def __init__(self,repo): self.repo=repo
    def all(self,tickers,period="1y"):
        out={}
        for name,ticker in tickers.items():
            try:
                df=yf.download(ticker,period=period,interval="1d",auto_adjust=True,progress=False,multi_level_index=False,timeout=20)
                if df is None or df.empty: out[name]=pd.DataFrame(); continue
                cols=[x for x in ["Open","High","Low","Close","Volume"] if x in df.columns]
                df=df[cols].dropna(subset=["Close"])
                if "Volume" not in df: df["Volume"]=0
                df=enrich(df); self.repo.save(name,df); out[name]=df
            except Exception:
                log.exception("download failed: %s",name); out[name]=pd.DataFrame()
        return out
