p = '/home/ec2-user/tiger-brain-v6/automation/tiger_live.py'
s = open(p).read()

# ---------------------------------------------------------------------------
# Ghost-alert fix.
#
# The bridge re-sent the SAME trade every 5 minutes because the backtest
# replays the seeded window on each scan, and a trade dated today keeps
# re-matching. The user saw one frozen "HDFCBANK score=114.4 premium=0"
# alert repeated for hours.
#
# Two guards:
#   1. Dedup — one alert per (symbol, strike, entry_ts). Replays are silent.
#   2. Realness — a trade with no premium priced cannot be actionable, so
#      it is not announced as a SIGNAL at all. We say "n/a" instead of
#      printing a fake ₹0.00.
# ---------------------------------------------------------------------------

old_init = '''    # --- Telegram signal bridge (zone engine scores) ---
    WATCH_SCORE_ENV = "TIGER_WATCH_SCORE_MIN"'''
new_init = '''    # --- Telegram signal bridge (zone engine scores) ---
    WATCH_SCORE_ENV = "TIGER_WATCH_SCORE_MIN"
    # One alert per (symbol, strike, entry_ts). The backtest replays the
    # seeded window on every 5-min scan, so without this the same trade
    # re-announces forever.
    _alerted_trades: set = set()'''
assert old_init in s, 'init anchor not found'
s = s.replace(old_init, new_init, 1)

old = '''                # An already-closed trade is not an actionable alert.
                # Skip it — otherwise the user gets a "🚨 SIGNAL" for a
                # position that no longer exists.
                if t.get("exit_ts") is not None:
                    continue
'''
new = '''                # An already-closed trade is not an actionable alert.
                # Skip it — otherwise the user gets a "🚨 SIGNAL" for a
                # position that no longer exists.
                if t.get("exit_ts") is not None:
                    continue

                # DEDUP: the backtest replays the seeded window on every
                # scan, so the same (symbol, strike, entry_ts) reappears
                # each time. Announce it once, then stay quiet.
                _key = (sym, t.get("strike"), str(ts))
                if _key in self._alerted_trades:
                    continue
                self._alerted_trades.add(_key)
'''
assert old in s, 'dedup anchor not found'
s = s.replace(old, new, 1)

# realness guard: don't announce a SIGNAL we cannot price
old2 = '''                is_signal = score >= signal_min
                mkt = "MCX" if seg == "commodity" else "NSE"'''
new2 = '''                is_signal = score >= signal_min
                mkt = "MCX" if seg == "commodity" else "NSE"
                # A SIGNAL we cannot price is not actionable. Demote to
                # WATCH and say so, rather than announce a ₹0 order.
                if is_signal and prem is None:
                    is_signal = False
                    mkt = f"{mkt} (premium n/a — unpriced, not tradable)"'''
assert old2 in s, 'realness anchor not found'
s = s.replace(old2, new2, 1)

open(p, 'w').write(s)
print("FIXED: alert dedup + unpriced signals demoted to WATCH")
