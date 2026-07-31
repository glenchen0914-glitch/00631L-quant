from dataclasses import dataclass,asdict
from datetime import datetime
from enum import StrEnum

class Regime(StrEnum): BULL="BULL"; UPTREND="UPTREND"; RANGE="RANGE"; DOWNTREND="DOWNTREND"
class Risk(StrEnum): LOW="LOW"; MEDIUM="MEDIUM"; HIGH="HIGH"
class Phase(StrEnum): P0="P0_WAITING"; P1="P1_PREPARE"; P2="P2_PILOT"; P3="P3_ADD"; P4="P4_HOLD"; P5="P5_TAKE_PROFIT"; P6="P6_COMPLETED"
class Action(StrEnum): WAIT="WAIT"; PILOT="PILOT"; ADD="ADD"; HOLD="HOLD"; REDUCE20="REDUCE_20"; REDUCE50="REDUCE_50"; EXIT="EXIT"

@dataclass
class Quality: valid:bool; completeness:float; missing:list; stale:list
@dataclass
class Market: regime:Regime; risk:Risk; score:int; confidence:int; summary:str
@dataclass
class Decision:
    symbol:str; name:str; price:float; phase:Phase; action:Action; position:int
    entry:int; exit:int; support:float|None; resistance:float|None
    invalidation:float|None; next_action:str; biggest_risk:str; checks:dict
@dataclass
class Result:
    generated_at:datetime; quality:Quality; market:Market; decisions:list
    def to_dict(self):
        d=asdict(self)
        def cv(x):
            if isinstance(x,datetime): return x.isoformat()
            if isinstance(x,StrEnum): return x.value
            if isinstance(x,dict): return {k:cv(v) for k,v in x.items()}
            if isinstance(x,list): return [cv(v) for v in x]
            return x
        return cv(d)
