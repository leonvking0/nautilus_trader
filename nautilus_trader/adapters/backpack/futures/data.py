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
"""
Backpack Exchange futures data client.
"""

import asyncio

import msgspec

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.data import BackpackDataClient
from nautilus_trader.adapters.backpack.futures.http.market import BackpackFuturesMarketHttpAPI
from nautilus_trader.adapters.backpack.futures.schemas.market import BackpackFundingRateMsg
from nautilus_trader.adapters.backpack.futures.schemas.market import BackpackMarkPriceMsg
from nautilus_trader.adapters.backpack.futures.schemas.market import BackpackOpenInterestMsg
from nautilus_trader.adapters.backpack.futures.types import BackpackFuturesMarkPriceUpdate
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.enums import LogColor
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.data import DataType
from nautilus_trader.model.data import MarkPriceUpdate
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId


class BackpackFuturesDataClient(BackpackDataClient):
    """
    Provides a data client for the Backpack Exchange futures markets.
    
    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    http_client : BackpackHttpClient
        The Backpack HTTP client.
    ws_client : BackpackWebSocketClient
        The Backpack WebSocket client.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    instrument_provider : InstrumentProvider
        The instrument provider.
    config : BackpackDataClientConfig
        The configuration for the client.
    name : str, optional
        The custom client ID.
    """
    
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        http_client: BackpackHttpClient,
        ws_client: BackpackWebSocketClient,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        instrument_provider: InstrumentProvider,
        config: BackpackDataClientConfig,
        name: str | None = None,
    ) -> None:
        super().__init__(
            loop=loop,
            http_client=http_client,
            ws_client=ws_client,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=instrument_provider,
            config=config,
            name=name,
        )
        
        # Futures-specific HTTP API
        self._futures_http_market = BackpackFuturesMarketHttpAPI(http_client)
        
        # Additional WebSocket message decoders
        self._decoder_mark_price = msgspec.json.Decoder(BackpackMarkPriceMsg)
        self._decoder_funding_rate = msgspec.json.Decoder(BackpackFundingRateMsg)
        self._decoder_open_interest = msgspec.json.Decoder(BackpackOpenInterestMsg)
        
        # Register custom data types
        self._custom_data_types = {
            BackpackFuturesMarkPriceUpdate: self._handle_mark_price_update,
        }
        
        self._log.info("BackpackFuturesDataClient initialized", LogColor.GREEN)
    
    async def _subscribe_mark_price(self, symbol: str) -> None:
        """Subscribe to mark price updates for a symbol."""
        stream = f"markPrice.{symbol}"
        await self._ws_client.subscribe([stream])
        self._log.info(f"Subscribed to {stream}")
    
    async def _unsubscribe_mark_price(self, symbol: str) -> None:
        """Unsubscribe from mark price updates for a symbol."""
        stream = f"markPrice.{symbol}"
        await self._ws_client.unsubscribe([stream])
        self._log.info(f"Unsubscribed from {stream}")
    
    async def _subscribe_funding_rate(self, symbol: str) -> None:
        """Subscribe to funding rate updates for a symbol."""
        stream = f"fundingRate.{symbol}"
        await self._ws_client.subscribe([stream])
        self._log.info(f"Subscribed to {stream}")
    
    async def _unsubscribe_funding_rate(self, symbol: str) -> None:
        """Unsubscribe from funding rate updates for a symbol."""
        stream = f"fundingRate.{symbol}"
        await self._ws_client.unsubscribe([stream])
        self._log.info(f"Unsubscribed from {stream}")
    
    async def _subscribe_open_interest(self, symbol: str) -> None:
        """Subscribe to open interest updates for a symbol."""
        stream = f"openInterest.{symbol}"
        await self._ws_client.subscribe([stream])
        self._log.info(f"Subscribed to {stream}")
    
    async def _unsubscribe_open_interest(self, symbol: str) -> None:
        """Unsubscribe from open interest updates for a symbol."""
        stream = f"openInterest.{symbol}"
        await self._ws_client.unsubscribe([stream])
        self._log.info(f"Unsubscribed from {stream}")
    
    def _handle_ws_message(self, raw: bytes) -> None:
        """Handle incoming WebSocket messages."""
        # Try parent class handlers first
        super()._handle_ws_message(raw)
        
        # Try futures-specific handlers
        try:
            # Check if it's a mark price message
            if b"markPrice" in raw:
                self._handle_mark_price_msg(raw)
            elif b"fundingRate" in raw:
                self._handle_funding_rate_msg(raw)
            elif b"openInterest" in raw:
                self._handle_open_interest_msg(raw)
        except Exception as e:
            self._log.error(f"Failed to handle futures WebSocket message: {e}")
    
    def _handle_mark_price_msg(self, raw: bytes) -> None:
        """Handle mark price WebSocket message."""
        msg = self._decoder_mark_price.decode(raw)
        
        # Get instrument ID
        instrument_id = self._get_cached_instrument_id(msg.data.symbol)
        
        # Parse to mark price update
        mark_price_update = msg.data.parse_to_mark_price_update(
            instrument_id=instrument_id,
            ts_init=self._clock.timestamp_ns(),
        )
        
        # Create custom data wrapper
        data_type = DataType(
            BackpackFuturesMarkPriceUpdate,
            metadata={"instrument_id": instrument_id},
        )
        custom_data = CustomData(data_type=data_type, data=mark_price_update)
        
        # Handle the custom data
        self._handle_data(custom_data)
        
        # Also emit standard MarkPriceUpdate
        self._handle_data(
            MarkPriceUpdate(
                instrument_id=instrument_id,
                price=mark_price_update.mark_price,
                ts_event=mark_price_update.ts_event,
                ts_init=mark_price_update.ts_init,
            ),
        )
    
    def _handle_funding_rate_msg(self, raw: bytes) -> None:
        """Handle funding rate WebSocket message."""
        msg = self._decoder_funding_rate.decode(raw)
        # TODO: Implement funding rate handling
        self._log.debug(f"Received funding rate: {msg.data}")
    
    def _handle_open_interest_msg(self, raw: bytes) -> None:
        """Handle open interest WebSocket message."""
        msg = self._decoder_open_interest.decode(raw)
        # TODO: Implement open interest handling
        self._log.debug(f"Received open interest: {msg.data}")
    
    def _handle_mark_price_update(self, data: BackpackFuturesMarkPriceUpdate) -> None:
        """Handle mark price update custom data."""
        # This is called when custom data is received
        # The data is already handled in _handle_mark_price_msg
        pass
    
    async def request_mark_prices(
        self,
        symbol: str | None = None,
    ) -> list:
        """
        Request mark prices for futures.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to request. If None, requests all.
            
        Returns
        -------
        list
            The mark price data.
        """
        return await self._futures_http_market.fetch_mark_prices(symbol)
    
    async def request_funding_rates(
        self,
        symbol: str | None = None,
    ) -> list:
        """
        Request funding rates for futures.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to request. If None, requests all.
            
        Returns
        -------
        list
            The funding rate data.
        """
        return await self._futures_http_market.fetch_funding_rates(symbol)
    
    async def request_open_interest(
        self,
        symbol: str | None = None,
    ) -> list:
        """
        Request open interest for futures.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to request. If None, requests all.
            
        Returns
        -------
        list
            The open interest data.
        """
        return await self._futures_http_market.fetch_open_interest(symbol)