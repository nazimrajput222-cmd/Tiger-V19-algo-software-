"""NSE 70/55 vs MCX 60/55 — engine gate aur Telegram dono segment-aware hone chahiye."""
from config.thresholds import SEGMENT_RULES, segment_rule


def test_nse_signal_70_watch_55():
    assert segment_rule("index", "SIGNAL") == 70.0
    assert segment_rule("stock", "SIGNAL") == 70.0
    assert segment_rule("index", "WATCH") == 55.0
    assert segment_rule("stock", "WATCH") == 55.0


def test_mcx_signal_60_watch_55():
    assert segment_rule("commodity", "SIGNAL") == 60.0
    assert segment_rule("commodity", "WATCH") == 55.0


def test_engine_gate_uses_segment_floor_not_global_75():
    import inspect
    import backtest.run_tiger_brain_backtest as m
    src = inspect.getsource(m.find_tiger_brain_entry)
    assert "segment_rule(seg" in src
    assert "score < MIN_SCORE_TO_ENTER" not in src      # global 75 gate removed
    assert "score < ROCKET_MIN_SCORE" not in src        # global 72 gate removed


def test_telegram_floors_are_segment_aware():
    import inspect
    import automation.tiger_live as tl
    src = inspect.getsource(tl.TigerLiveRunner._notify_zone_signals)
    assert "segment_rule" in src and "TIGER SIGNAL" in src and "TIGER WATCH" in src


def test_order_path_is_buy_only_and_options_only():
    import inspect
    import automation.tiger_live as tl
    src = inspect.getsource(tl.TigerLiveRunner._place_live_orders)
    assert 'transaction_type = "BUY"' in src
    assert "STRICT PATH" in src
    assert 'not in ("CE", "PE")' in src
