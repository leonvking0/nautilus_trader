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
Test suite for Backpack advanced order types.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.execution import BackpackExecutionClient
from nautilus_trader.adapters.backpack.factories import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.factories import BackpackLiveExecClientFactory
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.advanced_orders import BackpackAdvancedOrderParams
from nautilus_trader.adapters.backpack.schemas.advanced_orders import BackpackOrderUpdate
from nautilus_trader.adapters.backpack.schemas.advanced_orders import backpack_trigger_type_from_nautilus
from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.enums import TriggerType
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.orders import StopLimitOrder
from nautilus_trader.model.orders import StopMarketOrder
from nautilus_trader.model.orders import TrailingStopMarketOrder
from nautilus_trader.test_kit.stubs.identifiers import TestIdStubs


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    client = AsyncMock(spec=BackpackHttpClient)
    client.create_order = AsyncMock()
    client.cancel_order = AsyncMock()
    return client


@pytest.fixture
def mock_ws_client():
    """Create a mock WebSocket client."""
    client = MagicMock(spec=BackpackWebSocketClient)
    client.subscribe = AsyncMock()
    client.unsubscribe = AsyncMock()
    return client


@pytest.fixture
def instrument_provider(mock_http_client):
    """Create an instrument provider."""
    provider = BackpackSpotInstrumentProvider(
        http_client=mock_http_client,
    )
    return provider


@pytest.fixture
def exec_client(event_loop, mock_http_client, instrument_provider):
    """Create a test execution client."""
    msgbus = MessageBus()
    cache = Cache()
    clock = LiveClock()
    
    config = BackpackExecClientConfig(
        api_key="test_key",
        api_secret="test_secret",
    )
    
    client = BackpackExecutionClient(
        loop=event_loop,
        client=mock_http_client,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        instrument_provider=instrument_provider,
        config=config,
    )
    return client


class TestAdvancedOrderSchemas:
    """Test advanced order schemas."""
    
    def test_backpack_advanced_order_params(self):
        """Test BackpackAdvancedOrderParams creation and conversion."""
        params = BackpackAdvancedOrderParams(
            symbol="SOL_USDC",
            side="Bid",
            order_type="StopLimit",
            quantity="10",
            price="150.5",
            trigger_price="145.0",
            trigger_by="LastPrice",
            take_profit_trigger_price="160.0",
            stop_loss_trigger_price="140.0",
        )
        
        request_params = params.to_request_params()
        
        assert request_params["symbol"] == "SOL_USDC"
        assert request_params["side"] == "Bid"
        assert request_params["orderType"] == "StopLimit"
        assert request_params["quantity"] == "10"
        assert request_params["price"] == "150.5"
        assert request_params["triggerPrice"] == "145.0"
        assert request_params["triggerBy"] == "LastPrice"
        assert request_params["takeProfitTriggerPrice"] == "160.0"
        assert request_params["stopLossTriggerPrice"] == "140.0"
    
    def test_backpack_order_update_from_websocket(self):
        """Test BackpackOrderUpdate from WebSocket message."""
        ws_data = {
            "e": "orderAccepted",
            "E": 1694687692980000,
            "s": "SOL_USDC",
            "i": "1111343026172067",
            "c": "test-123",
            "S": "Bid",
            "o": "STOP",
            "P": "145.0",
            "B": "LastPrice",
            "a": "160.0",
            "b": "140.0",
        }
        
        update = BackpackOrderUpdate.from_websocket_message(ws_data)
        
        assert update.event_type == "orderAccepted"
        assert update.symbol == "SOL_USDC"
        assert update.trigger_price == "145.0"
        assert update.trigger_by == "LastPrice"
        assert update.take_profit_trigger_price == "160.0"
        assert update.stop_loss_trigger_price == "140.0"
    
    def test_trigger_type_conversion(self):
        """Test trigger type conversion from Nautilus to Backpack."""
        assert backpack_trigger_type_from_nautilus(TriggerType.DEFAULT) == "LastPrice"
        assert backpack_trigger_type_from_nautilus(TriggerType.LAST_PRICE) == "LastPrice"
        assert backpack_trigger_type_from_nautilus(TriggerType.MARK_PRICE) == "MarkPrice"
        assert backpack_trigger_type_from_nautilus(TriggerType.INDEX_PRICE) == "IndexPrice"


@pytest.mark.asyncio
class TestStopOrders:
    """Test stop order functionality."""
    
    async def test_submit_stop_market_order(self, exec_client, mock_http_client):
        """Test submitting a stop market order."""
        # Arrange
        order = StopMarketOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-stop-market-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("10"),
            trigger_price=Price.from_str("145.0"),
            trigger_type=TriggerType.LAST_PRICE,
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=0,
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123456",
            "status": "NEW",
        }
        
        # Act
        response = await exec_client._submit_stop_market_order(order)
        
        # Assert
        assert response["id"] == "123456"
        mock_http_client.create_order.assert_called_once()
        
        # Check the parameters passed
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["symbol"] == "SOL_USDC"
        assert call_args["side"] == "Bid"
        assert call_args["orderType"] == "Stop"
        assert call_args["quantity"] == "10"
        assert call_args["triggerPrice"] == "145.0"
        assert call_args["triggerBy"] == "LastPrice"
    
    async def test_submit_stop_limit_order(self, exec_client, mock_http_client):
        """Test submitting a stop limit order."""
        # Arrange
        order = StopLimitOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-stop-limit-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("5"),
            price=Price.from_str("140.0"),
            trigger_price=Price.from_str("142.0"),
            trigger_type=TriggerType.MARK_PRICE,
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=0,
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123457",
            "status": "NEW",
        }
        
        # Act
        response = await exec_client._submit_stop_limit_order(order)
        
        # Assert
        assert response["id"] == "123457"
        mock_http_client.create_order.assert_called_once()
        
        # Check the parameters passed
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["symbol"] == "SOL_USDC"
        assert call_args["side"] == "Ask"
        assert call_args["orderType"] == "StopLimit"
        assert call_args["quantity"] == "5"
        assert call_args["price"] == "140.0"
        assert call_args["triggerPrice"] == "142.0"
        assert call_args["triggerBy"] == "MarkPrice"


@pytest.mark.asyncio
class TestTakeProfitStopLoss:
    """Test take profit and stop loss functionality."""
    
    async def test_market_order_with_tp_sl(self, exec_client, mock_http_client):
        """Test market order with take profit and stop loss."""
        # Arrange
        order = MarketOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-market-tp-sl-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.1"),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=0,
            tags="tp:45000,sl:40000",  # Take profit at 45000, stop loss at 40000
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123458",
            "status": "NEW",
        }
        
        # Act
        response = await exec_client._submit_market_order(order)
        
        # Assert
        assert response["id"] == "123458"
        mock_http_client.create_order.assert_called_once()
        
        # Check that TP/SL parameters were added
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["takeProfitTriggerPrice"] == "45000"
        assert call_args["stopLossTriggerPrice"] == "40000"
        assert call_args["takeProfitTriggerBy"] == "LastPrice"
        assert call_args["stopLossTriggerBy"] == "LastPrice"
    
    async def test_limit_order_with_advanced_tp_sl(self, exec_client, mock_http_client):
        """Test limit order with advanced take profit and stop loss settings."""
        # Arrange
        order = LimitOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("ETH_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-limit-adv-tp-sl-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("1"),
            price=Price.from_str("2500"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=0,
            tags="tp:2700,tp_limit:2695,tp_by:MarkPrice,sl:2400,sl_by:IndexPrice",
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123459",
            "status": "NEW",
        }
        
        # Act
        response = await exec_client._submit_limit_order(order)
        
        # Assert
        assert response["id"] == "123459"
        mock_http_client.create_order.assert_called_once()
        
        # Check advanced TP/SL parameters
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["takeProfitTriggerPrice"] == "2700"
        assert call_args["takeProfitLimitPrice"] == "2695"
        assert call_args["takeProfitTriggerBy"] == "MarkPrice"
        assert call_args["stopLossTriggerPrice"] == "2400"
        assert call_args["stopLossTriggerBy"] == "IndexPrice"


@pytest.mark.asyncio
class TestTrailingStopOrders:
    """Test trailing stop order functionality."""
    
    async def test_submit_trailing_stop_market_order(self, exec_client, mock_http_client):
        """Test submitting a trailing stop market order."""
        # Arrange
        order = TrailingStopMarketOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-trailing-stop-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("10"),
            trigger_price=Price.from_str("145.0"),
            trigger_type=TriggerType.LAST_PRICE,
            trailing_offset=Decimal("5"),  # 5% trailing
            trailing_offset_type=2,  # Basis points type
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=0,
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123460",
            "status": "NEW",
        }
        
        # Act (Note: Currently implemented as regular stop order)
        response = await exec_client._submit_trailing_stop_market_order(order)
        
        # Assert
        assert response["id"] == "123460"
        mock_http_client.create_order.assert_called_once()
        
        # Check the parameters (converted to regular stop for now)
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["orderType"] == "Stop"
        assert call_args["triggerPrice"] == "145.0"


@pytest.mark.asyncio
class TestAdvancedOrderFeatures:
    """Test advanced order features like iceberg, post-only, etc."""
    
    async def test_iceberg_order(self, exec_client, mock_http_client):
        """Test iceberg order submission."""
        # Arrange
        order = LimitOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-iceberg-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("10"),
            price=Price.from_str("42000"),
            time_in_force=TimeInForce.GTC,
            display_qty=Quantity.from_str("1"),  # Display only 1 BTC at a time
            init_id=UUID4(),
            ts_init=0,
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123461",
            "status": "NEW",
        }
        
        # Act
        response = await exec_client._submit_limit_order(order)
        
        # Assert
        assert response["id"] == "123461"
        mock_http_client.create_order.assert_called_once()
        
        # Check iceberg parameter
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["icebergQty"] == "1"
    
    async def test_post_only_order(self, exec_client, mock_http_client):
        """Test post-only order submission."""
        # Arrange
        order = LimitOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("ETH_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-post-only-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("2"),
            price=Price.from_str("2600"),
            time_in_force=TimeInForce.GTC,
            post_only=True,
            init_id=UUID4(),
            ts_init=0,
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123462",
            "status": "NEW",
        }
        
        # Act
        response = await exec_client._submit_limit_order(order)
        
        # Assert
        assert response["id"] == "123462"
        mock_http_client.create_order.assert_called_once()
        
        # Check post-only parameter
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["postOnly"] == True
    
    async def test_reduce_only_stop_order(self, exec_client, mock_http_client):
        """Test reduce-only stop order."""
        # Arrange
        order = StopMarketOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=StrategyId("STRATEGY-001"),
            instrument_id=InstrumentId(Symbol("SOL_USDC_PERP"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("test-reduce-only-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("100"),
            trigger_price=Price.from_str("140.0"),
            trigger_type=TriggerType.MARK_PRICE,
            time_in_force=TimeInForce.GTC,
            reduce_only=True,
            init_id=UUID4(),
            ts_init=0,
        )
        
        mock_http_client.create_order.return_value = {
            "id": "123463",
            "status": "NEW",
        }
        
        # Act
        response = await exec_client._submit_stop_market_order(order)
        
        # Assert
        assert response["id"] == "123463"
        mock_http_client.create_order.assert_called_once()
        
        # Check reduce-only parameter
        call_args = mock_http_client.create_order.call_args[1]
        assert call_args["reduceOnly"] == True