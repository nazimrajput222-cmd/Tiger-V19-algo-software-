"""
Tiger Brain — Angel One SmartStream (WebSocket V2) engine
==========================================================
SDK ka `SmartWebSocketV2` production ke liye bharosemand nahi hai:
  * `input_request_dict` CLASS-level hai (sab instances share karte hain),
    har subscribe pe list extend hoti hai → duplicates.
  * Reconnect `_on_error` ke andar recursively `connect()` karta hai aur
    `_on_close` pe reconnect hota hi nahi → silent data-death.
  * Har tick INFO log + cwd mein `logs/` folder.

Isliye ye engine scratch se likha hai (sirf `websocket-client` pe):
  * Multi-connection sharding: Angel ki per-connection token limit ke andar
    tokens bhare jaate hain, zarurat ho to naya connection.
  * Auto-reconnect: kabhi give-up nahi (jab tak stop() na ho), exponential
    backoff + jitter, healthy data aate hi backoff reset.
  * Auto-resubscribe: har (re)connect pe connection ki poori registry
    dobara subscribe hoti hai.
  * Heartbeat: text "ping" har N sec; koi message N sec tak na aaye to
    stale maan ke force-close → reconnect.
  * Fresh auth har connect pe `auth_provider()` se (logout/re-login ke
    baad bhi stream zinda rehta hai).
  * Binary packet parser khud ka (Angel V2 layout, little-endian).
"""

from __future__ import annotations

import json
import logging
import random
import struct
import threading
import time
from typing import Callable, Iterable

logger = logging.getLogger("tiger_brain.broker.ws_v2")

# ---------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------
MODE_LTP = 1
MODE_QUOTE = 2
MODE_SNAP_QUOTE = 3

EXCHANGE_TYPE = {
    "NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4, "MCX": 5, "NCDEX": 7, "CDS": 13,
}
EXCHANGE_NAME = {v: k for k, v in EXCHANGE_TYPE.items()}

# Packet lengths per mode (bytes) — isse chhota packet corrupt maana jaata hai.
_MIN_LEN = {MODE_LTP: 51, MODE_QUOTE: 123, MODE_SNAP_QUOTE: 379}


def _price_divisor(exchange_type: int) -> float:
    # Angel prices paise mein bhejta hai; currency (CDS) 10^7 scale pe.
    return 10_000_000.0 if exchange_type == EXCHANGE_TYPE["CDS"] else 100.0


def _u(fmt: str, data: bytes, start: int):
    return struct.unpack_from("<" + fmt, data, start)[0]


def parse_tick(data: bytes) -> dict | None:
    """Angel SmartStream V2 binary packet → normalized tick dict.

    Prices RUPEES mein convert hote hain. `cum_volume` = din ka cumulative
    traded volume (QUOTE/SNAP_QUOTE mode mein hi aata hai).
    Corrupt/short packet → None (kabhi exception nahi).
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < _MIN_LEN[MODE_LTP]:
        return None
    try:
        mode = _u("B", data, 0)
        if mode not in _MIN_LEN or len(data) < _MIN_LEN[mode]:
            return None
        exch = _u("B", data, 1)
        raw_token = bytes(data[2:27]).split(b"\x00", 1)[0]
        token = raw_token.decode("ascii", errors="ignore").strip()
        if not token:
            return None
        div = _price_divisor(exch)
        tick = {
            "mode": mode,
            "exchange_type": exch,
            "exchange": EXCHANGE_NAME.get(exch, str(exch)),
            "token": token,
            "sequence": _u("q", data, 27),
            "exchange_ts_ms": _u("q", data, 35),
            "ltp": _u("q", data, 43) / div,
        }
        if mode in (MODE_QUOTE, MODE_SNAP_QUOTE):
            tick.update({
                "ltq": _u("q", data, 51),
                "atp": _u("q", data, 59) / div,
                "cum_volume": _u("q", data, 67),
                "total_buy_qty": _u("d", data, 75),
                "total_sell_qty": _u("d", data, 83),
                "open": _u("q", data, 91) / div,
                "high": _u("q", data, 99) / div,
                "low": _u("q", data, 107) / div,
                "close": _u("q", data, 115) / div,
            })
        if mode == MODE_SNAP_QUOTE:
            tick["last_trade_ts"] = _u("q", data, 123)
            tick["oi"] = _u("q", data, 131)
            bids, asks = [], []
            for i in range(10):
                off = 147 + i * 20
                flag = _u("H", data, off)
                qty = _u("q", data, off + 2)
                price = _u("q", data, off + 10) / div
                # Angel: flag 1 = buy (bid), 0 = sell (ask)
                (bids if flag == 1 else asks).append((price, qty))
            best_bid = max((p for p, q in bids if p > 0), default=0.0)
            best_ask = min((p for p, q in asks if p > 0), default=0.0)
            tick["best_bid"] = best_bid
            tick["best_ask"] = best_ask
            tick["upper_circuit"] = _u("q", data, 347) / div
            tick["lower_circuit"] = _u("q", data, 355) / div
        return tick
    except (struct.error, ValueError) as exc:
        logger.debug("Tick parse fail: %s", exc)
        return None


# ---------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------
class _Connection:
    """Ek WebSocket connection + uski subscription registry + lifecycle thread."""

    def __init__(self, engine: "SmartStreamV2", index: int):
        self.engine = engine
        self.index = index
        self.registry: dict[tuple[int, str], int] = {}   # (exch_type, token) → mode
        self.ws = None
        self.connected = False
        self.thread: threading.Thread | None = None
        self.last_msg_at = 0.0
        self.reconnects = 0
        self.attempt = 0
        self._send_lock = threading.Lock()

    # -- helpers --------------------------------------------------------
    def _send(self, payload: str) -> bool:
        ws = self.ws
        if ws is None or not self.connected:
            return False
        with self._send_lock:
            try:
                ws.send(payload)
                return True
            except Exception as exc:
                logger.warning("WS[%d] send fail: %s", self.index, exc)
                return False

    def send_subscription(self, action: int, items: dict[tuple[int, str], int]) -> None:
        """items (exch,token)→mode ko mode+exchange ke groups mein batch karke bhejo."""
        if not items:
            return
        grouped: dict[int, dict[int, list[str]]] = {}
        for (exch, token), mode in items.items():
            grouped.setdefault(mode, {}).setdefault(exch, []).append(token)
        batch = self.engine.batch_size
        for mode, by_exch in grouped.items():
            flat = [(e, t) for e, toks in by_exch.items() for t in toks]
            for i in range(0, len(flat), batch):
                chunk = flat[i:i + batch]
                token_list: dict[int, list[str]] = {}
                for e, t in chunk:
                    token_list.setdefault(e, []).append(t)
                req = {
                    "correlationID": f"tiger{self.index:02d}{action}",
                    "action": action,
                    "params": {
                        "mode": mode,
                        "tokenList": [
                            {"exchangeType": e, "tokens": toks}
                            for e, toks in token_list.items()
                        ],
                    },
                }
                self._send(json.dumps(req))

    # -- websocket callbacks -------------------------------------------
    def _on_open(self, ws):
        self.connected = True
        self.last_msg_at = self.engine.clock()
        with self.engine._lock:
            snapshot = dict(self.registry)
        logger.info("🔌 WS[%d] connected — resubscribing %d tokens", self.index, len(snapshot))
        self.send_subscription(1, snapshot)
        self.engine._status("connected", self.index)

    def _on_message(self, ws, message):
        self.last_msg_at = self.engine.clock()
        if isinstance(message, (bytes, bytearray)):
            tick = parse_tick(message)
            if tick is None:
                return
            # Healthy data aaya → backoff reset
            self.attempt = 0
            try:
                self.engine.on_tick(tick)
            except Exception as exc:  # callback ki galti socket ko na maare
                logger.error("on_tick callback error: %s", exc, exc_info=True)
            return
        text = str(message).strip()
        if text == "pong":
            return
        try:
            payload = json.loads(text)
        except ValueError:
            logger.debug("WS[%d] text: %s", self.index, text[:200])
            return
        if isinstance(payload, dict) and (payload.get("errorCode") or payload.get("errorMessage")):
            logger.error("❌ WS[%d] server error: %s — %s", self.index,
                         payload.get("errorCode"), payload.get("errorMessage"))
            self.engine._status("server_error", self.index, payload)

    def _on_error(self, ws, error):
        logger.warning("⚠️ WS[%d] error: %s", self.index, error)

    def _on_close(self, ws, *args):
        self.connected = False
        logger.warning("🔌 WS[%d] closed %s", self.index, args if args else "")

    # -- lifecycle -------------------------------------------------------
    def _heartbeat(self, ws, stop_evt: threading.Event):
        eng = self.engine
        last_ping = eng.clock()
        while not stop_evt.wait(1.0):
            if not self.connected:
                continue
            now = eng.clock()
            if now - self.last_msg_at > eng.stale_timeout_sec:
                logger.error("💀 WS[%d] stale %.0fs — force reconnect", self.index,
                             now - self.last_msg_at)
                try:
                    ws.close()
                except Exception:
                    pass
                return
            if now - last_ping >= eng.heartbeat_sec:
                last_ping = now
                self._send("ping")

    def run(self):
        eng = self.engine
        while not eng._stop.is_set():
            try:
                auth = eng.auth_provider()
            except Exception as exc:
                logger.error("WS[%d] auth fail: %s", self.index, exc)
                auth = None
            if auth:
                headers = [
                    f"Authorization: {auth['jwt']}",
                    f"x-api-key: {auth['api_key']}",
                    f"x-client-code: {auth['client_code']}",
                    f"x-feed-token: {auth['feed_token']}",
                ]
                ws = eng.ws_factory(
                    eng.url, header=headers,
                    on_open=self._on_open, on_message=self._on_message,
                    on_error=self._on_error, on_close=self._on_close,
                )
                self.ws = ws
                hb_stop = threading.Event()
                hb = threading.Thread(target=self._heartbeat, args=(ws, hb_stop),
                                      name=f"ws{self.index}-hb", daemon=True)
                hb.start()
                try:
                    ws.run_forever(skip_utf8_validation=True)
                except Exception as exc:
                    logger.error("WS[%d] run_forever crash: %s", self.index, exc)
                finally:
                    hb_stop.set()
                    self.connected = False
                    self.ws = None
            if eng._stop.is_set():
                break
            delay = min(eng.reconnect_max_sec,
                        eng.reconnect_base_sec * (2 ** self.attempt))
            delay += random.uniform(0, delay * 0.2)
            self.attempt = min(self.attempt + 1, 10)
            self.reconnects += 1
            eng._status("reconnecting", self.index, {"delay": round(delay, 1)})
            logger.warning("🔁 WS[%d] reconnect #%d in %.1fs", self.index,
                           self.reconnects, delay)
            eng.sleep_until_stop(delay)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self.run, name=f"ws{self.index}", daemon=True)
        self.thread.start()

    def close(self):
        ws = self.ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def _default_ws_factory(url, **kwargs):
    import websocket  # websocket-client
    return websocket.WebSocketApp(url, **kwargs)


class SmartStreamV2:
    """Sharded, self-healing Angel SmartStream V2 client."""

    def __init__(
        self,
        auth_provider: Callable[[], dict],
        on_tick: Callable[[dict], None],
        *,
        url: str = "wss://smartapisocket.angelone.in/smart-stream",
        max_tokens_per_connection: int = 1000,
        max_connections: int = 3,
        max_total_tokens: int | None = None,
        batch_size: int = 200,
        heartbeat_sec: float = 25,
        stale_timeout_sec: float = 60,
        reconnect_base_sec: float = 2.0,
        reconnect_max_sec: float = 60.0,
        ws_factory: Callable | None = None,
        clock: Callable[[], float] = time.monotonic,
        on_status: Callable | None = None,
    ):
        self.auth_provider = auth_provider
        self.on_tick = on_tick
        self.url = url
        self.max_tokens_per_connection = int(max_tokens_per_connection)
        self.max_connections = int(max_connections)
        self.max_total_tokens = int(max_total_tokens) if max_total_tokens else None
        self.batch_size = int(batch_size)
        self.heartbeat_sec = heartbeat_sec
        self.stale_timeout_sec = stale_timeout_sec
        self.reconnect_base_sec = reconnect_base_sec
        self.reconnect_max_sec = reconnect_max_sec
        self.ws_factory = ws_factory or _default_ws_factory
        self.clock = clock
        self.on_status = on_status
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._started = False
        self.connections: list[_Connection] = []
        self._owner: dict[tuple[int, str], _Connection] = {}

    # -- capacity --------------------------------------------------------
    @property
    def capacity(self) -> int:
        cap = self.max_tokens_per_connection * self.max_connections
        return min(cap, self.max_total_tokens) if self.max_total_tokens else cap

    def subscribed_count(self) -> int:
        with self._lock:
            return len(self._owner)

    def free_slots(self) -> int:
        return self.capacity - self.subscribed_count()

    def is_subscribed(self, exchange_type: int, token: str) -> bool:
        with self._lock:
            return (int(exchange_type), str(token)) in self._owner

    def _status(self, event: str, index: int, detail=None):
        if self.on_status:
            try:
                self.on_status(event, index, detail)
            except Exception:
                pass

    def _conn_with_room(self) -> _Connection | None:
        for c in self.connections:
            if len(c.registry) < self.max_tokens_per_connection:
                return c
        if len(self.connections) < self.max_connections:
            c = _Connection(self, len(self.connections))
            self.connections.append(c)
            if self._started:
                c.start()
            return c
        return None

    # -- public API ------------------------------------------------------
    def subscribe(self, specs: Iterable[tuple[int, str]], mode: int = MODE_QUOTE) -> list:
        """Tokens subscribe karo. Capacity se bahar wale tokens return hote hain
        (kabhi silently drop nahi)."""
        rejected = []
        per_conn: dict[int, dict[tuple[int, str], int]] = {}
        with self._lock:
            for exch, token in specs:
                key = (int(exch), str(token))
                owner = self._owner.get(key)
                if owner is not None:
                    if owner.registry.get(key) != mode:
                        owner.registry[key] = mode
                        per_conn.setdefault(owner.index, {})[key] = mode
                    continue
                conn = self._conn_with_room() if len(self._owner) < self.capacity else None
                if conn is None:
                    rejected.append(key)
                    continue
                conn.registry[key] = mode
                self._owner[key] = conn
                per_conn.setdefault(conn.index, {})[key] = mode
        for idx, items in per_conn.items():
            self.connections[idx].send_subscription(1, items)
        if rejected:
            logger.error("⛔ WS capacity %d full — %d tokens subscribe NAHI hue",
                         self.capacity, len(rejected))
        return rejected

    def unsubscribe(self, specs: Iterable[tuple[int, str]]) -> int:
        per_conn: dict[int, dict[tuple[int, str], int]] = {}
        with self._lock:
            for exch, token in specs:
                key = (int(exch), str(token))
                conn = self._owner.pop(key, None)
                if conn is None:
                    continue
                mode = conn.registry.pop(key, MODE_QUOTE)
                per_conn.setdefault(conn.index, {})[key] = mode
        for idx, items in per_conn.items():
            self.connections[idx].send_subscription(0, items)
        return sum(len(v) for v in per_conn.values())

    def start(self):
        with self._lock:
            self._stop.clear()
            self._started = True
            if not self.connections:
                self.connections.append(_Connection(self, 0))
            conns = list(self.connections)
        for c in conns:
            c.start()
        logger.info("🚀 SmartStream V2 started — %d connection(s), capacity %d",
                    len(conns), self.capacity)

    def stop(self, join_timeout: float = 5.0):
        self._stop.set()
        with self._lock:
            self._started = False
            conns = list(self.connections)
        for c in conns:
            c.close()
        for c in conns:
            if c.thread is not None:
                c.thread.join(timeout=join_timeout)
        logger.info("🛑 SmartStream V2 stopped.")

    def sleep_until_stop(self, seconds: float):
        self._stop.wait(seconds)

    def stats(self) -> dict:
        with self._lock:
            return {
                "connections": len(self.connections),
                "connected": sum(1 for c in self.connections if c.connected),
                "subscribed": len(self._owner),
                "capacity": self.capacity,
                "reconnects": sum(c.reconnects for c in self.connections),
            }
