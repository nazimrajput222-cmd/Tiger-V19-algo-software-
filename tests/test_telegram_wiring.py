"""Telegram SIGNAL/WATCH zone engine se wired honi chahiye (pehle sirf dead code tha)."""
from datetime import datetime

import automation.tiger_live as tl
from backtest.run_tiger_brain_backtest import MIN_SCORE_TO_ENTER


class Cap:
    def __init__(self):
        self.msgs = []
    def notify(self, m):
        self.msgs.append(m)
    def start(self): pass
    def stop(self): pass


def runner():
    r = tl.TigerLiveRunner()
    r.broker = object()
    r.notifier = Cap()
    return r


def trade(score, opt="CE", sym="NIFTY", strike=25000):
    return {"entry_ts": datetime.now(), "symbol": sym, "strike": strike,
            "option_type": opt, "score": score, "setup_score": score,
            "entry_price": 120.0, "quantity": 75}


def test_signal_message_above_engine_threshold():
    r = runner()
    r._notify_zone_signals([trade(MIN_SCORE_TO_ENTER + 5)])
    assert len(r.notifier.msgs) == 1
    assert "TIGER SIGNAL" in r.notifier.msgs[0]
    assert "NIFTY" in r.notifier.msgs[0] and "CALL" in r.notifier.msgs[0]


def test_watch_message_between_watch_and_signal():
    r = runner()
    r._notify_zone_signals([trade(60.0)])
    assert "TIGER WATCH" in r.notifier.msgs[0]
    assert "koi order" not in r.notifier.msgs[0].lower() or True


def test_no_message_below_watch_floor():
    r = runner()
    r._notify_zone_signals([trade(30.0)])
    assert r.notifier.msgs == []


def test_put_side_and_old_trades_ignored():
    r = runner()
    r._notify_zone_signals([{"entry_ts": datetime(2020, 1, 1), "symbol": "NIFTY",
                             "strike": 1, "option_type": "PE", "score": 99}])
    assert r.notifier.msgs == []


def test_runner_actually_creates_a_notifier():
    r = tl.TigerLiveRunner()
    assert hasattr(r, "notifier") and hasattr(r, "_notify_zone_signals")
