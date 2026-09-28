"""
Tiger Brain V6+V7 — NSE Holiday Calendar (Section 34 ka gap-fix)
===================================================================
Weekday logic (Mon-Fri trading, Sat/Sun off) apne aap sahi hai, par
declared market holidays (Diwali, Holi, Republic Day, etc.) alag se
maintain karni padti hain — NSE har saal apna circular nikalta hai.

⚠️ IMPORTANT — Ye list MANUALLY update karni padegi har saal:
Source: NSE India ke official "Trading Holidays" circular (nseindia.com)
Last verified: 2026 list, cross-checked via Zerodha's holiday calendar
(zerodha.com/marketintel/holiday-calendar) as of Aug 2026.

NSE beech saal mein bhi circular nikal ke calendar revise kar sakta hai
(jaisa Bajaj AMC ki site pe likha tha) — isliye ye list "best available
at time of writing" hai, gospel truth nahi. Naye saal (2027+) ke liye ye
list dobara update karni hogi — NSE ki site ya apne broker ki holiday
calendar page check karke.
"""

from __future__ import annotations

import os
from datetime import date

# 2026 NSE Equity/F&O trading holidays (jab exchange PURA band rehta hai)
# Format: date(year, month, day): "naam"
NSE_HOLIDAYS_2026 = {
    date(2026, 1, 15): "Municipal Corporation Elections in Maharashtra",
    date(2026, 1, 26): "Republic Day",
    date(2026, 3, 3): "Holi",
    date(2026, 3, 26): "Shri Ram Navami",
    date(2026, 3, 31): "Shri Mahavir Jayanti",
    date(2026, 4, 3): "Good Friday",
    date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
    date(2026, 5, 1): "Maharashtra Day",
    date(2026, 5, 28): "Bakri Eid",
    date(2026, 6, 26): "Moharram",
    date(2026, 9, 14): "Ganesh Chaturthi",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 10, 20): "Dussehra",
    date(2026, 11, 10): "Diwali-Balipratipada",
    date(2026, 11, 24): "Prakash Gurpurb Sri Guru Nanak Dev",
    date(2026, 12, 25): "Christmas",
}

# ⚠️ NOTE: 8 Nov 2026 (Diwali Laxmi Pujan) Sunday ko already hai, isliye
# already OFF day hai — par us din SPECIAL "Muhurat Trading" session hota
# hai (thodi der ke liye market khulta hai, sirf symbolic trading ke liye).
# Ye system abhi Muhurat Trading handle NAHI karta — agar Muhurat mein
# trade karna ho to ye ek manual override hoga, automate nahi kiya hai.
MUHURAT_TRADING_DATES_2026 = {
    date(2026, 11, 8): "Diwali Laxmi Pujan — Muhurat Trading (special short session)",
}


# Jin saalon ki list upar maujood hai. Iske bahar ke saal ke liye holiday
# ka jawab "pata nahi" hai — unhe seedha trading day maan lena galat
# missing-session alerts paida karta hai.
CALENDAR_YEARS = {2026}


def has_holiday_calendar(year: int) -> bool:
    """Kya is saal ki NSE holiday list is repo mein maujood hai?"""
    return year in CALENDAR_YEARS


# MCX jin dino POORA din band hai (morning + evening). Baaki NSE holidays pe
# MCX ka morning band aur evening (17:00+) khula rehta hai — MCX standard practice.
# Source: Zerodha holiday calendar "MCX holidays" section (2026).
MCX_FULL_CLOSED = {
    date(2026, 1, 26): "Republic Day",
    date(2026, 4, 3): "Good Friday",
    date(2026, 8, 15): "Independence Day",
    date(2026, 10, 2): "Mahatma Gandhi Jayanti",
    date(2026, 11, 8): "Diwali Laxmi Pujan (Muhurat only)",
    date(2026, 12, 25): "Christmas",
}

# Saal jin ki official list repo mein hai. Is list ke bahar ke saal
# FAIL-CLOSED hote hain (neeche dekho) — andaza wali dates kabhi nahi.
CALENDAR_YEARS = {2026}
CALENDAR_SOURCES = {2026: "NSE trading holidays 2026 (exchange circular)"}


def calendar_known(year: int) -> bool:
    return year in CALENDAR_YEARS


def load_holiday_file(path: str) -> int:
    """
    config/holidays/<year>.json load karo. Strict validation:
      * 'source' (official circular ref) likhna ZAROORI hai
      * har date usi saal ki honi chahiye
      * list khali nahi honi chahiye
    Galat file → ValueError (adhoori list kabhi load nahi hoti).
    """
    import json
    import os
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    year = int(raw["year"])
    if not raw.get("source"):
        raise ValueError(f"{path}: 'source' (official circular ref) zaroori hai")
    nse = {}
    for k, v in (raw.get("nse") or {}).items():
        d = date.fromisoformat(k)
        if d.year != year:
            raise ValueError(f"{path}: {k} saal {year} ka nahi hai")
        nse[d] = str(v)
    mcx = {}
    for k, v in (raw.get("mcx_full_closed") or {}).items():
        d = date.fromisoformat(k)
        if d.year != year:
            raise ValueError(f"{path}: {k} saal {year} ka nahi hai")
        mcx[d] = str(v)
    if not nse:
        raise ValueError(f"{path}: 'nse' list khali hai")
    NSE_HOLIDAYS_2026.update(nse)
    MCX_FULL_CLOSED.update(mcx)
    CALENDAR_YEARS.add(year)
    CALENDAR_SOURCES[year] = str(raw["source"])
    return year


def load_holiday_dir(directory: str = None) -> list:
    directory = directory or HOLIDAY_DIR
    loaded = []
    if not os.path.isdir(directory):
        return loaded
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        try:
            loaded.append(load_holiday_file(path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"[holidays] ERROR load {path}: {exc} — us saal ka calendar UNKNOWN")
    return loaded


def is_market_holiday(check_date: date) -> tuple:
    """
    Args:
        check_date: datetime.date object (datetime.datetime bhi chalega,
                     .date() karke pass karo agar zarurat pade)

    Returns:
        (bool, str | None) — (True/False, holiday ka naam ya None)
    """
    if hasattr(check_date, "date") and callable(check_date.date):
        check_date = check_date.date()

    if check_date in NSE_HOLIDAYS_2026:
        return True, NSE_HOLIDAYS_2026[check_date]

    if check_date.year not in CALENDAR_YEARS:
        # FAIL-CLOSED: is saal ki official list nahi → pata hi nahi ki kaunsa
        # din holiday hai. Andaze se trading day maanna = holiday pe order.
        return True, (f"⚠️ {check_date.year} ki holiday list load nahi — "
                      f"fail-closed (config/holidays/{check_date.year}.json chahiye)")

    return False, None


# JSON holiday files (agle saalon ke official lists) load karo
HOLIDAY_DIR = os.getenv(
    "TIGER_HOLIDAY_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "config", "holidays"),
)
load_holiday_dir()


def calendar_reminder(check_date: date = None) -> str | None:
    """1 December se agle saal ki list missing ho → reminder message."""
    d0 = check_date or date.today()
    d = d0.date() if hasattr(d0, "date") else d0
    nxt = d.year + 1
    if d.month == 12 and nxt not in CALENDAR_YEARS:
        return (f"📅 {nxt} ki NSE holiday list load nahi. Official circular aate hi "
                f"config/holidays/{nxt}.json daalo — warna {nxt} se trading fail-closed rahegi.")
    return None


# ============================================================
# QUICK MANUAL TEST
# Chalane ka tarika: repo ROOT se → python3 -m automation.holidays
# ============================================================
if __name__ == "__main__":
    from datetime import datetime

    print("=== NSE Holiday Check Test ===\n")

    test_dates = [
        date(2026, 1, 26),   # Republic Day — holiday
        date(2026, 3, 3),    # Holi — holiday
        date(2026, 6, 15),   # Random normal trading day
        datetime(2026, 12, 25, 10, 30),  # Christmas, as datetime not date
    ]

    for d in test_dates:
        is_holiday, name = is_market_holiday(d)
        print(f"{d}: {'HOLIDAY (' + name + ')' if is_holiday else 'normal trading day'}")

    print(f"\nTotal holidays loaded for 2026: {len(NSE_HOLIDAYS_2026)}")
    print("\n✅ Test complete — koi crash nahi hua.")
    print(
        "⚠️ REMINDER: Ye list 2026 ke liye hai. Har naye saal (2027 se) "
        "isko NSE ke official circular se update karna zaroori hai, warna "
        "system holiday ke din bhi 'trading day' samjhega."
)
  
