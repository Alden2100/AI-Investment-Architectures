"""Stage 5 — catalyst-detector driver.

Pure (leaf-skill calls only -> safe in a worker thread). Reuses the existing
catalyst-flagger (8-K + news event tagging, model-classified) and insider-trading-monitor
(Form 4), normalizing both into the events schema the Evidence Store stores:
    {type, date, source, confidence, hard_event, rationale}
"""
from __future__ import annotations

from imdata import skillkit


def _num(x):
    return x if isinstance(x, (int, float)) else None


def run(ticker: str, *, lookback: int = 90) -> dict:
    events = []

    cf = skillkit.call_skill("catalyst-flagger", ["--tickers", ticker, "--lookback", lookback])
    for ev in (cf.get("catalysts") or []):
        if not isinstance(ev, dict):
            continue
        if ev.get("ticker") and ev["ticker"].upper() != ticker.upper():
            continue
        events.append({
            "type": ev.get("type") or "catalyst",
            "date": ev.get("date"),
            "source": ev.get("source"),
            "confidence": _num(ev.get("confidence")),
            "hard_event": bool(ev.get("hard_event")),
            "rationale": ev.get("rationale"),
        })

    ins = skillkit.call_skill("insider-trading-monitor", ["--ticker", ticker])
    sig = (ins.get("signal") or "").lower()
    if sig and sig not in ("none", "neutral", "no signal", ""):
        net = ins.get("net_open_market_usd")
        events.append({
            "type": "insider",
            "date": None,
            "source": "SEC Form 4",
            "confidence": 0.6,
            "hard_event": True,
            "rationale": f"insider {sig}" + (f" (net ${net:,.0f})" if isinstance(net, (int, float)) else ""),
        })

    return {"ticker": ticker, "events": events,
            "summary": f"{len(events)} event(s) for {ticker} over {lookback}d"}
