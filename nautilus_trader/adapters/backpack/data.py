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

"""Backpack exchange data client implementation."""

import asyncio
from typing import Any

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.http.account import BackpackAccountHttpAPI
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.parsing import parse_market
from nautilus_trader.adapters.backpack.parsing import parse_order_book
from nautilus_trader.adapters.backpack.parsing import parse_ticker
from nautilus_trader.adapters.backpack.parsing import parse_trade
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.live.data_client import LiveMarketDataClient
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import DataType
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Instrument


class BackpackDataClient(LiveMarketDataClient):
    """
    Provides a data client for the Backpack exchange.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop for the client.
    client : BackpackHttpClient
        The Backpack HTTP client.
    msgbus : MessageBus
        The message bus for the client.
    cache : Cache
        The cache for the client.
    clock : LiveClock
        The clock for the client.
    config : BackpackDataClientConfig
        The configuration for the client.
    name : str, optional
        The custom client ID.

    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        client: BackpackHttpClient,
        msgbus: MessageBus,
        cache: Cache,
        clock: LiveClock,
        config: BackpackDataClientConfig,
        name: str | None = None,
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name or BACKPACK_VENUE.value),
            venue=BACKPACK_VENUE,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            instrument_provider=None,  # Will implement provider later
            config=config,
        )

        self._http_client = client
        self._log = Logger(name=name or BACKPACK_VENUE.value)
        
        # Account HTTP API for collateral data
        self._account_http = BackpackAccountHttpAPI(client)
        
        # WebSocket subscriptions tracking
        self._ws_subscriptions: dict[str, set[InstrumentId]] = {
            "ticker": set(),
            "trades": set(),
            "depth": set(),
            "markPrice": set(),  # For collateral valuation
        }
        
        # Last update timestamps for rate limiting
        self._last_quotes: dict[InstrumentId, int] = {}
        self._last_trades: dict[InstrumentId, int] = {}
        
        # Collateral weights and mark prices cache
        self._collateral_weights: dict[str, float] = {}
        self._mark_prices: dict[str, float] = {}
        self._collateral_update_task: asyncio.Task | None = None

    async def _connect(self) -> None:
        """Connect the data client."""
        self._log.info("Connecting to Backpack...")
        
        # Initialize instruments
        await self._load_instruments()
        
        # Load initial collateral weights
        await self._update_collateral_weights()
        
        # Start periodic collateral weight updates (every 60 seconds)
        self._collateral_update_task = asyncio.create_task(
            self._periodic_collateral_update()
        )
        
        # Connect WebSocket if needed
        if self._ws_subscriptions:
            # WebSocket connection will be implemented in Phase 2
            pass
            
        self._log.info("Connected to Backpack")

    async def _disconnect(self) -> None:
        """Disconnect the data client."""
        self._log.info("Disconnecting from Backpack...")
        
        # Cancel collateral update task
        if self._collateral_update_task:
            self._collateral_update_task.cancel()
            try:
                await self._collateral_update_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket connections
        # Will be implemented in Phase 2
        
        self._log.info("Disconnected from Backpack")

    async def _load_instruments(self) -> None:
        """Load all instruments from the exchange."""
        try:
            markets = await self._http_client.fetch_markets()
            
            for market_data in markets:
                instrument = parse_market(market_data)
                if instrument:
                    self._cache.add_instrument(instrument)
                    
            self._log.info(f"Loaded {len(markets)} instruments from Backpack")
            
        except Exception as e:
            self._log.error(f"Failed to load instruments: {e}")

    async def _subscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        """Subscribe to trade tick data for an instrument."""
        PyCondition.not_none(instrument_id, "instrument_id")
        
        self._ws_subscriptions["trades"].add(instrument_id)
        self._log.info(f"Subscribed to trade ticks for {instrument_id}")
        
        # WebSocket subscription will be implemented in Phase 2
        # For now, we can poll the REST API
        await self._poll_trades(instrument_id)

    async def _subscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        """Subscribe to quote tick data for an instrument."""
        PyCondition.not_none(instrument_id, "instrument_id")
        
        self._ws_subscriptions["ticker"].add(instrument_id)
        self._log.info(f"Subscribed to quote ticks for {instrument_id}")
        
        # WebSocket subscription will be implemented in Phase 2
        # For now, we can poll the REST API
        await self._poll_ticker(instrument_id)

    async def _subscribe_order_book_deltas(
        self,
        instrument_id: InstrumentId,
        book_type: BookType,
        depth: int | None = None,
        kwargs: dict | None = None,
    ) -> None:
        """Subscribe to order book delta data for an instrument."""
        PyCondition.not_none(instrument_id, "instrument_id")
        
        self._ws_subscriptions["depth"].add(instrument_id)
        self._log.info(f"Subscribed to order book deltas for {instrument_id}")
        
        # WebSocket subscription will be implemented in Phase 2
        # For now, we can poll the REST API
        await self._poll_order_book(instrument_id, depth)

    async def _subscribe_order_book_snapshots(
        self,
        instrument_id: InstrumentId,
        book_type: BookType,
        depth: int | None = None,
        kwargs: dict | None = None,
    ) -> None:
        """Subscribe to order book snapshot data for an instrument."""
        # Backpack doesn't have separate snapshot subscription
        # We'll use deltas subscription
        await self._subscribe_order_book_deltas(
            instrument_id=instrument_id,
            book_type=book_type,
            depth=depth,
            kwargs=kwargs,
        )

    async def _subscribe_bars(self, bar_type: BarType) -> None:
        """Subscribe to bar data for a bar type."""
        PyCondition.not_none(bar_type, "bar_type")
        
        self._log.warning(
            "Bar subscriptions not yet implemented for Backpack, "
            "will be available in Phase 2",
        )

    async def _unsubscribe_trade_ticks(self, instrument_id: InstrumentId) -> None:
        """Unsubscribe from trade tick data for an instrument."""
        self._ws_subscriptions["trades"].discard(instrument_id)
        self._log.info(f"Unsubscribed from trade ticks for {instrument_id}")

    async def _unsubscribe_quote_ticks(self, instrument_id: InstrumentId) -> None:
        """Unsubscribe from quote tick data for an instrument."""
        self._ws_subscriptions["ticker"].discard(instrument_id)
        self._log.info(f"Unsubscribed from quote ticks for {instrument_id}")

    async def _unsubscribe_order_book_deltas(self, instrument_id: InstrumentId) -> None:
        """Unsubscribe from order book delta data for an instrument."""
        self._ws_subscriptions["depth"].discard(instrument_id)
        self._log.info(f"Unsubscribed from order book deltas for {instrument_id}")

    async def _unsubscribe_order_book_snapshots(self, instrument_id: InstrumentId) -> None:
        """Unsubscribe from order book snapshot data for an instrument."""
        await self._unsubscribe_order_book_deltas(instrument_id)

    async def _unsubscribe_bars(self, bar_type: BarType) -> None:
        """Unsubscribe from bar data for a bar type."""
        self._log.warning(
            "Bar unsubscriptions not yet implemented for Backpack, "
            "will be available in Phase 2",
        )

    async def _request_instrument(self, instrument_id: InstrumentId, correlation_id: UUID4) -> None:
        """Request instrument details."""
        # Backpack doesn't have individual instrument endpoint
        # We need to fetch all markets and filter
        try:
            markets = await self._http_client.fetch_markets()
            
            for market_data in markets:
                instrument = parse_market(market_data)
                if instrument and instrument.id == instrument_id:
                    self._cache.add_instrument(instrument)
                    self._log.info(f"Loaded instrument {instrument_id}")
                    return
                    
            self._log.warning(f"Instrument {instrument_id} not found")
            
        except Exception as e:
            self._log.error(f"Failed to request instrument {instrument_id}: {e}")

    async def _request_instruments(self, venue: Venue, correlation_id: UUID4) -> None:
        """Request all instruments for the venue."""
        await self._load_instruments()

    async def _request_quote_ticks(
        self,
        instrument_id: InstrumentId,
        limit: int,
        correlation_id: UUID4,
        start: int | None = None,
        end: int | None = None,
    ) -> None:
        """Request historical quote ticks."""
        try:
            ticker_data = await self._http_client.fetch_ticker(
                symbol=instrument_id.symbol.value,
            )
            
            quote_tick = parse_ticker(ticker_data, instrument_id)
            if quote_tick:
                self._handle_quote_tick(quote_tick)
                
        except Exception as e:
            self._log.error(f"Failed to request quote ticks for {instrument_id}: {e}")

    async def _request_trade_ticks(
        self,
        instrument_id: InstrumentId,
        limit: int,
        correlation_id: UUID4,
        start: int | None = None,
        end: int | None = None,
    ) -> None:
        """Request historical trade ticks."""
        try:
            trades_data = await self._http_client.fetch_trades(
                symbol=instrument_id.symbol.value,
                limit=limit,
            )
            
            for trade_data in trades_data:
                trade_tick = parse_trade(trade_data, instrument_id)
                if trade_tick:
                    self._handle_trade_tick(trade_tick)
                    
        except Exception as e:
            self._log.error(f"Failed to request trade ticks for {instrument_id}: {e}")

    async def _request_bars(
        self,
        bar_type: BarType,
        limit: int,
        correlation_id: UUID4,
        start: int | None = None,
        end: int | None = None,
    ) -> None:
        """Request historical bars."""
        self._log.warning(
            "Bar requests not yet implemented for Backpack, "
            "will be available in Phase 2",
        )

    # Polling methods (temporary until WebSocket implementation)
    async def _poll_ticker(self, instrument_id: InstrumentId) -> None:
        """Poll ticker data via REST API."""
        try:
            ticker_data = await self._http_client.fetch_ticker(
                symbol=instrument_id.symbol.value,
            )
            
            quote_tick = parse_ticker(ticker_data, instrument_id)
            if quote_tick:
                self._handle_quote_tick(quote_tick)
                
        except Exception as e:
            self._log.error(f"Failed to poll ticker for {instrument_id}: {e}")

    async def _poll_trades(self, instrument_id: InstrumentId) -> None:
        """Poll trade data via REST API."""
        try:
            trades_data = await self._http_client.fetch_trades(
                symbol=instrument_id.symbol.value,
                limit=10,
            )
            
            for trade_data in trades_data:
                trade_tick = parse_trade(trade_data, instrument_id)
                if trade_tick:
                    self._handle_trade_tick(trade_tick)
                    
        except Exception as e:
            self._log.error(f"Failed to poll trades for {instrument_id}: {e}")

    async def _poll_order_book(self, instrument_id: InstrumentId, depth: int | None) -> None:
        """Poll order book data via REST API."""
        try:
            orderbook_data = await self._http_client.fetch_order_book(
                symbol=instrument_id.symbol.value,
                depth=depth or 20,
            )
            
            order_book_deltas = parse_order_book(orderbook_data, instrument_id)
            if order_book_deltas:
                self._handle_order_book_deltas(order_book_deltas)
                
        except Exception as e:
            self._log.error(f"Failed to poll order book for {instrument_id}: {e}")
    
    async def _update_collateral_weights(self) -> None:
        """Update collateral weights from the exchange."""
        try:
            # Fetch collateral information
            collateral = await self._account_http.fetch_collateral()
            
            # Update collateral weights
            self._collateral_weights.clear()
            for asset in collateral.assets:
                self._collateral_weights[asset.asset] = float(asset.weight)
            
            # Fetch collateral details for mark prices
            collateral_details = await self._account_http.fetch_collateral_details()
            
            # Update mark prices
            self._mark_prices.clear()
            for detail in collateral_details:
                self._mark_prices[detail.asset] = float(detail.markPrice)
            
            self._log.debug(
                f"Updated collateral weights for {len(self._collateral_weights)} assets",
            )
            
        except Exception as e:
            self._log.error(f"Failed to update collateral weights: {e}")
    
    async def _periodic_collateral_update(self) -> None:
        """Periodically update collateral weights."""
        while True:
            try:
                await asyncio.sleep(60)  # Update every 60 seconds
                await self._update_collateral_weights()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"Error in periodic collateral update: {e}")
                await asyncio.sleep(5)  # Retry after 5 seconds on error
    
    def get_collateral_weight(self, asset: str) -> float | None:
        """
        Get the collateral weight for an asset.
        
        Parameters
        ----------
        asset : str
            The asset symbol (e.g., "BTC", "SOL", "USDC").
        
        Returns
        -------
        float | None
            The collateral weight, or None if not available.
        
        """
        return self._collateral_weights.get(asset)
    
    def get_mark_price(self, asset: str) -> float | None:
        """
        Get the mark price for an asset.
        
        Parameters
        ----------
        asset : str
            The asset symbol (e.g., "BTC", "SOL").
        
        Returns
        -------
        float | None
            The mark price, or None if not available.
        
        """
        return self._mark_prices.get(asset)