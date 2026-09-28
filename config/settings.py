"""
Tiger Brain V6 — production settings (single source of truth)
=============================================================
Yahan se har execution-relevant constant nikalti hai. Deliberate rule:

    EXECUTION_MODE == "LIVE_REAL_MONEY"  →  DRY_RUN is FORCED False.

Matlab koi environment variable, koi .edit, koi manual change DRY_RUN ko
wapas True nahi kar sakta jab tak EXECUTION_MODE LIVE_REAL_MONEY hai. Ye
"dry-run override prevention" hai: ek typo se accidentally paper-trading pe
girna nahi chahiye, aur ek bewakoof change se live pe girna bhi nahi chahiye.

ALLOW_OPTION_SELLING ka matlab (dhyan se):
    False = koi NAYA short/naked SELL entry nahi. Sirf long premium BUY.
    Ye option-SELLING ko block NAHI karta — positions band karne ke liye
    SELL zaroori hai (stop-loss, trail, target, square-off). Agar ye
    literally implement hota ki koi SELL nahi ja sakta, to ek galat trade
    par position kabhi nahi nikalti = unlimited loss + broker auto-square-off
    par depend. Isliye: SELL sirf tab allowed hai jab wahi token pe long
    position HOLD ho rahi ho. Naya short kabhi nahi.
"""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# ---------------------------------------------------------------------
# 1. ENVIRONMENT / PROCESS LOCK (hardcoded defaults)
# ---------------------------------------------------------------------
TIGER_BRAIN_DRY_RUN = False          # hardcoded
EXECUTION_MODE = "LIVE_REAL_MONEY"   # hardcoded
ALLOW_OPTION_SELLING = False         # naya short nahi; exit SELL allowed

_NSE_SIGNAL = float(os.getenv("TIGER_NSE_SIGNAL_SCORE", "70"))
_NSE_WATCH = float(os.getenv("TIGER_NSE_WATCH_SCORE", "55"))
_MCX_SIGNAL = float(os.getenv("TIGER_MCX_SIGNAL_SCORE", "60"))
_MCX_WATCH = float(os.getenv("TIGER_MCX_WATCH_SCORE", "55"))

SEGMENT_RULES = {
    "NSE": {"SIGNAL": _NSE_SIGNAL, "WATCH": _NSE_WATCH},
    "MCX": {"SIGNAL": _MCX_SIGNAL, "WATCH": _MCX_WATCH},
}

# MCX underlying futures jo scan hote hain
MCX_UNDERLYINGS = tuple(
    r.strip().upper() for r in
    os.getenv("TIGER_MCX_ROOTS", "GOLDM,SILVERM,CRUDEOIL").split(",") if r.strip()
)

# ---------------------------------------------------------------------
# 2. BLAST / SELECTION GUARDRAILS
# ---------------------------------------------------------------------
DELTA_VELOCITY_MIN = 0.35      # delta expansion velocity floor
VOLUME_SMA_MULT = 3.0          # volume > 3x 20-period SMA
VOLUME_SMA_PERIOD = 20
MIN_OPEN_INTEREST = 1000       # minimum OI — strikes eliminate karne ke liye
MAX_SPREAD_PCT = 1.5           # (Ask-Bid)/Ask <= 1.5%
MIN_PREMIUM = 0.5              # inr, zero-premium avoid
MAX_PREMIUM = 500.0            # inr
CHEAP_PREFERENCE_PCT = 2.0     # premium as % of underlying (premium_max_pct_of_underlying)
LIMIT_BUY_BUFFER = 0.05        # Best Ask + 0.05
TICK_SIZE_DEFAULT = 0.05

# ---------------------------------------------------------------------
# 3. EXECUTION CONTROLS
# ---------------------------------------------------------------------
UNFILLED_CANCEL_SEC = 10.0
DUPLICATE_WINDOW_SEC = 60.0
MAX_POSITION_VALUE_PCT = 100.0  # full capital allowed at signal
MIN_MARGIN_BUFFER_PCT = 10.0    # required free margin buffer

# ---------------------------------------------------------------------
# 4. SESSIONS (IST)
# ---------------------------------------------------------------------
NSE_OPEN = time(9, 15)
NSE_CLOSE = time(15, 30)
MCX_OPEN = time(9, 0)
MCX_CLOSE_WINTER = time(23, 55)   # US standard time
MCX_CLOSE_DST = time(23, 30)      # US daylight time
NSE_PREOPEN = time(9, 14, 0)      # resume 60s before
MCX_PREOPEN = time(8, 59, 0)
NSE_LAST_ENTRY = time(15, 0)
MCX_LAST_ENTRY = time(23, 15)


def _us_dst_active(d) -> bool:
    def nth_sunday(year, month, n):
        first = d.replace(day=1, month=month, year=year)
        offset = (6 - first.weekday()) % 7
        return first.replace(day=1 + offset + 7 * (n - 1))
    return nth_sunday(d.year, 3, 2) <= d < nth_sunday(d.year, 11, 1)


def mcx_close_time(check_date=None) -> time:
    d0 = check_date or datetime.now(IST)
    check_date = d0.date() if isinstance(d0, datetime) else d0
    return MCX_CLOSE_DST if _us_dst_active(check_date) else MCX_CLOSE_WINTER


def _active(now: datetime, open_t: time, close_t: time) -> bool:
    # now.time() already ek datetime.time deta hai — uspar .time() nahi.
    return now.weekday() < 5 and open_t <= now.time() < close_t


def NSE_Session_Active(now: datetime = None) -> bool:
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    return _active(now, NSE_OPEN, NSE_CLOSE)


def MCX_Session_Active(now: datetime = None) -> bool:
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    close = mcx_close_time(now.date())
    return _active(now, MCX_OPEN, close)


def session_router(now: datetime = None) -> dict:
    now = now or datetime.now(IST)
    nse = NSE_Session_Active(now)
    mcx = MCX_Session_Active(now)
    return {
        "now_ist": now,
        "NSE": nse,
        "MCX": mcx,
        "live": nse or mcx,
        "segments": [s for s, on in (("NSE", nse), ("MCX", mcx)) if on],
    }


def should_hibernate(segment: str, now: datetime = None) -> bool:
    return not session_router(now)[segment]


def entry_allowed(segment: str, now: datetime = None) -> bool:
    now = now or datetime.now(IST)
    if not session_router(now)[segment]:
        return False
    cutoff = NSE_LAST_ENTRY if segment == "NSE" else MCX_LAST_ENTRY
    return now.time() < cutoff
