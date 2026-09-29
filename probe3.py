import sys, logging
sys.path.insert(0, '/home/ec2-user/tiger-brain-v6')
logging.disable(logging.CRITICAL)
from collections import Counter
from broker.angel_connect import AngelBroker
from data.loader import load_angel_instrument_master
from universe.dynamic_fno import build_daily_universe
from config.thresholds import BRAIN3, WS_V2
import data.tick_bars as tb, inspect
print("BAR_COLS in tick_bars:", getattr(tb, "BAR_COLS", "n/a"))
b = AngelBroker(); b.login()
master = load_angel_instrument_master()
roots = WS_V2.get("MCX_ALLOWED_ROOTS") or ()
uni = build_daily_universe(master, min_days_to_expiry=BRAIN3["MIN_DAYS_TO_EXPIRY"], mcx_roots=tuple(roots) or None)
print("MCX symbols (extra 1m bars beyond 220 NSE):")
for u in uni:
    if u.kind == "COMMODITY": print("  ", u.name, u.stream_token)
print()
print("NSE count:", sum(1 for u in uni if u.session=="NSE"), "| MCX count:", sum(1 for u in uni if u.session=="MCX"))
print("=> expected bars/min = NSE(%d) + MCX_if_trading(%d)" % (
    sum(1 for u in uni if u.session=="NSE"), sum(1 for u in uni if u.session=="MCX")))
