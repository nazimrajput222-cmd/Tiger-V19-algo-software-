"""Section 2/3: gamma-blast + selection guardrails + LIMIT BUY payload."""
from datetime import datetime, timedelta

import pytest

from config import settings as S
from engine.executor import (DuplicateLock, build_limit_buy, build_limit_sell,
                             check_margin, round_to_tick)
from engine.scorer import (Quote, SIGNAL, WATCH, NOISE, blast_criteria, classify,
                           passes_guardrails, select_contract, spread_pct,
                           resolve_segment)


def test_classify_matrix():
    assert classify(69.9, "NSE") == WATCH
    assert classify(70.0, "NSE") == SIGNAL
    assert classify(59.9, "MCX") == WATCH
    assert classify(60.0, "MCX") == SIGNAL
    assert classify(54.9, "NSE") == NOISE


def test_resolve_segment():
    assert resolve_segment("CRUDEOIL") == "MCX"
    assert resolve_segment("GOLDM") == "MCX"
    assert resolve_segment("SILVERM") == "MCX"
    assert resolve_segment("NIFTY") == "NSE"
    assert resolve_segment("RELIANCE") == "NSE"


def q(strike, ot="CE", ltp=5.0, bid=4.9, ask=5.1, oi=5000, sym=None):
    return Quote(token="1", symbol=sym or f"NIFTY{strike}{ot}", strike=strike,
                 option_type=ot, ltp=ltp, bid=bid, ask=ask, oi=oi, lot=75)


def test_spread_guardrail_rejects_wide():
    bad = q(25000, ltp=5.0, bid=1.0, ask=5.0)   # 80% spread
    ok, why = passes_guardrails(bad, 25000)
    assert ok is False and "spread" in why
    good = q(25000, ltp=5.0, bid=4.95, ask=5.05)  # 2% ... still >1.5
    assert passes_guardrails(good, 25000)[0] is False
    tight = q(25000, ltp=5.0, bid=4.98, ask=5.02)  # 0.8%
    assert passes_guardrails(tight, 25000)[0] is True


def test_oi_floor_rejects_illiquid():
    thin = q(25000, oi=100)
    ok, why = passes_guardrails(thin, 25000)
    assert ok is False and "OI" in why


def test_select_cheapest_liquid_otm():
    quotes = [q(24000, ltp=2.0, bid=1.99, ask=2.01),   # cheap OTM, tight spread
              q(25000, ltp=8.0, bid=7.95, ask=8.05),   # ATM pricier
              q(26000, ltp=1.0, bid=0.2, ask=1.5)]    # 87% spread → rejected
    c, why = select_contract(quotes, 25000, "CE")
    assert c is not None and c.strike == 24000
    assert "rejected" in why


def test_blast_criteria_all_three():
    vols = [100.0] * 20
    ok = blast_criteria(delta=0.5, volume=500, volumes=vols, spot=25100, vwap=25000)
    assert ok and len(ok.reasons) == 3
    # delta too low
    assert not blast_criteria(0.2, 500, vols, 25100, 25000)
    # no volume spike
    assert not blast_criteria(0.5, 150, vols, 25100, 25000)
    # no vwap cross
    assert not blast_criteria(0.5, 500, vols, 24900, 25000)


def test_limit_buy_payload_uses_ask_plus_buffer():
    p = build_limit_buy(q(25000, ltp=5.0, bid=4.98, ask=5.02), 75)
    assert p["transaction_type"] == "BUY"
    assert p["order_type"] == "LIMIT"
    # 5.02 + 0.05 = 5.07 → tick 0.05 pe UP-round = 5.10 (fill guarantee)
    assert p["price"] == pytest.approx(5.10)
    assert p["quantity"] == 75
    assert p["reference_ask"] == 5.02


def test_limit_buy_rejects_non_option():
    fut = Quote(token="1", symbol="CRUDEOIL19NOV26FUT", strike=0, option_type="FUT",
                ltp=5000, bid=4999, ask=5001, oi=10000)
    with pytest.raises(ValueError):
        build_limit_buy(fut, 1)


def test_sell_refuses_to_open_short():
    """ALLOW_OPTION_SELLING=False: no long → no SELL (no new short)."""
    with pytest.raises(ValueError):
        build_limit_sell(q(25000, ot="CE"), 75, held_qty=0)
    p = build_limit_sell(q(25000, ot="CE"), 75, held_qty=75)
    assert p["transaction_type"] == "SELL" and p["quantity"] == 75


def test_sell_caps_at_held():
    p = build_limit_sell(q(25000, ot="CE"), 150, held_qty=75)
    assert p["quantity"] == 75


def test_duplicate_lock_blocks_same_strike_60s():
    lock = DuplicateLock(window=60)
    payload = build_limit_buy(q(25000), 75)
    now = datetime(2026, 9, 28, 10, 0)
    assert lock.allow(payload, now)[0] is True
    assert lock.allow(payload, now + timedelta(seconds=30))[0] is False
    assert lock.allow(payload, now + timedelta(seconds=61))[0] is True


def test_margin_check():
    ok, why = check_margin(100000, 50000)
    assert ok is True
    ok2, why2 = check_margin(52000, 50000)   # need 50k + 10% buffer = 55k
    assert ok2 is False and "buffer" in why2


def test_round_to_tick():
    assert round_to_tick(5.07, 0.05) == 5.10
    assert round_to_tick(5.02, 0.05) == 5.05
