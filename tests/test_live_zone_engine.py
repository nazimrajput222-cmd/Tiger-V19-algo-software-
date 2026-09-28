"""Live zone engine: WS 1m/15m bars → ORIGINAL run_tiger_brain_backtest input."""
from datetime import datetime, timedelta

import pandas as pd

from automation.live_zone_engine import LiveZoneEngine


def bar(ts, o, h, l, c, v=1000):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_1m_bars_roll_into_15m_buckets():
    e = LiveZoneEngine()
    base = datetime(2026, 9, 28, 9, 15)
    for i in range(30):                     # 09:15 → 09:44 = two 15m bars
        e.on_bar_1m("NIFTY", bar(base + timedelta(minutes=i), 10, 12, 9, 11, 100))
    dm, dm1 = e.data_maps()
    assert len(dm1["NIFTY"]) == 30
    assert len(dm["NIFTY"]) == 2
    r = dm["NIFTY"].iloc[0]
    assert r["open"] == 10 and r["close"] == 11
    assert r["high"] == 12 and r["low"] == 9 and r["volume"] == 1500


def test_15m_buckets_split_at_0915_anchor():
    e = LiveZoneEngine()
    base = datetime(2026, 9, 28, 9, 15)
    for i in range(31):                     # 2 buckets
        e.on_bar_1m("NIFTY", bar(base + timedelta(minutes=i), 10, 12, 9, 11, 100))
    dm, _ = e.data_maps()
    assert len(dm["NIFTY"]) == 2
    assert list(dm["NIFTY"].index) == [base, base + timedelta(minutes=15)]


def test_candle_gate_blocks_only_the_same_candle():
    import pandas as pd
    e = LiveZoneEngine(candle_gate_sec=0.35, scan_dedup_sec=30.0)
    t1 = pd.Timestamp("2026-09-28 09:15")
    t2 = pd.Timestamp("2026-09-28 09:16")
    assert e.allow_candle("NIFTY", t1) is True
    assert e.allow_candle("NIFTY", t1) is False     # wahi candle, <0.35s
    assert e.allow_candle("NIFTY", t2) is True      # ALAG candle → chalti hai
    assert e.allow_scan("NIFTY") is True
    assert e.allow_scan("NIFTY") is False           # 30s dedup


def test_seed_history_then_live_bars_coexist():
    e = LiveZoneEngine()
    idx = pd.date_range("2026-09-25 09:15", periods=10, freq="5min")
    df = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                       "volume": 10.0}, index=idx)
    e.seed("NIFTY", df, df)
    e.on_bar_1m("NIFTY", bar(datetime(2026, 9, 28, 9, 15), 10, 12, 9, 11, 100))
    dm, dm1 = e.data_maps()
    assert len(dm1["NIFTY"]) == 11
    assert dm1["NIFTY"].index.is_monotonic_increasing


def test_original_engine_accepts_bridge_output(monkeypatch):
    """Bridge ka output original run_tiger_brain_backtest ke signature se fit hona chahiye."""
    e = LiveZoneEngine()
    base = datetime(2026, 9, 28, 9, 15)
    for i in range(60):
        e.on_bar_1m("NIFTY", bar(base + timedelta(minutes=i),
                                 10 + i * 0.1, 12 + i * 0.1, 9 + i * 0.1, 11 + i * 0.1, 100))
    dm, dm1 = e.data_maps()
    import inspect
    from backtest.run_tiger_brain_backtest import run_tiger_brain_backtest
    sig = inspect.signature(run_tiger_brain_backtest)
    assert "data_map" in sig.parameters
    assert sig.parameters["data_map_1m"].default is None
    # shape check: original engine ke helpers inhe consume kar sakte hain
    from backtest.intraday_backtest import _normalize_cols
    _normalize_cols(dm["NIFTY"]); _normalize_cols(dm1["NIFTY"])


def test_empty_until_enough_bars():
    e = LiveZoneEngine()
    e.on_bar_1m("X", bar(datetime(2026, 9, 28, 9, 15), 1, 2, 0.5, 1.5))
    dm, dm1 = e.data_maps()
    assert dm == {} and dm1 == {}
