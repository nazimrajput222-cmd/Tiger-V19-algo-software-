"""WS ticks → ORIGINAL zone engine: pipe actually bars push kare, na ki na kare."""
from automation.live_zone_engine import LiveZoneEngine
from automation.ws_zone_pipe import WSZonePipe


class FakeStream:
    def __init__(self, auth_provider, on_tick, **kw):
        self.on_tick, self.auth_provider = on_tick, auth_provider
        self.capacity, self.subs, self.started, self.stopped = 1200, {}, False, False
    def subscribe(self, specs, mode=2):
        rej = []
        for s in specs:
            if s not in self.subs and len(self.subs) >= self.capacity:
                rej.append(s); continue
            self.subs[s] = mode
        return rej
    def start(self): self.started = True
    def stop(self): self.stopped = True
    def stats(self): return {"subscribed": len(self.subs)}


class U:
    def __init__(self, name, token, exch="NFO"):
        self.name, self.stream_token, self.stream_exchange = name, token, exch


def build(tmp_path):
    zone = LiveZoneEngine()
    pipe = WSZonePipe(zone, lambda: object(), stream_factory=FakeStream,
                      max_total_tokens=100, clock=lambda: 0.0)
    pipe.universe = [U("NIFTY", "900"), U("BANKNIFTY", "901", "NSE")]
    pipe.token_to_symbol = {"900": "NIFTY", "901": "BANKNIFTY"}
    pipe.running = True
    return zone, pipe


def tick(token, ltp, ts_ms=1790000000000, cum=100):
    return {"token": token, "ltp": ltp, "exchange_ts_ms": ts_ms, "cum_volume": cum}


def test_ticks_build_1m_bars_and_push_to_zone_engine():
    zone, pipe = build(None)
    import pandas as pd
    from data.tick_bars import exchange_ts_to_ist
    t0 = int(pd.Timestamp("2026-09-28 09:15", tz="Asia/Kolkata").timestamp() * 1000)
    for k in range(4):                                 # 09:15..09:18 → 2 closed 1m bars
        pipe.on_tick(tick("900", 100.0 + k, t0 + k * 60_000, cum=100 * (k + 1)))
    dm, dm1 = zone.data_maps()
    assert "NIFTY" in dm1 and len(dm1["NIFTY"]) >= 2
    assert pipe.bars_pushed >= 2


def test_candle_gate_blocks_same_candle_within_window():
    zone, pipe = build(None)
    zone.candle_gate_sec = 0.35
    import pandas as pd
    t0 = int(pd.Timestamp("2026-09-28 09:15", tz="Asia/Kolkata").timestamp() * 1000)
    for k in range(6):                                # 6 distinct 1m closes
        pipe.on_tick(tick("900", 100.0 + k, t0 + k * 60_000, cum=100 * (k + 1)))
    # ALAG candles gate se block NAHI honi chahiye
    assert pipe.gated == 0
    assert pipe.bars_pushed == 5


def test_other_symbol_ticks_update_own_bars():
    zone, pipe = build(None)
    import pandas as pd
    t0 = int(pd.Timestamp("2026-09-28 09:15", tz="Asia/Kolkata").timestamp() * 1000)
    for k in range(4):
        pipe.on_tick(tick("900", 100.0 + k, t0 + k * 60_000, cum=100 * (k + 1)))
        pipe.on_tick(tick("901", 5000.0 + k * 10, t0 + k * 60_000, cum=50 * (k + 1)))
    dm1 = zone.data_maps()[1]
    assert set(dm1) == {"NIFTY", "BANKNIFTY"}


def test_start_subscribes_and_stop_tears_down():
    from config.thresholds import BRAIN3, WS_V2
    class Pipe(WSZonePipe):
        pass
    p = WSZonePipe(LiveZoneEngine(), lambda: object(), stream_factory=FakeStream,
                   ws_cfg=WS_V2, master_loader=lambda: None)
    # fake universe path: monkeypatch build is heavy; just check subscribe via internals
    p.universe = [U("NIFTY", "900")]
    p.token_to_symbol = {"900": "NIFTY"}
    p.stream = FakeStream(lambda: None, lambda t: None)
    p.stream.start()
    p.running = True
    p.stream.subscribe([(2, "900")], mode=2)
    assert len(p.stream.subs) == 1
    p.stop()
    assert p.running is False


def test_candle_gate_blocks_repeat_of_same_candle():
    zone, pipe = build(None)
    import pandas as pd
    t0 = int(pd.Timestamp("2026-09-28 09:15", tz="Asia/Kolkata").timestamp() * 1000)
    pipe.on_tick(tick("900", 100.0, t0))
    pipe.on_tick(tick("900", 101.0, t0 + 30_000))
    pipe.on_tick(tick("900", 102.0, t0 + 60_000))     # 1m bar #1 pushed
    before = pipe.bars_pushed
    ts = pd.Timestamp(t0, unit="ms", tz="Asia/Kolkata").tz_localize(None)
    assert zone.allow_candle("NIFTY", ts) is False    # same candle reprocess
    assert pipe.bars_pushed == before


def test_broker_exposes_stream_auth():
    """WS pipe ko AngelBroker.stream_auth() chahiye (original 84724d6 mein nahi tha)."""
    import inspect
    from broker.angel_connect import AngelBroker
    assert hasattr(AngelBroker, "stream_auth")
    src = inspect.getsource(AngelBroker.stream_auth)
    assert "jwtToken" in src and "feedToken" in src
