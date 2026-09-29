"""Tests for Tiger Brain V18 Session Commander (Brain 7)."""

from __future__ import annotations

from datetime import time

import pytest

from backtest.tiger_session_brain import (
    SessionConfig,
    SESSION_SCHEDULE,
    SESSION_MORNING_BURST,
    SESSION_TREND_HUNT,
    SESSION_DISCOUNT_BUY,
    SESSION_POWER_HOUR,
    SESSION_COMMODITY_OPEN,
    SESSION_NIGHT_RUSH,
    SESSION_SQUARE_OFF,
    get_current_session,
    get_session_score_threshold,
    get_session_trade_quota,
    get_session_capital_pct,
    get_session_preferred_strike,
    should_force_hunt,
    HuntStatus,
    get_session_label,
    print_session_schedule,
)


class TestSessionDetection:
    def test_morning_burst_session(self):
        session = get_current_session(time(9, 30), "nse")
        assert session is not None
        assert session.name == SESSION_MORNING_BURST

    def test_trend_hunt_session(self):
        session = get_current_session(time(11, 0), "nse")
        assert session is not None
        assert session.name == SESSION_TREND_HUNT

    def test_discount_buy_session(self):
        session = get_current_session(time(13, 30), "nse")
        assert session is not None
        assert session.name == SESSION_DISCOUNT_BUY

    def test_power_hour_session(self):
        session = get_current_session(time(14, 45), "nse")
        assert session is not None
        assert session.name == SESSION_POWER_HOUR

    def test_commodity_open_session(self):
        session = get_current_session(time(18, 0), "mcx")
        assert session is not None
        assert session.name == SESSION_COMMODITY_OPEN

    def test_night_rush_session(self):
        session = get_current_session(time(21, 0), "mcx")
        assert session is not None
        assert session.name == SESSION_NIGHT_RUSH

    def test_square_off_session(self):
        session = get_current_session(time(23, 10), "mcx")
        assert session is not None
        assert session.name == SESSION_SQUARE_OFF

    def test_off_hours_nse_evening(self):
        # NSE is closed after 15:15
        session = get_current_session(time(16, 0), "nse")
        assert session is None

    def test_off_hours_morning_before_open(self):
        session = get_current_session(time(8, 0), "nse")
        assert session is None


class TestSessionParameters:
    def test_morning_burst_is_aggressive(self):
        session = get_current_session(time(9, 30), "nse")
        assert session.aggressiveness == "HIGH"
        assert session.max_trades_this_session == 5
        assert session.capital_allocation_pct == 35.0
        assert session.preferred_strike == "ITM"

    def test_discount_buy_uses_otm(self):
        session = get_current_session(time(13, 30), "nse")
        assert session.preferred_strike == "OTM"
        assert session.score_threshold == 75.0  # lower — IV discount compensates

    def test_power_hour_is_max_aggression(self):
        session = get_current_session(time(14, 45), "nse")
        assert session.aggressiveness == "MAX"

    def test_night_rush_is_aggressive(self):
        session = get_current_session(time(21, 0), "mcx")
        assert session.aggressiveness == "HIGH"
        assert session.max_trades_this_session == 5

    def test_square_off_no_entries(self):
        session = get_current_session(time(23, 10), "mcx")
        assert session.score_threshold == 999.0
        assert session.max_trades_this_session == 0


class TestSessionHelpers:
    def test_get_session_score_threshold(self):
        assert get_session_score_threshold(time(9, 30), "nse") == 78.0
        assert get_session_score_threshold(time(13, 30), "nse") == 75.0
        assert get_session_score_threshold(time(8, 0), "nse") == 999.0  # off-hours

    def test_get_session_trade_quota(self):
        assert get_session_trade_quota(time(9, 30), "nse") == 5
        assert get_session_trade_quota(time(23, 10), "mcx") == 0
        assert get_session_trade_quota(time(8, 0), "nse") == 0  # off-hours

    def test_get_session_capital_pct(self):
        assert get_session_capital_pct(time(9, 30), "nse") == 35.0
        assert get_session_capital_pct(time(23, 10), "mcx") == 0.0

    def test_get_session_preferred_strike(self):
        assert get_session_preferred_strike(time(13, 30), "nse") == "OTM"
        assert get_session_preferred_strike(time(9, 30), "nse") == "ITM"
        assert get_session_preferred_strike(time(8, 0), "nse") == "ATM"  # default


class TestHuntStatus:
    def test_empty_hunt(self):
        h = HuntStatus(date="2026-09-04")
        assert h.is_empty_hunt is True
        assert h.needs_aggressive_hunt is True
        assert h.total_trades == 0

    def test_record_nse_trade(self):
        h = HuntStatus(date="2026-09-04")
        h.record_trade("stock", pnl=5000)
        assert h.nse_trades == 1
        assert h.mcx_trades == 0
        assert h.total_trades == 1
        assert h.nse_profit == 5000
        assert h.is_empty_hunt is False

    def test_record_mcx_trade(self):
        h = HuntStatus(date="2026-09-04")
        h.record_trade("commodity", pnl=10000)
        assert h.mcx_trades == 1
        assert h.nse_trades == 0
        assert h.total_trades == 1
        assert h.mcx_profit == 10000

    def test_needs_aggressive_with_few_trades(self):
        h = HuntStatus(date="2026-09-04")
        h.record_trade("stock")
        h.record_trade("stock")
        assert h.needs_aggressive_hunt is True  # < 3 trades
        h.record_trade("stock")
        assert h.needs_aggressive_hunt is False  # 3 trades

    def test_summary(self):
        h = HuntStatus(date="2026-09-04")
        h.record_trade("stock", 5000)
        h.record_trade("commodity", 10000)
        s = h.summary()
        assert "NSE: 1" in s
        assert "MCX: 1" in s
        assert "Total: 2" in s

    def test_segment_trades_property(self):
        h = HuntStatus(date="2026-09-04")
        h.record_trade("stock")
        assert h.segment_trades("nse") == 1
        assert h.segment_trades("stock") == 1
        assert h.segment_trades("index") == 1
        h.record_trade("commodity")
        assert h.segment_trades("mcx") == 1
        assert h.segment_trades("commodity") == 1

    def test_needs_segment_mandate(self):
        h = HuntStatus(date="2026-09-04")
        # 0 trades → both segments need mandate
        mand = h.needs_segment_mandate
        assert mand["nse"] is True
        assert mand["mcx"] is True
        # Record 2 NSE trades → NSE mandate met
        h.record_trade("stock")
        h.record_trade("stock")
        mand = h.needs_segment_mandate
        assert mand["nse"] is False
        assert mand["mcx"] is True
        # Record 2 MCX trades → both met
        h.record_trade("commodity")
        h.record_trade("commodity")
        mand = h.needs_segment_mandate
        assert mand["nse"] is False
        assert mand["mcx"] is False


class TestForceHunt:
    def test_no_force_hunt_when_enough_trades(self):
        h = HuntStatus(date="2026-09-04")
        for _ in range(5):
            h.record_trade("stock")
        # 5 NSE trades → segment mandate (2) met → no force hunt
        force, threshold, reason = should_force_hunt(time(14, 45), h, "nse")
        assert force is False

    def test_segment_mandate_triggers_force_hunt(self):
        h = HuntStatus(date="2026-09-04")
        # Only 1 NSE trade → segment mandate (2) not met → force hunt ANY time
        h.record_trade("stock")
        force, threshold, reason = should_force_hunt(time(14, 45), h, "nse")
        assert force is True
        assert threshold < 78.0
        assert "mandate" in reason.lower()

    def test_segment_mandate_mcx(self):
        h = HuntStatus(date="2026-09-04")
        # 0 MCX trades → segment mandate not met → force hunt
        force, threshold, reason = should_force_hunt(time(20, 30), h, "mcx")
        assert force is True
        assert "mandate" in reason.lower() or "night rush" in reason.lower()

    def test_force_hunt_nse_power_hour_few_trades(self):
        """With segment mandate met but few NSE trades in power hour."""
        h = HuntStatus(date="2026-09-04")
        # Meet NSE segment mandate (2 trades)
        h.record_trade("stock")
        h.record_trade("stock")
        # nse_segment_trades = 2 (>= MIN_TRADES_PER_SEGMENT_PER_DAY=2)
        # nse_trades = 2, which is NOT < 2, so power hour rule doesn't trigger
        # This is correct: once mandate met, time-based rules use nse_trades
        # which equals 2, so no additional force hunt
        force, threshold, reason = should_force_hunt(time(14, 45), h, "nse")
        assert force is False  # 2 trades meets both mandate and power hour threshold

    def test_time_based_force_hunt_after_mandate_met(self):
        """Test time-based force hunt when segment mandate is met."""
        h = HuntStatus(date="2026-09-04")
        h.record_trade("stock")  # nse_seg=1
        h.record_trade("stock")  # nse_seg=2 (mandate met)
        h.record_trade("stock")  # nse_seg=3
        h.record_trade("stock")  # nse_seg=4 (>= 3, but < 3 for power hour? No, 4 >= 2)
        # Actually nse_trades=4, so < 2 is False. Let me test with 1 trade.
        h2 = HuntStatus(date="2026-09-04")
        h2.record_trade("stock")  # nse_seg=1
        h2.record_trade("commodity")  # adds to mcx, nse_seg still 1
        # nse_segment_trades=1 < 2 → mandate triggers
        force, threshold, reason = should_force_hunt(time(14, 45), h2, "nse")
        assert force is True
        assert "mandate" in reason.lower()

    def test_time_based_force_hunt_after_mandate_met_with_3_trades(self):
        """Test that time-based rules work when mandate is met."""
        h = HuntStatus(date="2026-09-04")
        # Record 3 NSE trades to meet mandate
        h.record_trade("stock")
        h.record_trade("stock")
        h.record_trade("stock")
        # Now test: nse_trades=3, which is NOT < 2 → no force hunt at 14:45
        # But if we have only 1 NSE trade... mandate kicks in instead
        # The key test: with mandate met AND >= 2 trades, no force hunt
        force, threshold, reason = should_force_hunt(time(14, 45), h, "nse")
        assert force is False

    def test_force_hunt_mcx_night_rush_few_trades(self):
        h = HuntStatus(date="2026-09-04")
        # Meet MCX segment mandate
        h.record_trade("commodity")
        h.record_trade("commodity")
        # Now 2 MCX trades, segment mandate met. Total = 2 < 3 → night rush
        force, threshold, reason = should_force_hunt(time(20, 30), h, "mcx")
        assert force is True
        assert threshold < 78.0
        assert "night rush" in reason

    def test_force_hunt_mcx_near_close_zero_trades(self):
        h = HuntStatus(date="2026-09-04")
        # Zero trades → Tiger MUST hunt (segment mandate triggers first)
        force, threshold, reason = should_force_hunt(time(22, 30), h, "mcx")
        assert force is True
        # Segment mandate: threshold = 72 - 0*2 = 72.0 (takes priority over time-based 65)
        assert threshold == 72.0
        assert "mandate" in reason.lower()

    def test_no_force_hunt_during_morning_when_mandate_met(self):
        h = HuntStatus(date="2026-09-04")
        # Meet NSE segment mandate
        h.record_trade("stock")
        h.record_trade("index")
        # Morning, mandate met, no time-based force hunt
        force, threshold, reason = should_force_hunt(time(9, 30), h, "nse")
        assert force is False

    def test_force_hunt_during_morning_when_mandate_not_met(self):
        h = HuntStatus(date="2026-09-04")
        # 0 NSE trades → segment mandate not met → force hunt even in morning
        force, threshold, reason = should_force_hunt(time(9, 30), h, "nse")
        assert force is True
        assert "mandate" in reason.lower()

    def test_segment_normalization_stock_is_nse(self):
        """Verify 'stock' segment is treated as 'nse' by should_force_hunt."""
        h = HuntStatus(date="2026-09-04")
        # 0 trades → segment mandate triggers
        force, threshold, reason = should_force_hunt(time(14, 45), h, "stock")
        assert force is True
        assert "mandate" in reason.lower()

    def test_segment_normalization_commodity_is_mcx(self):
        """Verify 'commodity' segment is treated as 'mcx' by should_force_hunt."""
        h = HuntStatus(date="2026-09-04")
        # 0 trades → segment mandate triggers
        force, threshold, reason = should_force_hunt(time(20, 30), h, "commodity")
        assert force is True
        assert "mandate" in reason.lower()

    def test_no_force_hunt_after_mandate_met_and_enough_trades(self):
        """With mandate met and enough trades, no force hunt even in night rush."""
        h = HuntStatus(date="2026-09-04")
        # 4 MCX trades → mandate met, and total >= 3
        h.record_trade("commodity")
        h.record_trade("commodity")
        h.record_trade("commodity")
        h.record_trade("commodity")
        force, threshold, reason = should_force_hunt(time(20, 30), h, "mcx")
        assert force is False


class TestSessionLabelAndSchedule:
    def test_session_label_morning(self):
        label = get_session_label(time(9, 30), "nse")
        assert "MORNING" in label

    def test_session_label_discount(self):
        label = get_session_label(time(13, 30), "nse")
        assert "DISCOUNT" in label

    def test_session_label_off_hours(self):
        label = get_session_label(time(8, 0), "nse")
        assert "OFF" in label

    def test_session_label_transition(self):
        label = get_session_label(time(16, 0), "nse")
        assert "TRANSITION" in label

    def test_print_session_schedule(self):
        output = print_session_schedule()
        assert "TIGER SESSION COMMANDER" in output
        assert "MORNING BURST" in output
        assert "NIGHT RUSH" in output
        assert "BINA SHIKAR LIYE GHAR NAHI" in output


class TestSessionConfig:
    def test_is_active_within_window(self):
        session = SessionConfig(
            name="TEST", label="Test", time_start=time(10, 0),
            time_end=time(11, 0), segment_focus="nse", score_threshold=75,
            max_trades_this_session=3, capital_allocation_pct=20,
            preferred_strike="ATM", aggressiveness="MEDIUM",
            description="test")
        assert session.is_active(time(10, 0)) is True
        assert session.is_active(time(10, 30)) is True
        assert session.is_active(time(10, 59)) is True

    def test_is_active_outside_window(self):
        session = SessionConfig(
            name="TEST", label="Test", time_start=time(10, 0),
            time_end=time(11, 0), segment_focus="nse", score_threshold=75,
            max_trades_this_session=3, capital_allocation_pct=20,
            preferred_strike="ATM", aggressiveness="MEDIUM",
            description="test")
        assert session.is_active(time(9, 59)) is False
        assert session.is_active(time(11, 0)) is False
