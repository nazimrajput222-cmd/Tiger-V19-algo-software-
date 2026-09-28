"""
Tiger Brain — Live ZONE engine (original 84724d6 "One Man Army")
=================================================================
WS V2 sirf DATA deta hai. Strategy 100% original hai:

    WS ticks → 1m bars → 15m resample → run_tiger_brain_backtest()
    → trades → _place_live_orders / check_intraday_exit_v19

Is file mein koi naya scoring, gating ya SMC logic NAHI hai. Zone math
(`pipeline/intraday_strategies.py`), Black-Scholes Greeks aur V19 exits
sab original engine ke andar hi chalte hain — yahan sirf data pipe hai.

Do knobs jo 84724d6 mein nahi thay (naye add kiye, values spec ke mutabiq):
  CANDLE_GATE_SEC = 0.35  — ek symbol ke liye do candle-close process
                             ke beech kam se kam gap
  SCAN_DEDUP_SEC  = 30    — ek symbol ka zone scan 30s se zyada baar
                             repeat nahi hota
"""
from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger("tiger_brain.automation.live_zone_engine")

IST_FREQ_15M = "15min"
BAR_COLS = ["open", "high", "low", "close", "volume"]


class LiveZoneEngine:
    """WS bars → original zone engine ka data_map, plus dedup/candle-gate."""

    def __init__(
        self,
        max_bars_15m: int = 500,
        max_bars_1m: int = 2000,
        candle_gate_sec: float = 0.35,
        scan_dedup_sec: float = 30.0,
    ):
        self.max_bars_15m = max_bars_15m
        self.max_bars_1m = max_bars_1m
        self.candle_gate_sec = candle_gate_sec
        self.scan_dedup_sec = scan_dedup_sec

        self._bars_1m: dict[str, dict] = defaultdict(dict)   # symbol → {ts: bar}
        self._bars_15m: dict[str, dict] = defaultdict(dict)
        self._forming: dict[str, pd.Timestamp] = {}     # abhi bhar raha bucket
        self._last_process: dict[str, float] = {}             # candle gate
        self._last_bar: dict[str, tuple] = {}                 # symbol → (ts, at)
        self._last_scan: dict[str, float] = {}               # dedup
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 1m bars in (called by WS thread when a 1m bar closes)
    # ------------------------------------------------------------------
    def on_bar_1m(self, symbol: str, bar: dict):
        ts = pd.Timestamp(bar["timestamp"])
        with self._lock:
            store = self._bars_1m[symbol]
            store[ts] = {c: float(bar[c]) for c in BAR_COLS}
            if len(store) > self.max_bars_1m:
                for k in sorted(store)[: len(store) - self.max_bars_1m]:
                    store.pop(k, None)
        self._roll_15m(symbol, ts)

    def _roll_15m(self, symbol: str, bar_ts: pd.Timestamp):
        """1m → 15m. Angel ke 15m candles 09:15 se anchored hain (floor, no drift)."""
        bucket = bar_ts.replace(minute=(bar_ts.minute // 15) * 15,
                                second=0, microsecond=0)
        with self._lock:
            self._forming[symbol] = bucket
        with self._lock:
            b15 = self._bars_15m[symbol].setdefault(bucket, [])
            b15.append({
                "timestamp": bucket,
                "open": float(bar_ts and self._bars_1m[symbol][bar_ts]["open"]),
                "high": self._bars_1m[symbol][bar_ts]["high"],
                "low": self._bars_1m[symbol][bar_ts]["low"],
                "close": self._bars_1m[symbol][bar_ts]["close"],
                "volume": self._bars_1m[symbol][bar_ts]["volume"],
            })
            if len(b15) > 15:
                del b15[: len(b15) - 15]

    # ------------------------------------------------------------------
    # data maps for the ORIGINAL engine
    # ------------------------------------------------------------------
    def data_maps(self) -> tuple[dict, dict]:
        with self._lock:
            return self._build(self._bars_15m, self.max_bars_15m), \
                   self._build(self._bars_1m, self.max_bars_1m)

    def _build(self, store: dict, cap: int) -> dict:
        out = {}
        for sym, bars in store.items():
            if not bars:
                continue
            # 1m store: {ts: {o,h,l,c,v}} | 15m store: {ts: [1m bar, ...]}
            sample = next(iter(bars.values()))
            if isinstance(sample, list):         # 15m bucket → fold
                items = sorted(bars.items())
                # Abhi bhar raha bucket ORIGINAL engine ko do na do — warna
                # zone adhoore "15m bar" par banenge. Seeded (closed) bars
                # kabhi forming nahi hote, isliye safe hain.
                forming = self._forming.get(sym)
                if forming is not None and len(bars[forming]) < 15:
                    items = [(ts, b) for ts, b in items if ts != forming]
                rows = [{
                    "timestamp": b[0]["timestamp"], "open": b[0]["open"],
                    "high": max(x["high"] for x in b),
                    "low": min(x["low"] for x in b),
                    "close": b[-1]["close"],
                    "volume": sum(x["volume"] for x in b),
                } for _, b in items]
            else:                                # 1m bars
                rows = [dict(b, timestamp=ts) for ts, b in bars.items()]
            if len(rows) < 2:
                continue
            df = pd.DataFrame(rows).sort_values("timestamp")
            df = df.set_index("timestamp")
            df.index.name = "timestamp"
            out[sym] = df[BAR_COLS].tail(cap).copy()
        return out

    @staticmethod
    def _naive_ist(ts) -> pd.Timestamp:
        """Angel REST index tz-aware hota hai; live bars naive IST. Sab normalize."""
        t = pd.Timestamp(ts)
        if t.tzinfo is not None:
            t = t.tz_convert("Asia/Kolkata").tz_localize(None)
        return t

    def seed(self, symbol: str, df_1m: pd.DataFrame, df_15m: pd.DataFrame | None = None):
        """Warm-up: historical candles (Angel REST) ko live bars ke aage jodo."""
        with self._lock:
            if df_1m is not None and not df_1m.empty:
                store = self._bars_1m[symbol]
                for ts, row in df_1m.iterrows():
                    store[self._naive_ist(ts)] = {c: float(row[c]) for c in BAR_COLS}
                for k in sorted(store)[: max(0, len(store) - self.max_bars_1m)]:
                    store.pop(k, None)
            if df_15m is not None and not df_15m.empty:
                store = self._bars_15m[symbol]
                for ts, row in df_15m.iterrows():
                    store[self._naive_ist(ts)] = [{
                        "timestamp": self._naive_ist(ts),
                        "open": float(row["open"]), "high": float(row["high"]),
                        "low": float(row["low"]), "close": float(row["close"]),
                        "volume": float(row.get("volume", 0) or 0),
                    }]
                for k in sorted(store)[: max(0, len(store) - self.max_bars_15m)]:
                    store.pop(k, None)

    # ------------------------------------------------------------------
    # gates
    # ------------------------------------------------------------------
    def allow_candle(self, symbol: str, bar_ts=None) -> bool:
        """0.35s candle gate.

        Gate ka matlab: wahi candle 0.35s ke andar dobara process na ho.
        ALAG candle (alag timestamp) KABHI block nahi hota — 1m candles
        60s door band hoti hain, unhe gate throttling nahi karni chahiye.
        """
        now = time.monotonic()
        with self._lock:
            last_ts, last_at = self._last_bar.get(symbol, (None, 0.0))
            if bar_ts is not None and bar_ts == last_ts and now - last_at < self.candle_gate_sec:
                return False
            self._last_bar[symbol] = (bar_ts, now)
            self._last_process[symbol] = now
            return True

    def allow_scan(self, symbol: str) -> bool:
        """30s scan dedup."""
        now = time.monotonic()
        with self._lock:
            last = self._last_scan.get(symbol, 0.0)
            if now - last < self.scan_dedup_sec:
                return False
            self._last_scan[symbol] = now
            return True

    def stats(self) -> dict:
        with self._lock:
            return {
                "symbols_1m": len(self._bars_1m),
                "symbols_15m": len(self._bars_15m),
                "scanned": len(self._last_scan),
            }


def run_zone_engine(broker, data_map: dict, data_map_1m: dict,
                    start_capital: float, now: datetime | None = None) -> list:
    """
    ORIGINAL 84724d6 engine call — koi badlav nahi. Bas symbol set aur
    capital pass karta hai; scoring/gating/exit engine original hai.
    """
    from backtest.run_tiger_brain_backtest import run_tiger_brain_backtest

    combined = run_tiger_brain_backtest(
        data_map, start_capital=start_capital,
        data_map_1m=data_map_1m or None, broker=broker,
    )
    trades = combined.get("trades", [])
    stamp = (now or datetime.now()).strftime("%Y-%m-%d")
    return [t for t in trades if str(t.get("entry_ts", ""))[:10] == stamp]
