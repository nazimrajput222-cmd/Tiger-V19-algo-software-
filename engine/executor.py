"""
Tiger Brain V6 — engine/executor.py
====================================
Order payload construction + execution guards.

Rules (hardcoded, config/settings.py):
  * transaction_type = 'BUY'   (ALWAYS, options premium only)
  * order_type      = 'LIMIT'  (NEVER market)
  * price           = Best Ask + 0.05
  * unfilled > 10s  → auto-cancel
  * same strike within 60s → blocked (mutex)
  * insufficient margin → abort + alarm

ALLOW_OPTION_SELLING = False ka matlab (dhyan se):
    Naya SELL entry (short/naked) BAN. Positions band karne ke liye SELL
    chahiye — stop-loss, trail, square-off. Isliye sell_leg() sirf tab
    allowed hai jab wahi contract pe long qty HOLD ho. Naya short nahi.
"""
from __future__ import annotations

import logging
import math
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

try:
    from config import settings as S
    from engine.scorer import Quote
except ImportError:
    raise ImportError("Repo ROOT se chalao")

logger = logging.getLogger("tiger_brain.engine.executor")

BUY, SELL, LIMIT, MARKET = "BUY", "SELL", "LIMIT", "MARKET"
INTRADAY, CARRYFORWARD = "INTRADAY", "CARRYFORWARD"


# ---------------------------------------------------------------------
# pre-trade checks
# ---------------------------------------------------------------------
class MarginError(RuntimeError):
    pass


def check_margin(free_margin: float, need: float) -> tuple:
    """(ok, reason). Required buffer rakhta hai."""
    if need <= 0:
        return False, "nothing to buy"
    buffer_need = need * S.MIN_MARGIN_BUFFER_PCT / 100.0
    if free_margin < need + buffer_need:
        return False, (f"margin: free ₹{free_margin:,.0f} < need ₹{need:,.0f} "
                       f"+{S.MIN_MARGIN_BUFFER_PCT:g}% buffer ₹{buffer_need:,.0f}")
    return True, "ok"


# ---------------------------------------------------------------------
# payload
# ---------------------------------------------------------------------
def round_to_tick(price: float, tick: float, up: bool = True) -> float:
    tick = tick if tick and tick > 0 else S.TICK_SIZE_DEFAULT
    steps = math.ceil(price / tick - 1e-9) if up else math.floor(price / tick + 1e-9)
    return round(steps * tick, 2)


def build_limit_buy(q: Quote, quantity: int, ask: float = None,
                    product: str = INTRADAY) -> dict:
    """
    LIMIT BUY payload. Price = Best Ask + 0.05 (fill guarantee ke liye),
    tick size pe rounded UP.
    """
    if q.option_type not in ("CE", "PE"):
        raise ValueError(f"options-only: {q.symbol} is {q.option_type}, not CE/PE")
    ref = ask if ask and ask > 0 else (q.ask if q.ask > 0 else q.ltp)
    if ref <= 0:
        raise ValueError(f"no price for {q.symbol} (ltp={q.ltp} ask={q.ask})")
    price = round_to_tick(ref + S.LIMIT_BUY_BUFFER, q.tick, up=True)
    return {
        "tradingsymbol": q.symbol,
        "symboltoken": q.token,
        "exchange": _exchange_for(q),
        "transaction_type": BUY,
        "order_type": LIMIT,
        "product_type": product,
        "quantity": int(quantity),
        "price": price,
        "limit_price": price,
        "reference_ask": round(ref, 2),
        "buffer": S.LIMIT_BUY_BUFFER,
    }


def _exchange_for(q: Quote) -> str:
    sym = (q.symbol or "").upper()
    if any(r in sym for r in ("GOLDM", "SILVERM", "CRUDEOIL", "GOLDM", "NATURALGAS",
                              "SILVER", "GOLD", "COPPER")):
        return "MCX"
    return "NFO"


def build_limit_sell(q: Quote, quantity: int, held_qty: int,
                     product: str = INTRADAY) -> dict:
    """
    SELL sirf tab — jitna hold karte hain, utna. Naya short kabhi nahi.
    raises agar held_qty <= 0 (matlab ye exit nahi, ye naya short ban jayega).
    """
    if held_qty <= 0:
        raise ValueError(
            f"ALLOW_OPTION_SELLING={S.ALLOW_OPTION_SELLING}: no long position on "
            f"{q.symbol} — refusing to open a short")
    qty = min(int(quantity), int(held_qty))
    ref = q.bid if q.bid > 0 else q.ltp
    price = round_to_tick(ref - S.LIMIT_BUY_BUFFER, q.tick, up=False)
    return {
        "tradingsymbol": q.symbol,
        "symboltoken": q.token,
        "exchange": _exchange_for(q),
        "transaction_type": SELL,
        "order_type": LIMIT,
        "product_type": product,
        "quantity": qty,
        "price": price,
        "reference_bid": round(ref, 2),
    }


# ---------------------------------------------------------------------
# duplicate execution mutex
# ---------------------------------------------------------------------
class DuplicateLock:
    """Same strike pe 60s ke andar dobara order = BLOCKED."""

    def __init__(self, window: float = S.DUPLICATE_WINDOW_SEC):
        self.window = timedelta(seconds=window)
        self._seen: dict = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(payload: dict) -> str:
        return f"{payload.get('tradingsymbol')}|{payload.get('transaction_type')}|{payload.get('quantity')}"

    def allow(self, payload: dict, now: datetime = None) -> tuple:
        now = now or datetime.now()
        k = self.key(payload)
        with self._lock:
            prev = self._seen.get(k)
            if prev and now - prev < self.window:
                left = self.window - (now - prev)
                return False, f"duplicate {k} blocked ({left.seconds}s left in 60s window)"
            self._seen[k] = now
            # purge stale
            for kk in [x for x, t in self._seen.items() if now - t >= self.window]:
                self._seen.pop(kk, None)
            return True, "ok"


# ---------------------------------------------------------------------
# 10-second unfilled auto-cancel
# ---------------------------------------------------------------------
@dataclass
class OrderResult:
    placed: bool
    status: str
    order_id: Optional[str] = None
    filled_qty: int = 0
    avg_price: float = 0.0
    reason: str = ""
    cancelled_after_s: float = 0.0


def place_with_watchdog(broker, payload: dict, dup: DuplicateLock = None,
                        timeout: float = S.UNFILLED_CANCEL_SEC,
                        sleep: Callable[[float], None] = _time.sleep,
                        clock: Callable[[], float] = _time.monotonic) -> OrderResult:
    """
    LIMIT order place → poll. UNFILLED rahe to timeout par auto-cancel.
    """
    if dup is not None:
        ok, why = dup.allow(payload)
        if not ok:
            logger.warning("🚫 %s", why)
            return OrderResult(False, "DUPLICATE_BLOCKED", reason=why)

    placed = broker.place_option_order(
        tradingsymbol=payload["tradingsymbol"], symboltoken=payload["symboltoken"],
        exchange=payload["exchange"], transaction_type=payload["transaction_type"],
        quantity=payload["quantity"], product_type=payload["product_type"],
        order_type=payload["order_type"], price=payload["price"],
    )
    if not placed.get("success"):
        return OrderResult(False, "REJECTED", reason=str(placed.get("error")))

    oid = placed["order_id"]
    start = clock()
    polls = max(1, int(timeout / 0.5))
    for i in range(polls):
        st = broker.get_order_status(oid)
        state = str(st.get("status", "")).lower()
        filled = int(st.get("filled_qty") or 0)
        if state in ("complete", "rejected", "cancelled", "canceled"):
            return OrderResult(True, state.upper(), oid, filled,
                               float(st.get("avg_price") or payload["price"]))
        if filled >= payload["quantity"]:
            return OrderResult(True, "PARTIAL", oid, filled,
                               float(st.get("avg_price") or payload["price"]))
        if i < polls - 1:
            sleep(0.5)

    # ---- 10s unfilled → cancel ----
    elapsed = clock() - start
    logger.warning("⏱️ Order %s unfilled after %.0fs — auto-cancel", oid, elapsed)
    broker.cancel_order(oid)
    st = broker.get_order_status(oid)
    filled = int(st.get("filled_qty") or 0)
    return OrderResult(True, "CANCELLED_UNFILLED", oid, filled,
                       float(st.get("avg_price") or payload["price"]),
                       reason=f"cancelled after {elapsed:.1f}s unfilled",
                       cancelled_after_s=elapsed)
