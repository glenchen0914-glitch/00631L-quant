from dataclasses import dataclass, field

@dataclass(frozen=True)
class Config:
    start: str = "2014-10-31"
    db_path: str = "data/market.db"
    reports_dir: str = "reports"
    commission_rate: float = 0.001425
    commission_discount: float = 0.28
    sell_tax_rate: float = 0.001
    slippage_rate: float = 0.0005
    train_ratio: float = 0.70
    min_total_trades: int = 8
    min_test_trades: int = 5
    top_n: int = 30
    symbols: dict[str, str] = field(default_factory=lambda: {
        "etf": "00631L.TW",
        "twii": "^TWII",
        "nasdaq": "^IXIC",
        "sox": "^SOX",
        "sp500": "^GSPC",
        "vix": "^VIX",
        "dxy": "DX-Y.NYB",
        "us10y": "^TNX",
        "tsm_adr": "TSM",
    })