"""
Tiger Brain — WS → ZONE engine pipe
====================================
Jo link abhi tak missing tha: Angel SmartStream V2 ke live 1m bars ko
ORIGINAL zone engine ke `on_bar_1m()` mein daalna.

Pehle `ws_v2.py` / `tick_bars.py` / `dynamic_fno.py` repo mein thay par
kisi se connected nahi thay — zone engine sirf static warm-up history par
re-scan hota tha, yaani 20-minute cycle wahi signals dobara dobara de deta.

Yeh module sirf DATA pipe hai. Strategy, scoring, exits — sab original
`run_tiger_brain_backtest` ke andar, untouched.

Flow:
    Angel WS tick → TickBarAggregator(1m) → candle gate (0.35s)
                  → zone_engine.on_bar_1m(symbol, bar) → 15m resample
    scan dedup (30s) → intraday_scan (original 20-min job)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

import pandas as pd

from broker.ws_v2 import (EXCHANGE_TYPE, MODE_QUOTE, MODE_SNAP_QUOTE,
                          SmartStreamV2)
from data.tick_bars import TickBarAggregator, exchange_ts_to_ist

logger = logging.getLogger("tiger_brain.automation.ws_zone_pipe")

# Angel interval string for our 1m live bar (used for warm-up only)
_WARMUP_INTERVAL = "ONE_MINUTE"


class WSZonePipe:
    """Owns the WS connection and pushes 1m bars into the zone engine."""

    def __init__(
        self,
        zone_engine,
        broker_provider: Callable[[], object],
        *,
        master_loader: Callable | None = None,
        stream_factory=SmartStreamV2,
        ws_cfg: dict | None = None,
        clock=time.monotonic,
        max_total_tokens: int | None = 1200,
    ):
        self.zone = zone_engine
        self.broker_provider = broker_provider
        self.master_loader = master_loader
        self.stream_factory = stream_factory
        self.cfg = ws_cfg or {}
        self.clock = clock
        self.max_total_tokens = max_total_tokens

        self.agg = TickBarAggregator(bar_minutes=1, max_bars=2000)
        self.stream: SmartStreamV2 | None = None
        self.token_to_symbol: dict[str, str] = {}   # WS token → universe symbol
        self.universe: list = []
        self.running = False
        self.bars_pushed = 0
        self.gated = 0
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._timer: threading.Thread | None = None
        # Option contract quotes for execution guardrails (bid/ask/OI).
        self._quote_tokens: dict = {}       # token → (exchange, symbol)
        self._quotes: dict = {}             # token → {ltp,bid,ask,oi,at}

    # ------------------------------------------------------------------
    def _load_master(self):
        if self.master_loader is not None:
            return self.master_loader()
        from data.loader import load_angel_instrument_master
        return load_angel_instrument_master()

    def _auth(self) -> dict:
        return self.broker_provider().stream_auth()

    def start(self) -> bool:
        from universe.dynamic_fno import build_daily_universe
        from config.thresholds import BRAIN3

        with self._lock:
            if self.running:
                return True
            try:
                self.broker_provider()
                master = self._load_master()
                roots = self.cfg.get("MCX_ALLOWED_ROOTS") or ()
                self.universe = build_daily_universe(
                    master, min_days_to_expiry=BRAIN3["MIN_DAYS_TO_EXPIRY"],
                    mcx_roots=tuple(roots) or None)
            except Exception as exc:
                logger.error("❌ Zone pipe start fail: %s", exc, exc_info=True)
                return False
            if not self.universe:
                logger.error("❌ Zone pipe: universe khali")
                return False

            self.token_to_symbol = {u.stream_token: u.name for u in self.universe}
            self.stream = self.stream_factory(
                auth_provider=self._auth, on_tick=self.on_tick,
                url=self.cfg.get("URL", "wss://smartapisocket.angelone.in/smart-stream"),
                max_tokens_per_connection=self.cfg.get("MAX_TOKENS_PER_CONNECTION", 1000),
                max_connections=self.cfg.get("MAX_CONNECTIONS", 3),
                max_total_tokens=self.max_total_tokens,
                heartbeat_sec=self.cfg.get("HEARTBEAT_SEC", 25),
                stale_timeout_sec=self.cfg.get("STALE_TIMEOUT_SEC", 60),
                reconnect_base_sec=self.cfg.get("RECONNECT_BASE_SEC", 2.0),
                reconnect_max_sec=self.cfg.get("RECONNECT_MAX_SEC", 60.0),
            )
            self._stop.clear()
            self.running = True

        self.stream.start()
        specs = [(EXCHANGE_TYPE[u.stream_exchange], u.stream_token) for u in self.universe]
        rejected = self.stream.subscribe(specs, mode=MODE_QUOTE)
        logger.info("🔌 Zone pipe: %d/%d underlying tokens subscribed (cap %d)",
                    len(specs) - len(rejected), len(specs), self.stream.capacity)
        if rejected:
            logger.warning("⚠️ %d tokens capacity se bahar — scan unke liye nahi chalega",
                           len(rejected))

        self._timer = threading.Thread(target=self._flush_loop, name="zone-pipe",
                                       daemon=True)
        self._timer.start()
        return True

    # ------------------------------------------------------------------
    def on_tick(self, tick: dict):
        """WS callback — halka: 1m bar banana, zone engine ko dena, aur
        (agar token option contract ka hai) execution quote cache karna."""
        token = tick.get("token")
        if token in self._quote_tokens:
            self._quotes[token] = {
                "ltp": float(tick.get("ltp") or 0),
                "bid": float(tick.get("best_bid") or 0),
                "ask": float(tick.get("best_ask") or 0),
                "oi": float(tick.get("oi") or 0),
                "at": time.time(),
            }
        sym = self.token_to_symbol.get(token)
        ltp = float(tick.get("ltp") or 0)
        if sym is None or ltp <= 0:
            return
        ts_ms = tick.get("exchange_ts_ms") or 0
        ts = exchange_ts_to_ist(ts_ms) if ts_ms > 0 else None
        if ts is None:
            return
        for bar in self.agg.on_tick(token, ts, ltp, tick.get("cum_volume"),
                                    tick.get("oi")):
            self._push(sym, bar)

    def _push(self, symbol: str, bar) -> bool:
        """0.35s candle gate yahan lagta hai."""
        if not self.zone.allow_candle(symbol, bar.start):
            self.gated += 1
            return False
        self.zone.on_bar_1m(symbol, {
            "timestamp": bar.start, "open": bar.open, "high": bar.high,
            "low": bar.low, "close": bar.close, "volume": bar.volume,
        })
        self.bars_pushed += 1
        if self.bars_pushed % 50 == 1:
            logger.info("📥 Zone engine: %d bars pushed (%d gated)", self.bars_pushed,
                        self.gated)
        return True

    def _flush_loop(self):
        """Illiquid tokens ka 1m bar time se band karo (next tick na aaye to)."""
        while not self._stop.wait(1.0):
            try:
                from datetime import datetime
                for token, bar in self.agg.flush(datetime.now()).items():
                    sym = self.token_to_symbol.get(token)
                    if sym:
                        self._push(sym, bar)
            except Exception as exc:
                logger.error("Zone pipe flush error: %s", exc)

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # option quotes (execution guardrails)
    # ------------------------------------------------------------------
    def register_option_quote(self, exchange: str, token: str, symbol: str) -> None:
        """Signal aaya contract — uska SNAP_QUOTE feed ready karo."""
        with self._lock:
            self._quote_tokens[str(token)] = (exchange, symbol)
        if self.stream is not None:
            self.stream.subscribe([(EXCHANGE_TYPE[exchange], str(token))],
                                 mode=MODE_SNAP_QUOTE)

    def quote(self, token: str, wait_s: float = 3.0) -> dict | None:
        """Token ka bid/ask/OI wait karke do (max wait_s)."""
        import time as _t
        key = str(token)
        end = _t.time() + wait_s
        while _t.time() < end:
            q = self._quotes.get(key)
            if q and q.get("ask", 0) > 0:
                return q
            _t.sleep(0.1)
        return self._quotes.get(key)

    def allow_scan(self, symbol: str) -> bool:
        return self.zone.allow_scan(symbol)

    def stop(self):
        with self._lock:
            if not self.running:
                return
            self.running = False
            self._stop.set()
            stream = self.stream
        if stream is not None:
            stream.stop()
        logger.info("🛑 Zone pipe stopped (bars pushed: %d)", self.bars_pushed)

    def status(self) -> dict:
        return {
            "running": self.running,
            "underlying_tokens": len(self.token_to_symbol),
            "bars_pushed": self.bars_pushed,
            "gated": self.gated,
            "stream": self.stream.stats() if self.stream else None,
        }
