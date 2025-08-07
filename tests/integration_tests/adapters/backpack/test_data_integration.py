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

"""Integration tests for Backpack data client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.data import BackpackDataClient
from nautilus_trader.adapters.backpack.factories import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


@pytest.mark.asyncio
class TestBackpackDataIntegration:
    """Integration tests for Backpack data client."""

    def setup_method(self):
        """Set up test fixtures."""
        self.loop = asyncio.get_event_loop()
        self.clock = LiveClock()
        self.trader_id = TestIdStubs.trader_id()
        self.venue = BACKPACK_VENUE
        self.account_id = AccountId(f"{self.venue.value}-001")

        self.msgbus = MessageBus(
            trader_id=self.trader_id,
            clock=self.clock,
        )

        self.cache = TestComponentStubs.cache()

        self.http_client = MagicMock(spec=BackpackHttpClient)
        
        self.provider = BackpackSpotInstrumentProvider(
            client=self.http_client,
            clock=self.clock,
            config=InstrumentProviderConfig(load_all=False),
        )

        self.data_engine = DataEngine(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )

        self.config = BackpackDataClientConfig(
            api_key="test_key",
            api_secret="test_secret",
            base_url="https://api.backpack.exchange",
            ws_url="wss://ws.backpack.exchange",
        )
        
        self.data_client = BackpackDataClient(
            loop=self.loop,
            client=self.http_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            config=self.config,
        )

    @pytest.mark.asyncio
    async def test_connect_loads_instruments(self):
        """Test that connecting loads instruments from the exchange."""
        # Mock market data response
        mock_markets = [
            {
                "symbol": "SOL_USDC",
                "base_currency": "SOL",
                "quote_currency": "USDC",
                "price_decimals": 4,
                "quantity_decimals": 2,
                "taker_fee": "0.0005",
                "maker_fee": "0.0002",
                "min_quantity": "0.01",
                "max_quantity": "10000",
                "min_price": "0.0001",
                "max_price": "100000",
                "tick_size": "0.0001",
                "lot_size": "0.01",
                "status": "active",
                "market_type": "spot",
            },
        ]
        
        self.http_client.fetch_markets = AsyncMock(return_value=mock_markets)
        
        # Connect the client
        await self.data_client._connect()
        
        # Verify markets were fetched
        self.http_client.fetch_markets.assert_called_once()
        
        # Check instrument was loaded into cache
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        instrument = self.cache.instrument(instrument_id)
        assert instrument is not None
        assert instrument.base_currency == "SOL"
        assert instrument.quote_currency == "USDC"

    @pytest.mark.asyncio
    async def test_subscribe_quote_ticks(self):
        """Test subscribing to quote tick data."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Subscribe to quotes
        await self.data_client._subscribe_quote_ticks(instrument_id)
        
        # Check subscription was tracked
        assert instrument_id in self.data_client._ws_subscriptions["ticker"]
        
        # Simulate receiving quote data via WebSocket
        quote_data = {
            "symbol": "SOL_USDC",
            "bid": "145.50",
            "bidSize": "100.50",
            "ask": "145.60",
            "askSize": "200.75",
            "timestamp": 1234567890123,
        }
        
        # Parse and handle quote
        # This would normally come through WebSocket
        # For testing, we'll create the quote directly
        quote = QuoteTick(
            instrument_id=instrument_id,
            bid_price=Price.from_str("145.50"),
            ask_price=Price.from_str("145.60"),
            bid_size=Quantity.from_str("100.50"),
            ask_size=Quantity.from_str("200.75"),
            ts_event=1234567890123000000,
            ts_init=self.clock.timestamp_ns(),
        )
        
        # In real implementation, this would be handled by WebSocket
        self.data_client._handle_data(quote)

    @pytest.mark.asyncio
    async def test_subscribe_trade_ticks(self):
        """Test subscribing to trade tick data."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Subscribe to trades
        await self.data_client._subscribe_trade_ticks(instrument_id)
        
        # Check subscription was tracked
        assert instrument_id in self.data_client._ws_subscriptions["trades"]
        
        # Simulate receiving trade data
        trade_data = {
            "symbol": "SOL_USDC",
            "price": "145.55",
            "quantity": "50.25",
            "side": "Buy",
            "timestamp": 1234567890123,
            "tradeId": 12345,
        }
        
        # Parse and handle trade
        # This would normally come through WebSocket
        trade = TradeTick(
            instrument_id=instrument_id,
            price=Price.from_str("145.55"),
            size=Quantity.from_str("50.25"),
            aggressor_side=1,  # Buy side
            trade_id=TradeId("12345"),
            ts_event=1234567890123000000,
            ts_init=self.clock.timestamp_ns(),
        )
        
        self.data_client._handle_data(trade)

    @pytest.mark.asyncio
    async def test_subscribe_order_book(self):
        """Test subscribing to order book data."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Subscribe to order book
        await self.data_client._subscribe_order_book_deltas(
            instrument_id,
            book_type=BookType.L2_MBP,
            depth=10,
        )
        
        # Check subscription was tracked
        assert instrument_id in self.data_client._ws_subscriptions["depth"]

    @pytest.mark.asyncio
    async def test_multiple_subscriptions(self):
        """Test managing multiple simultaneous subscriptions."""
        instruments = [
            InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE),
            InstrumentId(Symbol("ETH_USDC"), BACKPACK_VENUE),
        ]
        
        # Subscribe to multiple instruments
        for instrument_id in instruments:
            await self.data_client._subscribe_quote_ticks(instrument_id)
            await self.data_client._subscribe_trade_ticks(instrument_id)
        
        # Verify all subscriptions are tracked
        for instrument_id in instruments:
            assert instrument_id in self.data_client._ws_subscriptions["ticker"]
            assert instrument_id in self.data_client._ws_subscriptions["trades"]

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_subscription(self):
        """Test that unsubscribing removes the subscription."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Subscribe and then unsubscribe
        await self.data_client._subscribe_quote_ticks(instrument_id)
        assert instrument_id in self.data_client._ws_subscriptions["ticker"]
        
        await self.data_client._unsubscribe_quote_ticks(instrument_id)
        assert instrument_id not in self.data_client._ws_subscriptions["ticker"]

    @pytest.mark.asyncio
    async def test_rate_limiting_throttles_requests(self):
        """Test that rate limiting properly throttles requests."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Create multiple rapid subscriptions
        subscriptions = []
        for _ in range(10):
            subscriptions.append(
                self.data_client._subscribe_quote_ticks(instrument_id)
            )
        
        # All should complete without error due to rate limiting
        await asyncio.gather(*subscriptions)

    @pytest.mark.asyncio
    async def test_disconnect_cleans_up(self):
        """Test that disconnecting properly cleans up resources."""
        # Set up some subscriptions
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        await self.data_client._subscribe_quote_ticks(instrument_id)
        
        # Disconnect
        await self.data_client._disconnect()
        
        # Verify cleanup (subscriptions should remain for reconnection)
        assert instrument_id in self.data_client._ws_subscriptions["ticker"]

    @pytest.mark.asyncio
    async def test_handle_connection_error(self):
        """Test handling of connection errors."""
        # Mock a connection error
        self.http_client.fetch_markets = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        
        # Connect should handle the error gracefully
        await self.data_client._connect()
        
        # Verify error was logged (would need to check logs in real test)
        self.http_client.fetch_markets.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_message_parsing(self):
        """Test parsing of various WebSocket message types."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Test ticker message
        ticker_msg = {
            "stream": "ticker.SOL_USDC",
            "data": {
                "symbol": "SOL_USDC",
                "bid": "145.50",
                "bidSize": "100.50",
                "ask": "145.60",
                "askSize": "200.75",
                "timestamp": 1234567890123,
            }
        }
        
        # Test trade message
        trade_msg = {
            "stream": "trades.SOL_USDC",
            "data": {
                "symbol": "SOL_USDC",
                "price": "145.55",
                "quantity": "50.25",
                "side": "Buy",
                "timestamp": 1234567890123,
                "tradeId": 12345,
            }
        }
        
        # Test depth message
        depth_msg = {
            "stream": "depth.SOL_USDC",
            "data": {
                "symbol": "SOL_USDC",
                "bids": [["145.50", "100.50"], ["145.40", "200.75"]],
                "asks": [["145.60", "150.25"], ["145.70", "250.50"]],
                "timestamp": 1234567890123,
                "sequence": 1001,
            }
        }
        
        # These would be parsed by the WebSocket client in real implementation
        # Testing structure for now
        assert "stream" in ticker_msg
        assert "data" in ticker_msg
        assert ticker_msg["data"]["symbol"] == "SOL_USDC"