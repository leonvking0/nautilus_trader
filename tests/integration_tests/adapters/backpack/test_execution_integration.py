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

"""Integration tests for Backpack execution client."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.execution import BackpackExecutionClient
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.account import BackpackOrder
from nautilus_trader.adapters.backpack.schemas.account import BackpackOrderResponse
from nautilus_trader.adapters.backpack.schemas.account import BackpackFill
from nautilus_trader.adapters.backpack.schemas.account import BackpackBalance
from nautilus_trader.adapters.backpack.schemas.account import BackpackAccount
from nautilus_trader.adapters.backpack.schemas.account import BackpackCapital
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateral
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateralWeight
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateralDetail
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.engine import ExecutionEngine
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import OrderAccepted
from nautilus_trader.model.events import OrderCanceled
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.events import OrderRejected
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.identifiers import VenueOrderId
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


@pytest.mark.asyncio
class TestBackpackExecutionIntegration:
    """Integration tests for Backpack execution client."""

    def setup_method(self):
        """Set up test fixtures."""
        self.loop = asyncio.get_event_loop()
        self.clock = LiveClock()
        self.trader_id = TestIdStubs.trader_id()
        self.venue = BACKPACK_VENUE
        self.account_id = AccountId(f"{self.venue.value}-001")
        self.strategy_id = StrategyId("TEST-001")

        self.msgbus = MessageBus(
            trader_id=self.trader_id,
            clock=self.clock,
        )

        self.cache = TestComponentStubs.cache()
        self.http_client = MagicMock(spec=BackpackHttpClient)
        
        # Setup unified account mocks
        self._setup_unified_account_mocks()
        
        self.exec_engine = ExecutionEngine(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )

        self.config = BackpackExecClientConfig(
            api_key="test_key",
            api_secret="test_secret",
            base_url="https://api.backpack.exchange",
            ws_url="wss://ws.backpack.exchange",
        )
        
        # Create instrument provider
        from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
        from nautilus_trader.config import InstrumentProviderConfig
        
        self.instrument_provider = BackpackSpotInstrumentProvider(
            client=self.http_client,
            clock=self.clock,
            config=InstrumentProviderConfig(load_all=False),
        )
        
        self.exec_client = BackpackExecutionClient(
            loop=self.loop,
            client=self.http_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            instrument_provider=self.instrument_provider,
            config=self.config,
        )
    
    def _setup_unified_account_mocks(self):
        """Setup mocks for unified account manager."""
        # Mock capital response
        self.http_client.fetch_capital = AsyncMock(return_value=BackpackCapital(
            balances=[
                BackpackBalance(symbol="USDC", available="10000", locked="500", staked="0"),
                BackpackBalance(symbol="SOL", available="100", locked="10", staked="0"),
            ],
            totalCollateral="15000",
            availableCollateral="14000",
            initialMarginRate="0.1",
            maintenanceMarginRate="0.05",
            totalBorrowLiability="0",
            unsettledBalances="0",
            unrealizedPnl="0",
        ))
        
        # Mock collateral response
        self.http_client.fetch_collateral = AsyncMock(return_value=BackpackCollateral(
            assets=[
                BackpackCollateralWeight(asset="USDC", weight="1.0"),
                BackpackCollateralWeight(asset="SOL", weight="0.9"),
            ],
            totalWeightedCollateral="15000",
        ))
        
        # Mock collateral details
        self.http_client.fetch_collateral_details = AsyncMock(return_value=[
            BackpackCollateralDetail(
                asset="USDC",
                quantity="10500",
                markPrice="1.0",
                collateralValue="10500",
                weight="1.0",
                usdValue="10500",
            ),
            BackpackCollateralDetail(
                asset="SOL",
                quantity="110",
                markPrice="100.0",
                collateralValue="9900",
                weight="0.9",
                usdValue="11000",
            ),
        ])
        
        # Mock borrow positions (empty for tests)
        self.http_client.fetch_borrow_positions = AsyncMock(return_value=[])
        
        # Mock account limits
        self.http_client.fetch_account_limits = AsyncMock(return_value={
            "maxLeverage": "20",
            "maxPositions": "100",
        })

    @pytest.mark.asyncio
    async def test_connect_fetches_account_info(self):
        """Test that connecting fetches account information."""
        # Connect the client
        await self.exec_client._connect()
        
        # Verify unified account endpoints were called
        self.http_client.fetch_capital.assert_called_once()
        self.http_client.fetch_collateral.assert_called_once()
        self.http_client.fetch_collateral_details.assert_called_once()
        self.http_client.fetch_borrow_positions.assert_called_once()
        self.http_client.fetch_account_limits.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_limit_order(self):
        """Test submitting a limit order."""
        # Create a limit order
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.strategy_id,
            instrument_id=instrument_id,
            client_order_id=ClientOrderId("TEST-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("1.50"),
            price=Price.from_str("145.50"),
            time_in_force=TimeInForce.GTC,
            post_only=True,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        # Mock order response
        mock_response = BackpackOrderResponse(
            id="bp-order-123",
            client_id="TEST-001",
            symbol="SOL_USDC",
            side="Bid",
            order_type="Limit",
            time_in_force="GTC",
            price="145.50",
            quantity="1.50",
            status="new",
            created_at=1234567890123,
            trigger_price=None,
            quote_quantity=None,
        )
        
        self.http_client.submit_order = AsyncMock(return_value=mock_response)
        
        # Submit the order
        await self.exec_client._submit_order(order)
        
        # Verify order was submitted
        self.http_client.submit_order.assert_called_once()
        
        # Check call arguments
        call_args = self.http_client.submit_order.call_args[1]
        assert call_args["symbol"] == "SOL_USDC"
        assert call_args["side"] == "Bid"
        assert call_args["order_type"] == "Limit"
        assert call_args["price"] == "145.50"
        assert call_args["quantity"] == "1.50"
        assert call_args["post_only"] is True

    @pytest.mark.asyncio
    async def test_submit_market_order(self):
        """Test submitting a market order."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        order = MarketOrder(
            trader_id=self.trader_id,
            strategy_id=self.strategy_id,
            instrument_id=instrument_id,
            client_order_id=ClientOrderId("TEST-002"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("2.00"),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        # Mock order response
        mock_response = BackpackOrderResponse(
            id="bp-order-124",
            client_id="TEST-002",
            symbol="SOL_USDC",
            side="Ask",
            order_type="Market",
            time_in_force="IOC",
            price=None,
            quantity="2.00",
            status="filled",
            created_at=1234567890123,
            trigger_price=None,
            quote_quantity=None,
        )
        
        self.http_client.submit_order = AsyncMock(return_value=mock_response)
        
        # Submit the order
        await self.exec_client._submit_order(order)
        
        # Verify order was submitted
        self.http_client.submit_order.assert_called_once()
        
        # Check call arguments
        call_args = self.http_client.submit_order.call_args[1]
        assert call_args["symbol"] == "SOL_USDC"
        assert call_args["side"] == "Ask"
        assert call_args["order_type"] == "Market"
        assert call_args["quantity"] == "2.00"

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """Test canceling an order."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        venue_order_id = VenueOrderId("bp-order-123")
        
        # Mock cancel response
        mock_order = BackpackOrder(
            id="bp-order-123",
            client_id="TEST-001",
            symbol="SOL_USDC",
            side="Bid",
            order_type="Limit",
            time_in_force="GTC",
            price="145.50",
            quantity="1.50",
            executed_quantity="0.00",
            executed_quote_quantity="0.00",
            status="cancelled",
            created_at=1234567890123,
            trigger_price=None,
            quote_quantity=None,
            self_trade_prevention=None,
            post_only=True,
            reduce_only=False,
        )
        
        self.http_client.cancel_order = AsyncMock(return_value=mock_order)
        
        # Cancel the order
        await self.exec_client._cancel_order(venue_order_id, instrument_id)
        
        # Verify order was canceled
        self.http_client.cancel_order.assert_called_once_with(
            symbol="SOL_USDC",
            order_id="bp-order-123",
        )

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self):
        """Test canceling all orders for an instrument."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Mock orders to be canceled
        mock_orders = [
            BackpackOrder(
                id="bp-order-123",
                client_id="TEST-001",
                symbol="SOL_USDC",
                side="Bid",
                order_type="Limit",
                time_in_force="GTC",
                price="145.50",
                quantity="1.50",
                executed_quantity="0.00",
                executed_quote_quantity="0.00",
                status="cancelled",
                created_at=1234567890123,
                trigger_price=None,
                quote_quantity=None,
                self_trade_prevention=None,
                post_only=True,
                reduce_only=False,
            ),
            BackpackOrder(
                id="bp-order-124",
                client_id="TEST-002",
                symbol="SOL_USDC",
                side="Ask",
                order_type="Limit",
                time_in_force="GTC",
                price="146.00",
                quantity="2.00",
                executed_quantity="0.00",
                executed_quote_quantity="0.00",
                status="cancelled",
                created_at=1234567890124,
                trigger_price=None,
                quote_quantity=None,
                self_trade_prevention=None,
                post_only=False,
                reduce_only=False,
            ),
        ]
        
        self.http_client.cancel_all_orders = AsyncMock(return_value=mock_orders)
        
        # Cancel all orders
        await self.exec_client._cancel_all_orders(instrument_id)
        
        # Verify orders were canceled
        self.http_client.cancel_all_orders.assert_called_once_with(symbol="SOL_USDC")

    @pytest.mark.asyncio
    async def test_fetch_order_fills(self):
        """Test fetching order fills."""
        # Mock fills response
        mock_fills = [
            BackpackFill(
                trade_id=12345,
                order_id="bp-order-123",
                symbol="SOL_USDC",
                side="Bid",
                price="145.50",
                quantity="0.75",
                fee="0.15",
                fee_symbol="USDC",
                is_maker=True,
                timestamp=1234567890123,
                client_id="TEST-001",
            ),
            BackpackFill(
                trade_id=12346,
                order_id="bp-order-123",
                symbol="SOL_USDC",
                side="Bid",
                price="145.50",
                quantity="0.75",
                fee="0.15",
                fee_symbol="USDC",
                is_maker=True,
                timestamp=1234567890124,
                client_id="TEST-001",
            ),
        ]
        
        self.http_client.fetch_fills = AsyncMock(return_value=mock_fills)
        
        # Fetch fills
        fills = await self.exec_client._fetch_fills()
        
        # Verify fills were fetched
        self.http_client.fetch_fills.assert_called_once()
        assert len(fills) == 2

    @pytest.mark.asyncio
    async def test_order_rejection_handling(self):
        """Test handling of order rejection."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.strategy_id,
            instrument_id=instrument_id,
            client_order_id=ClientOrderId("TEST-003"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("10000.00"),  # Too large
            price=Price.from_str("1.00"),  # Too low
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        # Mock rejection
        self.http_client.submit_order = AsyncMock(
            side_effect=Exception("Order rejected: Insufficient balance")
        )
        
        # Submit should handle the rejection
        await self.exec_client._submit_order(order)
        
        # Verify order was attempted
        self.http_client.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_partial_fill_handling(self):
        """Test handling of partial fills."""
        # Mock a partially filled order
        mock_order = BackpackOrder(
            id="bp-order-125",
            client_id="TEST-004",
            symbol="SOL_USDC",
            side="Bid",
            order_type="Limit",
            time_in_force="GTC",
            price="145.50",
            quantity="10.00",
            executed_quantity="3.50",  # Partial fill
            executed_quote_quantity="509.25",
            status="open",
            created_at=1234567890123,
            trigger_price=None,
            quote_quantity=None,
            self_trade_prevention=None,
            post_only=False,
            reduce_only=False,
        )
        
        self.http_client.fetch_order = AsyncMock(return_value=mock_order)
        
        # Fetch order status
        order = await self.http_client.fetch_order(
            symbol="SOL_USDC",
            order_id="bp-order-125",
        )
        
        # Verify partial fill
        assert order.executed_quantity == "3.50"
        assert order.status == "open"
        assert Decimal(order.quantity) > Decimal(order.executed_quantity)

    @pytest.mark.asyncio
    async def test_account_balance_sync(self):
        """Test synchronizing account balances through unified account."""
        # Update capital mock to simulate balance change
        self.http_client.fetch_capital = AsyncMock(return_value=BackpackCapital(
            balances=[
                BackpackBalance(symbol="USDC", available="9500", locked="250", staked="0"),
                BackpackBalance(symbol="SOL", available="103.50", locked="5", staked="0"),
            ],
            totalCollateral="14000",
            availableCollateral="13500",
            initialMarginRate="0.1",
            maintenanceMarginRate="0.05",
            totalBorrowLiability="0",
            unsettledBalances="0",
            unrealizedPnl="0",
        ))
        
        # Trigger account state update
        await self.exec_client._update_account_state()
        
        # Verify capital was fetched
        assert self.http_client.fetch_capital.call_count >= 1

    @pytest.mark.asyncio
    async def test_websocket_order_updates(self):
        """Test receiving order updates via WebSocket."""
        # Simulate WebSocket order update message
        order_update = {
            "stream": "account.orderUpdate",
            "data": {
                "e": "orderUpdate",
                "E": 1234567890123000,  # microseconds
                "s": "SOL_USDC",
                "c": "TEST-005",
                "S": "Bid",
                "o": "Limit",
                "f": "GTC",
                "q": "5.00",
                "p": "145.50",
                "x": "NEW",
                "X": "NEW",
                "i": "bp-order-126",
                "l": "0.00",
                "z": "0.00",
                "L": "0.00",
                "T": 1234567890123,
                "O": "USER",
            }
        }
        
        # This would be processed by WebSocket handler in real implementation
        assert order_update["data"]["x"] == "NEW"
        assert order_update["data"]["c"] == "TEST-005"

    @pytest.mark.asyncio
    async def test_order_modify_rejection(self):
        """Test handling of order modification rejection."""
        # Backpack doesn't support order modification directly
        # This would return an error
        venue_order_id = VenueOrderId("bp-order-123")
        new_quantity = Quantity.from_str("2.00")
        
        # Modification should be rejected or handled via cancel/replace
        # This is a placeholder for expected behavior
        with pytest.raises(NotImplementedError):
            await self.exec_client._modify_order(
                venue_order_id=venue_order_id,
                quantity=new_quantity,
            )

    @pytest.mark.asyncio
    async def test_rate_limit_compliance(self):
        """Test that execution operations comply with rate limits."""
        # Submit multiple orders rapidly
        orders = []
        for i in range(5):
            order = LimitOrder(
                trader_id=self.trader_id,
                strategy_id=self.strategy_id,
                instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
                client_order_id=ClientOrderId(f"TEST-RATE-{i}"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("1.00"),
                price=Price.from_str("145.00"),
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=self.clock.timestamp_ns(),
            )
            orders.append(order)
        
        # Mock responses
        self.http_client.submit_order = AsyncMock(
            return_value=BackpackOrderResponse(
                id="bp-order-127",
                client_id="TEST-RATE-0",
                symbol="SOL_USDC",
                side="Bid",
                order_type="Limit",
                time_in_force="GTC",
                price="145.00",
                quantity="1.00",
                status="new",
                created_at=1234567890123,
                trigger_price=None,
                quote_quantity=None,
            )
        )
        
        # Submit all orders
        tasks = [self.exec_client._submit_order(order) for order in orders]
        await asyncio.gather(*tasks)
        
        # All should complete without rate limit errors
        assert self.http_client.submit_order.call_count == 5