# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

"""Live WebSocket streaming tests for Backpack adapter."""

import asyncio
import time
from collections import deque
from decimal import Decimal
from typing import Dict, List, Any

import pytest

from .base import BackpackTestBase, live_only


class TestBackpackLiveWebSocket(BackpackTestBase):
    """Test cases for WebSocket streaming with live Backpack API."""
    
    @live_only
    @pytest.mark.asyncio
    async def test_websocket_streaming_depth(self):
        """Validate WebSocket depth streaming accuracy."""
        self.require_live_mode()
        
        received_messages = deque(maxlen=100)
        
        async def message_handler(message: Dict[str, Any]):
            received_messages.append(message)
        
        # Connect and subscribe to depth
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        await self.ws_client.subscribe_depth("SOL_USDC")
        
        # Collect messages for 5 seconds
        await asyncio.sleep(5)
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Validate received messages
        assert len(received_messages) > 0, "Should receive depth updates"
        
        # Check message structure
        for msg in received_messages:
            if msg.get("stream") == "depth":
                data = msg.get("data", {})
                assert "s" in data, "Should have symbol"
                assert "bids" in data or "b" in data, "Should have bids"
                assert "asks" in data or "a" in data, "Should have asks"
                
                # Validate bid/ask structure if full snapshot
                if "bids" in data and "asks" in data:
                    bids = data["bids"]
                    asks = data["asks"]
                    
                    # Check ordering
                    if len(bids) > 1:
                        for i in range(1, len(bids)):
                            assert Decimal(bids[i][0]) < Decimal(bids[i-1][0]), \
                                "Bids should be descending"
                    
                    if len(asks) > 1:
                        for i in range(1, len(asks)):
                            assert Decimal(asks[i][0]) > Decimal(asks[i-1][0]), \
                                "Asks should be ascending"
    
    @live_only
    @pytest.mark.asyncio
    async def test_websocket_streaming_trades(self):
        """Validate WebSocket trades streaming."""
        self.require_live_mode()
        
        received_trades = []
        
        async def message_handler(message: Dict[str, Any]):
            if message.get("stream") == "trades":
                received_trades.append(message["data"])
        
        # Connect and subscribe to trades
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        await self.ws_client.subscribe_trades("SOL_USDC")
        
        # Collect messages for 10 seconds (trades might be less frequent)
        await asyncio.sleep(10)
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Validate received trades
        if received_trades:  # Might not receive trades in quiet market
            for trade in received_trades:
                assert "p" in trade, "Trade should have price"
                assert "q" in trade, "Trade should have quantity"
                assert "t" in trade, "Trade should have trade ID"
                assert "T" in trade, "Trade should have timestamp"
                assert "m" in trade, "Trade should have maker flag"
                
                # Validate values
                assert Decimal(trade["p"]) > 0, "Price should be positive"
                assert Decimal(trade["q"]) > 0, "Quantity should be positive"
    
    @live_only
    @pytest.mark.asyncio
    async def test_websocket_reconnection(self):
        """Test WebSocket reconnection logic."""
        self.require_live_mode()
        
        connection_events = []
        
        async def connection_handler(event: str):
            connection_events.append((event, time.time()))
        
        self.ws_client.on_connect = lambda: connection_handler("connected")
        self.ws_client.on_disconnect = lambda: connection_handler("disconnected")
        
        # Initial connection
        await self.ws_client.connect()
        await self.ws_client.subscribe_depth("SOL_USDC")
        
        # Wait for connection
        await asyncio.sleep(2)
        
        # Force disconnect
        await self.ws_client.disconnect()
        
        # Wait and reconnect
        await asyncio.sleep(1)
        await self.ws_client.connect()
        await self.ws_client.subscribe_depth("SOL_USDC")
        
        # Wait for reconnection
        await asyncio.sleep(2)
        
        # Final disconnect
        await self.ws_client.disconnect()
        
        # Validate connection events
        assert len(connection_events) >= 2, "Should have connect/disconnect events"
        assert connection_events[0][0] == "connected"
        assert any(e[0] == "disconnected" for e in connection_events)
    
    @live_only
    @pytest.mark.asyncio
    async def test_websocket_multiple_subscriptions(self):
        """Test multiple simultaneous subscriptions."""
        self.require_live_mode()
        
        received_by_stream = {
            "depth": [],
            "trades": [],
            "ticker": [],
        }
        
        async def message_handler(message: Dict[str, Any]):
            stream = message.get("stream")
            if stream in received_by_stream:
                received_by_stream[stream].append(message)
        
        # Connect and subscribe to multiple streams
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        
        await self.ws_client.subscribe_depth("SOL_USDC")
        await self.ws_client.subscribe_trades("SOL_USDC")
        await self.ws_client.subscribe_ticker("SOL_USDC")
        
        # Collect messages
        await asyncio.sleep(5)
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Validate we received messages from multiple streams
        active_streams = sum(1 for msgs in received_by_stream.values() if msgs)
        assert active_streams >= 2, f"Should receive from multiple streams: {received_by_stream.keys()}"
    
    @live_only
    @pytest.mark.asyncio
    async def test_websocket_sequence_numbers(self):
        """Test that WebSocket messages have proper sequence numbers."""
        self.require_live_mode()
        
        sequence_numbers = []
        
        async def message_handler(message: Dict[str, Any]):
            data = message.get("data", {})
            if "u" in data:  # Update ID/sequence number
                sequence_numbers.append(int(data["u"]))
        
        # Connect and subscribe
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        await self.ws_client.subscribe_depth("SOL_USDC")
        
        # Collect messages
        await asyncio.sleep(5)
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Validate sequence numbers are increasing
        if len(sequence_numbers) > 1:
            for i in range(1, len(sequence_numbers)):
                assert sequence_numbers[i] >= sequence_numbers[i-1], \
                    f"Sequence should be non-decreasing: {sequence_numbers[i-1]} -> {sequence_numbers[i]}"
    
    @live_only
    @pytest.mark.asyncio
    async def test_websocket_order_updates(self):
        """Test WebSocket order update streaming."""
        self.require_live_mode()
        
        order_updates = []
        
        async def message_handler(message: Dict[str, Any]):
            if message.get("stream") == "orderUpdate":
                order_updates.append(message["data"])
        
        # Connect and subscribe to order updates
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        await self.ws_client.subscribe_orders()
        
        # Place and cancel a test order to generate updates
        ticker = await self.http_client.get_ticker("SOL_USDC")
        market_price = Decimal(ticker["lastPrice"])
        test_price = Decimal(str(round(float(market_price) * 0.9, 2)))
        
        order_result = await self.http_client.place_order(
            symbol="SOL_USDC",
            side="Bid",
            orderType="Limit",
            price=str(test_price),
            quantity="0.1",
            timeInForce="GTC",
        )
        
        order_id = order_result["id"]
        
        # Wait for order update
        await asyncio.sleep(2)
        
        # Cancel order
        await self.http_client.cancel_order("SOL_USDC", order_id)
        
        # Wait for cancel update
        await asyncio.sleep(2)
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Validate order updates
        assert len(order_updates) >= 1, "Should receive order updates"
        
        for update in order_updates:
            assert "e" in update, "Should have event type"
            assert "s" in update, "Should have symbol"
            assert "i" in update, "Should have order ID"
            assert "S" in update, "Should have side"
            assert "X" in update, "Should have status"
    
    @live_only
    @pytest.mark.asyncio
    async def test_websocket_data_consistency(self):
        """Test consistency between WebSocket and REST data."""
        self.require_live_mode()
        
        ws_depth = None
        
        async def message_handler(message: Dict[str, Any]):
            nonlocal ws_depth
            if message.get("stream") == "depth":
                ws_depth = message["data"]
        
        # Connect and subscribe
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        await self.ws_client.subscribe_depth("SOL_USDC")
        
        # Wait for depth update
        await asyncio.sleep(3)
        
        # Get REST depth at same time
        rest_depth = await self.http_client.get_depth("SOL_USDC")
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Compare if we got WebSocket data
        if ws_depth:
            # Extract best bid/ask from both
            ws_bids = ws_depth.get("bids", ws_depth.get("b", []))
            ws_asks = ws_depth.get("asks", ws_depth.get("a", []))
            
            if ws_bids and ws_asks and rest_depth["bids"] and rest_depth["asks"]:
                ws_best_bid = Decimal(ws_bids[0][0])
                ws_best_ask = Decimal(ws_asks[0][0])
                rest_best_bid = Decimal(rest_depth["bids"][0][0])
                rest_best_ask = Decimal(rest_depth["asks"][0][0])
                
                # Prices should be close (within 1% due to timing)
                bid_diff = abs(ws_best_bid - rest_best_bid) / rest_best_bid
                ask_diff = abs(ws_best_ask - rest_best_ask) / rest_best_ask
                
                assert bid_diff < Decimal("0.01"), f"Bid difference too large: {bid_diff}"
                assert ask_diff < Decimal("0.01"), f"Ask difference too large: {ask_diff}"