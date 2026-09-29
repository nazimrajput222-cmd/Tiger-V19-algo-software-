import sys, logging
sys.path.insert(0, '/home/ec2-user/tiger-brain-v6')
logging.disable(logging.CRITICAL)
from datetime import datetime, timedelta
import random
from automation.live_zone_engine import LiveZoneEngine
from pipeline.intraday_strategies import detect_zones
random.seed(42)
ze = LiveZoneEngine(max_bars_15m=500, max_bars_1m=5000)
day0 = datetime(2026, 9, 1, 9, 15, 0)
px = 25000.0
# 5 trading days x 375 min, with impulse moves so S/D zones form
for day in range(5):
    for m in range(375):
        for s in range(0, 60, 15):
            r = random.random()
            if r > 0.97: px += random.uniform(-180, 180)   # impulse
            else: px += random.uniform(-6, 6)
            ze.on_bar_1m("NIFTY", {"timestamp": day0 + timedelta(days=day, minutes=m, seconds=s),
                                   "open": px, "high": px + 2, "low": px - 2,
                                   "close": px, "volume": random.randint(200, 3000)})
dm15, _ = ze.data_maps()
d15 = dm15["NIFTY"]
print(f"15m bars total: {len(d15)}")
for i in (40, 60, len(d15)-1):
    z = detect_zones(d15, i, lookback=i)
    print(f"  detect_zones(i={i}) -> {len(z)} zones" + ("" if i>=40 else "   [below 40-bar lookback min]"))
last = detect_zones(d15, len(d15)-1, lookback=len(d15)-1)
if last:
    z0 = last[0]
    print(f"  sample zone: type={z0.get('type')} top={z0.get('top'):.2f} bottom={z0.get('bottom'):.2f} score={z0.get('score')}")
print("ZONE DETECTION: WORKING" if last else "ZONE DETECTION: still 0")
