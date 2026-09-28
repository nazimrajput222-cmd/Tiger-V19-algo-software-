"""LIVE order path ab engine/ guardrails use karta hai — MARKET nahi, LIMIT."""
import inspect

import automation.tiger_live as tl
from engine.executor import DuplicateLock, build_limit_buy, place_with_watchdog
from engine.scorer import Quote, passes_guardrails


def test_entry_path_uses_limit_not_market():
    src = inspect.getsource(tl.TigerLiveRunner._place_live_orders)
    assert 'order_type="MARKET"' not in src, "entry path mein MARKET order zinda hai"
    assert "build_limit_buy" in src and "place_with_watchdog" in src
    assert "DuplicateLock" in src


def test_entry_path_enforces_all_three_guardrails():
    src = inspect.getsource(tl.TigerLiveRunner._place_live_orders)
    assert "passes_guardrails" in src      # OI >= 1000 + spread <= 1.5%
    assert "check_margin" in src           # margin buffer
    assert "register_option_quote" in src  # real bid/ask/OI from WS


def test_pipe_collects_option_quotes():
    src = inspect.getsource(tl.WSZonePipe.on_tick)
    assert "_quote_tokens" in src and "best_bid" in src and "best_ask" in src and "oi" in src
    assert inspect.getsource(tl.WSZonePipe.register_option_quote).count("MODE_SNAP_QUOTE") == 1


def _q(**kw):
    d = dict(token="1", symbol="NIFTY25000CE", strike=25000, option_type="CE",
             ltp=5.0, bid=4.98, ask=5.02, oi=5000, lot=75)
    d.update(kw)
    return Quote(**d)


def test_guardrail_rejects_thin_oi():
    ok, why = passes_guardrails(_q(oi=500), 25000)
    assert ok is False and "OI" in why


def test_guardrail_rejects_wide_spread():
    ok, why = passes_guardrails(_q(bid=1.0, ask=5.0), 25000)
    assert ok is False and "spread" in why


def test_guardrail_accepts_healthy():
    assert passes_guardrails(_q(), 25000)[0] is True


def test_limit_price_is_ask_plus_buffer():
    p = build_limit_buy(_q(), 75)
    assert p["order_type"] == "LIMIT" and p["transaction_type"] == "BUY"
    assert p["price"] == 5.10          # 5.02 + 0.05, rounded up to tick


class B:
    def __init__(self, statuses):
        self.statuses, self.orders, self.cancels = list(statuses), [], []
    def place_option_order(self, **kw):
        self.orders.append(kw); return {"success": True, "order_id": "O1"}
    def get_order_status(self, oid):
        return self.statuses.pop(0) if self.statuses else {"status": "complete",
                                                            "filled_qty": 75,
                                                            "avg_price": 5.1}
    def cancel_order(self, oid):
        self.cancels.append(oid); return True


def test_unfilled_order_auto_cancelled_after_10s():
    br = B([{"status": "open", "filled_qty": 0, "avg_price": 0}] * 40 +
           [{"status": "cancelled", "filled_qty": 0, "avg_price": 0}])
    r = place_with_watchdog(br, build_limit_buy(_q(), 75), DuplicateLock(),
                            sleep=lambda s: None, clock=lambda: 0.0)
    assert r.status == "CANCELLED_UNFILLED"
    assert br.cancels == ["O1"]


def test_duplicate_lock_blocks_second_order_in_60s():
    br = B([])
    lock = DuplicateLock()
    p = build_limit_buy(_q(), 75)
    assert place_with_watchdog(br, p, lock, sleep=lambda s: None).placed is True
    r2 = place_with_watchdog(br, p, lock, sleep=lambda s: None)
    assert r2.status == "DUPLICATE_BLOCKED" and len(br.orders) == 1
