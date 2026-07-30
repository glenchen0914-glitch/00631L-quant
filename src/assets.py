from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pandas as pd

from src.config import Config
from src.pipeline import (
    Strategy, backtest, build_db, build_features, data_quality_report,
    download_all, make_decision, optimize, read_manual_today, save_outputs,
    strategy_description
)

ASSETS = {
    "00631L": {
        "name": "元大台灣50正2",
        "ticker": "00631L.TW",
        "start": "2014-10-31",
        "reports_dir": "reports",
        "db_path": "data/market_00631L.db",
        "features_path": "data/features_00631L.parquet",
        "min_total_trades": 8,
        "min_test_trades": 5,
        "top_n": 30,
        "mode": "leveraged_rebound",
    },
    "00981A": {
        "name": "主動統一台股增長",
        "ticker": "00981A.TW",
        "start": "2025-05-01",
        "reports_dir": "reports/00981A",
        "db_path": "data/market_00981A.db",
        "features_path": "data/features_00981A.parquet",
        "min_total_trades": 3,
        "min_test_trades": 1,
        "top_n": 15,
        "mode": "active_etf_short",
    },
}

def _fallback_board(df: pd.DataFrame, cfg: Config, asset_code: str):
    s = Strategy(
        name=f"{asset_code}_TECH",
        week_k_max=45,
        rsi_max=50,
        require_k_cross=False,
        require_macd_improve=True,
        require_close_ma20=False,
        require_twii_ma20=False,
        stop_loss=0.06 if asset_code == "00981A" else 0.07,
        take_profit=0.12 if asset_code == "00981A" else 0.15,
        max_hold=15 if asset_code == "00981A" else 20,
    )
    split = max(60, int(len(df) * cfg.train_ratio))
    train, test = df.iloc[:split], df.iloc[split:]
    mt, _ = backtest(train, s, cfg)
    ms, tr = backtest(test, s, cfg)

    def safe(m):
        return m or {
            "trades": 0, "win_rate": 0.0, "avg_return": 0.0,
            "profit_factor": 0.0, "max_drawdown": 0.0,
            "cagr": 0.0, "total_return": 0.0,
        }

    mt, ms = safe(mt), safe(ms)
    row = {
        "name": s.name,
        "week_k_max": s.week_k_max,
        "rsi_max": s.rsi_max,
        "require_k_cross": s.require_k_cross,
        "require_macd_improve": s.require_macd_improve,
        "require_close_ma20": s.require_close_ma20,
        "require_twii_ma20": s.require_twii_ma20,
        "stop_loss": s.stop_loss,
        "take_profit": s.take_profit,
        "max_hold": s.max_hold,
        "description": "短線技術備援策略｜MACD改善｜風險優先",
        "score": 0.0,
        "final_score": 0.0,
        "wf_windows": 0,
        "wf_positive_windows": 0,
        "wf_median_pf": None,
        "wf_median_return": None,
    }
    for k, v in mt.items():
        row[f"{k}_train"] = v
    for k, v in ms.items():
        row[f"{k}_test"] = v
    return pd.DataFrame([row]), {s.name: tr}

def _configure(asset_code: str) -> Config:
    spec = ASSETS[asset_code]
    base = Config()
    symbols = dict(base.symbols)
    symbols["etf"] = spec["ticker"]
    return Config(
        start=spec["start"],
        db_path=spec["db_path"],
        reports_dir=spec["reports_dir"],
        commission_rate=base.commission_rate,
        commission_discount=base.commission_discount,
        sell_tax_rate=base.sell_tax_rate,
        slippage_rate=base.slippage_rate,
        train_ratio=base.train_ratio,
        min_total_trades=spec["min_total_trades"],
        min_test_trades=spec["min_test_trades"],
        top_n=spec["top_n"],
        symbols=symbols,
    )

def _apply_asset_rules(decision: dict, df: pd.DataFrame, asset_code: str) -> dict:
    spec = ASSETS[asset_code]
    decision["asset_code"] = asset_code
    decision["asset_name"] = spec["name"]
    decision["version"] = "V17 Dual Short-Term Final"
    decision["analysis_type"] = "短線操作"
    decision["progress_label"] = "落底進度" if asset_code == "00631L" else "短線轉強進度"
    decision["history_rows"] = int(len(df))
    decision["history_status"] = (
        "充足" if len(df) >= 500 else
        "有限" if len(df) >= 220 else
        "不足"
    )

    if asset_code == "00981A":
        last = df.iloc[-1]
        progress = int(decision["bottom_progress_pct"])
        regime = int(decision["market_regime"]["score"])
        ensemble = float(decision["ensemble_signal"]["vote_ratio"])
        above_ma20 = bool(last["close"] > last["ma20"])
        macd_up = bool(last["macd_hist"] > df["macd_hist"].iloc[-2])
        vol_ratio = float(last["volume"] / df["volume"].rolling(20).mean().iloc[-1])
        data_days = len(df)

        # 00981A歷史較短：模型只輔助，核心採短線趨勢、量價與市場環境。
        if data_days < 140:
            decision["stage"] = "資料觀察"
            decision["suggested_position_pct"] = 0
            decision["action"] = "歷史資料不足，暫不進場"
        elif progress >= 75 and regime >= 60 and above_ma20 and macd_up and ensemble >= 0.40:
            decision["stage"] = "短線布局"
            decision["suggested_position_pct"] = 20
            decision["action"] = "短線訊號共振，可建立20%試單"
        elif progress >= 60 and regime >= 50 and above_ma20 and macd_up and vol_ratio >= 0.90:
            decision["stage"] = "試單"
            decision["suggested_position_pct"] = 10
            decision["action"] = "轉強條件初步成立，可建立10%試單"
        elif progress >= 45:
            decision["stage"] = "觀察"
            decision["suggested_position_pct"] = 0
            decision["action"] = "接近短線布局區，等待量價確認"
        else:
            decision["stage"] = "觀察"
            decision["suggested_position_pct"] = 0
            decision["action"] = "不進場，維持0%"

        decision["short_term_factors"] = {
            "above_ma20": above_ma20,
            "macd_improving": macd_up,
            "volume_ratio_20d": vol_ratio,
            "relative_strength_20d": float(
                df["close"].pct_change(20).iloc[-1] -
                df["twii_close"].pct_change(20).iloc[-1]
            ) if "twii_close" in df else None,
        }

        exp = decision["decision_explanation"]
        if above_ma20:
            exp["positive"].append("價格站上20日均線")
        else:
            exp["negative"].append("價格仍在20日均線下方")
        if macd_up:
            exp["positive"].append("MACD柱體改善")
        else:
            exp["negative"].append("MACD尚未改善")
        if vol_ratio >= 1.10:
            exp["positive"].append("成交量高於20日均量")
        elif vol_ratio < 0.80:
            exp["negative"].append("成交量不足")
        if data_days < 500:
            exp["missing"].append("上市歷史較短，模型與回測可信度受限")

        # 歷史短時不允許顯示高信心。
        grade = decision["confidence_grade"]
        if data_days < 500:
            grade["score"] = min(int(grade["score"]), 49)
            grade["grade"] = "D" if grade["score"] < 40 else "C"
        decision["backtest_confidence"]["note"] = (
            decision["backtest_confidence"]["note"] +
            "；00981A上市歷史較短，決策以短線技術與市場環境為主"
        )

    return decision

def _fix_dashboard_title(report_dir: str, decision: dict) -> None:
    p = Path(report_dir) / "dashboard.html"
    if not p.exists():
        return
    html = p.read_text(encoding="utf-8")
    html = html.replace(
        "00631L 每日決策 V6.0 Final",
        f"{decision['asset_code']} 每日決策 V17 Dual Short-Term Final"
    )
    label = decision.get("progress_label", "落底進度")
    if label != "落底進度":
        html = html.replace("落底進度：", f"{label}：")
        html = html.replace("<h3>落底進度拆解</h3>", f"<h3>{label}拆解</h3>")
    p.write_text(html, encoding="utf-8")

def run_asset(asset_code: str) -> dict:
    cfg = _configure(asset_code)
    spec = ASSETS[asset_code]
    data = download_all(cfg)
    quality = data_quality_report(data, cfg.symbols)
    build_db(data, cfg)
    feat = build_features(data)

    fpath = Path(spec["features_path"])
    fpath.parent.mkdir(parents=True, exist_ok=True)
    feat.to_parquet(fpath)

    try:
        board, trades = optimize(feat, cfg)
        fallback = False
    except RuntimeError as exc:
        print(f"⚠️ {asset_code} 正式回測門檻未通過，改用短線技術備援：{exc}")
        board, trades = _fallback_board(feat, cfg, asset_code)
        fallback = True

    manual = read_manual_today("data/manual/manual_inputs.csv")
    decision = make_decision(feat, board, manual, quality)
    decision = _apply_asset_rules(decision, feat, asset_code)
    decision["fallback_strategy"] = fallback
    save_outputs(feat, board, trades, decision, cfg)
    _fix_dashboard_title(spec["reports_dir"], decision)
    print(f"✅ {asset_code} 完成：{decision['action']}")
    return decision

def run_dual() -> dict[str, dict]:
    results = {}
    for asset_code in ("00631L", "00981A"):
        results[asset_code] = run_asset(asset_code)

    summary = {
        code: {
            "date": d["data_date"],
            "action": d["action"],
            "position_pct": d["suggested_position_pct"],
            "confidence": d["confidence_grade"],
            "reference_close": d["reference_close"],
        }
        for code, d in results.items()
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/dual_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results

if __name__ == "__main__":
    run_dual()
