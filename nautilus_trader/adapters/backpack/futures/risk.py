"""
Backpack Exchange futures risk management and liquidation monitoring.

This module provides real-time position health monitoring, liquidation price
calculations, and automated risk alerts for perpetual futures trading.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from enum import Enum
from typing import Any

from nautilus_trader.common.component import Component
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.position import Position

from nautilus_trader.adapters.backpack.futures.margin import BackpackFuturesMarginCalculator
from nautilus_trader.adapters.backpack.futures.position_manager import BackpackFuturesPositionManager
from nautilus_trader.adapters.backpack.futures.types import BackpackPosition


class RiskLevel(Enum):
    """Risk level enumeration for position health monitoring."""
    
    SAFE = "SAFE"
    WARNING = "WARNING"
    DANGER = "DANGER"
    CRITICAL = "CRITICAL"


class PositionHealthReport(Event):
    """
    Event representing a position health report.
    
    Attributes:
        position_id: The position identifier
        symbol: The trading symbol
        margin_ratio: Current margin ratio (0-1, where 1 = 100% margin used)
        liquidation_price: Price at which position will be liquidated
        current_price: Current mark price
        distance_to_liquidation: Percentage distance to liquidation
        risk_level: Current risk level
        message: Optional risk message
    """
    
    def __init__(
        self,
        position_id: str,
        symbol: str,
        margin_ratio: Decimal,
        liquidation_price: Decimal,
        current_price: Decimal,
        distance_to_liquidation: Decimal,
        risk_level: RiskLevel,
        message: str | None = None,
        event_id: UUID4 | None = None,
        ts_event: int | None = None,
        ts_init: int | None = None,
    ) -> None:
        super().__init__(event_id, ts_event, ts_init)
        self.position_id = position_id
        self.symbol = symbol
        self.margin_ratio = margin_ratio
        self.liquidation_price = liquidation_price
        self.current_price = current_price
        self.distance_to_liquidation = distance_to_liquidation
        self.risk_level = risk_level
        self.message = message


class BackpackLiquidationMonitor(Component):
    """
    Monitors position health and liquidation risks for Backpack perpetuals.
    
    This component continuously tracks position margin ratios, calculates
    liquidation prices, and emits risk alerts when positions approach
    dangerous levels.
    """
    
    # Risk level thresholds (as margin ratio percentages)
    MARGIN_RATIO_WARNING = Decimal("0.70")  # 70% margin used
    MARGIN_RATIO_DANGER = Decimal("0.85")   # 85% margin used
    MARGIN_RATIO_CRITICAL = Decimal("0.95") # 95% margin used
    
    # Distance to liquidation thresholds (as percentages)
    DISTANCE_WARNING = Decimal("10.0")   # 10% away from liquidation
    DISTANCE_DANGER = Decimal("5.0")     # 5% away from liquidation
    DISTANCE_CRITICAL = Decimal("2.0")   # 2% away from liquidation
    
    def __init__(
        self,
        margin_calculator: BackpackFuturesMarginCalculator,
        position_manager: BackpackFuturesPositionManager,
        clock: LiveClock,
        logger: Logger,
        msgbus: MessageBus,
        check_interval: float = 1.0,  # Check positions every second
    ) -> None:
        """
        Initialize the liquidation monitor.
        
        Args:
            margin_calculator: Margin calculator for liquidation prices
            position_manager: Position manager for tracking positions
            clock: Live clock for scheduling checks
            logger: Logger for risk alerts
            msgbus: Message bus for emitting events
            check_interval: Interval in seconds between health checks
        """
        super().__init__(
            clock=clock,
            logger=logger,
            msgbus=msgbus,
        )
        
        self._margin_calculator = margin_calculator
        self._position_manager = position_manager
        self._check_interval = check_interval
        self._monitoring_task: asyncio.Task | None = None
        self._last_risk_levels: dict[str, RiskLevel] = {}
        self._mark_prices: dict[str, Decimal] = {}
        
    def start(self) -> None:
        """Start the liquidation monitor."""
        if self._monitoring_task is None or self._monitoring_task.done():
            self._monitoring_task = asyncio.create_task(self._monitor_loop())
            self._log.info("Liquidation monitor started")
            
    def stop(self) -> None:
        """Stop the liquidation monitor."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            self._log.info("Liquidation monitor stopped")
            
    def update_mark_price(self, symbol: str, mark_price: Decimal) -> None:
        """
        Update the mark price for a symbol.
        
        Args:
            symbol: The trading symbol
            mark_price: The current mark price
        """
        self._mark_prices[symbol] = mark_price
        
    async def _monitor_loop(self) -> None:
        """Main monitoring loop that continuously checks position health."""
        while True:
            try:
                await self._check_all_positions()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Error in liquidation monitor: {e}")
                await asyncio.sleep(self._check_interval)
                
    async def _check_all_positions(self) -> None:
        """Check health of all open positions."""
        positions = self._position_manager.get_all_positions()
        
        for position in positions.values():
            if position.quantity == Decimal("0"):
                continue  # Skip closed positions
                
            mark_price = self._mark_prices.get(position.symbol)
            if mark_price is None:
                self._log.warning(f"No mark price available for {position.symbol}")
                continue
                
            health_report = self.check_position_health(position, mark_price)
            
            # Emit event if risk level changed or is above WARNING
            if health_report.risk_level != RiskLevel.SAFE:
                self._emit_health_report(health_report)
                
            # Log alerts for dangerous positions
            self._log_risk_alert(position, health_report)
            
    def check_position_health(
        self,
        position: BackpackPosition,
        mark_price: Decimal,
    ) -> PositionHealthReport:
        """
        Check the health of a specific position.
        
        Args:
            position: The position to check
            mark_price: Current mark price
            
        Returns:
            Position health report with risk metrics
        """
        # Calculate liquidation price
        liquidation_price = self.calculate_liquidation_price(position)
        
        # Calculate margin ratio
        margin_ratio = position.margin_ratio
        
        # Calculate distance to liquidation
        if position.side == "long":
            distance = ((mark_price - liquidation_price) / mark_price) * Decimal("100")
        else:  # short
            distance = ((liquidation_price - mark_price) / mark_price) * Decimal("100")
            
        # Determine risk level
        risk_level = self._determine_risk_level(margin_ratio, distance)
        
        # Generate risk message
        message = self._generate_risk_message(risk_level, margin_ratio, distance)
        
        return PositionHealthReport(
            position_id=position.position_id,
            symbol=position.symbol,
            margin_ratio=margin_ratio,
            liquidation_price=liquidation_price,
            current_price=mark_price,
            distance_to_liquidation=distance,
            risk_level=risk_level,
            message=message,
        )
        
    def calculate_liquidation_price(
        self,
        position: BackpackPosition,
    ) -> Decimal:
        """
        Calculate the liquidation price for a position.
        
        Args:
            position: The position to calculate for
            
        Returns:
            The liquidation price
        """
        return self._margin_calculator.calculate_liquidation_price(
            position_side=position.side,
            entry_price=position.entry_price,
            position_size=position.quantity,
            leverage=self._margin_calculator.get_leverage(position.symbol),
        )
        
    def check_liquidation_risk(
        self,
        position: BackpackPosition,
        mark_price: Decimal,
    ) -> bool:
        """
        Check if a position is at immediate risk of liquidation.
        
        Args:
            position: The position to check
            mark_price: Current mark price
            
        Returns:
            True if position is at immediate liquidation risk
        """
        liquidation_price = self.calculate_liquidation_price(position)
        
        if position.side == "long":
            return mark_price <= liquidation_price
        else:  # short
            return mark_price >= liquidation_price
            
    def _determine_risk_level(
        self,
        margin_ratio: Decimal,
        distance_to_liquidation: Decimal,
    ) -> RiskLevel:
        """
        Determine the risk level based on margin ratio and distance to liquidation.
        
        Args:
            margin_ratio: Current margin ratio (0-1)
            distance_to_liquidation: Percentage distance to liquidation
            
        Returns:
            The determined risk level
        """
        # Check critical conditions first
        if margin_ratio >= self.MARGIN_RATIO_CRITICAL or distance_to_liquidation <= self.DISTANCE_CRITICAL:
            return RiskLevel.CRITICAL
            
        # Check danger conditions
        if margin_ratio >= self.MARGIN_RATIO_DANGER or distance_to_liquidation <= self.DISTANCE_DANGER:
            return RiskLevel.DANGER
            
        # Check warning conditions
        if margin_ratio >= self.MARGIN_RATIO_WARNING or distance_to_liquidation <= self.DISTANCE_WARNING:
            return RiskLevel.WARNING
            
        return RiskLevel.SAFE
        
    def _generate_risk_message(
        self,
        risk_level: RiskLevel,
        margin_ratio: Decimal,
        distance: Decimal,
    ) -> str | None:
        """Generate a risk message based on the risk level."""
        if risk_level == RiskLevel.CRITICAL:
            return f"CRITICAL: Position at extreme liquidation risk! Margin ratio: {margin_ratio:.2%}, Distance: {distance:.2f}%"
        elif risk_level == RiskLevel.DANGER:
            return f"DANGER: Position approaching liquidation. Margin ratio: {margin_ratio:.2%}, Distance: {distance:.2f}%"
        elif risk_level == RiskLevel.WARNING:
            return f"WARNING: Elevated risk detected. Margin ratio: {margin_ratio:.2%}, Distance: {distance:.2f}%"
        return None
        
    def _emit_health_report(self, report: PositionHealthReport) -> None:
        """Emit a position health report event."""
        # Only emit if risk level changed or is critical
        last_level = self._last_risk_levels.get(report.position_id)
        
        if last_level != report.risk_level or report.risk_level == RiskLevel.CRITICAL:
            self._msgbus.publish_data(
                data_type=type(report),
                data=report,
            )
            self._last_risk_levels[report.position_id] = report.risk_level
            
    def _log_risk_alert(
        self,
        position: BackpackPosition,
        report: PositionHealthReport,
    ) -> None:
        """Log risk alerts based on position health."""
        if report.risk_level == RiskLevel.CRITICAL:
            self._log.error(
                f"[CRITICAL RISK] {position.symbol} {position.side} position: "
                f"Margin ratio={report.margin_ratio:.2%}, "
                f"Liquidation price={report.liquidation_price}, "
                f"Current price={report.current_price}, "
                f"Distance={report.distance_to_liquidation:.2f}%"
            )
        elif report.risk_level == RiskLevel.DANGER:
            self._log.warning(
                f"[HIGH RISK] {position.symbol} {position.side} position: "
                f"Margin ratio={report.margin_ratio:.2%}, "
                f"Distance to liquidation={report.distance_to_liquidation:.2f}%"
            )
        elif report.risk_level == RiskLevel.WARNING:
            self._log.info(
                f"[RISK WARNING] {position.symbol} {position.side} position: "
                f"Margin ratio={report.margin_ratio:.2%}, "
                f"Distance to liquidation={report.distance_to_liquidation:.2f}%"
            )
            
    def get_position_risk_summary(self) -> dict[str, dict[str, Any]]:
        """
        Get a summary of all position risks.
        
        Returns:
            Dictionary mapping position IDs to risk summaries
        """
        summary = {}
        positions = self._position_manager.get_all_positions()
        
        for position_id, position in positions.items():
            if position.quantity == Decimal("0"):
                continue
                
            mark_price = self._mark_prices.get(position.symbol)
            if mark_price:
                health = self.check_position_health(position, mark_price)
                summary[position_id] = {
                    "symbol": position.symbol,
                    "side": position.side,
                    "quantity": position.quantity,
                    "mark_price": mark_price,
                    "liquidation_price": health.liquidation_price,
                    "margin_ratio": health.margin_ratio,
                    "distance_to_liquidation": health.distance_to_liquidation,
                    "risk_level": health.risk_level.value,
                    "message": health.message,
                }
                
        return summary