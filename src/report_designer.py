from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stars(score: int) -> str:
    n = max(1, min(5, round(score / 20)))
    return "★" * n + "☆" * (5 - n)


def _status(target: int, gate_cap: int, score: int) -> tuple[str, str]:
    if gate_cap == 0:
        return "🔴", "禁止交易"
    if target >= 60:
        return "🟢", "可依階梯執行"
    if target == 20:
        return "🟡", "僅允許20%試單"
    if score >= 35:
        return "🟡", "接近試單門檻，等待確認"
    return "🔴", "暫不進場"


def _trade_quality(score: int, gate_cap: int) -> tuple[int, str]:
    quality = min(score, gate_cap)
    if gate_cap == 0:
        return 0, "不可交易"
    if quality >= 75:
        return quality, "高度成熟"
    if quality >= 60:
        return quality, "可交易"
    if quality >= 40:
        return quality, "試單階段"
    return quality, "尚未成熟"


def _levels(report: dict[str, Any]) -> dict[str, float]:
    close = _f(report.get("reference_close"))
    atr = max(_f(report.get("risk", {}).get("atr")), close * 0.005)
    return {
        "first": round(close - 0.35 * atr, 2),
        "second": round(close - 0.85 * atr, 2),
        "third": round(close - 1.35 * atr, 2),
        "stop": round(_f(report.get("risk", {}).get("initial_stop")), 2),
        "tp1": round(_f(report.get("risk", {}).get("first_take_profit")), 2),
    }


def _reasons(report: dict[str, Any], positive: bool) -> list[str]:
    reasons = list(report.get("scores", {}).get("reasons", []))
    if positive:
        return reasons[:4]
    negatives: list[str] = []
    scores = report.get("scores", {})
    if int(scores.get("trend", 0)) < 20:
        negatives.append("趨勢分數偏低")
    if int(scores.get("pullback", 0)) < 20:
        negatives.append("拉回品質尚未達標")
    if int(scores.get("momentum", 0)) < 10:
        negatives.append("短線動能不足")
    if int(report.get("position", {}).get("target_pct", 0)) == 0:
        negatives.append("尚未跨越20%試單門檻")
    return negatives[:4]


def _biggest_mistake(report: dict[str, Any], session: str) -> str:
    gap = _f(report.get("execution", {}).get("gap_pct"))
    target = int(report.get("position", {}).get("target_pct", 0))
    if session == "premarket" or gap > 1.5:
        return "開高直接追價"
    if target == 0:
        return "因單日上漲而破壞進場紀律"
    return "跌破防守線後仍不減倉"


def _summary(report: dict[str, Any], session: str) -> str:
    score = int(report.get("scores", {}).get("total", 0))
    target = int(report.get("position", {}).get("target_pct", 0))
    gate = int(report.get("gate", {}).get("cap_pct", 100))
    levels = _levels(report)
    if gate == 0:
        return "今日觸發硬性風險門檻，禁止新建多單，先以保護本金為主。"
    if target == 0:
        if score >= 35:
            return f"距離20%試單門檻已近；等待價格接近第一買點 {levels['first']:.2f}，並出現止跌或動能確認，不追高。"
        return f"目前條件仍不足；先觀察第一買點 {levels['first']:.2f}，未出現確認訊號前維持空手。"
    if target == 20:
        return f"僅允許20%試單，優先在 {levels['first']:.2f} 附近分批，不宜一次追滿。"
    return f"趨勢已達配置門檻，可依階梯執行；防守線 {levels['stop']:.2f} 必須遵守。"


def build_falcon_message(report: dict[str, Any], *, session: str) -> str:
    asset = report.get("asset_code", "-")
    gate = report.get("gate", {})
    scores = report.get("scores", {})
    position = report.get("position", {})
    execution = report.get("execution", {})
    score = int(scores.get("total", 0))
    target = int(position.get("target_pct", 0))
    cap = int(gate.get("cap_pct", 100))
    icon, status = _status(target, cap, score)
    quality, quality_label = _trade_quality(score, cap)
    levels = _levels(report)
    positives = _reasons(report, True)
    negatives = _reasons(report, False)
    current = _f(report.get("reference_close"))
    distance = ((current / levels["first"] - 1) * 100) if levels["first"] else 0
    title = "07:00盤前" if session == "premarket" else "14:35收盤"
    actual_time = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")

    lines = [
        f"{asset} Falcon {title}",
        f"實際執行：{actual_time}",
        "",
        f"{icon} 操作結論：{status}",
        f"目標倉位：{target}%｜Gate上限：{cap}%（{gate.get('level', '-')}）",
        f"交易成熟度：{quality}%（{quality_label}） {_stars(quality)}",
        f"策略分數：{score}/100｜趨勢{scores.get('trend', 0)} 拉回{scores.get('pullback', 0)} 動能{scores.get('momentum', 0)}",
    ]
    if session == "premarket" and report.get("overnight_market"):
        market = report["overnight_market"]
        lines.append(f"隔夜環境：{market.get('label', '-')} {market.get('score', 0)}/100")

    lines += [
        "",
        "【條件式觀察價位】",
        f"參考價：{current:.2f}",
        f"第一買點：{levels['first']:.2f}（目前高於買點約{distance:.1f}%）",
        f"第二買點：{levels['second']:.2f}",
        f"第三買點：{levels['third']:.2f}",
        f"防守線：{levels['stop']:.2f}｜首段停利：{levels['tp1']:.2f}",
        "到價不等於直接買進，仍須等待止跌、量價或動能確認。",
        "",
        "【今日執行規則】",
        f"• {execution.get('chase_rule', '依買點分批，不追價')}",
        f"• {_summary(report, session)}",
        f"• 今天不能犯的錯：{_biggest_mistake(report, session)}",
    ]
    if positives:
        lines += ["", "【支持理由】"] + [f"• {x}" for x in positives]
    if negatives:
        lines += ["", "【尚未確認】"] + [f"• {x}" for x in negatives]
    research = report.get("research_evidence") or {}
    h5 = research.get("horizons", {}).get("5", {})
    validation = research.get("validation_5d", {})
    if research and h5.get("sample_count", 0) >= 30:
        lines += [
            "",
            "【Research歷史證據】",
            f"相似樣本：{h5.get('sample_count')}次｜5日勝率：{h5.get('win_rate_pct')}%",
            f"平均5日報酬：{h5.get('average_return_pct')}%｜扣估計成本後：{h5.get('expected_return_after_cost_pct')}%",
            f"樣本外方向正確率：{validation.get('directional_accuracy_pct')}%（{validation.get('oos_cases')}例）",
            f"研究信心：{research.get('confidence', '審慎')}；歷史相似不代表未來保證。",
        ]
    lines += [
        "",
        "【AI一句話】",
        _summary(report, session),
        "",
        ("信心說明：已加入Research Engine歷史相似樣本與樣本外驗證；仍須服從Gate與風控。"
         if research else
         "信心說明：目前為規則模型信心；Research Engine尚無可用報告，故不顯示虛構歷史勝率。"),
    ]
    return "\n".join(lines)
