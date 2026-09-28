"""
Tiger Brain V6 — engine/scorer.py
=================================
Segment routing + score matrix + "gamma-blast" contract selection.

Yeh layer ZONE strategy ko replace NAHI karti. Uski rooh (detect_zones,
volume_delta, V19 exits) backtest/run_tiger_brain_backtest.py mein hai.
Yeh sirf teen kaam karta hai:

  1. score + segment  →  WATCH (alert only) ya SIGNAL (order)
  2. blast criteria   →  delta velocity, volume 3x SMA20, VWAP cross
  3. contract pick    →  cheap OTM/slightly-ITM, OI floor, spread <= 1.5%

Rule table (config/settings.py se aati hai, yahan hardcode nahi):
  NSE: 55 <= score < 70 → WATCH   |  score >= 70 → SIGNAL
  MCX: 55 <= score < 60 → WATCH   |  score >= 60 → SIGNAL
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

try:
    from config import settings as S
except ImportError:
    raise ImportError("Repo ROOT se chalao")


WATCH = "WATCH"
SIGNAL = "SIGNAL"
NOISE = "NOISE"


# ---------------------------------------------------------------------
# 1. segment routing
# ---------------------------------------------------------------------
def resolve_segment(symbol: str) -> str:
    """MCX commodity → 'MCX', baaki sab → 'NSE'."""
    s = (symbol or "").upper()
    if s in set(S.MCX_UNDERLYINGS):
        return "MCX"
    from universe.fno_universe import segment_of
    return "MCX" if segment_of(symbol) == "commodity" else "NSE"


def classify(score: float, segment: str) -> str:
    """score → WATCH / SIGNAL / NOISE for the given segment."""
    rules = S.SEGMENT_RULES[segment]
    if score >= rules["SIGNAL"]:
        return SIGNAL
    if score >= rules["WATCH"]:
        return WATCH
    return NOISE


def thresholds(segment: str) -> dict:
    return dict(S.SEGMENT_RULES[segment])


# ---------------------------------------------------------------------
# 2. gamma-blast criteria
# ---------------------------------------------------------------------
@dataclass
class BlastResult:
    ok: bool
    reasons: list

    def __bool__(self):
        return self.ok


def delta_expansion_velocity(prev_delta: float, cur_delta: float) -> float:
    """Kitni tez se delta badha. Positive momentum zaroori."""
    if prev_delta <= 0:
        return 0.0
    return (cur_delta - prev_delta) / abs(prev_delta)


def blast_criteria(delta: float, volume: float, volumes, spot: float,
                   vwap: float, tick_velocity: float = 0.0) -> BlastResult:
    """
    Teen conditions SAATH me chahiye:
      a) delta > 0.35 with positive expansion velocity
      b) volume > 3x 20-period SMA (aur positive order-flow delta)
      c) spot ne VWAP cross kiya
    """
    reasons = []
    ok = True

    if delta > S.DELTA_VELOCITY_MIN:
        reasons.append(f"delta {delta:.2f} > {S.DELTA_VELOCITY_MIN}")
    else:
        reasons.append(f"delta {delta:.2f} <= {S.DELTA_VELOCITY_MIN}")
        ok = False

    sma = _sma(volumes, S.VOLUME_SMA_PERIOD)
    if sma > 0 and volume > S.VOLUME_SMA_MULT * sma:
        reasons.append(f"vol {volume:,.0f} > {S.VOLUME_SMA_MULT:g}x SMA20 {sma:,.0f}")
    else:
        reasons.append(f"vol {volume:,.0f} vs SMA20 {sma:,.0f} — no spike")
        ok = False

    if vwap > 0 and spot > vwap:
        reasons.append(f"spot {spot:.2f} > VWAP {vwap:.2f} (+{tick_velocity:g} vel)")
    else:
        reasons.append(f"spot {spot:.2f} vs VWAP {vwap:.2f} — no cross")
        ok = False

    return BlastResult(ok, reasons)


def _sma(values, period: int) -> float:
    vals = [v for v in list(values)[-period:] if v is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


# ---------------------------------------------------------------------
# 3. contract selection — cheap, liquid, tight spread
# ---------------------------------------------------------------------
@dataclass
class Quote:
    token: str
    symbol: str
    strike: float
    option_type: str      # CE / PE
    ltp: float
    bid: float
    ask: float
    oi: float
    lot: int = 1
    tick: float = S.TICK_SIZE_DEFAULT


def spread_pct(q: Quote) -> float:
    if q.ask <= 0:
        return 999.0
    return (q.ask - q.bid) / q.ask * 100.0


def passes_guardrails(q: Quote, spot: float) -> tuple:
    """(ok, reason). Cheap + liquid + tight spread."""
    if q.oi < S.MIN_OPEN_INTEREST:
        return False, f"OI {q.oi:,.0f} < {S.MIN_OPEN_INTEREST:,.0f}"
    if spread_pct(q) > S.MAX_SPREAD_PCT:
        return False, f"spread {spread_pct(q):.2f}% > {S.MAX_SPREAD_PCT}%"
    if not (S.MIN_PREMIUM <= q.ltp <= S.MAX_PREMIUM):
        return False, f"premium ₹{q.ltp:.2f} outside [{S.MIN_PREMIUM},{S.MAX_PREMIUM}]"
    if spot > 0 and q.ltp > spot * S.CHEAP_PREFERENCE_PCT / 100.0:
        return False, f"premium ₹{q.ltp:.2f} > {S.CHEAP_PREFERENCE_PCT}% of spot ₹{spot:.2f}"
    return True, "ok"


def select_contract(quotes, spot: float, option_type: str) -> tuple:
    """
    Cheapest liquid OTM/slightly-ITM contract.

    'Slightly ITM' = moneyness 0.90..1.05.
    Cheapest first, but spread + OI guardrails must pass.
    """
    if spot <= 0:
        return None, "spot unavailable"
    lo, hi = spot * 0.90, spot * 1.05
    pool = [q for q in quotes
            if q.option_type == option_type and lo <= q.strike <= hi]
    if not pool:
        return None, (f"no {option_type} in moneyness band "
                      f"{lo:.1f}–{hi:.1f}")
    pool.sort(key=lambda q: (q.ltp if q.ltp > 0 else 1e9))
    rejected = []
    for q in pool:
        ok, why = passes_guardrails(q, spot)
        if ok:
            if rejected:
                return q, f"picked cheapest of {len(pool)} ({len(rejected)} rejected)"
            return q, f"cheapest of {len(pool)}"
        rejected.append(f"{q.symbol}:{why}")
    return None, f"all {len(pool)} failed guardrails → " + rejected[0]
