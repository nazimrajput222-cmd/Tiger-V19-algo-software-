"""
Tiger Brain — Tick → N-minute bar aggregator (WebSocket V2 data plane)
======================================================================
Angel SmartStream har tick pe `volume_trade_for_the_day` bhejta hai —
ye din ka CUMULATIVE volume hai, bar ka nahi. Scanner (Brain 1 volume
velocity) ko har bar ka apna volume chahiye, isliye:

    bar_volume = (bar ke last tick ka cumulative) - (pichhle tick ka cumulative)

Rules (galat volume se galat signal banta hai, isliye strict):
  1. Kisi token ka PEHLA tick sirf baseline hai — uska cumulative pichhle
     poore din ka volume hai, is bar ka nahi. Us bar pe `volume_partial`
     flag lagta hai.
  2. Naya din → baseline reset.
  3. Cumulative peeche gaya (reconnect pe stale snapshot) → naya baseline,
     negative volume KABHI nahi banta.
  4. Bar time se close hota hai (flush), sirf agle tick ka intezaar nahi —
     warna illiquid contract ka bar ghanton khula reh jaata.
  5. Khali bucket ke liye bar fabricate nahi hota (koi trade nahi = koi bar
     nahi), Angel historical candles jaisa hi.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import pandas as pd

IST = timezone(timedelta(hours=5, minutes=30))


def exchange_ts_to_ist(ms: int | float) -> datetime:
    """Angel `exchange_timestamp` (epoch milliseconds) → naive IST datetime."""
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=IST).replace(tzinfo=None)


def bucket_start(ts: datetime, bar_minutes: int) -> datetime:
    """Tick timestamp ko uske bar ke start pe floor karo (09:17:42 → 09:15 for 5m)."""
    minute_of_day = ts.hour * 60 + ts.minute
    floored = minute_of_day - (minute_of_day % bar_minutes)
    return ts.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


@dataclass
class Bar:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    ticks: int = 0
    oi: float | None = None
    volume_partial: bool = False

    def as_row(self) -> dict:
        return {
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume,
        }


@dataclass
class _TokenState:
    current: Bar | None = None
    last_cum: int | None = None
    last_cum_day: date | None = None
    bars: deque = field(default_factory=deque)
    last_price: float | None = None
    last_tick_at: datetime | None = None
    last_closed: datetime | None = None   # sabse naye closed bar ka start
    carry_volume: float = 0.0             # closed bar pe aaye late ticks ka volume


class TickBarAggregator:
    """Thread-safe tick → bar builder, per token."""

    def __init__(self, bar_minutes: int = 5, max_bars: int = 400):
        if bar_minutes <= 0 or (60 % bar_minutes != 0 and bar_minutes % 60 != 0):
            raise ValueError(f"bar_minutes {bar_minutes} ghante ko barabar nahi baantta")
        self.bar_minutes = bar_minutes
        self.max_bars = max_bars
        self._states: dict[str, _TokenState] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _state(self, token: str) -> _TokenState:
        st = self._states.get(token)
        if st is None:
            st = _TokenState(bars=deque(maxlen=self.max_bars))
            self._states[token] = st
        return st

    def _volume_delta(self, st: _TokenState, ts: datetime, cum: int | None) -> tuple[float, bool]:
        """Returns (delta, is_baseline)."""
        if cum is None:
            return 0.0, False
        cum = int(cum)
        day = ts.date()
        if st.last_cum is None or st.last_cum_day != day:
            st.last_cum, st.last_cum_day = cum, day
            return 0.0, True
        if cum < st.last_cum:
            # Stale/restarted snapshot — naya baseline, negative volume nahi.
            st.last_cum = cum
            return 0.0, True
        delta = cum - st.last_cum
        st.last_cum = cum
        return float(delta), False

    def on_tick(
        self, token: str, ts: datetime, price: float,
        cum_volume: int | None = None, oi: float | None = None,
    ) -> list[Bar]:
        """Ek tick lo. Jo bars is tick se close hue unki list return karo."""
        if price is None or price <= 0:
            return []
        closed: list[Bar] = []
        with self._lock:
            st = self._state(token)
            delta, baseline = self._volume_delta(st, ts, cum_volume)
            b_start = bucket_start(ts, self.bar_minutes)
            cur = st.current

            if cur is not None and b_start > cur.start:
                st.bars.append(cur)
                st.last_closed = cur.start
                closed.append(cur)
                cur = None

            if cur is None and st.last_closed is not None and b_start <= st.last_closed:
                # Late tick (exchange ts server ghadi se peeche): bar pehle hi
                # time se close ho chuka — naya duplicate bar NAHI. Volume
                # agle bar mein jaata hai, OHLC nahi chhedte.
                st.carry_volume += delta
                return closed

            if cur is None:
                cur = Bar(start=b_start, open=price, high=price, low=price,
                          close=price, volume=st.carry_volume, ticks=0)
                st.carry_volume = 0.0
                st.current = cur
                if baseline:
                    cur.volume_partial = True
            elif b_start < cur.start:
                # Out-of-order (late) tick: OHLC mat chhedo, volume current
                # bar mein hi jaata hai (cumulative already aage badh chuka).
                cur.volume += delta
                return closed

            if baseline and cur.ticks > 0:
                cur.volume_partial = True
            cur.high = max(cur.high, price)
            cur.low = min(cur.low, price)
            cur.close = price
            cur.volume += delta
            cur.ticks += 1
            if oi is not None:
                cur.oi = float(oi)
            st.last_price = price
            st.last_tick_at = ts
        return closed

    def flush(self, now: datetime) -> dict[str, Bar]:
        """Jin tokens ka current bar time se khatam ho gaya, unhe close karo."""
        closed: dict[str, Bar] = {}
        span = timedelta(minutes=self.bar_minutes)
        with self._lock:
            for token, st in self._states.items():
                cur = st.current
                if cur is not None and now >= cur.start + span:
                    st.bars.append(cur)
                    st.last_closed = cur.start
                    st.current = None
                    closed[token] = cur
        return closed

    def seed(self, token: str, df: pd.DataFrame) -> int:
        """Historical bars (Angel candles) ko live bars se PEHLE jodo."""
        if df is None or df.empty:
            return 0
        with self._lock:
            st = self._state(token)
            existing = list(st.bars)
            first_live = existing[0].start if existing else (
                st.current.start if st.current is not None else None)
            seeded = []
            for ts, row in df.sort_index().iterrows():
                start = pd.Timestamp(ts).to_pydatetime()
                if start.tzinfo is not None:
                    start = start.astimezone(IST).replace(tzinfo=None)
                if first_live is not None and start >= first_live:
                    continue
                seeded.append(Bar(
                    start=start, open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0), ticks=0,
                ))
            merged = (seeded + existing)[-self.max_bars:]
            st.bars = deque(merged, maxlen=self.max_bars)
            if merged and (st.last_closed is None or merged[-1].start > st.last_closed):
                st.last_closed = merged[-1].start
            return len(seeded)

    # ------------------------------------------------------------------
    def bars_frame(self, token: str) -> pd.DataFrame:
        """Closed bars ka OHLCV DataFrame (scanner input)."""
        with self._lock:
            st = self._states.get(token)
            bars = list(st.bars) if st else []
        if not bars:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame([b.as_row() for b in bars], index=[b.start for b in bars])
        df.index.name = "timestamp"
        # Scanner (ATR combine) duplicate index pe crash karta hai — kabhi mat bhejo
        if not df.index.is_unique:
            df = df[~df.index.duplicated(keep="last")]
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()
        return df

    def last_bar_partial(self, token: str) -> bool:
        """Latest closed bar ka volume baseline-tick ki wajah se adhoora hai?"""
        with self._lock:
            st = self._states.get(token)
            return bool(st and st.bars and st.bars[-1].volume_partial)

    def bar_count(self, token: str) -> int:
        with self._lock:
            st = self._states.get(token)
            return len(st.bars) if st else 0

    def last_price(self, token: str) -> tuple[float | None, datetime | None]:
        with self._lock:
            st = self._states.get(token)
            if st is None:
                return None, None
            return st.last_price, st.last_tick_at

    def drop(self, token: str) -> None:
        with self._lock:
            self._states.pop(token, None)
