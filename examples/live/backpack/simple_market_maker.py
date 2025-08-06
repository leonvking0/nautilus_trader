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
Simple Market Maker Strategy for Backpack Exchange

This example shows a basic market-making strategy that:
1. Maintains orders on both sides of the order book
2. Updates spreads based on market conditions
3. Manages inventory risk
4. Uses WebSocket streaming for real-time data

*** THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
*** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***
"""

import asyncio
import os
from decimal import Decimal

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.factories import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.factories import BackpackLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.core.data import Data
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.trading.strategy import Strategy


class SimpleMarketMakerConfig(StrategyConfig):
    """Configuration for the simple market maker strategy."""
    
    instrument_id: InstrumentId
    trade_size: Decimal  # Order size in base currency
    spread_bps: int = 20  # Spread in basis points (0.20%)
    max_position: Decimal = Decimal("10.0")  # Maximum position size
    update_interval_secs: int = 5  # How often to update orders
    inventory_skew_factor: Decimal = Decimal("0.1")  # Inventory adjustment factor


class SimpleMarketMaker(Strategy):
    """
    A simple market-making strategy for Backpack Exchange.
    
    Places bid and ask orders around the mid-price and adjusts
    spreads based on inventory.
    """
    
    def __init__(self, config: SimpleMarketMakerConfig) -> None:
        super().__init__(config)
        
        # Configuration
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.spread_bps = config.spread_bps
        self.max_position = config.max_position
        self.update_interval_secs = config.update_interval_secs
        self.inventory_skew_factor = config.inventory_skew_factor
        
        # State
        self.instrument: Instrument | None = None
        self.mid_price: Decimal | None = None
        self.bid_order: LimitOrder | None = None
        self.ask_order: LimitOrder | None = None
        self._update_task: asyncio.Task | None = None
        
    def on_start(self) -> None:
        """Called when the strategy starts."""
        self.instrument = self.cache.instrument(self.instrument_id)
        if not self.instrument:
            self.log.error(f"Instrument {self.instrument_id} not found")
            self.stop()
            return
        
        # Subscribe to market data
        self.subscribe_quote_ticks(self.instrument_id)
        self.subscribe_trade_ticks(self.instrument_id)
        self.subscribe_order_book_deltas(self.instrument_id)
        
        # Request initial snapshot
        self.request_quote_ticks(self.instrument_id)
        
        # Start order update loop
        self._update_task = asyncio.create_task(self._update_orders_loop())
        
        self.log.info(f"Started SimpleMarketMaker for {self.instrument_id}")
    
    def on_stop(self) -> None:
        """Called when the strategy stops."""
        # Cancel all orders
        self._cancel_all_orders()
        
        # Cancel update task
        if self._update_task:
            self._update_task.cancel()
        
        self.log.info("Stopped SimpleMarketMaker")
    
    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Handle quote tick updates."""
        # Update mid price
        self.mid_price = (tick.bid_price + tick.ask_price) / 2
        
        # Log spread
        spread_bps = ((tick.ask_price - tick.bid_price) / self.mid_price) * 10000
        self.log.debug(f"Quote: bid={tick.bid_price}, ask={tick.ask_price}, spread={spread_bps:.1f}bps")
    
    def on_trade_tick(self, tick: TradeTick) -> None:
        """Handle trade tick updates."""
        # Update mid price based on last trade
        if self.mid_price is None:
            self.mid_price = Decimal(str(tick.price))
        else:
            # Weighted average with existing mid price
            self.mid_price = (self.mid_price * Decimal("0.7") + 
                             Decimal(str(tick.price)) * Decimal("0.3"))
    
    def on_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        """Handle order book updates."""
        # Could use this for more sophisticated pricing
        pass
    
    def on_order_filled(self, event) -> None:
        """Handle order fill events."""
        self.log.info(f"Order filled: {event.order_side} {event.last_qty} @ {event.last_px}")
        
        # Check position limits
        position = self.portfolio.net_position(self.instrument_id)
        if position and abs(position.quantity) > self.max_position:
            self.log.warning(f"Position limit reached: {position.quantity}")
            self._reduce_position()
    
    async def _update_orders_loop(self) -> None:
        """Periodically update market making orders."""
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval_secs)
                self._update_orders()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Error in update loop: {e}")
    
    def _update_orders(self) -> None:
        """Update or place market making orders."""
        if self.mid_price is None:
            self.log.debug("No mid price available yet")
            return
        
        # Cancel existing orders
        self._cancel_all_orders()
        
        # Calculate position-adjusted spreads
        position = self.portfolio.net_position(self.instrument_id)
        position_qty = Decimal(str(position.quantity)) if position else Decimal("0")
        
        # Adjust spreads based on inventory
        # If long, make ask more aggressive (lower) and bid less aggressive
        # If short, make bid more aggressive (higher) and ask less aggressive
        inventory_adjustment = position_qty * self.inventory_skew_factor
        
        bid_spread = Decimal(self.spread_bps) / Decimal("10000") + inventory_adjustment
        ask_spread = Decimal(self.spread_bps) / Decimal("10000") - inventory_adjustment
        
        # Ensure minimum spread
        min_spread = Decimal("0.0010")  # 0.10% minimum
        bid_spread = max(bid_spread, min_spread)
        ask_spread = max(ask_spread, min_spread)
        
        # Calculate prices
        bid_price = self.mid_price * (Decimal("1") - bid_spread)
        ask_price = self.mid_price * (Decimal("1") + ask_spread)
        
        # Round to tick size
        if self.instrument:
            bid_price = self._round_to_tick_size(bid_price)
            ask_price = self._round_to_tick_size(ask_price)
        
        # Place orders
        self._place_order(OrderSide.BUY, bid_price)
        self._place_order(OrderSide.SELL, ask_price)
        
        self.log.info(
            f"Updated orders: bid={bid_price:.4f}, ask={ask_price:.4f}, "
            f"position={position_qty:.2f}"
        )
    
    def _place_order(self, side: OrderSide, price: Decimal) -> None:
        """Place a limit order."""
        if not self.instrument:
            return
        
        order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=self.instrument.make_qty(self.trade_size),
            price=self.instrument.make_price(price),
            time_in_force=TimeInForce.GTD,  # Good till date
            expire_time=self.clock.utc_now() + pd.Timedelta(minutes=5),  # 5 min expiry
            post_only=True,  # Ensure maker fees
        )
        
        self.submit_order(order)
        
        # Track orders
        if side == OrderSide.BUY:
            self.bid_order = order
        else:
            self.ask_order = order
    
    def _cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        for order in self.cache.orders_open(instrument_id=self.instrument_id):
            if order.is_open:
                self.cancel_order(order)
    
    def _round_to_tick_size(self, price: Decimal) -> Decimal:
        """Round price to the instrument's tick size."""
        if not self.instrument:
            return price
        
        tick_size = Decimal(str(self.instrument.price_increment))
        return (price / tick_size).quantize(Decimal("1")) * tick_size
    
    def _reduce_position(self) -> None:
        """Reduce position when limits are exceeded."""
        position = self.portfolio.net_position(self.instrument_id)
        if not position:
            return
        
        # Place aggressive order to reduce position
        side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
        
        # Use more aggressive price
        if self.mid_price:
            if side == OrderSide.SELL:
                price = self.mid_price * Decimal("0.999")  # 0.1% below mid
            else:
                price = self.mid_price * Decimal("1.001")  # 0.1% above mid
            
            self._place_order(side, price)
            self.log.info(f"Reducing position with {side} order at {price}")


def main():
    """Run the simple market maker on Backpack."""
    
    # Get configuration from environment
    testnet = os.getenv("BACKPACK_TESTNET", "true").lower() == "true"
    symbol = os.getenv("BACKPACK_SYMBOL", "SOL_USDC")
    
    # Trading node configuration
    config_node = TradingNodeConfig(
        trader_id=TraderId("MM-002"),
        logging=LoggingConfig(
            log_level="INFO",
            use_pyo3=True,
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=5,
            snapshot_orders=True,
            snapshot_positions=True,
            snapshot_positions_interval_secs=10.0,
        ),
        data_clients={
            BACKPACK_VENUE.value: BackpackDataClientConfig(
                api_key=os.getenv("BACKPACK_API_KEY"),
                api_secret=os.getenv("BACKPACK_API_SECRET"),
                testnet=testnet,
                instrument_provider=InstrumentProviderConfig(
                    load_all=True,
                ),
            ),
        },
        exec_clients={
            BACKPACK_VENUE.value: BackpackExecClientConfig(
                api_key=os.getenv("BACKPACK_API_KEY"),
                api_secret=os.getenv("BACKPACK_API_SECRET"),
                testnet=testnet,
                instrument_provider=InstrumentProviderConfig(
                    load_all=True,
                ),
            ),
        },
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )
    
    # Create trading node
    node = TradingNode(config=config_node)
    
    # Strategy configuration
    strategy_config = SimpleMarketMakerConfig(
        instrument_id=InstrumentId.from_str(f"{symbol}.{BACKPACK_VENUE}"),
        trade_size=Decimal("0.1"),  # 0.1 SOL per order
        spread_bps=20,  # 0.20% spread
        max_position=Decimal("5.0"),  # Max 5 SOL position
        update_interval_secs=5,  # Update every 5 seconds
        inventory_skew_factor=Decimal("0.05"),  # 5% inventory adjustment
    )
    
    # Create and add strategy
    strategy = SimpleMarketMaker(config=strategy_config)
    node.trader.add_strategy(strategy)
    
    # Register Backpack factories
    node.add_data_client_factory(BACKPACK_VENUE.value, BackpackLiveDataClientFactory)
    node.add_exec_client_factory(BACKPACK_VENUE.value, BackpackLiveExecClientFactory)
    
    # Build node
    node.build()
    
    return node


if __name__ == "__main__":
    # Import pandas for time operations
    import pandas as pd
    
    print("Starting Backpack Simple Market Maker...")
    print("Configuration:")
    print(f"  Testnet: {os.getenv('BACKPACK_TESTNET', 'true')}")
    print(f"  Symbol: {os.getenv('BACKPACK_SYMBOL', 'SOL_USDC')}")
    print("\n*** THIS IS A TEST STRATEGY - DO NOT USE WITH REAL MONEY ***\n")
    
    node = main()
    
    try:
        node.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        node.dispose()
        print("Shutdown complete")