from pathlib import Path
import sys, json, tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.notify import build_line_message
from src.performance import update_performance

sample = {
    "data_date":"2026-07-30",
    "action":"不進場，維持0%",
    "suggested_position_pct":0,
    "bottom_progress_pct":31,
    "reference_close":28.26,
    "confidence_grade":{"grade":"D","score":27},
    "market_regime":{"label":"偏空","score":13},
    "entry_plan":{"first":27.58,"second":26.52,"third":25.45,"stop":24.77},
    "decision_explanation":{
        "positive":[],
        "negative":["市場環境偏空"],
        "missing":["融資資料未提供"]
    },
    "stage":"觀察",
    "strategy":"S00001",
    "model_consensus":{"probability":0.428},
    "ensemble_signal":{"vote_ratio":0.0},
}
msg = build_line_message(sample)
assert "00631L 每日決策" in msg
assert "第一筆 27.58" in msg
assert "市場環境偏空" in msg

with tempfile.TemporaryDirectory() as td:
    d = Path(td)/"daily_decision.json"
    h = Path(td)/"decision_history.csv"
    d.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    update_performance(str(d), str(h))
    assert h.exists()
    text = h.read_text(encoding="utf-8")
    assert "2026-07-30" in text

print("PASS: LINE 訊息與決策歷史")
