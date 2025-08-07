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
Backpack Exchange futures execution client.
"""

import asyncio
from decimal import Decimal

import msgspec

from nautilus_trader.adapters.backpack.common.account import BackpackUnifiedAccountManager
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.execution import BackpackExecutionClient
from nautilus_trader.adapters.backpack.futures.enums import BackpackFuturesPositionSide
from nautilus_trader.adapters.backpack.futures.enums import backpack_futures_position_side_to_nautilus
from nautilus_trader.adapters.backpack.futures.enums import nautilus_position_side_to_backpack_futures
from nautilus_trader.adapters.backpack.futures.enums import order_side_to_position_side
from nautilus_trader.adapters.backpack.futures.http.position import BackpackFuturesPositionHttpAPI
from nautilus_trader.adapters.backpack.futures.providers import BackpackFuturesInstrumentProvider
from nautilus_trader.adapters.backpack.futures.schemas.position import BackpackFuturesPosition
from nautilus_trader.adapters.backpack.futures.schemas.position import BackpackFuturesPositionUpdate
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.execution.messages import GeneratePositionStatusReports
from nautilus_trader.execution.reports import PositionStatusReport
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.orders import Order


class BackpackFuturesExecutionClient(BackpackExecutionClient):
    """
    Provides an execution client for the Backpack Exchange futures markets.
    
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
    instrument_provider : BackpackFuturesInstrumentProvider
        The futures instrument provider.
    config : BackpackExecClientConfig
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
        config: BackpackExecClientConfig,
        name: str | None = None,
    ) -> None:
        # Initialize parent class
        super().__init__(
            loop=loop,
            client=client,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
            name=name or "BACKPACK-FUTURES",
        )
        
        # Override account type for futures
        self._oms_type = OmsType.HEDGING  # Futures uses hedging
        
        # Futures-specific HTTP API
        self._futures_http_position = BackpackFuturesPositionHttpAPI(client)
        
        # Position tracking
        self._is_dual_side_position = True  # Futures always uses dual-side (hedge mode)
        self._positions: dict[str, BackpackFuturesPosition] = {}
        
        # WebSocket message decoders
        self._decoder_position_update = msgspec.json.Decoder(BackpackFuturesPositionUpdate)
        
        self._log.info("BackpackFuturesExecutionClient initialized", LogColor.GREEN)
        self._log.info(f"Account type: {self._account_type}", LogColor.BLUE)
        self._log.info(f"OMS type: {self._oms_type}", LogColor.BLUE)
    
    async def _update_account_state(self) -> None:
        """Update account state including futures positions."""
        # Call parent to update unified account
        await super()._update_account_state()
        
        # Fetch and process futures positions
        await self._update_positions()
        
        # Update unified account with futures positions
        if self._account_manager and self._account_manager._unified_account:
            self._account_manager._unified_account.futuresPositions = list(self._positions.values())
    
    async def _update_positions(self) -> None:
        """Update all futures positions."""
        try:
            positions = await self._futures_http_position.fetch_positions()
            
            for position in positions:
                self._positions[position.symbol] = position
                
                # Generate position status report
                instrument_id = InstrumentId(Symbol(position.symbol), BACKPACK_VENUE)
                
                # Create position ID
                position_id = PositionId(f"{position.symbol}_{position.side}")
                
                # Create position status report
                report = PositionStatusReport(
                    account_id=self._account_id,
                    instrument_id=instrument_id,
                    position_side=backpack_futures_position_side_to_nautilus(position.side),
                    quantity=position.size,
                    report_id=position_id,
                    ts_last=millis_to_nanos(int(position.timestamp * 1000)),
                    ts_init=self._clock.timestamp_ns(),
                )
                
                self._handle_position_status_report(report)
            
            self._log.info(f"Updated {len(positions)} futures positions")
            
        except Exception as e:
            self._log.error(f"Failed to update positions: {e}")
    
    async def _generate_position_status_reports(
        self,
        symbol: Symbol | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> list[PositionStatusReport]:
        """Generate position status reports for futures positions."""
        reports = []
        
        if symbol:
            # Single symbol
            backpack_symbol = self._get_backpack_symbol(
                InstrumentId(symbol, BACKPACK_VENUE),
            )
            positions = await self._futures_http_position.fetch_positions(backpack_symbol)
        else:
            # All positions
            positions = await self._futures_http_position.fetch_positions()
        
        for position in positions:
            instrument_id = self._get_cached_instrument_id(position.symbol)
            
            # Create position ID if using position IDs
            position_id = None
            if self._use_position_ids:
                position_id = PositionId(f"{position.symbol}_{position.side}")
            
            report = position.parse_to_position_status_report(
                account=self.get_account(),
                instrument_id=instrument_id,
                position_id=position_id,
                ts_init=self._clock.timestamp_ns(),
            )
            
            reports.append(report)
        
        return reports
    
    def _check_order_validity(self, order: Order) -> bool:
        """Check if order is valid for futures trading."""
        # Call parent validation first
        if not super()._check_order_validity(order):
            return False
        
        # Futures-specific validations
        if order.order_type == OrderType.MARKET:
            # Market orders don't support post-only
            if order.is_post_only:
                self._log.error("Market orders cannot be post-only in futures")
                return False
        
        # Check reduce-only compatibility
        if order.is_reduce_only:
            # Need to verify position exists
            symbol = self._get_backpack_symbol(order.instrument_id)
            position = self._positions.get(symbol)
            
            if not position or Decimal(position.size) == 0:
                self._log.error(f"Cannot place reduce-only order: no position for {symbol}")
                return False
        
        return True
    
    async def _submit_order(self, command: Order) -> None:
        """Submit order with futures-specific parameters."""
        # Add futures-specific parameters
        order_data = await self._build_order_data(command)
        
        # Add reduce-only flag if applicable
        if command.is_reduce_only:
            order_data["reduceOnly"] = True
        
        # Add position side for hedge mode
        if self._is_dual_side_position:
            position_side = order_side_to_position_side(
                command.side,
                command.is_reduce_only,
            )
            order_data["positionSide"] = nautilus_position_side_to_backpack_futures(position_side)
        
        # Submit the order
        await self._submit_order_data(order_data, command)
    
    async def modify_leverage(
        self,
        instrument_id: InstrumentId,
        leverage: int,
    ) -> None:
        """
        Modify leverage for a futures instrument.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument to modify leverage for.
        leverage : int
            The new leverage value (1-125).
        """
        symbol = self._get_backpack_symbol(instrument_id)
        
        try:
            result = await self._futures_http_position.modify_leverage(symbol, leverage)
            self._log.info(f"Modified leverage for {symbol} to {leverage}x: {result}")
        except Exception as e:
            self._log.error(f"Failed to modify leverage for {symbol}: {e}")
    
    async def modify_margin_type(
        self,
        instrument_id: InstrumentId,
        margin_type: str,
    ) -> None:
        """
        Modify margin type for a futures instrument.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument to modify margin type for.
        margin_type : str
            The margin type (CROSS or ISOLATED).
        """
        symbol = self._get_backpack_symbol(instrument_id)
        
        try:
            result = await self._futures_http_position.modify_margin_type(symbol, margin_type)
            self._log.info(f"Modified margin type for {symbol} to {margin_type}: {result}")
        except Exception as e:
            self._log.error(f"Failed to modify margin type for {symbol}: {e}")
    
    async def add_margin(
        self,
        instrument_id: InstrumentId,
        amount: str,
    ) -> None:
        """
        Add margin to an isolated futures position.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument to add margin to.
        amount : str
            The amount of margin to add.
        """
        symbol = self._get_backpack_symbol(instrument_id)
        
        try:
            result = await self._futures_http_position.add_margin(symbol, amount)
            self._log.info(f"Added {amount} margin to {symbol}: {result}")
        except Exception as e:
            self._log.error(f"Failed to add margin to {symbol}: {e}")
    
    def _handle_ws_message(self, raw: bytes) -> None:
        """Handle incoming WebSocket messages."""
        # Try parent class handlers first
        super()._handle_ws_message(raw)
        
        # Try futures-specific handlers
        try:
            # Check if it's a position update
            if b"POSITION_UPDATE" in raw:
                self._handle_position_update(raw)
        except Exception as e:
            self._log.error(f"Failed to handle futures WebSocket message: {e}")
    
    def _handle_position_update(self, raw: bytes) -> None:
        """Handle position update WebSocket message."""
        update = self._decoder_position_update.decode(raw)
        
        # Update cached position
        # TODO: Update position cache and generate report
        
        self._log.debug(f"Received position update: {update}")