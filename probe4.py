import sys, logging
sys.path.insert(0, '/home/ec2-user/tiger-brain-v6')
logging.disable(logging.CRITICAL)
import pandas as pd
from datetime import datetime, timedelta
from data.tick_bars import TickBarAggregator, bucket_start
from automation.live_zone_engine import LiveZoneEngine
from pipeline.intraday_strategies import detect_zones

# --- 1. tick -> 1m bar: OHLCV integrity ---
agg = TickBarAggregator(bar_minutes=1, max_bars=2000)
base = datetime(2026, 9, 29, 13, 0, 0)
px = 100.0
for s in range(180):                      # 3 minutes of ticks
    ts = base + timedelta(seconds=s * 1)  # 1 tick/sec
    px += (0.01 if s % 7 < 4 else -0.02)
    agg.on_tick("999", ts, px, cum_volume=1000 + s)
# force close
closed = agg.on_tick("999", base + timedelta(minutes=3, seconds=1), px, cum_volume=9999)
print("=== TEST 1: tick -> 1m OHLCV ===")
for b in closed:
    o, h, l, c, v = b.open, b.high, b.low, b.close, b.volume
    print(f"  bar {b.start:%H:%M} O={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f} V={v:,.0f} ticks={b.ticks}")
    assert h >= max(o, l, c), "HIGH must be >= O/L/C"
    assert l <= min(o, h, c), "LOW must be <= O/H/C"
    assert h >= l, "HIGH >= LOW"
    assert v >= 0, "volume non-negative"
print("  OHLC INVARIANTS: PASS")

# --- 2. 1m -> 15m resampling via real LiveZoneEngine ---
print()
print("=== TEST 2: 1m -> 15m resample (real LiveZoneEngine) ===")
ze = LiveZoneEngine(max_bars_15m=500, max_bars_1m=2000)
day0 = datetime(2026, 9, 28, 9, 15, 0)
px = 25000.0
n = 0
for m in range(0, 240):                    # 240 minutes = 4 hours
    for s in range(0, 60, 10):             # 6 ticks per minute
        px += 0.05 * ((n % 11) - 5)
        ze.on_bar_1m("NIFTY", {"timestamp": day0 + timedelta(minutes=m, seconds=s),
                               "open": px, "high": px + 0.4, "low": px - 0.4,
                               "close": px, "volume": 100 + n % 50})
        n += 1
dm15, dm1 = ze.data_maps()
d15 = dm15["NIFTY"]
print(f"  1m bars built: {len(dm1['NIFTY'])}   15m bars built: {len(d15)}")
print(f"  15m columns: {list(d15.columns)}")
print(f"  15m index tz: {d15.index.tz}   monotonic: {d15.index.is_monotonic_increasing}")
print("  first 4 15m rows:")
print(d15.head(4).to_string())
# integrity
assert list(d15.columns) == ["open","high","low","close","volume"], "col mismatch"
assert d15.index.is_monotonic_increasing, "index not sorted"
assert (d15["high"] >= d15["low"]).all(), "H<L corruption"
assert (d15["high"] >= d15[["open","close"]].max(axis=1)).all(), "H < O/C corruption"
assert (d15["low"] <= d15[["open","close"]].min(axis=1)).all(), "L > O/C corruption"
assert not d15.isna().any().any(), "NaN in OHLCV"
print("  RESAMPLE INVARIANTS: PASS (no NaN, H>=L, H>=O/C, L<=O/C, sorted)")

# --- 3. zone detection accepts it ---
print()
print("=== TEST 3: detect_zones consumes it ===")
z = detect_zones(d15, len(d15) - 1, lookback=len(d15) - 1)
print(f"  zones detected: {len(z)}")
print("  ZONE ENGINE PIPELINE: END-TO-END PASS")
