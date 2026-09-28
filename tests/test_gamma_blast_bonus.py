"""Gamma-Blast = SCORER BONUS only. Kabhi gate nahi — fail par trade reject nahi."""
import numpy as np
import pandas as pd

from backtest.run_tiger_brain_backtest import (GAMMA_BLAST_BONUS, gamma_blast_bonus)
from config.thresholds import segment_rule


def bars(vols, closes):
    """Realistic candles: open = previous close, so every bar has a body.
    (open == close would make volume_delta() return 0 and is not a real bar.)"""
    n = len(vols)
    idx = pd.date_range("2026-09-28 09:15", periods=n, freq="1min")
    c = np.array(closes, dtype=float)
    o = np.empty(n)
    o[0] = c[0] - 0.1
    o[1:] = c[:-1]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.2,
                         "low": np.minimum(o, c) - 0.2, "close": c,
                         "volume": np.array(vols, dtype=float)}, index=idx)


def test_all_three_criteria_met_gives_bonus():
    # steady small volume, then one huge bar with strong body
    vols = [1000.0] * 21 + [9000.0]
    # drifting closes → non-zero body → real delta each bar
    closes = [100.0 + 0.05 * i for i in range(21)] + [102.0]
    df = bars(vols, closes)
    pts, det = gamma_blast_bonus(df, 21, spot=103.0, vwap_val=100.0)
    assert pts == GAMMA_BLAST_BONUS
    assert "OK" in det[0]


def test_zero_prior_deltas_are_conservative_not_fatal():
    """5 flat candles ka avg |delta| = 0 → velocity undefined. Bonus 0 milta
    hai (conservative), lekin function CRASH nahi karta aur koi gate nahi —
    trade reject nahi hota. Yahi invariant matter karta hai."""
    vols = [1000.0] * 21 + [9000.0]
    closes = [100.0] * 21 + [103.0]        # flat history, then one big body
    df = bars(vols, closes)
    pts, det = gamma_blast_bonus(df, 21, spot=103.0, vwap_val=100.0)
    assert pts == 0                          # no bonus (conservative)
    assert isinstance(det, list) and det     # still reports what it saw
    assert "vol" in det[0] and "vwap" in det[0]


def test_no_volume_spike_gives_zero_but_not_rejection():
    df = bars([1000.0] * 22, [100.0] * 22)
    pts, det = gamma_blast_bonus(df, 21, spot=103.0, vwap_val=100.0)
    assert pts == 0
    assert "gamma-blast" in det[0]


def test_no_vwap_cross_gives_zero():
    vols = [1000.0] * 21 + [9000.0]
    closes = [100.0 + 0.05 * i for i in range(21)] + [102.0]
    df = bars(vols, closes)
    pts, det = gamma_blast_bonus(df, 21, spot=99.0, vwap_val=100.0)  # spot BELOW vwap
    assert pts == 0


def test_insufficient_data_returns_zero_not_error():
    df = bars([1000.0, 1100.0], [100.0, 101.0])
    pts, det = gamma_blast_bonus(df, 0, spot=101.0, vwap_val=100.0)
    assert pts == 0 and "skip" in det[0]
    assert gamma_blast_bonus(None, None, 100.0, 100.0)[0] == 0


def test_bonus_layer_is_not_a_gate_in_source():
    """Source mein gamma-blast ke aas-paas koi 'continue' nahi hona chahiye."""
    import inspect
    import backtest.run_tiger_brain_backtest as m
    src = inspect.getsource(m.gamma_blast_bonus)
    assert "continue" not in src
    # aur entry function mein bonus add hota hai, gate ke PEHLE
    full = inspect.getsource(m.find_tiger_brain_entry)
    i_bonus = full.index("gb_points, gb_details")
    i_gate = full.index("if not is_rocket")
    assert i_bonus < i_gate


def test_floors_remain_locked_nse70_mcx60():
    assert segment_rule("index", "SIGNAL") == 70.0
    assert segment_rule("stock", "SIGNAL") == 70.0
    assert segment_rule("commodity", "SIGNAL") == 60.0
