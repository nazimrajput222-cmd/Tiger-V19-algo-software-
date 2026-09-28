"""
Tiger Brain — Telegram controller notifications (non-blocking)
================================================================
72+ score signal / premium rocket / order status → turant Telegram pe.

Design:
  * Trading thread KABHI network pe block nahi hota — `notify()` sirf queue
    mein daalta hai, ek daemon worker thread bhejta hai.
  * Credentials sirf env se: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    (.env file — gitignored). Code/git mein token kabhi nahi.
  * Telegram limits: ek chat pe ~1 msg/sec → worker throttle karta hai;
    HTTP 429 pe `retry_after` respect karke retry.
  * Queue full ho (network down) to purane messages drop nahi — naya
    message drop + log (trading kabhi ruke nahi).
"""

from __future__ import annotations

import html
import json
import logging
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Callable

logger = logging.getLogger("tiger_brain.automation.telegram")

API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4000


def _http_post(url: str, payload: dict, timeout: float = 10.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            body = {}
        return exc.code, body


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        *,
        min_interval_sec: float = 1.0,
        max_queue: int = 500,
        max_retries: int = 3,
        sender: Callable[[str, dict], tuple[int, dict]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.bot_token = bot_token if bot_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.bot_token and self.chat_id)
        self.min_interval_sec = min_interval_sec
        self.max_retries = max_retries
        self._sender = sender or _http_post
        self._sleep = sleep
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        if not self.enabled:
            logger.warning("⚠️ Telegram OFF — TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID env mein nahi.")

    # ------------------------------------------------------------------
    def start(self):
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="telegram", daemon=True)
        self._thread.start()

    def stop(self, drain_timeout: float = 5.0):
        if self._thread is None:
            return
        deadline = time.monotonic() + drain_timeout
        while not self._q.empty() and time.monotonic() < deadline:
            time.sleep(0.05)
        self._stop.set()
        self._q.put(None)
        self._thread.join(timeout=2.0)

    def notify(self, text: str) -> bool:
        """Non-blocking enqueue. Returns False agar disabled/queue full."""
        if not self.enabled:
            logger.info("[telegram-off] %s", text.replace("\n", " | ")[:300])
            return False
        try:
            self._q.put_nowait(text[:MAX_MESSAGE_LEN])
            return True
        except queue.Full:
            self.dropped += 1
            logger.error("Telegram queue full — message drop: %s", text[:120])
            return False

    def send_now(self, text: str) -> bool:
        """Synchronous send (tests / startup self-check ke liye)."""
        if not self.enabled:
            return False
        return self._deliver(text[:MAX_MESSAGE_LEN])

    # ------------------------------------------------------------------
    def _deliver(self, text: str) -> bool:
        url = API_URL.format(token=self.bot_token)
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        for attempt in range(self.max_retries):
            try:
                status, body = self._sender(url, payload)
            except Exception as exc:
                status, body = 0, {"description": str(exc)}
            if status == 200 and body.get("ok", True):
                self.sent += 1
                return True
            if status == 429:
                retry_after = float((body.get("parameters") or {}).get("retry_after", 1))
                self._sleep(min(retry_after, 30.0))
                continue
            if 400 <= status < 500:
                break  # bad token/chat — retry bekaar
            self._sleep(min(2 ** attempt, 10))
        self.failed += 1
        # Token kabhi log nahi hota
        logger.error("❌ Telegram send fail (status=%s): %s", status,
                     (body or {}).get("description", "?"))
        return False

    def _run(self):
        last = 0.0
        while not self._stop.is_set():
            item = self._q.get()
            if item is None:
                break
            wait = self.min_interval_sec - (time.monotonic() - last)
            if wait > 0:
                self._sleep(wait)
            self._deliver(item)
            last = time.monotonic()


# ----------------------------------------------------------------------
# Message formats
# ----------------------------------------------------------------------
def _e(v) -> str:
    return html.escape(str(v))


def format_signal_alert(signal: dict) -> str:
    """72+ score signal — LOUD format."""
    ts = signal.get("time") or datetime.now()
    side = "CALL 📈" if signal.get("option_type") == "CE" else "PUT 📉"
    return (
        "🚨🚨🐅 <b>TIGER 72+ SIGNAL</b> 🐅🚨🚨\n"
        f"<b>{_e(signal.get('underlying'))}</b> — {side}\n"
        f"Strike: <b>{_e(signal.get('strike'))} {_e(signal.get('option_type'))}</b>"
        f"  ({_e(signal.get('tradingsymbol'))})\n"
        f"Premium: <b>₹{float(signal.get('premium') or 0):.2f}</b>\n"
        f"Score: <b>{float(signal.get('score') or 0):.1f}</b>"
        f"  | Underlying ₹{float(signal.get('underlying_price') or 0):.2f}\n"
        f"Mode: {_e(signal.get('mode', 'LIVE'))}  | {ts:%d-%b %H:%M:%S}"
    )


def format_rocket_alert(r: dict) -> str:
    ts = r.get("time") or datetime.now()
    return (
        "🚀🚀 <b>PREMIUM ROCKET</b> 🚀🚀\n"
        f"<b>{_e(r.get('underlying'))}</b> {_e(r.get('strike'))} {_e(r.get('option_type'))}"
        f"  ({_e(r.get('tradingsymbol'))})\n"
        f"Premium: ₹{float(r.get('from_premium') or 0):.2f} → "
        f"<b>₹{float(r.get('premium') or 0):.2f}</b>"
        f"  (<b>+{float(r.get('change_pct') or 0):.1f}%</b> in "
        f"{_e(r.get('window_min'))} min)\n"
        f"{ts:%d-%b %H:%M:%S}"
    )


def format_order_update(o: dict) -> str:
    icon = "✅" if o.get("success") else "❌"
    return (
        f"{icon} <b>ORDER {_e(o.get('side', 'BUY'))}</b> {_e(o.get('tradingsymbol'))}\n"
        f"Qty: {_e(o.get('quantity'))} @ ₹{float(o.get('price') or 0):.2f}"
        f"  | Status: <b>{_e(o.get('status'))}</b>\n"
        f"{_e(o.get('note', ''))}"
    )


def format_watch_alert(w: dict) -> str:
    """Trigger se neeche ka score — sirf nazar, koi order nahi."""
    ts = w.get("time") or datetime.now()
    side = "CALL" if w.get("option_type") == "CE" else "PUT"
    return (
        f"👀 <b>TIGER WATCH</b> (score {float(w.get('score') or 0):.1f} — "
        f"trade {float(w.get('trigger_score') or 0):.0f}+ pe)\n"
        f"<b>{_e(w.get('underlying'))}</b> {side} {_e(w.get('strike'))} {_e(w.get('option_type'))}"
        f"  ({_e(w.get('tradingsymbol'))})\n"
        f"Premium: ₹{float(w.get('premium') or 0):.2f}  | {ts:%d-%b %H:%M:%S}\n"
        f"Koi order NAHI"
    )
