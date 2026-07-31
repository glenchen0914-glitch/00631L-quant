from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass(frozen=True)
class Strategy:
    pilot_threshold:int
    add_threshold:int
    exit_watch_threshold:int
    exit_reduce_threshold:int
    exit_full_threshold:int
    pilot_position_pct:int
    add_position_pct:int
    stale_market_days:int

@dataclass(frozen=True)
class Settings:
    timezone:str
    database_path:str
    line_enabled:bool
    tickers:dict
    strategy:Strategy
    weights:dict

def load_settings(path="config/settings.yaml"):
    raw=yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Settings(raw["timezone"],raw["database_path"],raw.get("line_enabled",True),
                    raw["tickers"],Strategy(**raw["strategy"]),raw["weights"])
