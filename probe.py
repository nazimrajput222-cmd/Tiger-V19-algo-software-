import sys, logging
sys.path.insert(0, '/home/ec2-user/tiger-brain-v6')
logging.disable(logging.CRITICAL)
from collections import Counter
from broker.angel_connect import AngelBroker
from data.loader import load_angel_instrument_master
from universe.dynamic_fno import build_daily_universe
from config.thresholds import BRAIN3, WS_V2

b = AngelBroker(); b.login()
master = load_angel_instrument_master()
roots = WS_V2.get("MCX_ALLOWED_ROOTS") or ()
uni = build_daily_universe(master, min_days_to_expiry=BRAIN3["MIN_DAYS_TO_EXPIRY"],
                           mcx_roots=tuple(roots) or None)
print("=== UNIVERSE ===")
print("TOTAL SUBSCRIBED UNDERLYINGS:", len(uni))
print("BY_KIND:", dict(Counter(u.kind for u in uni)))
print("BY_SESSION:", dict(Counter(u.session for u in uni)))
print("BY_EXCHANGE:", dict(Counter(u.stream_exchange for u in uni)))
print()
print("=== INDEX TOKENS (%d) ===" % sum(1 for u in uni if u.kind=="INDEX"))
for u in sorted(uni, key=lambda x: x.name):
    if u.kind == "INDEX":
        print(f"  {u.name:12s} tok={u.stream_token:12s} exch={u.stream_exchange:5s} sym={u.stream_symbol}")
print()
print("=== COMMODITY TOKENS (%d) ===" % sum(1 for u in uni if u.kind=="COMMODITY"))
for u in sorted(uni, key=lambda x: x.name):
    if u.kind == "COMMODITY":
        print(f"  {u.name:12s} tok={u.stream_token:12s} exch={u.stream_exchange:5s} sym={u.stream_symbol}")
print()
stocks = sorted([u for u in uni if u.kind == "STOCK"], key=lambda x: x.name)
print("=== STOCK TOKENS (count=%d) — ALL ===" % len(stocks))
for u in stocks:
    print(f"  {u.name:14s} tok={u.stream_token:12s} exch={u.stream_exchange:5s} sym={u.stream_symbol}")
