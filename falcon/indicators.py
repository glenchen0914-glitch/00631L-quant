import numpy as np
import pandas as pd

def enrich(df):
    o=df.copy().sort_index()
    c,h,l,v=o.Close.astype(float),o.High.astype(float),o.Low.astype(float),o.Volume.astype(float)
    for n in (5,10,20,60): o[f"SMA{n}"]=c.rolling(n).mean()
    e12,e26=c.ewm(span=12,adjust=False).mean(),c.ewm(span=26,adjust=False).mean()
    o["MACD"]=e12-e26; o["SIGNAL"]=o.MACD.ewm(span=9,adjust=False).mean(); o["HIST"]=o.MACD-o.SIGNAL
    lo,hi=l.rolling(9).min(),h.rolling(9).max()
    rsv=((c-lo)/(hi-lo).replace(0,np.nan)*100).fillna(50)
    o["K"]=rsv.ewm(com=2,adjust=False).mean(); o["D"]=o.K.ewm(com=2,adjust=False).mean()
    pc=c.shift(1); tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    o["ATR14"]=tr.rolling(14).mean(); o["VOL_RATIO"]=v/v.rolling(20).mean().replace(0,np.nan)
    o["LOW20"]=l.rolling(20).min(); o["HIGH20"]=h.rolling(20).max()
    return o
