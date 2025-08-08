"""
Integration tests for Backpack futures position lifecycle.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.futures.execution import BackpackFuturesExecutionClient
from nautilus_trader.adapters.backpack.futures.margin import BackpackFuturesMarginCalculator
from nautilus_trader.adapters.backpack.futures.position_manager import BackpackFuturesPositionManager
from nautilus_trader.adapters.backpack.futures.risk import BackpackLiquidationMonitor, RiskLevel
from nautilus_trader.adapters.backpack.futures.types import BackpackPosition
from nautilus_trader.model.enums import OrderSide, OrderType, PositionSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


class TestBackpackFuturesPositionLifecycle:
    """Integration tests for complete position lifecycle."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create test components
        self.clock = TestComponentStubs.clock()
        self.logger = TestComponentStubs.logger()
        self.msgbus = TestComponentStubs.msgbus()
        self.cache = TestComponentStubs.cache()
        
        # Create real components
        self.margin_calculator = BackpackFuturesMarginCalculator()
        self.position_manager = BackpackFuturesPositionManager(logger=self.logger)
        
        # Create liquidation monitor
        self.liquidation_monitor = BackpackLiquidationMonitor(
            margin_calculator=self.margin_calculator,
            position_manager=self.position_manager,
            clock=self.clock,
            logger=self.logger,
            msgbus=self.msgbus,
            check_interval=1.0,
        )
        
        # Create execution client with mocked network components
        with patch("nautilus_trader.adapters.backpack.futures.execution.BackpackWebSocketClient"):
            with patch("nautilus_trader.adapters.backpack.futures.execution.BackpackHttpClient"):
                self.exec_client = BackpackFuturesExecutionClient(
                    loop=asyncio.get_event_loop(),
                    msgbus=self.msgbus,
                    cache=self.cache,
                    clock=self.clock,
                    logger=self.logger,
                    instrument_provider=MagicMock(),
                    base_url_ws="wss://ws.backpack.exchange",
                    base_url_http="https://api.backpack.exchange",
                    api_key="test_key",
                    api_secret="test_secret",
                    is_testnet=True,
                )
                
        # Replace with real position manager
        self.exec_client._position_manager = self.position_manager
        
        # Mock network clients
        self.ws_client = MagicMock()
        self.http_client = MagicMock()
        self.exec_client._ws_client = self.ws_client
        self.exec_client._http_client = self.http_client
        
    @pytest.mark.asyncio
    async def test_open_new_position(self):
        """Test opening a new position from zero."""
        symbol = "SOL-PERP"
        instrument_id = InstrumentId(Symbol(symbol), Venue("BACKPACK"))
        
        # Set leverage
        self.margin_calculator.set_leverage(symbol, Decimal("10"))
        
        # Create buy order to open long position
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("10"),
            price=Price.from_str("100.00"),
        )
        
        # Mock order submission response
        self.http_client.submit_order = AsyncMock(return_value={
            "id": "order_001",
            "clientId": str(order.client_order_id),
            "symbol": symbol,
            "side": "Buy",
            "orderType": "Limit",
            "price": "100.00",
            "quantity": "10",
            "status": "Filled",
            "timestamp": 1234567890000,
        })
        
        # Submit order
        await self.exec_client.submit_order(order)
        
        # Simulate position update from exchange
        position = BackpackPosition(
            symbol=symbol,
            position_id="pos_001",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("100"),
            liquidation_price=Decimal("92.5"),  # With 10x leverage
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.1"),  # 10% margin used
            initial_margin=Decimal("100"),  # 10 * 100 / 10 = 100
            maintenance_margin=Decimal("25"),  # 2.5% of 1000
        )
        
        self.position_manager.update_position(position)
        
        # Verify position is tracked
        tracked_position = self.position_manager.get_position_by_symbol(symbol)
        assert tracked_position is not None
        assert tracked_position.side == "long"
        assert tracked_position.quantity == Decimal("10")
        assert tracked_position.entry_price == Decimal("100")
        
        # Check position health
        self.liquidation_monitor.update_mark_price(symbol, Decimal("100"))
        health_report = self.liquidation_monitor.check_position_health(position, Decimal("100"))
        assert health_report.risk_level == RiskLevel.SAFE
        
    @pytest.mark.asyncio
    async def test_increase_position_size(self):
        """Test increasing an existing position size."""
        symbol = "BTC-PERP"
        instrument_id = InstrumentId(Symbol(symbol), Venue("BACKPACK"))
        
        # Set leverage
        self.margin_calculator.set_leverage(symbol, Decimal("20"))
        
        # Create initial position
        initial_position = BackpackPosition(
            symbol=symbol,
            position_id="pos_002",
            side="short",
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            mark_price=Decimal("50000"),
            liquidation_price=Decimal("52500"),  # Short liquidation
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.05"),
            initial_margin=Decimal("2500"),
            maintenance_margin=Decimal("1250"),
        )
        
        self.position_manager.update_position(initial_position)
        
        # Create order to increase position
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,  # Sell to increase short
            quantity=Quantity.from_str("0.5"),
            price=Price.from_str("49900.00"),
        )
        
        # Mock order submission
        self.http_client.submit_order = AsyncMock(return_value={
            "id": "order_002",
            "clientId": str(order.client_order_id),
            "symbol": symbol,
            "side": "Sell",
            "orderType": "Limit",
            "price": "49900.00",
            "quantity": "0.5",
            "status": "Filled",
            "timestamp": 1234567891000,
        })
        
        await self.exec_client.submit_order(order)
        
        # Simulate updated position from exchange
        updated_position = BackpackPosition(
            symbol=symbol,
            position_id="pos_002",
            side="short",
            quantity=Decimal("1.5"),  # Increased from 1 to 1.5
            entry_price=Decimal("49966.67"),  # Weighted average
            mark_price=Decimal("49900"),
            liquidation_price=Decimal("52465"),  # New liquidation
            unrealized_pnl=Decimal("100"),  # Small profit
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.075"),
            initial_margin=Decimal("3747.50"),
            maintenance_margin=Decimal("1874"),
        )
        
        self.position_manager.update_position(updated_position)
        
        # Verify position increase
        tracked_position = self.position_manager.get_position_by_symbol(symbol)
        assert tracked_position.quantity == Decimal("1.5")
        assert tracked_position.unrealized_pnl == Decimal("100")
        
    @pytest.mark.asyncio
    async def test_reduce_position_size(self):
        """Test reducing an existing position size."""
        symbol = "ETH-PERP"
        instrument_id = InstrumentId(Symbol(symbol), Venue("BACKPACK"))
        
        # Set leverage
        self.margin_calculator.set_leverage(symbol, Decimal("15"))
        
        # Create initial position
        initial_position = BackpackPosition(
            symbol=symbol,
            position_id="pos_003",
            side="long",
            quantity=Decimal("5"),
            entry_price=Decimal("3500"),
            mark_price=Decimal("3600"),
            liquidation_price=Decimal("3267"),  # Long liquidation
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.067"),
            initial_margin=Decimal("1166.67"),
            maintenance_margin=Decimal("437.50"),
        )
        
        self.position_manager.update_position(initial_position)
        
        # Create reduce-only order
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,  # Sell to reduce long
            quantity=Quantity.from_str("2"),
            price=Price.from_str("3620.00"),
            tags=["reduce_only"],
        )
        
        # Mock order submission
        self.http_client.submit_order = AsyncMock(return_value={
            "id": "order_003",
            "clientId": str(order.client_order_id),
            "symbol": symbol,
            "side": "Sell",
            "orderType": "Limit",
            "price": "3620.00",
            "quantity": "2",
            "status": "Filled",
            "reduceOnly": True,
            "timestamp": 1234567892000,
        })
        
        await self.exec_client.submit_order(order)
        
        # Simulate reduced position from exchange
        reduced_position = BackpackPosition(
            symbol=symbol,
            position_id="pos_003",
            side="long",
            quantity=Decimal("3"),  # Reduced from 5 to 3
            entry_price=Decimal("3500"),  # Entry price unchanged
            mark_price=Decimal("3620"),
            liquidation_price=Decimal("3267"),
            unrealized_pnl=Decimal("360"),  # Reduced unrealized
            realized_pnl=Decimal("240"),  # Realized profit from reduction
            margin_ratio=Decimal("0.067"),
            initial_margin=Decimal("700"),
            maintenance_margin=Decimal("262.50"),
        )
        
        self.position_manager.update_position(reduced_position)
        
        # Verify position reduction
        tracked_position = self.position_manager.get_position_by_symbol(symbol)
        assert tracked_position.quantity == Decimal("3")
        assert tracked_position.realized_pnl == Decimal("240")
        
    @pytest.mark.asyncio
    async def test_close_position_completely(self):
        """Test closing a position completely."""
        symbol = "SOL-PERP"
        instrument_id = InstrumentId(Symbol(symbol), Venue("BACKPACK"))
        
        # Create initial position
        initial_position = BackpackPosition(
            symbol=symbol,
            position_id="pos_004",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("110"),
            liquidation_price=Decimal("92.5"),
            unrealized_pnl=Decimal("100"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.1"),
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
        self.position_manager.update_position(initial_position)
        
        # Create order to close position
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,  # Sell to close long
            quantity=Quantity.from_str("10"),
            price=Price.from_str("110.00"),
            tags=["reduce_only"],
        )
        
        # Mock order submission
        self.http_client.submit_order = AsyncMock(return_value={
            "id": "order_004",
            "clientId": str(order.client_order_id),
            "symbol": symbol,
            "side": "Sell",
            "orderType": "Limit",
            "price": "110.00",
            "quantity": "10",
            "status": "Filled",
            "reduceOnly": True,
            "timestamp": 1234567893000,
        })
        
        await self.exec_client.submit_order(order)
        
        # Close position
        self.position_manager.close_position("pos_004", Decimal("100"))
        
        # Verify position is closed
        tracked_position = self.position_manager.get_position_by_symbol(symbol)
        assert tracked_position is None or tracked_position.quantity == Decimal("0")
        
        # Verify realized PnL
        closed_position = self.position_manager.get_position("pos_004")
        if closed_position:
            assert closed_position.realized_pnl == Decimal("100")
            
    @pytest.mark.asyncio
    async def test_position_approaching_liquidation(self):
        """Test monitoring position approaching liquidation."""
        symbol = "BTC-PERP"
        
        # Set leverage
        self.margin_calculator.set_leverage(symbol, Decimal("25"))
        
        # Create risky position
        risky_position = BackpackPosition(
            symbol=symbol,
            position_id="pos_005",
            side="long",
            quantity=Decimal("2"),
            entry_price=Decimal("50000"),
            mark_price=Decimal("48500"),  # Price dropped significantly
            liquidation_price=Decimal("48000"),  # Very close to liquidation
            unrealized_pnl=Decimal("-3000"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.88"),  # 88% margin used - DANGER
            initial_margin=Decimal("4000"),
            maintenance_margin=Decimal("2500"),
        )
        
        self.position_manager.update_position(risky_position)
        
        # Update mark price and check health
        self.liquidation_monitor.update_mark_price(symbol, Decimal("48500"))
        health_report = self.liquidation_monitor.check_position_health(
            risky_position,
            Decimal("48500"),
        )
        
        # Verify risk level
        assert health_report.risk_level == RiskLevel.DANGER
        assert health_report.distance_to_liquidation < Decimal("5")  # Less than 5% to liquidation
        assert "DANGER" in health_report.message
        
    @pytest.mark.asyncio
    async def test_position_liquidation_event(self):
        """Test handling position liquidation."""
        symbol = "ETH-PERP"
        
        # Create position about to be liquidated
        doomed_position = BackpackPosition(
            symbol=symbol,
            position_id="pos_006",
            side="short",
            quantity=Decimal("10"),
            entry_price=Decimal("3500"),
            mark_price=Decimal("3675"),  # Price rose above liquidation
            liquidation_price=Decimal("3675"),  # At liquidation price
            unrealized_pnl=Decimal("-1750"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("1.0"),  # 100% margin used
            initial_margin=Decimal("1400"),
            maintenance_margin=Decimal("875"),
        )
        
        self.position_manager.update_position(doomed_position)
        
        # Check if position is at liquidation risk
        is_at_risk = self.liquidation_monitor.check_liquidation_risk(
            doomed_position,
            Decimal("3675"),
        )
        
        assert is_at_risk is True
        
        # Simulate liquidation event
        self.position_manager.close_position("pos_006", Decimal("-1750"))
        
        # Verify position is closed
        tracked_position = self.position_manager.get_position("pos_006")
        assert tracked_position.quantity == Decimal("0")
        assert tracked_position.realized_pnl == Decimal("-1750")
        
    @pytest.mark.asyncio
    async def test_multiple_positions_management(self):
        """Test managing multiple positions simultaneously."""
        # Create multiple positions
        positions = [
            BackpackPosition(
                symbol="SOL-PERP",
                position_id="multi_001",
                side="long",
                quantity=Decimal("10"),
                entry_price=Decimal("100"),
                mark_price=Decimal("105"),
                liquidation_price=Decimal("90"),
                unrealized_pnl=Decimal("50"),
                realized_pnl=Decimal("0"),
                margin_ratio=Decimal("0.2"),
                initial_margin=Decimal("100"),
                maintenance_margin=Decimal("25"),
            ),
            BackpackPosition(
                symbol="BTC-PERP",
                position_id="multi_002",
                side="short",
                quantity=Decimal("0.5"),
                entry_price=Decimal("50000"),
                mark_price=Decimal("49500"),
                liquidation_price=Decimal("55000"),
                unrealized_pnl=Decimal("250"),
                realized_pnl=Decimal("0"),
                margin_ratio=Decimal("0.15"),
                initial_margin=Decimal("1250"),
                maintenance_margin=Decimal("625"),
            ),
            BackpackPosition(
                symbol="ETH-PERP",
                position_id="multi_003",
                side="long",
                quantity=Decimal("3"),
                entry_price=Decimal("3500"),
                mark_price=Decimal("3550"),
                liquidation_price=Decimal("3150"),
                unrealized_pnl=Decimal("150"),
                realized_pnl=Decimal("0"),
                margin_ratio=Decimal("0.25"),
                initial_margin=Decimal("700"),
                maintenance_margin=Decimal("262.50"),
            ),
        ]
        
        # Update all positions
        for position in positions:
            self.position_manager.update_position(position)
            self.margin_calculator.set_leverage(position.symbol, Decimal("10"))
            
        # Get all positions
        all_positions = self.position_manager.get_all_positions()
        assert len(all_positions) == 3
        
        # Calculate total unrealized PnL
        total_pnl = self.position_manager.get_total_unrealized_pnl()
        assert total_pnl == Decimal("450")  # 50 + 250 + 150
        
        # Calculate total margin used
        total_margin = self.position_manager.get_total_margin_used()
        assert total_margin == Decimal("2050")  # 100 + 1250 + 700
        
        # Check health of all positions
        for position in positions:
            self.liquidation_monitor.update_mark_price(position.symbol, position.mark_price)
            health_report = self.liquidation_monitor.check_position_health(
                position,
                position.mark_price,
            )
            assert health_report.risk_level == RiskLevel.SAFE
            
    @pytest.mark.asyncio
    async def test_position_reconciliation_workflow(self):
        """Test full position reconciliation workflow."""
        # Setup local positions
        local_positions = [
            BackpackPosition(
                symbol="SOL-PERP",
                position_id="recon_001",
                side="long",
                quantity=Decimal("10"),
                entry_price=Decimal("100"),
                mark_price=Decimal("105"),
                liquidation_price=Decimal("90"),
                unrealized_pnl=Decimal("50"),
                realized_pnl=Decimal("0"),
                margin_ratio=Decimal("0.2"),
                initial_margin=Decimal("100"),
                maintenance_margin=Decimal("25"),
            ),
        ]
        
        for position in local_positions:
            self.position_manager.update_position(position)
            
        # Mock exchange positions (with differences)
        exchange_positions = [
            BackpackPosition(
                symbol="SOL-PERP",
                position_id="recon_001",
                side="long",
                quantity=Decimal("12"),  # Different quantity
                entry_price=Decimal("101"),  # Different entry
                mark_price=Decimal("105"),
                liquidation_price=Decimal("91"),
                unrealized_pnl=Decimal("48"),
                realized_pnl=Decimal("5"),
                margin_ratio=Decimal("0.22"),
                initial_margin=Decimal("121"),
                maintenance_margin=Decimal("30"),
            ),
            BackpackPosition(
                symbol="BTC-PERP",
                position_id="recon_002",
                side="short",
                quantity=Decimal("1"),
                entry_price=Decimal("50000"),
                mark_price=Decimal("50000"),
                liquidation_price=Decimal("55000"),
                unrealized_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
                margin_ratio=Decimal("0.1"),
                initial_margin=Decimal("5000"),
                maintenance_margin=Decimal("1250"),
            ),
        ]
        
        # Perform reconciliation
        discrepancies = self.position_manager.reconcile_positions(exchange_positions)
        
        # Verify discrepancies detected
        assert len(discrepancies) > 0
        
        # Verify positions updated
        sol_position = self.position_manager.get_position("recon_001")
        assert sol_position.quantity == Decimal("12")
        
        btc_position = self.position_manager.get_position("recon_002")
        assert btc_position is not None
        assert btc_position.symbol == "BTC-PERP"