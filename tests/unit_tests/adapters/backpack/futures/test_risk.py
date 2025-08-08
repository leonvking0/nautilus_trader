"""
Unit tests for BackpackLiquidationMonitor.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.futures.margin import BackpackFuturesMarginCalculator
from nautilus_trader.adapters.backpack.futures.position_manager import BackpackFuturesPositionManager
from nautilus_trader.adapters.backpack.futures.risk import (
    BackpackLiquidationMonitor,
    PositionHealthReport,
    RiskLevel,
)
from nautilus_trader.adapters.backpack.futures.types import BackpackPosition
from nautilus_trader.common.component import LiveClock, Logger, MessageBus


class TestBackpackLiquidationMonitor:
    """Test suite for Backpack liquidation monitor."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.margin_calculator = MagicMock(spec=BackpackFuturesMarginCalculator)
        self.position_manager = MagicMock(spec=BackpackFuturesPositionManager)
        self.clock = MagicMock(spec=LiveClock)
        self.logger = MagicMock(spec=Logger)
        self.msgbus = MagicMock(spec=MessageBus)
        
        self.monitor = BackpackLiquidationMonitor(
            margin_calculator=self.margin_calculator,
            position_manager=self.position_manager,
            clock=self.clock,
            logger=self.logger,
            msgbus=self.msgbus,
            check_interval=0.1,  # Fast interval for testing
        )
        
        # Create test position
        self.test_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_123",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("105"),
            liquidation_price=Decimal("90"),
            unrealized_pnl=Decimal("50"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.3"),
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
    def test_update_mark_price(self):
        """Test updating mark price for a symbol."""
        symbol = "SOL-PERP"
        mark_price = Decimal("105.50")
        
        self.monitor.update_mark_price(symbol, mark_price)
        
        assert self.monitor._mark_prices[symbol] == mark_price
        
    def test_calculate_liquidation_price(self):
        """Test liquidation price calculation."""
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("92.50")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        liquidation_price = self.monitor.calculate_liquidation_price(self.test_position)
        
        assert liquidation_price == Decimal("92.50")
        self.margin_calculator.calculate_liquidation_price.assert_called_once_with(
            position_side="long",
            entry_price=Decimal("100"),
            position_size=Decimal("10"),
            leverage=Decimal("10"),
        )
        
    def test_check_liquidation_risk_long_safe(self):
        """Test liquidation risk check for safe long position."""
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        mark_price = Decimal("105")  # Well above liquidation price
        is_at_risk = self.monitor.check_liquidation_risk(self.test_position, mark_price)
        
        assert is_at_risk is False
        
    def test_check_liquidation_risk_long_danger(self):
        """Test liquidation risk check for long position at risk."""
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        mark_price = Decimal("89")  # Below liquidation price
        is_at_risk = self.monitor.check_liquidation_risk(self.test_position, mark_price)
        
        assert is_at_risk is True
        
    def test_check_liquidation_risk_short_safe(self):
        """Test liquidation risk check for safe short position."""
        short_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_456",
            side="short",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("95"),
            liquidation_price=Decimal("110"),
            unrealized_pnl=Decimal("50"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.3"),
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("110")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        mark_price = Decimal("95")  # Well below liquidation price
        is_at_risk = self.monitor.check_liquidation_risk(short_position, mark_price)
        
        assert is_at_risk is False
        
    def test_check_liquidation_risk_short_danger(self):
        """Test liquidation risk check for short position at risk."""
        short_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_456",
            side="short",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("111"),
            liquidation_price=Decimal("110"),
            unrealized_pnl=Decimal("-110"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.9"),
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("110")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        mark_price = Decimal("111")  # Above liquidation price
        is_at_risk = self.monitor.check_liquidation_risk(short_position, mark_price)
        
        assert is_at_risk is True
        
    def test_check_position_health_safe(self):
        """Test position health check for safe position."""
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        # Safe position: margin ratio 30%, distance to liquidation 14.3%
        mark_price = Decimal("105")
        health_report = self.monitor.check_position_health(self.test_position, mark_price)
        
        assert health_report.risk_level == RiskLevel.SAFE
        assert health_report.margin_ratio == Decimal("0.3")
        assert health_report.liquidation_price == Decimal("90")
        assert health_report.message is None
        
    def test_check_position_health_warning(self):
        """Test position health check for position with warning."""
        # Position with warning level risk
        warning_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_123",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("97"),
            liquidation_price=Decimal("90"),
            unrealized_pnl=Decimal("-30"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.75"),  # 75% margin used (above warning threshold)
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        mark_price = Decimal("97")  # 7.2% from liquidation
        health_report = self.monitor.check_position_health(warning_position, mark_price)
        
        assert health_report.risk_level == RiskLevel.WARNING
        assert "WARNING" in health_report.message
        
    def test_check_position_health_danger(self):
        """Test position health check for position in danger."""
        # Position with danger level risk
        danger_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_123",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("94"),
            liquidation_price=Decimal("90"),
            unrealized_pnl=Decimal("-60"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.87"),  # 87% margin used (above danger threshold)
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        mark_price = Decimal("94")  # 4.3% from liquidation
        health_report = self.monitor.check_position_health(danger_position, mark_price)
        
        assert health_report.risk_level == RiskLevel.DANGER
        assert "DANGER" in health_report.message
        
    def test_check_position_health_critical(self):
        """Test position health check for critical position."""
        # Position with critical level risk
        critical_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_123",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("91.5"),
            liquidation_price=Decimal("90"),
            unrealized_pnl=Decimal("-85"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.96"),  # 96% margin used (above critical threshold)
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        mark_price = Decimal("91.5")  # 1.6% from liquidation
        health_report = self.monitor.check_position_health(critical_position, mark_price)
        
        assert health_report.risk_level == RiskLevel.CRITICAL
        assert "CRITICAL" in health_report.message
        
    def test_determine_risk_level_by_margin_ratio(self):
        """Test risk level determination based on margin ratio."""
        # Test various margin ratios
        assert self.monitor._determine_risk_level(Decimal("0.5"), Decimal("20")) == RiskLevel.SAFE
        assert self.monitor._determine_risk_level(Decimal("0.72"), Decimal("15")) == RiskLevel.WARNING
        assert self.monitor._determine_risk_level(Decimal("0.86"), Decimal("12")) == RiskLevel.DANGER
        assert self.monitor._determine_risk_level(Decimal("0.96"), Decimal("8")) == RiskLevel.CRITICAL
        
    def test_determine_risk_level_by_distance(self):
        """Test risk level determination based on distance to liquidation."""
        # Test various distances (with safe margin ratio)
        assert self.monitor._determine_risk_level(Decimal("0.3"), Decimal("25")) == RiskLevel.SAFE
        assert self.monitor._determine_risk_level(Decimal("0.3"), Decimal("9")) == RiskLevel.WARNING
        assert self.monitor._determine_risk_level(Decimal("0.3"), Decimal("4")) == RiskLevel.DANGER
        assert self.monitor._determine_risk_level(Decimal("0.3"), Decimal("1.5")) == RiskLevel.CRITICAL
        
    def test_get_position_risk_summary(self):
        """Test getting risk summary for all positions."""
        # Setup positions
        positions = {
            "pos_123": self.test_position,
            "pos_456": BackpackPosition(
                symbol="BTC-PERP",
                position_id="pos_456",
                side="short",
                quantity=Decimal("0"),  # Closed position
                entry_price=Decimal("50000"),
                mark_price=Decimal("50000"),
                liquidation_price=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                realized_pnl=Decimal("100"),
                margin_ratio=Decimal("0"),
                initial_margin=Decimal("0"),
                maintenance_margin=Decimal("0"),
            ),
        }
        
        self.position_manager.get_all_positions.return_value = positions
        self.monitor._mark_prices = {
            "SOL-PERP": Decimal("105"),
            "BTC-PERP": Decimal("50000"),
        }
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        summary = self.monitor.get_position_risk_summary()
        
        # Should only include open position
        assert len(summary) == 1
        assert "pos_123" in summary
        assert summary["pos_123"]["symbol"] == "SOL-PERP"
        assert summary["pos_123"]["risk_level"] == "SAFE"
        
    @pytest.mark.asyncio
    async def test_monitor_loop_check_positions(self):
        """Test monitor loop checks positions periodically."""
        # Setup mock positions
        self.position_manager.get_all_positions.return_value = {
            "pos_123": self.test_position,
        }
        self.monitor._mark_prices = {"SOL-PERP": Decimal("105")}
        self.margin_calculator.calculate_liquidation_price.return_value = Decimal("90")
        self.margin_calculator.get_leverage.return_value = Decimal("10")
        
        # Start monitoring with very short interval
        self.monitor._check_interval = 0.01
        
        # Run monitor for a short time
        monitor_task = asyncio.create_task(self.monitor._monitor_loop())
        await asyncio.sleep(0.03)
        monitor_task.cancel()
        
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        # Verify positions were checked
        assert self.position_manager.get_all_positions.call_count >= 2
        
    def test_emit_health_report_on_change(self):
        """Test health report is emitted when risk level changes."""
        report = PositionHealthReport(
            position_id="pos_123",
            symbol="SOL-PERP",
            margin_ratio=Decimal("0.85"),
            liquidation_price=Decimal("90"),
            current_price=Decimal("94"),
            distance_to_liquidation=Decimal("4.3"),
            risk_level=RiskLevel.DANGER,
            message="Test danger message",
        )
        
        # First emission
        self.monitor._emit_health_report(report)
        
        assert self.msgbus.publish_data.called
        assert self.monitor._last_risk_levels["pos_123"] == RiskLevel.DANGER
        
        # Same level - should not emit
        self.msgbus.publish_data.reset_mock()
        self.monitor._emit_health_report(report)
        
        assert not self.msgbus.publish_data.called
        
        # Changed level - should emit
        report.risk_level = RiskLevel.CRITICAL
        self.monitor._emit_health_report(report)
        
        assert self.msgbus.publish_data.called
        
    def test_log_risk_alerts(self):
        """Test risk alerts are logged appropriately."""
        # Test critical alert
        critical_report = PositionHealthReport(
            position_id="pos_123",
            symbol="SOL-PERP",
            margin_ratio=Decimal("0.96"),
            liquidation_price=Decimal("90"),
            current_price=Decimal("91.5"),
            distance_to_liquidation=Decimal("1.6"),
            risk_level=RiskLevel.CRITICAL,
            message="Critical message",
        )
        
        self.monitor._log_risk_alert(self.test_position, critical_report)
        self.logger.error.assert_called_once()
        
        # Test danger alert
        self.logger.reset_mock()
        danger_report = PositionHealthReport(
            position_id="pos_123",
            symbol="SOL-PERP",
            margin_ratio=Decimal("0.87"),
            liquidation_price=Decimal("90"),
            current_price=Decimal("94"),
            distance_to_liquidation=Decimal("4.3"),
            risk_level=RiskLevel.DANGER,
            message="Danger message",
        )
        
        self.monitor._log_risk_alert(self.test_position, danger_report)
        self.logger.warning.assert_called_once()
        
        # Test warning alert
        self.logger.reset_mock()
        warning_report = PositionHealthReport(
            position_id="pos_123",
            symbol="SOL-PERP",
            margin_ratio=Decimal("0.75"),
            liquidation_price=Decimal("90"),
            current_price=Decimal("97"),
            distance_to_liquidation=Decimal("7.2"),
            risk_level=RiskLevel.WARNING,
            message="Warning message",
        )
        
        self.monitor._log_risk_alert(self.test_position, warning_report)
        self.logger.info.assert_called_once()