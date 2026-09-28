"""SAFETY: original 84724d6 order path mein DRY_RUN gate nahi tha — real order chala jaata.
Ab DRY_RUN=true pe koi bhi order place nahi hona chahiye."""
from datetime import datetime

import automation.tiger_live as tl


class Broker:
    def __init__(self):
        self.orders = []
        self.session_data = {"data": []}

    def is_session_valid(self):
        return True

    def get_balance(self):
        return 100000.0

    def get_positions(self):
        return []

    def place_option_order(self, **kw):
        self.orders.append(kw)
        return {"success": True, "order_id": "1", "error": None}


def runner(monkeypatch, dry):
    monkeypatch.setitem(tl.DRY_RUN, "__x__", None) if False else None
    import config.thresholds as th
    monkeypatch.setattr(th, "DRY_RUN", dry)
    monkeypatch.setattr(tl, "DRY_RUN", dry)
    r = tl.TigerLiveRunner()
    r.broker = Broker()
    return r


TRADES = [{"symbol": "NIFTY", "entry_ts": datetime.now(), "exit_ts": None,
           "strike": 25000, "option_type": "CE", "quantity": 75, "score": 88,
           "entry_price": 100.0, "action": "BUY", "is_delivery": False,
           "lot_size": 75, "expiry": "06OCT2026", "option_type_raw": "CE"}]


def test_dry_run_places_no_entry_order(monkeypatch):
    r = runner(monkeypatch, True)
    n = r._place_live_orders(TRADES)
    assert n == 0
    assert r.broker.orders == []


def test_dry_run_places_no_exit_order(monkeypatch):
    r = runner(monkeypatch, True)
    assert r._place_exit_orders([{"symbol": "NIFTY"}]) == 0
    assert r.broker.orders == []


def test_dry_run_signal_is_logged(monkeypatch, caplog):
    r = runner(monkeypatch, True)
    msgs = []
    r.notifier = type("N", (), {"notify": staticmethod(msgs.append)})()
    r._place_live_orders(TRADES)
    assert any("DRY_RUN" in m for m in msgs)


def test_zone_engine_is_seeded_from_warmup(monkeypatch):
    """Bina warm-up ke zone engine 40-bar lookback poora hi nahi kar pata."""
    import pandas as pd
    import config.thresholds as th
    monkeypatch.setattr(th, "WS_V2", dict(th.WS_V2, ENABLED=True))
    monkeypatch.setattr(tl, "WS_V2", dict(tl.WS_V2, ENABLED=True))
    r = tl.TigerLiveRunner()
    r.broker = Broker()
    idx = pd.date_range("2026-09-20 09:15", periods=60, freq="15min")
    df15 = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                         "volume": 100.0}, index=idx)
    df1 = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
                        "volume": 10.0}, index=pd.date_range("2026-09-28 09:15",
                                                             periods=60, freq="1min"))
    r.data_map, r.data_map_1m = {"NIFTY": df15}, {"NIFTY": df1}
    r.zone_engine.seed("NIFTY", df1, df15)
    dm, dm1 = r.zone_engine.data_maps()
    assert len(dm["NIFTY"]) >= 50 and len(dm1["NIFTY"]) >= 50
    # seeded maps engine ko milti hain
    got15, got1 = r._live_data_maps()
    assert "NIFTY" in got15 and "NIFTY" in got1
