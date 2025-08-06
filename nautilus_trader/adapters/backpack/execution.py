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

"""Backpack exchange execution client implementation."""

import asyncio
from decimal import Decimal
from typing import Any

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.common.enums import (
    backpack_order_side_from_nautilus,
    backpack_order_status_to_nautilus,
    backpack_order_type_from_nautilus,
    backpack_time_in_force_from_nautilus,
)
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.parsing import parse_balance
from nautilus_trader.adapters.backpack.parsing import parse_order
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.accounting.accounts.cash import CashAccount
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.messages import CancelAllOrders
from nautilus_trader.execution.messages import CancelOrder
from nautilus_trader.execution.messages import ModifyOrder
from nautilus_trader.execution.messages import SubmitOrder
from nautilus_trader.execution.messages import SubmitOrderList
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import VenueOrderId
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.objects import Money
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.orders import Order


class BackpackExecutionClient(LiveExecutionClient):
    """
    Provides an execution client for the Backpack exchange.

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
        super().__init__(
            loop=loop,
            client_id=ClientId(name or BACKPACK_VENUE.value),
            venue=BACKPACK_VENUE,
            oms_type=OmsType.NETTING,  # Backpack uses netting accounts
            account_type=AccountType.CASH,
            base_currency=USD,  # Can be configured
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )

        self._http_client = client
        self._log = Logger(name=name or BACKPACK_VENUE.value)
        self._ws_client: BackpackWebSocketClient | None = None
        
        # Order tracking
        self._pending_orders: dict[ClientOrderId, Order] = {}
        self._venue_order_ids: dict[ClientOrderId, VenueOrderId] = {}
        
        # Account information
        self._account_id = AccountId(f"{BACKPACK_VENUE}-SPOT-{config.account_id or '001'}")
        self._account: CashAccount | None = None

    async def _connect(self) -> None:
        """Connect the execution client."""
        self._log.info("Connecting to Backpack execution...")
        
        # Initialize account
        await self._update_account_state()
        
        # Connect WebSocket for order updates
        self._ws_client = BackpackWebSocketClient(
            api_key=self._http_client._api_key,
            api_secret=self._http_client._api_secret,
            testnet=self._http_client._testnet,
            handler=self._handle_ws_message,
            logger=self._log,
        )
        
        await self._ws_client.connect()
        
        # Subscribe to order updates
        await self._ws_client.subscribe_order_update()
        
        self._log.info("Connected to Backpack execution with WebSocket")

    async def _disconnect(self) -> None:
        """Disconnect the execution client."""
        self._log.info("Disconnecting from Backpack execution...")
        
        # Close WebSocket connections
        if self._ws_client:
            await self._ws_client.disconnect()
            self._ws_client = None
        
        self._log.info("Disconnected from Backpack execution")

    async def _update_account_state(self) -> None:
        """Update the account state from the exchange."""
        try:
            balances_data = await self._http_client.fetch_balance()
            
            balances = []
            for balance_data in balances_data.get("balances", []):
                account_balance = parse_balance(balance_data)
                if account_balance:
                    balances.append(account_balance)
            
            if not balances:
                # Add a default balance if none exist
                balances.append(
                    AccountBalance(
                        total=Money(0, USD),
                        locked=Money(0, USD),
                        free=Money(0, USD),
                    ),
                )
            
            account_state = AccountState(
                account_id=self._account_id,
                account_type=AccountType.CASH,
                base_currency=USD,
                reported=True,
                balances=balances,
                margins=[],
                info={},
                event_id=UUID4(),
                ts_event=self._clock.timestamp_ns(),
                ts_init=self._clock.timestamp_ns(),
            )
            
            self._send_account_state(account_state)
            self._log.info(f"Updated account state for {self._account_id}")
            
        except Exception as e:
            self._log.error(f"Failed to update account state: {e}")

    async def _submit_order(self, command: SubmitOrder) -> None:
        """Submit an order to the exchange."""
        PyCondition.not_none(command, "command")
        
        order = command.order
        self._pending_orders[order.client_order_id] = order
        
        try:
            # Prepare order parameters
            params = {
                "symbol": order.instrument_id.symbol.value,
                "side": backpack_order_side_from_nautilus(order.side),
                "quantity": str(order.quantity),
                "client_order_id": str(order.client_order_id),
            }
            
            if isinstance(order, LimitOrder):
                params["order_type"] = "Limit"
                params["price"] = str(order.price)
                params["time_in_force"] = backpack_time_in_force_from_nautilus(
                    order.time_in_force,
                )
            elif isinstance(order, MarketOrder):
                params["order_type"] = "Market"
            else:
                self._log.error(f"Unsupported order type: {type(order)}")
                return
            
            # Submit order to exchange
            response = await self._http_client.create_order(**params)
            
            # Parse response and generate events
            if response:
                venue_order_id = VenueOrderId(str(response.get("id", "")))
                self._venue_order_ids[order.client_order_id] = venue_order_id
                
                # Generate order accepted event
                self.generate_order_accepted(
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    venue_order_id=venue_order_id,
                    ts_event=self._clock.timestamp_ns(),
                )
                
                # Check if order was immediately filled
                status = backpack_order_status_to_nautilus(response.get("status", ""))
                if status == OrderStatus.FILLED:
                    self._handle_order_filled(order, response)
                    
            self._log.info(f"Submitted order {order.client_order_id}")
            
        except Exception as e:
            self._log.error(f"Failed to submit order {order.client_order_id}: {e}")
            
            # Generate order rejected event
            self.generate_order_rejected(
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=str(e),
                ts_event=self._clock.timestamp_ns(),
            )
            
            self._pending_orders.pop(order.client_order_id, None)

    async def _submit_order_list(self, command: SubmitOrderList) -> None:
        """Submit a list of orders to the exchange."""
        PyCondition.not_none(command, "command")
        
        # Backpack supports batch orders
        # Will implement in Phase 3
        self._log.warning("Batch order submission not yet implemented for Backpack")
        
        # For now, submit orders individually
        for order in command.order_list.orders:
            submit_command = SubmitOrder(
                trader_id=command.trader_id,
                strategy_id=command.strategy_id,
                order=order,
                command_id=UUID4(),
                ts_init=self._clock.timestamp_ns(),
            )
            await self._submit_order(submit_command)

    async def _modify_order(self, command: ModifyOrder) -> None:
        """Modify an existing order."""
        PyCondition.not_none(command, "command")
        
        # Backpack doesn't support order modification
        # Need to cancel and replace
        self._log.warning(
            f"Order modification not supported by Backpack, "
            f"consider cancel and replace for order {command.client_order_id}",
        )

    async def _cancel_order(self, command: CancelOrder) -> None:
        """Cancel an order on the exchange."""
        PyCondition.not_none(command, "command")
        
        try:
            venue_order_id = self._venue_order_ids.get(command.client_order_id)
            
            if venue_order_id:
                response = await self._http_client.cancel_order(
                    order_id=venue_order_id.value,
                    symbol=command.instrument_id.symbol.value,
                    client_order_id=str(command.client_order_id),
                )
                
                if response:
                    # Generate order canceled event
                    self.generate_order_canceled(
                        strategy_id=command.strategy_id,
                        instrument_id=command.instrument_id,
                        client_order_id=command.client_order_id,
                        venue_order_id=venue_order_id,
                        ts_event=self._clock.timestamp_ns(),
                    )
                    
                    self._log.info(f"Canceled order {command.client_order_id}")
            else:
                self._log.warning(
                    f"Cannot cancel order {command.client_order_id}: "
                    f"venue order ID not found",
                )
                
        except Exception as e:
            self._log.error(f"Failed to cancel order {command.client_order_id}: {e}")

    async def _cancel_all_orders(self, command: CancelAllOrders) -> None:
        """Cancel all orders for an instrument."""
        PyCondition.not_none(command, "command")
        
        try:
            # Fetch open orders
            open_orders = await self._http_client.fetch_open_orders(
                symbol=command.instrument_id.symbol.value if command.instrument_id else None,
            )
            
            # Cancel each order
            for order_data in open_orders:
                order_id = order_data.get("id")
                if order_id:
                    await self._http_client.cancel_order(
                        order_id=order_id,
                        symbol=order_data.get("symbol"),
                    )
                    
            self._log.info(
                f"Canceled all orders for "
                f"{command.instrument_id or 'all instruments'}",
            )
            
        except Exception as e:
            self._log.error(f"Failed to cancel all orders: {e}")

    def _handle_order_filled(self, order: Order, response: dict) -> None:
        """Handle a filled order."""
        filled_qty = Decimal(str(response.get("executedQuantity", "0")))
        avg_price = Decimal(str(response.get("avgFillPrice", "0")))
        
        if filled_qty > 0:
            # Generate order filled event
            venue_order_id = self._venue_order_ids.get(order.client_order_id)
            
            self.generate_order_filled(
                strategy_id=order.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                venue_order_id=venue_order_id,
                venue_position_id=None,  # Backpack doesn't use position IDs
                trade_id=VenueOrderId(str(response.get("id", ""))),
                order_side=order.side,
                order_type=order.order_type,
                last_qty=order.quantity,
                last_px=order.price if isinstance(order, LimitOrder) else avg_price,
                quote_currency=order.instrument_id.quote_currency,
                commission=Money(0, USD),  # Will be calculated from fees
                liquidity_side=order.liquidity_side,
                ts_event=self._clock.timestamp_ns(),
            )
            
        self._pending_orders.pop(order.client_order_id, None)
    
    def _handle_ws_message(self, data: dict) -> None:
        """Handle WebSocket message for order updates."""
        stream = data.get("stream", "")
        
        if "orderUpdate" in stream:
            self._handle_order_update(data)
        elif "positionUpdate" in stream:
            self._handle_position_update(data)
        else:
            self._log.debug(f"Unhandled execution stream: {stream}")
    
    def _handle_order_update(self, data: dict) -> None:
        """Handle order update from WebSocket."""
        try:
            # Parse order update based on event type
            event_type = data.get("data", {}).get("e", "")
            
            if event_type == "orderAccepted":
                self._handle_order_accepted(data)
            elif event_type == "orderFill":
                self._handle_order_fill(data)
            elif event_type == "orderCancelled":
                self._handle_order_cancelled(data)
            elif event_type == "orderExpired":
                self._handle_order_expired(data)
            else:
                self._log.debug(f"Unhandled order event type: {event_type}")
                
        except Exception as e:
            self._log.error(f"Error handling order update: {e}")
    
    def _handle_order_accepted(self, data: dict) -> None:
        """Handle order accepted event."""
        # Extract order details from WebSocket message
        order_data = data.get("data", {})
        client_order_id_str = order_data.get("c")
        venue_order_id_str = order_data.get("i")
        
        if not venue_order_id_str:
            return
            
        # Find the corresponding pending order
        for client_order_id, order in self._pending_orders.items():
            if client_order_id_str and str(client_order_id) == client_order_id_str:
                # Generate accepted event
                venue_order_id = VenueOrderId(venue_order_id_str)
                self._venue_order_ids[client_order_id] = venue_order_id
                
                self.generate_order_accepted(
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=client_order_id,
                    venue_order_id=venue_order_id,
                    ts_event=order_data.get("T", self._clock.timestamp_ns()),
                )
                break
    
    def _handle_order_fill(self, data: dict) -> None:
        """Handle order fill event."""
        # Extract fill details from WebSocket message
        order_data = data.get("data", {})
        venue_order_id_str = order_data.get("i")
        
        if not venue_order_id_str:
            return
            
        # Find the corresponding order
        venue_order_id = VenueOrderId(venue_order_id_str)
        
        # Generate fill event
        # Implementation details would parse the fill data
        # and generate appropriate fill events
        
    def _handle_order_cancelled(self, data: dict) -> None:
        """Handle order cancelled event."""
        # Extract cancellation details from WebSocket message
        order_data = data.get("data", {})
        venue_order_id_str = order_data.get("i")
        
        if not venue_order_id_str:
            return
            
        # Generate cancelled event
        venue_order_id = VenueOrderId(venue_order_id_str)
        
        # Find client order ID
        for client_order_id, v_order_id in self._venue_order_ids.items():
            if v_order_id == venue_order_id:
                order = self._cache.order(client_order_id)
                if order:
                    self.generate_order_canceled(
                        strategy_id=order.strategy_id,
                        instrument_id=order.instrument_id,
                        client_order_id=client_order_id,
                        venue_order_id=venue_order_id,
                        ts_event=order_data.get("T", self._clock.timestamp_ns()),
                    )
                break
    
    def _handle_order_expired(self, data: dict) -> None:
        """Handle order expired event."""
        # Similar to cancelled but with expired status
        self._handle_order_cancelled(data)
    
    def _handle_position_update(self, data: dict) -> None:
        """Handle position update from WebSocket."""
        # Position updates for futures trading
        # Will be implemented when futures support is added
        pass