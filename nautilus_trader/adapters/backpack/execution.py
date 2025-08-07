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

from nautilus_trader.adapters.backpack.common.account import BackpackUnifiedAccountManager
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.common.enums import (
    backpack_order_side_from_nautilus,
    backpack_order_status_to_nautilus,
    backpack_order_type_from_nautilus,
    backpack_time_in_force_from_nautilus,
)
from nautilus_trader.adapters.backpack.common.system_orders import BackpackSystemOrderHandler
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.http.account import BackpackAccountHttpAPI
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.parsing import parse_balance
from nautilus_trader.adapters.backpack.parsing import parse_order
from nautilus_trader.adapters.backpack.schemas.advanced_orders import BackpackAdvancedOrderParams
from nautilus_trader.adapters.backpack.schemas.advanced_orders import backpack_order_type_for_stop
from nautilus_trader.adapters.backpack.schemas.advanced_orders import backpack_trigger_type_from_nautilus
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.accounting.accounts.margin import MarginAccount
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.providers import InstrumentProvider
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
from nautilus_trader.model.enums import TriggerType
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
from nautilus_trader.model.orders import StopLimitOrder
from nautilus_trader.model.orders import StopMarketOrder
from nautilus_trader.model.orders import TrailingStopMarketOrder


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
    instrument_provider : InstrumentProvider
        The instrument provider for the client.
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
        instrument_provider: InstrumentProvider,
        config: BackpackExecClientConfig,
        name: str | None = None,
    ) -> None:
        super().__init__(
            loop=loop,
            client_id=ClientId(name or BACKPACK_VENUE.value),
            venue=BACKPACK_VENUE,
            oms_type=OmsType.NETTING,  # Backpack uses netting accounts
            account_type=AccountType.MARGIN,  # Unified account is margin type
            base_currency=USD,  # Can be configured
            instrument_provider=instrument_provider,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
        )

        self._http_client = client
        self._ws_client: BackpackWebSocketClient | None = None
        
        # Order tracking
        self._pending_orders: dict[ClientOrderId, Order] = {}
        self._venue_order_ids: dict[ClientOrderId, VenueOrderId] = {}
        
        # Account information
        self._account_id = AccountId(f"{BACKPACK_VENUE}-UNIFIED-001")
        self._account: MarginAccount | None = None
        
        # Unified account manager (will be shared with futures client)
        self._account_manager: BackpackUnifiedAccountManager | None = None
        
        # System order handler for liquidations, ADL, etc.
        self._system_order_handler: BackpackSystemOrderHandler | None = None
        
        # Order submission method mapping
        self._submit_order_methods = {
            OrderType.MARKET: self._submit_market_order,
            OrderType.LIMIT: self._submit_limit_order,
            OrderType.STOP_MARKET: self._submit_stop_market_order,
            OrderType.STOP_LIMIT: self._submit_stop_limit_order,
            OrderType.TRAILING_STOP_MARKET: self._submit_trailing_stop_market_order,
        }

    def set_account_manager(self, account_manager: BackpackUnifiedAccountManager) -> None:
        """
        Set the unified account manager (for sharing with futures client).
        
        Parameters
        ----------
        account_manager : BackpackUnifiedAccountManager
            The unified account manager to use.
        """
        self._account_manager = account_manager
        self._log.info("Using shared unified account manager")

    async def _connect(self) -> None:
        """Connect the execution client."""
        self._log.info("Connecting to Backpack execution...")
        
        # Initialize unified account manager
        if not self._account_manager:
            account_http = BackpackAccountHttpAPI(self._http_client)
            self._account_manager = BackpackUnifiedAccountManager(
                account_http=account_http,
                logger=self._log,
            )
            
            # Initialize account
            self._account = await self._account_manager.initialize(
                account_id=self._account_id,
                base_currency=self.base_currency,
            )
        
        # Update account state
        await self._update_account_state()
        
        # Initialize system order handler
        self._system_order_handler = BackpackSystemOrderHandler(
            msgbus=self._msgbus,
            account_id=self._account_id,
            logger=self._log,
        )
        
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
        
        self._log.info("Connected to Backpack execution with WebSocket and system order handler")

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
            if not self._account_manager:
                self._log.error("Account manager not initialized")
                return
                
            # Refresh unified account state
            unified_account = await self._account_manager.refresh_account_state()
            if not unified_account:
                self._log.error("Failed to refresh unified account state")
                return
            
            # Get the updated Nautilus account
            if self._account_manager._nautilus_account:
                self._account = self._account_manager._nautilus_account
                
                # Get unified position information
                unified_positions = self._account_manager.get_unified_positions()
                total_margin_used = self._account_manager.calculate_total_margin_used()
                
                # Create account state from the unified account
                account_state = AccountState(
                    account_id=self._account_id,
                    account_type=AccountType.MARGIN,
                    base_currency=self._base_currency,
                    reported=True,
                    balances=self._account.balances(),
                    margins=self._account.margins(),
                    info={
                        "totalCollateral": str(unified_account.totalCollateral),
                        "availableCollateral": str(unified_account.availableCollateral),
                        "marginRatio": str(unified_account.marginRatio),
                        "totalBorrowLiability": str(unified_account.totalBorrowLiability),
                        "totalMarginUsed": str(total_margin_used),
                        "positionCount": str(len(unified_positions)),
                    },
                    event_id=UUID4(),
                    ts_event=self._clock.timestamp_ns(),
                    ts_init=self._clock.timestamp_ns(),
                )
                
                self._send_account_state(account_state)
                self._log.info(
                    f"Updated unified account state for {self._account_id} "
                    f"with {len(unified_positions)} positions",
                )
            
        except Exception as e:
            self._log.error(f"Failed to update account state: {e}")

    async def _submit_order(self, command: SubmitOrder) -> None:
        """Submit an order to the exchange."""
        PyCondition.not_none(command, "command")
        
        order = command.order
        self._pending_orders[order.client_order_id] = order
        
        try:
            # Check and execute auto-borrow if needed (for buy orders)
            if self._account_manager and order.side == OrderSide.BUY:
                # Calculate required USDC for the order
                if isinstance(order, LimitOrder):
                    required_usdc = Decimal(str(order.price)) * Decimal(str(order.quantity))
                elif isinstance(order, MarketOrder):
                    # For market orders, estimate based on current market price
                    # This is a simplified estimation - should use actual market price
                    required_usdc = Decimal(str(order.quantity)) * Decimal("100")  # Placeholder
                else:
                    required_usdc = Decimal("0")
                
                # Check and execute auto-borrow
                if required_usdc > 0:
                    success = await self._account_manager.check_and_execute_auto_borrow(
                        required_usdc=required_usdc,
                    )
                    if not success:
                        self._log.warning(
                            f"Auto-borrow check failed for order {order.client_order_id}",
                        )
            
            # Use order type specific submission method
            submit_method = self._submit_order_methods.get(order.order_type)
            if submit_method is None:
                self._log.error(f"Unsupported order type: {order.order_type}")
                self.generate_order_rejected(
                    strategy_id=order.strategy_id,
                    instrument_id=order.instrument_id,
                    client_order_id=order.client_order_id,
                    reason=f"Unsupported order type: {order.order_type}",
                    ts_event=self._clock.timestamp_ns(),
                )
                self._pending_orders.pop(order.client_order_id, None)
                return
            
            # Submit order using the appropriate method
            response = await submit_method(order)
            
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

    def _apply_take_profit_stop_loss(self, order: Order, params: BackpackAdvancedOrderParams) -> None:
        """
        Apply take profit and stop loss parameters from order tags.
        
        Parameters
        ----------
        order : Order
            The order to extract tags from.
        params : BackpackAdvancedOrderParams
            The parameters to update with TP/SL values.
        
        """
        if order.tags is None:
            return
            
        # Parse tags for take profit and stop loss
        # Expected format: "tp:150.5" or "sl:140.0" or "tp:150.5,sl:140.0"
        for tag in order.tags.split(","):
            tag = tag.strip()
            if tag.startswith("tp:"):
                # Take profit
                tp_price = tag[3:]
                params.take_profit_trigger_price = tp_price
                params.take_profit_trigger_by = "LastPrice"
            elif tag.startswith("sl:"):
                # Stop loss
                sl_price = tag[3:]
                params.stop_loss_trigger_price = sl_price
                params.stop_loss_trigger_by = "LastPrice"
            elif tag.startswith("tp_limit:"):
                # Take profit limit price
                params.take_profit_limit_price = tag[9:]
            elif tag.startswith("sl_limit:"):
                # Stop loss limit price
                params.stop_loss_limit_price = tag[9:]
            elif tag.startswith("tp_by:"):
                # Take profit trigger by
                params.take_profit_trigger_by = tag[6:]
            elif tag.startswith("sl_by:"):
                # Stop loss trigger by
                params.stop_loss_trigger_by = tag[6:]

    async def _submit_market_order(self, order: MarketOrder) -> dict | None:
        """Submit a market order to the exchange."""
        advanced_params = BackpackAdvancedOrderParams(
            symbol=order.instrument_id.symbol.value,
            side=backpack_order_side_from_nautilus(order.side),
            order_type="Market",
            quantity=str(order.quantity),
            client_order_id=str(order.client_order_id),
        )
        
        # Check for take profit/stop loss tags
        self._apply_take_profit_stop_loss(order, advanced_params)
        
        params = advanced_params.to_request_params()
        return await self._http_client.create_order(**params)

    async def _submit_limit_order(self, order: LimitOrder) -> dict | None:
        """Submit a limit order to the exchange."""
        advanced_params = BackpackAdvancedOrderParams(
            symbol=order.instrument_id.symbol.value,
            side=backpack_order_side_from_nautilus(order.side),
            order_type="Limit",
            quantity=str(order.quantity),
            price=str(order.price),
            time_in_force=backpack_time_in_force_from_nautilus(order.time_in_force),
            client_order_id=str(order.client_order_id),
        )
        
        # Handle post-only orders
        if order.is_post_only:
            advanced_params.post_only = True
            
        # Handle iceberg orders
        if order.display_qty is not None:
            advanced_params.iceberg_qty = str(order.display_qty)
            
        # Check for take profit/stop loss tags
        self._apply_take_profit_stop_loss(order, advanced_params)
        
        params = advanced_params.to_request_params()
        return await self._http_client.create_order(**params)

    async def _submit_stop_market_order(self, order: StopMarketOrder) -> dict | None:
        """Submit a stop market order to the exchange."""
        advanced_params = BackpackAdvancedOrderParams(
            symbol=order.instrument_id.symbol.value,
            side=backpack_order_side_from_nautilus(order.side),
            order_type="Stop",
            quantity=str(order.quantity),
            trigger_price=str(order.trigger_price),
            trigger_by=backpack_trigger_type_from_nautilus(order.trigger_type),
            client_order_id=str(order.client_order_id),
        )
        
        # Handle reduce-only orders
        if order.is_reduce_only:
            advanced_params.reduce_only = True
        
        params = advanced_params.to_request_params()
        return await self._http_client.create_order(**params)

    async def _submit_stop_limit_order(self, order: StopLimitOrder) -> dict | None:
        """Submit a stop limit order to the exchange."""
        advanced_params = BackpackAdvancedOrderParams(
            symbol=order.instrument_id.symbol.value,
            side=backpack_order_side_from_nautilus(order.side),
            order_type="StopLimit",
            quantity=str(order.quantity),
            price=str(order.price),
            trigger_price=str(order.trigger_price),
            trigger_by=backpack_trigger_type_from_nautilus(order.trigger_type),
            time_in_force=backpack_time_in_force_from_nautilus(order.time_in_force),
            client_order_id=str(order.client_order_id),
        )
        
        # Handle reduce-only orders
        if order.is_reduce_only:
            advanced_params.reduce_only = True
            
        # Handle post-only orders
        if order.is_post_only:
            advanced_params.post_only = True
            
        # Handle iceberg orders
        if order.display_qty is not None:
            advanced_params.iceberg_qty = str(order.display_qty)
        
        params = advanced_params.to_request_params()
        return await self._http_client.create_order(**params)

    async def _submit_trailing_stop_market_order(self, order: TrailingStopMarketOrder) -> dict | None:
        """Submit a trailing stop market order to the exchange."""
        # Check if Backpack supports trailing stops natively
        # For now, we'll implement client-side trailing logic
        self._log.warning(
            f"Trailing stop orders not yet fully implemented for Backpack. "
            f"Order {order.client_order_id} will be submitted as a regular stop order.",
        )
        
        # Convert to a regular stop market order for now
        # In a full implementation, we would track price and adjust the stop
        advanced_params = BackpackAdvancedOrderParams(
            symbol=order.instrument_id.symbol.value,
            side=backpack_order_side_from_nautilus(order.side),
            order_type="Stop",
            quantity=str(order.quantity),
            trigger_price=str(order.trigger_price) if order.trigger_price else None,
            trigger_by=backpack_trigger_type_from_nautilus(order.trigger_type),
            client_order_id=str(order.client_order_id),
        )
        
        # Handle reduce-only orders
        if order.is_reduce_only:
            advanced_params.reduce_only = True
        
        params = advanced_params.to_request_params()
        return await self._http_client.create_order(**params)

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
            # Check if this is a system order
            order_data = data.get("data", {})
            if self._system_order_handler:
                system_order = self._system_order_handler.identify_system_order(order_data)
                if system_order:
                    self._log.warning(
                        f"System order detected: type={system_order.order_type} "
                        f"reason={system_order.reason} id={system_order.order_id}",
                    )
                    # Publish system order event to message bus
                    self._msgbus.publish(
                        topic="backpack.system_order",
                        msg={"system_order": system_order, "raw_data": order_data},
                    )
            
            # Parse order update based on event type
            event_type = order_data.get("e", "")
            
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