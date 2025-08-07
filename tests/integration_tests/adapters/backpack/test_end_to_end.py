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

"""End-to-end integration tests for Backpack adapter."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.data import BackpackDataClient
from nautilus_trader.adapters.backpack.execution import BackpackExecutionClient
from nautilus_trader.adapters.backpack.factories import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.factories import BackpackLiveExecClientFactory
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.account import BackpackAccount
from nautilus_trader.adapters.backpack.schemas.account import BackpackBalance
from nautilus_trader.adapters.backpack.schemas.account import BackpackCapital
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateral
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateralWeight
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateralDetail
from nautilus_trader.adapters.backpack.schemas.account import BackpackFill
from nautilus_trader.adapters.backpack.schemas.account import BackpackOrder
from nautilus_trader.adapters.backpack.schemas.account import BackpackOrderResponse
from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.execution.engine import ExecutionEngine
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.risk.engine import RiskEngine
from nautilus_trader.test_kit.stubs.component import TestComponentStubs
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs
from nautilus_trader.trading.strategy import Strategy


class SimpleTestStrategy(Strategy):
    """Simple strategy for end-to-end testing."""
    
    def __init__(self):
        super().__init__()
        self.instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        self.quotes_received = 0
        self.trades_received = 0
        self.order_accepted = False
        self.order_filled = False
        
    def on_start(self):
        """Subscribe to market data on start."""
        self.subscribe_quote_ticks(self.instrument_id)
        self.subscribe_trade_ticks(self.instrument_id)
        
    def on_quote_tick(self, tick):
        """Handle quote tick."""
        self.quotes_received += 1
        
        # Place an order after receiving first quote
        if self.quotes_received == 1:
            self.place_test_order(tick.bid_price)
    
    def on_trade_tick(self, tick):
        """Handle trade tick."""
        self.trades_received += 1
    
    def place_test_order(self, price):
        """Place a test limit order."""
        order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("1.00"),
            price=Price.from_str(str(price.as_double() * 0.95)),  # 5% below market
            time_in_force=TimeInForce.GTC,
            post_only=True,
        )
        self.submit_order(order)


@pytest.mark.asyncio
class TestBackpackEndToEnd:
    """End-to-end integration tests for Backpack adapter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.loop = asyncio.get_event_loop()
        self.clock = LiveClock()
        self.trader_id = TraderId("TESTER-001")
        self.venue = BACKPACK_VENUE
        self.account_id = AccountId(f"{self.venue.value}-001")
        self.strategy_id = StrategyId("TEST-001")

        # Create message bus
        self.msgbus = MessageBus(
            trader_id=self.trader_id,
            clock=self.clock,
        )

        # Create cache
        self.cache = Cache()
        
        # Create HTTP client
        self.http_client = MagicMock(spec=BackpackHttpClient)
        
        # Setup unified account mocks
        self._setup_unified_account_mocks()
        
        # Create instrument provider
        self.provider = BackpackSpotInstrumentProvider(
            client=self.http_client,
            clock=self.clock,
            config=InstrumentProviderConfig(load_all=False),
        )

        # Create engines
        self.data_engine = DataEngine(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )
        
        self.exec_engine = ExecutionEngine(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )
        
        self.risk_engine = RiskEngine(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )
        
        self.portfolio = Portfolio(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )

        # Create data client
        self.data_client = BackpackDataClient(
            loop=self.loop,
            client=self.http_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            config=BackpackDataClientConfig(
                api_key="test_key",
                api_secret="test_secret",
                base_url="https://api.backpack.exchange",
                ws_url="wss://ws.backpack.exchange",
            ),
        )
        
        # Create instrument provider
        from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
        from nautilus_trader.config import InstrumentProviderConfig
        
        self.instrument_provider = BackpackSpotInstrumentProvider(
            client=self.http_client,
            clock=self.clock,
            config=InstrumentProviderConfig(load_all=False),
        )
        
        # Create execution client
        self.exec_client = BackpackExecutionClient(
            loop=self.loop,
            client=self.http_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            instrument_provider=self.instrument_provider,
            config=BackpackExecClientConfig(
                api_key="test_key",
                api_secret="test_secret",
                base_url="https://api.backpack.exchange",
                ws_url="wss://ws.backpack.exchange",
            ),
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
    async def test_full_trading_flow(self):
        """Test complete trading flow from market data to order execution."""
        # Mock market data
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
        
        # Connect clients
        await self.data_client._connect()
        await self.exec_client._connect()
        
        # Create and start strategy
        strategy = SimpleTestStrategy()
        strategy.register(
            trader_id=self.trader_id,
            portfolio=self.portfolio,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )
        
        # Simulate market data
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Mock order submission
        mock_order_response = BackpackOrderResponse(
            id="bp-order-001",
            client_id="TEST-ORDER-001",
            symbol="SOL_USDC",
            side="Bid",
            order_type="Limit",
            time_in_force="GTC",
            price="138.22",
            quantity="1.00",
            status="new",
            created_at=1234567890123,
            trigger_price=None,
            quote_quantity=None,
        )
        
        self.http_client.submit_order = AsyncMock(return_value=mock_order_response)
        
        # Start strategy (subscribes to data)
        strategy.start()
        
        # Simulate receiving a quote
        from nautilus_trader.model.data import QuoteTick
        quote = QuoteTick(
            instrument_id=instrument_id,
            bid_price=Price.from_str("145.50"),
            ask_price=Price.from_str("145.60"),
            bid_size=Quantity.from_str("100.00"),
            ask_size=Quantity.from_str("200.00"),
            ts_event=self.clock.timestamp_ns(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        # Process quote (should trigger order)
        self.data_engine.process(quote)
        strategy.on_quote_tick(quote)
        
        # Verify order was submitted
        await asyncio.sleep(0.1)  # Allow async operations
        self.http_client.submit_order.assert_called_once()
        
        # Simulate order fill
        mock_fill = BackpackFill(
            trade_id=12345,
            order_id="bp-order-001",
            symbol="SOL_USDC",
            side="Bid",
            price="138.22",
            quantity="1.00",
            fee="0.14",
            fee_symbol="USDC",
            is_maker=True,
            timestamp=1234567890123,
            client_id="TEST-ORDER-001",
        )
        
        self.http_client.fetch_fills = AsyncMock(return_value=[mock_fill])
        
        # Process fill
        fills = await self.exec_client._fetch_fills()
        assert len(fills) == 1
        assert fills[0].quantity == "1.00"

    @pytest.mark.asyncio
    async def test_market_maker_scenario(self):
        """Test a market making scenario with bid/ask orders."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Create bid and ask orders
        bid_order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.strategy_id,
            instrument_id=instrument_id,
            client_order_id=ClientOrderId("MM-BID-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("5.00"),
            price=Price.from_str("145.00"),
            time_in_force=TimeInForce.GTC,
            post_only=True,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        ask_order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.strategy_id,
            instrument_id=instrument_id,
            client_order_id=ClientOrderId("MM-ASK-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("5.00"),
            price=Price.from_str("146.00"),
            time_in_force=TimeInForce.GTC,
            post_only=True,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        # Mock order responses
        bid_response = BackpackOrderResponse(
            id="bp-bid-001",
            client_id="MM-BID-001",
            symbol="SOL_USDC",
            side="Bid",
            order_type="Limit",
            time_in_force="GTC",
            price="145.00",
            quantity="5.00",
            status="new",
            created_at=1234567890123,
            trigger_price=None,
            quote_quantity=None,
        )
        
        ask_response = BackpackOrderResponse(
            id="bp-ask-001",
            client_id="MM-ASK-001",
            symbol="SOL_USDC",
            side="Ask",
            order_type="Limit",
            time_in_force="GTC",
            price="146.00",
            quantity="5.00",
            status="new",
            created_at=1234567890124,
            trigger_price=None,
            quote_quantity=None,
        )
        
        # Submit both orders
        self.http_client.submit_order = AsyncMock(
            side_effect=[bid_response, ask_response]
        )
        
        await self.exec_client._submit_order(bid_order)
        await self.exec_client._submit_order(ask_order)
        
        # Verify both orders submitted
        assert self.http_client.submit_order.call_count == 2
        
        # Simulate partial fill on bid
        mock_fill = BackpackFill(
            trade_id=12346,
            order_id="bp-bid-001",
            symbol="SOL_USDC",
            side="Bid",
            price="145.00",
            quantity="2.50",
            fee="0.36",
            fee_symbol="USDC",
            is_maker=True,
            timestamp=1234567890125,
            client_id="MM-BID-001",
        )
        
        self.http_client.fetch_fills = AsyncMock(return_value=[mock_fill])
        
        # Cancel remaining orders
        mock_canceled_orders = [
            BackpackOrder(
                id="bp-bid-001",
                client_id="MM-BID-001",
                symbol="SOL_USDC",
                side="Bid",
                order_type="Limit",
                time_in_force="GTC",
                price="145.00",
                quantity="5.00",
                executed_quantity="2.50",
                executed_quote_quantity="362.50",
                status="cancelled",
                created_at=1234567890123,
                trigger_price=None,
                quote_quantity=None,
                self_trade_prevention=None,
                post_only=True,
                reduce_only=False,
            ),
            BackpackOrder(
                id="bp-ask-001",
                client_id="MM-ASK-001",
                symbol="SOL_USDC",
                side="Ask",
                order_type="Limit",
                time_in_force="GTC",
                price="146.00",
                quantity="5.00",
                executed_quantity="0.00",
                executed_quote_quantity="0.00",
                status="cancelled",
                created_at=1234567890124,
                trigger_price=None,
                quote_quantity=None,
                self_trade_prevention=None,
                post_only=True,
                reduce_only=False,
            ),
        ]
        
        self.http_client.cancel_all_orders = AsyncMock(return_value=mock_canceled_orders)
        
        # Cancel all orders
        await self.exec_client._cancel_all_orders(instrument_id)
        
        # Verify cancellation
        self.http_client.cancel_all_orders.assert_called_once_with(symbol="SOL_USDC")

    @pytest.mark.asyncio
    async def test_stop_loss_scenario(self):
        """Test stop loss order scenario."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Create stop loss order
        stop_order = self.exec_client.order_factory.stop_limit(
            instrument_id=instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("10.00"),
            price=Price.from_str("140.00"),  # Limit price
            trigger_price=Price.from_str("141.00"),  # Stop trigger
            time_in_force=TimeInForce.GTC,
            reduce_only=True,
        )
        
        # Mock response for stop order
        stop_response = BackpackOrderResponse(
            id="bp-stop-001",
            client_id=str(stop_order.client_order_id),
            symbol="SOL_USDC",
            side="Ask",
            order_type="Stop_Limit",
            time_in_force="GTC",
            price="140.00",
            trigger_price="141.00",
            quantity="10.00",
            status="new",
            created_at=1234567890123,
            quote_quantity=None,
        )
        
        self.http_client.submit_order = AsyncMock(return_value=stop_response)
        
        # Submit stop order
        await self.exec_client._submit_order(stop_order)
        
        # Verify stop order parameters
        call_args = self.http_client.submit_order.call_args[1]
        assert call_args["order_type"] == "Stop_Limit"
        assert call_args["trigger_price"] == "141.00"
        assert call_args["reduce_only"] is True

    @pytest.mark.asyncio
    async def test_portfolio_sync(self):
        """Test portfolio synchronization through unified account."""
        # Connect and sync
        await self.exec_client._connect()
        
        # Simulate trades occurring - update capital mock
        self.http_client.fetch_capital = AsyncMock(return_value=BackpackCapital(
            balances=[
                BackpackBalance(symbol="USDC", available="8500", locked="0", staked="0"),  # Bought SOL
                BackpackBalance(symbol="SOL", available="110", locked="0", staked="0"),  # Received SOL
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
        
        # Verify capital was fetched with updated balances
        assert self.http_client.fetch_capital.call_count >= 2  # Initial connect + update

    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test error recovery in trading operations."""
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        
        # Create order
        order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.strategy_id,
            instrument_id=instrument_id,
            client_order_id=ClientOrderId("ERROR-TEST-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("1000000.00"),  # Excessive quantity
            price=Price.from_str("0.01"),  # Very low price
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        # Mock rejection
        self.http_client.submit_order = AsyncMock(
            side_effect=Exception("Insufficient balance")
        )
        
        # Submit should handle error
        await self.exec_client._submit_order(order)
        
        # Verify error was handled
        self.http_client.submit_order.assert_called_once()
        
        # Test connection recovery
        self.http_client.fetch_markets = AsyncMock(
            side_effect=[Exception("Connection lost"), mock_markets]
        )
        
        # First attempt fails, second succeeds
        await self.data_client._connect()
        await self.data_client._connect()
        
        assert self.http_client.fetch_markets.call_count == 2

    @pytest.mark.asyncio
    async def test_multi_instrument_trading(self):
        """Test trading multiple instruments simultaneously."""
        instruments = [
            InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE),
            InstrumentId(Symbol("ETH_USDC"), BACKPACK_VENUE),
        ]
        
        orders = []
        responses = []
        
        for i, instrument_id in enumerate(instruments):
            # Create order for each instrument
            order = LimitOrder(
                trader_id=self.trader_id,
                strategy_id=self.strategy_id,
                instrument_id=instrument_id,
                client_order_id=ClientOrderId(f"MULTI-{i}"),
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("1.00"),
                price=Price.from_str(f"{100 + i * 50}.00"),
                time_in_force=TimeInForce.GTC,
                init_id=UUID4(),
                ts_init=self.clock.timestamp_ns(),
            )
            orders.append(order)
            
            # Create response
            response = BackpackOrderResponse(
                id=f"bp-multi-{i}",
                client_id=f"MULTI-{i}",
                symbol=str(instrument_id.symbol),
                side="Bid",
                order_type="Limit",
                time_in_force="GTC",
                price=f"{100 + i * 50}.00",
                quantity="1.00",
                status="new",
                created_at=1234567890123 + i,
                trigger_price=None,
                quote_quantity=None,
            )
            responses.append(response)
        
        # Mock responses
        self.http_client.submit_order = AsyncMock(side_effect=responses)
        
        # Submit all orders
        tasks = [self.exec_client._submit_order(order) for order in orders]
        await asyncio.gather(*tasks)
        
        # Verify all orders submitted
        assert self.http_client.submit_order.call_count == 3