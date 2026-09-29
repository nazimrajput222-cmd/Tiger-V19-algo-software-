"""Regression tests for the Mandatory Hunt wiring.

Two bugs shipped once and are guarded here:
  1. should_force_hunt(..., seg=...) raised TypeError — the parameter is
     named `segment`. That killed EVERY scan while the hunt was live.
  2. the hunt was evaluated once per bar with a hardcoded "nse" segment,
     so MCX symbols were scored against the NSE floor.
"""

from __future__ import annotations

import inspect
from datetime import time

import pytest

from backtest.tiger_session_brain import should_force_hunt, HuntStatus


class TestHuntSignature:
    def test_third_param_is_named_segment_not_seg(self):
        """Guards bug #1: caller must not use seg= as a keyword."""
        params = list(inspect.signature(should_force_hunt).parameters)
        assert "segment" in params, f"expected 'segment' param, got {params}"
        assert "seg" not in params, (
            "if the param were renamed to 'seg', existing callers using "
            "segment= would break — keep it as 'segment'"
        )

    def test_seg_keyword_is_rejected_loudly(self):
        """`seg=` MUST raise — that is the bug we shipped. If someone ever
        aliases the param to `seg`, this test fails and the caller gets
        updated too. Silent acceptance would hide the mismatch."""
        h = HuntStatus(date="2026-09-29")
        with pytest.raises(TypeError, match="unexpected keyword argument 'seg'"):
            should_force_hunt(time(21, 0), h, seg="mcx")

    def test_segment_keyword_works(self):
        h = HuntStatus(date="2026-09-29")
        force, floor, _ = should_force_hunt(
            time(21, 0), h, segment="mcx")
        assert force is True
        assert floor == 55.0

    def test_positional_call_works(self):
        h = HuntStatus(date="2026-09-29")
        force, floor, _ = should_force_hunt(time(21, 0), h, "mcx")
        assert force is True
        assert floor == 55.0


class TestHuntPerSegment:
    def test_mcx_segment_gets_mcx_floor(self):
        """Guards bug #2: MCX must be scored on the MCX floor (55)."""
        h = HuntStatus(date="2026-09-29")
        assert should_force_hunt(time(21, 0), h, "mcx")[1] == 55.0

    def test_nse_segment_still_gated_to_1445(self):
        """NSE must NOT hunt early — only from 14:45."""
        h = HuntStatus(date="2026-09-29")
        assert should_force_hunt(time(21, 0), h, "nse")[0] is False
        assert should_force_hunt(time(14, 45), h, "nse")[0] is True

    def test_one_mcx_trade_does_not_affect_nse_count(self):
        """Counts are tracked per segment — a commodity fill must not
        suppress the NSE hunt (and vice versa)."""
        h = HuntStatus(date="2026-09-29")
        h.record_trade("commodity")
        assert should_force_hunt(time(21, 0), h, "mcx")[0] is False   # filled
        assert should_force_hunt(time(14, 50), h, "nse")[0] is True   # unaffected
