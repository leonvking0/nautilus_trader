"""
Integration tests for Backpack futures execution client.
"""

import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.futures.execution import BackpackFuturesExecutionClient
from nautilus_trader.adapters.backpack.futures.position_manager import BackpackFuturesPositionManager
from nautilus_trader.adapters.backpack.futures.types import BackpackPosition
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder, MarketOrder
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


class TestBackpackFuturesExecutionIntegration:
    """Integration tests for Backpack futures execution client."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create test components
        self.clock = TestComponentStubs.clock()
        self.logger = TestComponentStubs.logger()
        self.msgbus = TestComponentStubs.msgbus()
        self.cache = TestComponentStubs.cache()
        
        # Create execution client with mocked WebSocket and HTTP
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
                
        # Mock WebSocket and HTTP clients
        self.ws_client = MagicMock()
        self.http_client = MagicMock()
        self.exec_client._ws_client = self.ws_client
        self.exec_client._http_client = self.http_client
        
        # Mock position manager
        self.exec_client._position_manager = MagicMock(spec=BackpackFuturesPositionManager)
        
    @pytest.mark.asyncio
    async def test_submit_market_order(self):
        """Test submitting a market order for futures."""
        # Create test order
        instrument_id = InstrumentId(Symbol("SOL-PERP"), Venue("BACKPACK"))
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("10"),
            price=Price.from_str("100.00"),
        )
        
        # Mock HTTP response
        self.http_client.submit_order = AsyncMock(return_value={
            "id": "order_123",
            "clientId": str(order.client_order_id),
            "symbol": "SOL-PERP",
            "side": "Buy",
            "orderType": "Limit",
            "price": "100.00",
            "quantity": "10",
            "status": "New",
            "timestamp": 1234567890000,
        })
        
        # Submit order
        await self.exec_client.submit_order(order)
        
        # Verify order was submitted
        self.http_client.submit_order.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_submit_reduce_only_order(self):
        """Test submitting a reduce-only order."""
        # Setup existing position
        existing_position = BackpackPosition(
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
        
        self.exec_client._position_manager.get_position_by_symbol.return_value = existing_position
        
        # Create reduce-only order (selling to reduce long)
        instrument_id = InstrumentId(Symbol("SOL-PERP"), Venue("BACKPACK"))
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("5"),
            price=Price.from_str("105.00"),
            tags=["reduce_only"],
        )
        
        # Mock HTTP response
        self.http_client.submit_order = AsyncMock(return_value={
            "id": "order_456",
            "clientId": str(order.client_order_id),
            "symbol": "SOL-PERP",
            "side": "Sell",
            "orderType": "Limit",
            "price": "105.00",
            "quantity": "5",
            "status": "New",
            "reduceOnly": True,
            "timestamp": 1234567890000,
        })
        
        # Submit order
        await self.exec_client.submit_order(order)
        
        # Verify reduce-only flag was set
        call_args = self.http_client.submit_order.call_args
        assert call_args[1].get("reduce_only") is True
        
    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test canceling a futures order."""
        # Create test order
        instrument_id = InstrumentId(Symbol("BTC-PERP"), Venue("BACKPACK"))
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("1"),
            price=Price.from_str("50000.00"),
        )
        
        # Mock HTTP response
        self.http_client.cancel_order = AsyncMock(return_value={
            "id": "order_789",
            "clientId": str(order.client_order_id),
            "status": "Cancelled",
        })
        
        # Cancel order
        await self.exec_client.cancel_order(order)
        
        # Verify order was cancelled
        self.http_client.cancel_order.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_handle_position_update_message(self):
        """Test handling position update WebSocket message."""
        # Create position update message
        msg_data = {
            "stream": "account.positionUpdate",
            "data": {
                "symbol": "SOL-PERP",
                "positionId": "pos_123",
                "side": "Long",
                "quantity": "15",
                "entryPrice": "102.50",
                "markPrice": "108.00",
                "liquidationPrice": "92.25",
                "unrealizedPnl": "82.50",
                "realizedPnl": "10.00",
                "marginRatio": "0.35",
                "initialMargin": "153.75",
                "maintenanceMargin": "38.44",
                "timestamp": 1234567890000,
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Handle message
        self.exec_client._handle_position_update_msg(raw_msg)
        
        # Verify position manager was updated
        self.exec_client._position_manager.update_position.assert_called_once()
        
        # Check position data
        call_args = self.exec_client._position_manager.update_position.call_args
        position = call_args[0][0]
        assert isinstance(position, BackpackPosition)
        assert position.symbol == "SOL-PERP"
        assert position.quantity == Decimal("15")
        assert position.entry_price == Decimal("102.50")
        
    @pytest.mark.asyncio
    async def test_handle_adl_event(self):
        """Test handling auto-deleveraging event."""
        # Create ADL event message
        msg_data = {
            "stream": "account.adl",
            "data": {
                "symbol": "BTC-PERP",
                "positionId": "pos_456",
                "side": "Short",
                "price": "55000.00",
                "quantity": "2",
                "type": "ADL",
                "timestamp": 1234567890000,
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Mock message bus
        self.msgbus.send = MagicMock()
        
        # Handle ADL event
        self.exec_client._handle_adl_event(raw_msg)
        
        # Verify execution report was generated
        assert self.msgbus.send.called
        
        # Verify position was updated
        self.exec_client._position_manager.close_position.assert_called()
        
    @pytest.mark.asyncio
    async def test_handle_liquidation_event(self):
        """Test handling liquidation event."""
        # Create liquidation event message
        msg_data = {
            "stream": "account.liquidation",
            "data": {
                "symbol": "ETH-PERP",
                "positionId": "pos_789",
                "side": "Long",
                "price": "3200.00",
                "quantity": "5",
                "type": "LIQUIDATION",
                "lossAmount": "500.00",
                "timestamp": 1234567890000,
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Mock message bus
        self.msgbus.send = MagicMock()
        
        # Handle liquidation event
        self.exec_client._handle_liquidation_event(raw_msg)
        
        # Verify execution report was generated
        assert self.msgbus.send.called
        
        # Verify position was closed
        self.exec_client._position_manager.close_position.assert_called()
        
    @pytest.mark.asyncio
    async def test_position_reconciliation(self):
        """Test position reconciliation with exchange."""
        # Mock exchange positions
        exchange_positions = [
            {
                "symbol": "SOL-PERP",
                "positionId": "pos_123",
                "side": "Long",
                "quantity": "10",
                "entryPrice": "100.00",
                "markPrice": "105.00",
                "liquidationPrice": "90.00",
                "unrealizedPnl": "50.00",
                "realizedPnl": "0",
                "marginRatio": "0.30",
                "initialMargin": "100.00",
                "maintenanceMargin": "25.00",
            }
        ]
        
        self.http_client.get_positions = AsyncMock(return_value=exchange_positions)
        
        # Perform reconciliation
        await self.exec_client._reconcile_positions()
        
        # Verify positions were fetched
        self.http_client.get_positions.assert_called_once()
        
        # Verify position manager reconciliation
        self.exec_client._position_manager.reconcile_positions.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_order_validation_insufficient_margin(self):
        """Test order validation with insufficient margin."""
        # Setup margin check to fail
        self.exec_client._check_margin_requirements = MagicMock(return_value=False)
        
        # Create large order
        instrument_id = InstrumentId(Symbol("BTC-PERP"), Venue("BACKPACK"))
        order = TestIdStubs.limit_order(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("100"),  # Large quantity
            price=Price.from_str("50000.00"),
        )
        
        # Attempt to submit order
        with pytest.raises(Exception) as exc_info:
            await self.exec_client.submit_order(order)
            
        assert "margin" in str(exc_info.value).lower()
        
    @pytest.mark.asyncio
    async def test_batch_order_submission(self):
        """Test submitting multiple orders in batch."""
        # Create multiple orders
        orders = []
        for i in range(5):
            instrument_id = InstrumentId(Symbol("SOL-PERP"), Venue("BACKPACK"))
            order = TestIdStubs.limit_order(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
                quantity=Quantity.from_str(str(i + 1)),
                price=Price.from_str(str(100 + i)),
            )
            orders.append(order)
            
        # Mock HTTP responses
        self.http_client.submit_order = AsyncMock(side_effect=[
            {
                "id": f"order_{i}",
                "clientId": str(order.client_order_id),
                "symbol": "SOL-PERP",
                "side": "Buy" if i % 2 == 0 else "Sell",
                "orderType": "Limit",
                "price": str(100 + i),
                "quantity": str(i + 1),
                "status": "New",
                "timestamp": 1234567890000 + i * 1000,
            }
            for i, order in enumerate(orders)
        ])
        
        # Submit orders
        tasks = [self.exec_client.submit_order(order) for order in orders]
        await asyncio.gather(*tasks)
        
        # Verify all orders were submitted
        assert self.http_client.submit_order.call_count == len(orders)
        
    @pytest.mark.asyncio
    async def test_websocket_reconnection_with_positions(self):
        """Test WebSocket reconnection resubscribes to position updates."""
        # Setup active positions
        self.exec_client._position_manager.get_open_positions.return_value = {
            "pos_123": BackpackPosition(
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
        }
        
        # Mock WebSocket subscribe
        self.ws_client.subscribe = AsyncMock()
        
        # Simulate reconnection
        await self.exec_client._on_ws_reconnect()
        
        # Verify position update stream was resubscribed
        self.ws_client.subscribe.assert_called()
        call_args = self.ws_client.subscribe.call_args
        assert "account.positionUpdate" in call_args[0][0]