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
