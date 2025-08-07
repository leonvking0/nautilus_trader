#!/usr/bin/env python3
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
Example demonstrating advanced order types on Backpack Exchange.

This example shows how to use:
- Stop Market Orders
- Stop Limit Orders  
- Take Profit and Stop Loss with regular orders
- Iceberg Orders
- Post-Only Orders
"""

import asyncio
import os
from decimal import Decimal

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.factories import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.factories import BackpackLiveExecClientFactory
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.enums import TriggerType
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.model.orders import StopLimitOrder
from nautilus_trader.model.orders import StopMarketOrder
from nautilus_trader.model.orders import TrailingStopMarketOrder
from nautilus_trader.trading.strategy import Strategy


class AdvancedOrdersStrategy(Strategy):
    """
    Example strategy demonstrating advanced order types on Backpack.
    
    This strategy shows various ways to use stop orders, take profit,
    stop loss, and other advanced features.
    """
    
    def __init__(self) -> None:
        super().__init__()
        
        # Track our orders
        self.stop_orders = []
        self.tp_sl_orders = []
        
    def on_start(self) -> None:
        """Called when the strategy starts."""
        self.log.info("Advanced Orders Strategy started")
        
        # Subscribe to the instruments we want to trade
        self.subscribe_quote_ticks(InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE))
        self.subscribe_quote_ticks(InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE))
        
        # Schedule order examples
        self.clock.set_timer(
            name="demo_orders",
            interval=5.0,  # Run after 5 seconds
            callback=self.demonstrate_orders,
            alert_time=None,
            start_time=None,
            stop_time=None,
        )
    
    def demonstrate_orders(self, alert) -> None:
        """Demonstrate various advanced order types."""
        
        # Example 1: Stop Market Order
        # Use case: Buy SOL if price breaks above resistance at 150
        self.submit_stop_market_order()
        
        # Example 2: Stop Limit Order
        # Use case: Sell SOL if price falls below support at 140, but only at 139 or better
        self.submit_stop_limit_order()
        
        # Example 3: Market Order with Take Profit and Stop Loss
        # Use case: Buy BTC with automatic TP at 45000 and SL at 40000
        self.submit_market_order_with_tp_sl()
        
        # Example 4: Limit Order with Advanced TP/SL
        # Use case: Buy ETH with limit order and complex TP/SL settings
        self.submit_limit_order_with_advanced_tp_sl()
        
        # Example 5: Iceberg Order
        # Use case: Buy large amount of BTC without showing full size
        self.submit_iceberg_order()
        
        # Example 6: Post-Only Order
        # Use case: Provide liquidity and get maker fees
        self.submit_post_only_order()
        
        # Example 7: Trailing Stop Order
        # Use case: Protect profits with a trailing stop
        self.submit_trailing_stop_order()
    
    def submit_stop_market_order(self) -> None:
        """Submit a stop market order."""
        self.log.info("Submitting STOP MARKET order: Buy SOL if price >= 150")
        
        order = StopMarketOrder(
            trader_id=self.trader_id,
            strategy_id=self.id,
            instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("STOP-MARKET-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("10"),
            trigger_price=Price.from_str("150.0"),  # Trigger when price reaches 150
            trigger_type=TriggerType.LAST_PRICE,    # Use last traded price
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        self.submit_order(order)
        self.stop_orders.append(order)
    
    def submit_stop_limit_order(self) -> None:
        """Submit a stop limit order."""
        self.log.info("Submitting STOP LIMIT order: Sell SOL if price <= 140, limit at 139")
        
        order = StopLimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.id,
            instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("STOP-LIMIT-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("5"),
            price=Price.from_str("139.0"),          # Limit price after trigger
            trigger_price=Price.from_str("140.0"),  # Trigger when price reaches 140
            trigger_type=TriggerType.MARK_PRICE,    # Use mark price for futures
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        self.submit_order(order)
        self.stop_orders.append(order)
    
    def submit_market_order_with_tp_sl(self) -> None:
        """Submit a market order with take profit and stop loss."""
        self.log.info("Submitting MARKET order with TP=45000, SL=40000")
        
        # Use tags to specify take profit and stop loss
        order = MarketOrder(
            trader_id=self.trader_id,
            strategy_id=self.id,
            instrument_id=InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("MARKET-TP-SL-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.01"),
            time_in_force=TimeInForce.IOC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
            tags="tp:45000,sl:40000",  # Take profit at 45000, stop loss at 40000
        )
        
        self.submit_order(order)
        self.tp_sl_orders.append(order)
    
    def submit_limit_order_with_advanced_tp_sl(self) -> None:
        """Submit a limit order with advanced take profit and stop loss settings."""
        self.log.info("Submitting LIMIT order with advanced TP/SL")
        
        # Advanced TP/SL with limit prices and trigger references
        order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.id,
            instrument_id=InstrumentId(Symbol("ETH_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("LIMIT-ADV-TP-SL-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.1"),
            price=Price.from_str("2500"),
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
            tags="tp:2700,tp_limit:2695,tp_by:MarkPrice,sl:2400,sl_by:IndexPrice",
        )
        
        self.submit_order(order)
        self.tp_sl_orders.append(order)
    
    def submit_iceberg_order(self) -> None:
        """Submit an iceberg order (shows only partial quantity)."""
        self.log.info("Submitting ICEBERG order: Show only 0.01 BTC of 0.1 BTC total")
        
        order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.id,
            instrument_id=InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("ICEBERG-001"),
            order_side=OrderSide.BUY,
            quantity=Quantity.from_str("0.1"),       # Total quantity
            price=Price.from_str("42000"),
            time_in_force=TimeInForce.GTC,
            display_qty=Quantity.from_str("0.01"),   # Show only 0.01 at a time
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        self.submit_order(order)
    
    def submit_post_only_order(self) -> None:
        """Submit a post-only order (maker only)."""
        self.log.info("Submitting POST-ONLY order for maker fees")
        
        order = LimitOrder(
            trader_id=self.trader_id,
            strategy_id=self.id,
            instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("POST-ONLY-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("2"),
            price=Price.from_str("155.0"),  # Above market for sell
            time_in_force=TimeInForce.GTC,
            post_only=True,  # Ensure we're maker, not taker
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        self.submit_order(order)
    
    def submit_trailing_stop_order(self) -> None:
        """Submit a trailing stop order."""
        self.log.info("Submitting TRAILING STOP order with 5% trailing")
        
        order = TrailingStopMarketOrder(
            trader_id=self.trader_id,
            strategy_id=self.id,
            instrument_id=InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE),
            client_order_id=ClientOrderId("TRAILING-STOP-001"),
            order_side=OrderSide.SELL,
            quantity=Quantity.from_str("5"),
            trigger_price=Price.from_str("145.0"),   # Initial trigger
            trigger_type=TriggerType.LAST_PRICE,
            trailing_offset=Decimal("500"),          # 5% in basis points (500 bp)
            trailing_offset_type=2,                  # Basis points
            time_in_force=TimeInForce.GTC,
            init_id=UUID4(),
            ts_init=self.clock.timestamp_ns(),
        )
        
        self.submit_order(order)
        self.stop_orders.append(order)
    
    def on_order_accepted(self, event) -> None:
        """Handle order accepted events."""
        self.log.info(f"Order accepted: {event.client_order_id}")
    
    def on_order_filled(self, event) -> None:
        """Handle order filled events."""
        self.log.info(f"Order filled: {event.client_order_id} @ {event.last_px}")
    
    def on_order_rejected(self, event) -> None:
        """Handle order rejected events."""
        self.log.warning(f"Order rejected: {event.client_order_id} - {event.reason}")
    
    def on_stop(self) -> None:
        """Called when the strategy stops."""
        # Cancel all pending orders
        self.cancel_all_orders(InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE))
        self.cancel_all_orders(InstrumentId(Symbol("BTC_USDC"), BACKPACK_VENUE))
        self.cancel_all_orders(InstrumentId(Symbol("ETH_USDC"), BACKPACK_VENUE))
        
        self.log.info("Advanced Orders Strategy stopped")


async def main():
    """Run the advanced orders example."""
    
    # Check for API credentials
    api_key = os.getenv("BACKPACK_API_KEY")
    api_secret = os.getenv("BACKPACK_API_SECRET")
    
    if not api_key or not api_secret:
        print("Please set BACKPACK_API_KEY and BACKPACK_API_SECRET environment variables")
        return
    
    # Create components
    loop = asyncio.get_event_loop()
    clock = LiveClock()
    msgbus = MessageBus()
    cache = Cache()
    
    # Configure data client
    data_config = BackpackDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
    )
    
    # Configure execution client
    exec_config = BackpackExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
    )
    
    # Create data client factory
    data_factory = BackpackLiveDataClientFactory(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        config=data_config,
    )
    
    # Create execution client factory
    exec_factory = BackpackLiveExecClientFactory(
        loop=loop,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
        config=exec_config,
    )
    
    # Create data and execution clients
    data_client = await data_factory.create_async()
    exec_client = await exec_factory.create_async()
    
    # Connect clients
    await data_client.connect()
    await exec_client.connect()
    
    # Create and start strategy
    strategy = AdvancedOrdersStrategy()
    strategy.register(
        trader_id=TraderId("TRADER-001"),
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    
    # Initialize strategy
    strategy.start()
    
    # Run for demonstration period
    await asyncio.sleep(60)  # Run for 1 minute
    
    # Stop strategy
    strategy.stop()
    
    # Disconnect clients
    await data_client.disconnect()
    await exec_client.disconnect()
    
    print("Advanced orders example completed")


if __name__ == "__main__":
    asyncio.run(main())