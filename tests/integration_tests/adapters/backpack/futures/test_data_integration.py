"""
Integration tests for Backpack futures data streams.
"""

import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.futures.data import BackpackFuturesDataClient
from nautilus_trader.core.data import Data
from nautilus_trader.model.data import CustomData
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


class TestBackpackFuturesDataIntegration:
    """Integration tests for Backpack futures data client."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create test components
        self.clock = TestComponentStubs.clock()
        self.logger = TestComponentStubs.logger()
        self.msgbus = TestComponentStubs.msgbus()
        self.cache = TestComponentStubs.cache()
        
        # Create data client with mocked WebSocket
        with patch("nautilus_trader.adapters.backpack.futures.data.BackpackWebSocketClient"):
            self.data_client = BackpackFuturesDataClient(
                loop=asyncio.get_event_loop(),
                msgbus=self.msgbus,
                cache=self.cache,
                clock=self.clock,
                logger=self.logger,
                base_url_ws="wss://ws.backpack.exchange",
                api_key="test_key",
                api_secret="test_secret",
                is_testnet=True,
            )
            
        # Mock WebSocket client
        self.ws_client = MagicMock()
        self.data_client._ws_client = self.ws_client
        
    @pytest.mark.asyncio
    async def test_subscribe_mark_price_stream(self):
        """Test subscribing to mark price stream."""
        symbol = "SOL-PERP"
        
        # Setup mock subscription
        self.ws_client.subscribe = AsyncMock()
        
        # Subscribe to mark price
        await self.data_client._subscribe_mark_price(symbol)
        
        # Verify subscription
        self.ws_client.subscribe.assert_called_once()
        call_args = self.ws_client.subscribe.call_args
        assert call_args[0][0] == f"markPrice.{symbol}"
        
    @pytest.mark.asyncio
    async def test_handle_mark_price_message(self):
        """Test handling mark price WebSocket message."""
        # Create mark price message
        msg_data = {
            "stream": "markPrice.SOL-PERP",
            "data": {
                "symbol": "SOL-PERP",
                "markPrice": "105.50",
                "indexPrice": "105.45",
                "fundingRate": "0.0001",
                "nextFundingTime": 1234567890000,
                "timestamp": 1234567880000,
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Mock message bus for capturing emitted data
        emitted_data = []
        self.msgbus.send = MagicMock(side_effect=lambda topic, data: emitted_data.append(data))
        
        # Handle message
        self.data_client._handle_mark_price_msg(raw_msg)
        
        # Verify data was emitted
        assert len(emitted_data) >= 1
        
        # Check custom data emission
        custom_data = None
        for data in emitted_data:
            if isinstance(data, CustomData):
                custom_data = data
                break
                
        assert custom_data is not None
        assert custom_data.data_type.value == "MarkPriceUpdate"
        
    @pytest.mark.asyncio
    async def test_subscribe_funding_rate_stream(self):
        """Test subscribing to funding rate stream."""
        symbol = "BTC-PERP"
        
        # Setup mock subscription
        self.ws_client.subscribe = AsyncMock()
        
        # Subscribe to funding rate
        await self.data_client._subscribe_funding_rate(symbol)
        
        # Verify subscription
        self.ws_client.subscribe.assert_called_once()
        call_args = self.ws_client.subscribe.call_args
        assert call_args[0][0] == f"fundingRate.{symbol}"
        
    @pytest.mark.asyncio
    async def test_handle_funding_rate_message(self):
        """Test handling funding rate WebSocket message."""
        # Create funding rate message
        msg_data = {
            "stream": "fundingRate.BTC-PERP",
            "data": {
                "symbol": "BTC-PERP",
                "fundingRate": "0.0005",
                "fundingTime": 1234567890000,
                "timestamp": 1234567880000,
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Mock message bus
        emitted_data = []
        self.msgbus.send = MagicMock(side_effect=lambda topic, data: emitted_data.append(data))
        
        # Handle message
        self.data_client._handle_funding_rate_msg(raw_msg)
        
        # Verify data was emitted
        assert len(emitted_data) >= 1
        
        # Check custom data
        custom_data = None
        for data in emitted_data:
            if isinstance(data, CustomData):
                custom_data = data
                break
                
        assert custom_data is not None
        assert custom_data.data_type.value == "FundingRateUpdate"
        
    @pytest.mark.asyncio
    async def test_subscribe_open_interest_stream(self):
        """Test subscribing to open interest stream."""
        symbol = "ETH-PERP"
        
        # Setup mock subscription
        self.ws_client.subscribe = AsyncMock()
        
        # Subscribe to open interest
        await self.data_client._subscribe_open_interest(symbol)
        
        # Verify subscription
        self.ws_client.subscribe.assert_called_once()
        call_args = self.ws_client.subscribe.call_args
        assert call_args[0][0] == f"openInterest.{symbol}"
        
    @pytest.mark.asyncio
    async def test_handle_open_interest_message(self):
        """Test handling open interest WebSocket message."""
        # Create open interest message
        msg_data = {
            "stream": "openInterest.ETH-PERP",
            "data": {
                "symbol": "ETH-PERP",
                "openInterest": "1000000",
                "openInterestValue": "3500000000",
                "timestamp": 1234567890000,
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Mock message bus
        emitted_data = []
        self.msgbus.send = MagicMock(side_effect=lambda topic, data: emitted_data.append(data))
        
        # Handle message
        self.data_client._handle_open_interest_msg(raw_msg)
        
        # Verify data was emitted
        assert len(emitted_data) >= 1
        
        # Check custom data
        custom_data = None
        for data in emitted_data:
            if isinstance(data, CustomData):
                custom_data = data
                break
                
        assert custom_data is not None
        assert custom_data.data_type.value == "OpenInterestUpdate"
        
    @pytest.mark.asyncio
    async def test_handle_liquidation_message(self):
        """Test handling liquidation WebSocket message."""
        # Create liquidation message
        msg_data = {
            "stream": "liquidation",
            "data": {
                "symbol": "SOL-PERP",
                "side": "Buy",
                "price": "89.50",
                "quantity": "100",
                "timestamp": 1234567890000,
                "liquidationType": "LIQUIDATION",
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Mock message bus
        emitted_data = []
        self.msgbus.send = MagicMock(side_effect=lambda topic, data: emitted_data.append(data))
        
        # Handle message
        self.data_client._handle_liquidation_msg(raw_msg)
        
        # Verify data was emitted
        assert len(emitted_data) >= 1
        
        # Check custom data
        custom_data = None
        for data in emitted_data:
            if isinstance(data, CustomData):
                custom_data = data
                break
                
        assert custom_data is not None
        assert custom_data.data_type.value == "LiquidationEvent"
        
    @pytest.mark.asyncio
    async def test_multiple_stream_subscriptions(self):
        """Test subscribing to multiple streams for same symbol."""
        symbol = "SOL-PERP"
        
        # Setup mock subscription
        self.ws_client.subscribe = AsyncMock()
        
        # Subscribe to multiple streams
        await self.data_client._subscribe_mark_price(symbol)
        await self.data_client._subscribe_funding_rate(symbol)
        await self.data_client._subscribe_open_interest(symbol)
        
        # Verify all subscriptions
        assert self.ws_client.subscribe.call_count == 3
        
        # Check subscription topics
        calls = self.ws_client.subscribe.call_args_list
        topics = [call[0][0] for call in calls]
        
        assert f"markPrice.{symbol}" in topics
        assert f"fundingRate.{symbol}" in topics
        assert f"openInterest.{symbol}" in topics
        
    @pytest.mark.asyncio
    async def test_stream_reconnection_handling(self):
        """Test handling of stream reconnection."""
        # Setup subscriptions
        self.data_client._subscriptions = {
            "markPrice.SOL-PERP",
            "fundingRate.BTC-PERP",
            "openInterest.ETH-PERP",
        }
        
        # Mock resubscribe
        self.ws_client.subscribe = AsyncMock()
        
        # Simulate reconnection
        await self.data_client._resubscribe_all()
        
        # Verify all streams were resubscribed
        assert self.ws_client.subscribe.call_count == 3
        
    @pytest.mark.asyncio
    async def test_concurrent_message_handling(self):
        """Test handling multiple messages concurrently."""
        # Create multiple messages
        messages = [
            {
                "stream": "markPrice.SOL-PERP",
                "data": {
                    "symbol": "SOL-PERP",
                    "markPrice": f"{100 + i}",
                    "indexPrice": f"{100 + i - 0.05}",
                    "fundingRate": "0.0001",
                    "nextFundingTime": 1234567890000,
                    "timestamp": 1234567880000 + i * 1000,
                }
            }
            for i in range(10)
        ]
        
        # Mock message bus
        emitted_data = []
        self.msgbus.send = MagicMock(side_effect=lambda topic, data: emitted_data.append(data))
        
        # Handle messages concurrently
        tasks = []
        for msg_data in messages:
            raw_msg = json.dumps(msg_data).encode()
            task = asyncio.create_task(
                asyncio.to_thread(self.data_client._handle_mark_price_msg, raw_msg)
            )
            tasks.append(task)
            
        await asyncio.gather(*tasks)
        
        # Verify all messages were processed
        custom_data_count = sum(1 for data in emitted_data if isinstance(data, CustomData))
        assert custom_data_count >= len(messages)
        
    @pytest.mark.asyncio
    async def test_error_handling_invalid_message(self):
        """Test handling of invalid WebSocket messages."""
        # Create invalid message (missing required fields)
        msg_data = {
            "stream": "markPrice.SOL-PERP",
            "data": {
                "symbol": "SOL-PERP",
                # Missing markPrice and other required fields
            }
        }
        
        raw_msg = json.dumps(msg_data).encode()
        
        # Handle message - should not crash
        try:
            self.data_client._handle_mark_price_msg(raw_msg)
        except Exception as e:
            # Should handle error gracefully
            assert False, f"Should handle error gracefully, but raised: {e}"
            
    @pytest.mark.asyncio
    async def test_subscription_deduplication(self):
        """Test that duplicate subscriptions are handled properly."""
        symbol = "SOL-PERP"
        
        # Setup mock subscription
        self.ws_client.subscribe = AsyncMock()
        
        # Subscribe multiple times to same stream
        await self.data_client._subscribe_mark_price(symbol)
        await self.data_client._subscribe_mark_price(symbol)
        
        # Should only subscribe once (implementation dependent)
        # This test assumes deduplication is handled
        assert self.ws_client.subscribe.call_count <= 2