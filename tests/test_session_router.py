"""Section 1: off-market blocking + hibernate + preopen resume."""
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import (NSE_Session_Active, MCX_Session_Active, entry_allowed,
                             mcx_close_time, session_router, should_hibernate)
IST = ZoneInfo("Asia/Kolkata")


def d(y, m, dd, hh, mm, ss=0):
    return datetime(y, m, dd, hh, mm, ss, tzinfo=IST)


def test_nse_session_window():
    assert NSE_Session_Active(d(2026, 9, 28, 9, 15)) is True
    assert NSE_Session_Active(d(2026, 9, 28, 9, 14, 59)) is False
    assert NSE_Session_Active(d(2026, 9, 28, 15, 30)) is False
    assert NSE_Session_Active(d(2026, 9, 28, 12, 0)) is True
    assert NSE_Session_Active(d(2026, 10, 3, 12, 0)) is False   # Saturday


def test_mcx_session_window_and_close():
    assert MCX_Session_Active(d(2026, 9, 28, 9, 0)) is True
    assert MCX_Session_Active(d(2026, 9, 28, 8, 59, 59)) is False
    assert mcx_close_time(d(2026, 9, 28, 12, 0)).hour == 23 and mcx_close_time(d(2026, 9, 28, 12, 0)).minute == 30
    assert mcx_close_time(d(2026, 12, 1, 12, 0)).hour == 23 and mcx_close_time(d(2026, 12, 1, 12, 0)).minute == 55
    assert MCX_Session_Active(d(2026, 9, 28, 23, 29)) is True
    assert MCX_Session_Active(d(2026, 9, 28, 23, 31)) is False


def test_hibernate_when_closed():
    assert should_hibernate("NSE", d(2026, 9, 28, 8, 0)) is True
    assert should_hibernate("NSE", d(2026, 9, 28, 10, 0)) is False
    assert should_hibernate("MCX", d(2026, 9, 28, 8, 30)) is True


def test_entry_allowed_blocks_offmarket_and_cutoff():
    assert entry_allowed("NSE", d(2026, 9, 28, 8, 0)) is False    # off-market
    assert entry_allowed("NSE", d(2026, 9, 28, 15, 5)) is False   # 15:00 cutoff
    assert entry_allowed("NSE", d(2026, 9, 28, 10, 0)) is True
    assert entry_allowed("MCX", d(2026, 9, 28, 20, 0)) is True
    assert entry_allowed("MCX", d(2026, 9, 28, 23, 20)) is False  # 23:15 cutoff


def test_router_reports_segments():
    r = session_router(d(2026, 9, 28, 10, 0))
    assert r["NSE"] and r["MCX"] and r["live"]
    r2 = session_router(d(2026, 9, 28, 20, 0))
    assert r2["NSE"] is False and r2["MCX"] is True
