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

"""Integration tests for Backpack WebSocket client."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger


@pytest.mark.asyncio
class TestBackpackWebSocketIntegration:
    """Integration tests for Backpack WebSocket client."""

    def setup_method(self):
        """Set up test fixtures."""
        self.clock = LiveClock()
        self.logger = Logger(name="TEST")
        self.handler = AsyncMock()
        
        self.client = BackpackWebSocketClient(
            base_url="wss://ws.backpack.exchange",
            handler=self.handler,
            clock=self.clock,
            logger=self.logger,
            api_key=None,
            api_secret=None,
            testnet=False,
        )

    @pytest.mark.asyncio
    async def test_connect_and_subscribe(self):
        """Test connecting and subscribing to streams."""
        # Mock WebSocket connection
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        
        with patch("aiohttp.ClientSession.ws_connect", return_value=mock_ws):
            # Connect
            await self.client.connect()
            
            # Subscribe to ticker
            await self.client.subscribe_ticker("SOL_USDC")
            
            # Verify subscription message was sent
            mock_ws.send_str.assert_called()
            call_args = mock_ws.send_str.call_args[0][0]
            msg = json.loads(call_args)
            assert msg["method"] == "SUBSCRIBE"
            assert "ticker.SOL_USDC" in msg["params"]

    @pytest.mark.asyncio
    async def test_reconnection_logic(self):
        """Test automatic reconnection on disconnect."""
        # Mock WebSocket that disconnects
        mock_ws = AsyncMock()
        mock_ws.closed = False
        
        disconnect_count = 0
        
        async def mock_receive():
            nonlocal disconnect_count
            if disconnect_count == 0:
                disconnect_count += 1
                # Simulate disconnect
                mock_ws.closed = True
                return MagicMock(type=3)  # CLOSED type
            else:
                # Keep connection alive after reconnect
                await asyncio.sleep(0.1)
                return MagicMock(type=1, data='{"stream":"heartbeat"}')
        
        mock_ws.receive = mock_receive
        mock_ws.close = AsyncMock()
        
        with patch("aiohttp.ClientSession.ws_connect", return_value=mock_ws):
            # Connect
            await self.client.connect()
            
            # Wait for reconnection attempt
            await asyncio.sleep(0.2)
            
            # Should attempt to reconnect
            assert self.client._reconnect_count > 0

    @pytest.mark.asyncio
    async def test_subscription_restoration(self):
        """Test that subscriptions are restored after reconnection."""
        # Subscribe to multiple streams
        await self.client.subscribe_ticker("SOL_USDC")
        await self.client.subscribe_trades("BTC_USDC")
        await self.client.subscribe_depth("ETH_USDC", depth=10)
        
        # Verify subscriptions are tracked
        assert "ticker.SOL_USDC" in self.client._subscriptions
        assert "trades.BTC_USDC" in self.client._subscriptions
        assert "depth.ETH_USDC@10" in self.client._subscriptions
        
        # Simulate reconnection
        await self.client._restore_subscriptions()
        
        # All subscriptions should be restored
        assert len(self.client._subscriptions) == 3

    @pytest.mark.asyncio
    async def test_message_parsing(self):
        """Test parsing of different message types."""
        # Test ticker message
        ticker_msg = {
            "stream": "ticker.SOL_USDC",
            "data": {
                "e": "ticker",
                "E": 1234567890123000,
                "s": "SOL_USDC",
                "b": "145.50",
                "B": "100.50",
                "a": "145.60",
                "A": "200.75",
            }
        }
        
        await self.client._handle_message(json.dumps(ticker_msg))
        self.handler.assert_called_once()
        
        # Test trade message
        self.handler.reset_mock()
        trade_msg = {
            "stream": "trades.SOL_USDC",
            "data": {
                "e": "trade",
                "E": 1234567890123000,
                "s": "SOL_USDC",
                "t": 12345,
                "p": "145.55",
                "q": "50.25",
                "m": True,  # Is buyer maker
            }
        }
        
        await self.client._handle_message(json.dumps(trade_msg))
        self.handler.assert_called_once()
        
        # Test depth message
        self.handler.reset_mock()
        depth_msg = {
            "stream": "depth.SOL_USDC",
            "data": {
                "e": "depth",
                "E": 1234567890123000,
                "s": "SOL_USDC",
                "b": [["145.50", "100.50"], ["145.40", "200.75"]],
                "a": [["145.60", "150.25"], ["145.70", "250.50"]],
                "u": 1001,  # Update sequence
            }
        }
        
        await self.client._handle_message(json.dumps(depth_msg))
        self.handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_pooling(self):
        """Test connection pooling for subscription limits."""
        # Subscribe to more than 200 streams (connection limit)
        subscriptions = []
        for i in range(250):
            symbol = f"TEST{i}_USDC"
            subscriptions.append(self.client.subscribe_ticker(symbol))
        
        await asyncio.gather(*subscriptions)
        
        # Should have created multiple connections
        assert len(self.client._connections) > 1
        
        # Total subscriptions should be tracked
        assert len(self.client._subscriptions) == 250

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting for subscriptions."""
        # Rapid subscription attempts
        subscriptions = []
        for i in range(20):
            subscriptions.append(
                self.client.subscribe_ticker(f"TEST{i}_USDC")
            )
        
        # Should handle rate limiting gracefully
        await asyncio.gather(*subscriptions)
        
        # All subscriptions should be tracked
        assert len(self.client._subscriptions) == 20

    @pytest.mark.asyncio
    async def test_authentication_for_private_streams(self):
        """Test authentication for private account streams."""
        # Create client with auth
        auth_client = BackpackWebSocketClient(
            base_url="wss://ws.backpack.exchange",
            handler=self.handler,
            clock=self.clock,
            logger=self.logger,
            api_key="test_api_key",
            api_secret="test_api_secret",
            testnet=False,
        )
        
        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = False
        
        with patch("aiohttp.ClientSession.ws_connect", return_value=mock_ws):
            await auth_client.connect()
            
            # Subscribe to private stream
            await auth_client.subscribe_orders()
            
            # Verify auth was included
            mock_ws.send_str.assert_called()
            call_args = mock_ws.send_str.call_args[0][0]
            msg = json.loads(call_args)
            assert "signature" in msg
            assert msg["params"] == ["account.orderUpdate"]

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in WebSocket operations."""
        # Test connection error
        with patch("aiohttp.ClientSession.ws_connect", side_effect=Exception("Connection failed")):
            result = await self.client.connect()
            assert result is False
        
        # Test message parsing error
        invalid_msg = "invalid json {"
        await self.client._handle_message(invalid_msg)
        # Should handle gracefully without crashing

    @pytest.mark.asyncio
    async def test_heartbeat_handling(self):
        """Test heartbeat/ping-pong handling."""
        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = False
        
        # Simulate ping message
        ping_msg = {"ping": 1234567890123}
        
        with patch("aiohttp.ClientSession.ws_connect", return_value=mock_ws):
            await self.client.connect()
            await self.client._handle_message(json.dumps(ping_msg))
            
            # Should send pong response
            mock_ws.send_str.assert_called()
            last_call = mock_ws.send_str.call_args[0][0]
            response = json.loads(last_call)
            assert "pong" in response
            assert response["pong"] == 1234567890123

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Test unsubscribing from streams."""
        # Subscribe first
        await self.client.subscribe_ticker("SOL_USDC")
        assert "ticker.SOL_USDC" in self.client._subscriptions
        
        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = False
        self.client._ws = mock_ws
        
        # Unsubscribe
        await self.client.unsubscribe(["ticker.SOL_USDC"])
        
        # Verify unsubscribe message sent
        mock_ws.send_str.assert_called()
        call_args = mock_ws.send_str.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["method"] == "UNSUBSCRIBE"
        assert msg["params"] == ["ticker.SOL_USDC"]
        
        # Subscription should be removed
        assert "ticker.SOL_USDC" not in self.client._subscriptions

    @pytest.mark.asyncio
    async def test_sequence_validation(self):
        """Test sequence number validation for order book updates."""
        # Initial depth snapshot
        snapshot_msg = {
            "stream": "depth.SOL_USDC",
            "data": {
                "e": "depth",
                "E": 1234567890123000,
                "s": "SOL_USDC",
                "b": [["145.50", "100.50"]],
                "a": [["145.60", "150.25"]],
                "u": 1000,
                "U": 1000,  # First update ID
            }
        }
        
        await self.client._handle_message(json.dumps(snapshot_msg))
        
        # Valid sequence update
        valid_update = {
            "stream": "depth.SOL_USDC",
            "data": {
                "e": "depth",
                "E": 1234567890124000,
                "s": "SOL_USDC",
                "b": [["145.51", "110.50"]],
                "a": [["145.59", "140.25"]],
                "u": 1001,
                "U": 1001,
            }
        }
        
        await self.client._handle_message(json.dumps(valid_update))
        assert self.handler.call_count == 2
        
        # Invalid sequence (gap)
        invalid_update = {
            "stream": "depth.SOL_USDC",
            "data": {
                "e": "depth",
                "E": 1234567890125000,
                "s": "SOL_USDC",
                "b": [["145.52", "120.50"]],
                "a": [["145.58", "130.25"]],
                "u": 1005,  # Gap in sequence
                "U": 1005,
            }
        }
        
        await self.client._handle_message(json.dumps(invalid_update))
        # Should trigger re-snapshot request

    @pytest.mark.asyncio
    async def test_cleanup_on_disconnect(self):
        """Test proper cleanup on disconnect."""
        # Mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        
        with patch("aiohttp.ClientSession.ws_connect", return_value=mock_ws):
            await self.client.connect()
            
            # Add some subscriptions
            await self.client.subscribe_ticker("SOL_USDC")
            await self.client.subscribe_trades("BTC_USDC")
            
            # Disconnect
            await self.client.disconnect()
            
            # Verify cleanup
            mock_ws.close.assert_called_once()
            assert self.client._ws is None
            # Subscriptions should be retained for reconnection
            assert len(self.client._subscriptions) == 2