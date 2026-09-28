"""Fail-closed calendar: unknown year = no trading (NOT an assumed trading day)."""
import json
from datetime import date

import pytest

import automation.holidays as H
from automation.scheduler import get_day_mode


def test_known_2026_holidays_still_block():
    assert H.is_market_holiday(date(2026, 10, 2))[0] is True
    assert get_day_mode(__import__("datetime").datetime(2026, 10, 2, 10, 0)) == "OFF"


def test_normal_trading_day_unaffected():
    assert H.is_market_holiday(date(2026, 9, 30))[0] is False
    assert get_day_mode(__import__("datetime").datetime(2026, 9, 30, 10, 0)) == "TRADING"


def test_unknown_year_fails_closed(monkeypatch):
    """2027 ki list nahi → holiday maano, trading mat maano."""
    monkeypatch.setattr(H, "CALENDAR_YEARS", {2026})
    ok, name = H.is_market_holiday(date(2027, 1, 26))
    assert ok is True and "fail-closed" in name
    import datetime
    assert get_day_mode(datetime.datetime(2027, 1, 26, 10, 0)) == "OFF"


def test_load_valid_holiday_file(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "CALENDAR_YEARS", {2026})
    p = tmp_path / "2027.json"
    p.write_text(json.dumps({"year": 2027, "source": "NSE circular X",
                             "nse": {"2027-01-26": "Republic Day"},
                             "mcx_full_closed": {"2027-01-26": "Republic Day"}}))
    year = H.load_holiday_file(str(p))
    assert year == 2027
    assert H.is_market_holiday(date(2027, 1, 26)) == (True, "Republic Day")


@pytest.mark.parametrize("bad", [
    {"year": 2027, "nse": {"2027-01-26": "X"}},                       # no source
    {"year": 2027, "source": "X", "nse": {}},                          # empty
    {"year": 2027, "source": "X", "nse": {"2026-01-26": "wrong year"}}, # wrong year
])
def test_invalid_files_rejected(tmp_path, bad):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        H.load_holiday_file(str(p))


def test_december_reminder():
    assert H.calendar_reminder(date(2026, 12, 1)) is not None
    assert H.calendar_reminder(date(2026, 11, 30)) is None


def test_template_is_not_loaded():
    import os
    assert os.path.exists(os.path.join(H.HOLIDAY_DIR, "TEMPLATE.json.example"))
    assert 2027 not in H.CALENDAR_YEARS
