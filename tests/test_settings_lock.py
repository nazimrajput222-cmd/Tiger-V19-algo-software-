"""Section 4: environment/process lock + dry-run override prevention."""
import importlib
import os

import pytest


def test_hardcoded_live_defaults():
    from config import settings as S
    assert S.TIGER_BRAIN_DRY_RUN is False
    assert S.EXECUTION_MODE == "LIVE_REAL_MONEY"
    assert S.ALLOW_OPTION_SELLING is False


def test_dry_run_cannot_be_overridden_by_env(monkeypatch):
    """EXECUTION_MODE LIVE_REAL_MONEY → DRY_RUN hardcoded False rehta hai,
    chahe env kuch bhi bole."""
    monkeypatch.setenv("TIGER_BRAIN_DRY_RUN", "true")
    import config.settings as S
    importlib.reload(S)
    assert S.TIGER_BRAIN_DRY_RUN is False
    assert S.EXECUTION_MODE == "LIVE_REAL_MONEY"


def test_score_matrix_locked():
    from config import settings as S
    assert S.SEGMENT_RULES["NSE"] == {"SIGNAL": 70.0, "WATCH": 55.0}
    assert S.SEGMENT_RULES["MCX"] == {"SIGNAL": 60.0, "WATCH": 55.0}
    assert set(S.MCX_UNDERLYINGS) == {"GOLDM", "SILVERM", "CRUDEOIL"}


def test_no_market_order_ever():
    from engine import executor as E
    assert E.LIMIT == "LIMIT" and E.MARKET == "MARKET"
    src = open(E.__file__).read()
    assert 'order_type": MARKET' not in src   # market order payload nahi banta
