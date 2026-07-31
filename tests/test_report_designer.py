from src.report_designer import build_falcon_message


def sample_report():
    return {
        "asset_code": "00631L",
        "reference_close": 32.0,
        "gate": {"cap_pct": 100, "level": "正常", "reasons": ["未觸發硬性風險門檻"]},
        "scores": {"trend": 18, "pullback": 15, "momentum": 8, "total": 41,
                   "reasons": ["5MA高於10MA", "MACD柱體改善", "價格接近支撐區"]},
        "position": {"target_pct": 20},
        "risk": {"atr": 0.8, "initial_stop": 30.8, "first_take_profit": 33.6},
        "execution": {"gap_pct": 0, "chase_rule": "允許依買點分批"},
        "overnight_market": {"label": "偏多", "score": 72},
    }


def test_message_contains_actionable_sections():
    text = build_falcon_message(sample_report(), session="premarket")
    for key in ["操作結論", "交易成熟度", "第一買點", "防守線", "今天不能犯的錯", "AI一句話"]:
        assert key in text
    assert "歷史勝率" not in text or "不顯示虛構歷史勝率" in text


def test_message_respects_gate_block():
    report = sample_report()
    report["gate"]["cap_pct"] = 0
    report["gate"]["level"] = "封鎖"
    report["position"]["target_pct"] = 0
    text = build_falcon_message(report, session="close")
    assert "禁止交易" in text
    assert "禁止新建多單" in text
