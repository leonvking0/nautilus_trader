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
Simple Market Making Strategy for Backtesting with OrderBook Data.

This strategy demonstrates:
1. Dynamic spread adjustment based on volatility and orderbook imbalance
2. Inventory risk management with position limits
3. Queue position modeling for realistic fills
4. Performance tracking metrics
"""

from decimal import Decimal

import numpy as np
import pandas as pd

from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Data
from nautilus_trader.indicators.atr import AverageTrueRange
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.trading.strategy import Strategy


class SimpleMMBacktestConfig(StrategyConfig):
    """Configuration for simple market making backtest strategy."""
    
    instrument_id: InstrumentId
    trade_size: Decimal = Decimal("0.1")  # Base order size
    
    # Spread parameters
    base_spread_bps: int = 20  # Base spread in basis points
    min_spread_bps: int = 10   # Minimum spread
    max_spread_bps: int = 100  # Maximum spread
    
    # Inventory management
    max_position: Decimal = Decimal("5.0")  # Maximum position size
    inventory_skew_factor: Decimal = Decimal("0.1")  # How much to skew prices based on inventory
    
    # Risk parameters
    stop_loss_pct: Decimal = Decimal("0.02")  # 2% stop loss
    
    # Order book parameters
    book_type: BookType = BookType.L2_MBP
    orderbook_imbalance_threshold: Decimal = Decimal("0.6")  # Threshold for directional bias
    
    # Volatility
    atr_period: int = 20
    volatility_adjustment: bool = True
    
    # Execution
    update_interval_seconds: int = 5  # How often to update orders
    order_levels: int = 1  # Number of order levels on each side


class SimpleMMBacktest(Strategy):
    """
    Simple market making strategy for backtesting with orderbook data.
    
    Maintains orders on both sides of the book with dynamic spread adjustment
    based on volatility and orderbook imbalance.
    """
    
    def __init__(self, config: SimpleMMBacktestConfig) -> None:
        super().__init__(config)
        
        # Configuration
        self.instrument_id = config.instrument_id
        self.trade_size = config.trade_size
        self.base_spread_bps = config.base_spread_bps
        self.min_spread_bps = config.min_spread_bps
        self.max_spread_bps = config.max_spread_bps
        self.max_position = config.max_position
        self.inventory_skew_factor = config.inventory_skew_factor
        self.stop_loss_pct = config.stop_loss_pct
        self.book_type = config.book_type
        self.orderbook_imbalance_threshold = config.orderbook_imbalance_threshold
        self.atr_period = config.atr_period
        self.volatility_adjustment = config.volatility_adjustment
        self.update_interval_seconds = config.update_interval_seconds
        self.order_levels = config.order_levels
        
        # State
        self.instrument: Instrument | None = None
        self.orderbook: OrderBook | None = None
        self.atr: AverageTrueRange | None = None
        
        # Tracking
        self.bid_orders: list[LimitOrder] = []
        self.ask_orders: list[LimitOrder] = []
        self.last_update_time = None
        self.mid_price: Decimal | None = None
        self.current_spread_bps: int = self.base_spread_bps
        
        # Performance metrics
        self.metrics = {
            "total_trades": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "spread_captured": Decimal("0"),
            "max_position": Decimal("0"),
            "orderbook_updates": 0,
            "order_updates": 0,
        }
    
    def on_start(self) -> None:
        """Initialize the strategy."""
        self.instrument = self.cache.instrument(self.instrument_id)
        if not self.instrument:
            self.log.error(f"Instrument {self.instrument_id} not found")
            self.stop()
            return
        
        # Initialize orderbook
        self.orderbook = OrderBook(
            instrument_id=self.instrument_id,
            book_type=self.book_type,
        )
        
        # Initialize ATR indicator for volatility
        if self.volatility_adjustment:
            # Subscribe to bars for ATR calculation
            bar_type = BarType.from_str(f"{self.instrument_id}-1-MINUTE-LAST-INTERNAL")
            self.atr = AverageTrueRange(self.atr_period)
            self.register_indicator_for_bars(bar_type, self.atr)
            self.subscribe_bars(bar_type)
        
        # Subscribe to market data
        self.subscribe_order_book_deltas(
            instrument_id=self.instrument_id,
            book_type=self.book_type,
        )
        self.subscribe_trade_ticks(self.instrument_id)
        self.subscribe_quote_ticks(self.instrument_id)
        
        self.log.info(f"Started SimpleMMBacktest for {self.instrument_id}")
    
    def on_stop(self) -> None:
        """Clean up on strategy stop."""
        self._cancel_all_orders()
        self._print_metrics()
        self.log.info("Stopped SimpleMMBacktest")
    
    def on_order_book_deltas(self, deltas: OrderBookDeltas) -> None:
        """Handle orderbook updates."""
        # Update local orderbook
        self.orderbook.apply_deltas(deltas)
        self.metrics["orderbook_updates"] += 1
        
        # Update mid price from orderbook
        best_bid = self.orderbook.best_bid_price()
        best_ask = self.orderbook.best_ask_price()
        
        if best_bid and best_ask:
            self.mid_price = (Decimal(str(best_bid)) + Decimal(str(best_ask))) / 2
            
            # Check if we should update orders
            if self._should_update_orders():
                self._update_orders()
    
    def on_order_book_delta(self, delta: OrderBookDelta) -> None:
        """Handle single orderbook delta."""
        # Update local orderbook
        self.orderbook.apply_delta(delta)
        
        # Update mid price if we have both sides
        best_bid = self.orderbook.best_bid_price()
        best_ask = self.orderbook.best_ask_price()
        
        if best_bid and best_ask:
            self.mid_price = (Decimal(str(best_bid)) + Decimal(str(best_ask))) / 2
    
    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Handle quote tick."""
        # Update mid price
        self.mid_price = (Decimal(str(tick.bid_price)) + Decimal(str(tick.ask_price))) / 2
        
        # Check if we should update orders
        if self._should_update_orders():
            self._update_orders()
    
    def on_trade_tick(self, tick: TradeTick) -> None:
        """Handle trade tick."""
        # Could use for additional market impact modeling
        pass
    
    def on_bar(self, bar: Bar) -> None:
        """Handle bar update for volatility calculation."""
        # ATR will be automatically updated if registered
        pass
    
    def on_order_filled(self, event: OrderFilled) -> None:
        """Handle order fill."""
        self.metrics["total_trades"] += 1
        
        if event.order_side == OrderSide.BUY:
            self.metrics["buy_trades"] += 1
        else:
            self.metrics["sell_trades"] += 1
        
        # Calculate spread capture (simplified)
        if self.mid_price:
            spread_capture = abs(Decimal(str(event.last_px)) - self.mid_price)
            self.metrics["spread_captured"] += spread_capture
        
        # Update max position
        position = self.portfolio.net_position(self.instrument_id)
        if position:
            position_size = abs(Decimal(str(position.quantity)))
            self.metrics["max_position"] = max(self.metrics["max_position"], position_size)
        
        # Check for risk limits
        self._check_risk_limits()
        
        self.log.info(
            f"Order filled: {event.order_side} {event.last_qty} @ {event.last_px} | "
            f"Position: {position.quantity if position else 0}"
        )
    
    def _should_update_orders(self) -> bool:
        """Check if orders should be updated."""
        if self.last_update_time is None:
            return True
        
        time_since_update = (self.clock.timestamp_ns() - self.last_update_time) / 1e9
        return time_since_update >= self.update_interval_seconds
    
    def _update_orders(self) -> None:
        """Update market making orders."""
        if not self.mid_price:
            return
        
        # Cancel existing orders
        self._cancel_all_orders()
        
        # Calculate current spread based on market conditions
        self._calculate_dynamic_spread()
        
        # Get orderbook imbalance
        imbalance = self._calculate_orderbook_imbalance()
        
        # Get current position
        position = self.portfolio.net_position(self.instrument_id)
        position_qty = Decimal(str(position.quantity)) if position else Decimal("0")
        
        # Calculate inventory-adjusted spreads
        bid_spread, ask_spread = self._calculate_inventory_adjusted_spreads(
            position_qty,
            imbalance,
        )
        
        # Place orders at multiple levels
        self._place_orders(bid_spread, ask_spread)
        
        self.last_update_time = self.clock.timestamp_ns()
        self.metrics["order_updates"] += 1
    
    def _calculate_dynamic_spread(self) -> None:
        """Calculate dynamic spread based on volatility."""
        base_spread = self.base_spread_bps
        
        if self.volatility_adjustment and self.atr and self.atr.initialized:
            # Adjust spread based on ATR (volatility)
            atr_value = float(self.atr.value)
            if self.mid_price and atr_value > 0:
                volatility_ratio = atr_value / float(self.mid_price)
                # Increase spread when volatility is high
                volatility_multiplier = 1 + (volatility_ratio * 10)  # Scale factor
                base_spread = int(base_spread * volatility_multiplier)
        
        # Apply limits
        self.current_spread_bps = max(
            self.min_spread_bps,
            min(base_spread, self.max_spread_bps)
        )
    
    def _calculate_orderbook_imbalance(self) -> Decimal:
        """Calculate orderbook imbalance (0 = balanced, 1 = all bids, -1 = all asks)."""
        if not self.orderbook:
            return Decimal("0")
        
        # Get top N levels from each side
        bid_volume = Decimal("0")
        ask_volume = Decimal("0")
        
        # Sum volumes from top levels
        for i in range(min(5, self.orderbook.count_bid())):
            level = self.orderbook.get_bid_by_index(i)
            if level:
                bid_volume += Decimal(str(level.size))
        
        for i in range(min(5, self.orderbook.count_ask())):
            level = self.orderbook.get_ask_by_index(i)
            if level:
                ask_volume += Decimal(str(level.size))
        
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return Decimal("0")
        
        # Return imbalance: positive = more bids, negative = more asks
        return (bid_volume - ask_volume) / total_volume
    
    def _calculate_inventory_adjusted_spreads(
        self,
        position_qty: Decimal,
        imbalance: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """Calculate bid and ask spreads adjusted for inventory and orderbook imbalance."""
        base_spread_decimal = Decimal(self.current_spread_bps) / Decimal("10000")
        
        # Inventory adjustment
        # If long, widen bid spread (buy less aggressively) and tighten ask spread (sell more aggressively)
        # If short, opposite
        inventory_adjustment = position_qty * self.inventory_skew_factor / self.max_position
        
        # Imbalance adjustment
        # If imbalance > 0 (more bids), widen bid spread and tighten ask spread
        # If imbalance < 0 (more asks), opposite
        imbalance_adjustment = imbalance * Decimal("0.25") * base_spread_decimal
        
        bid_spread = base_spread_decimal + inventory_adjustment + imbalance_adjustment
        ask_spread = base_spread_decimal - inventory_adjustment - imbalance_adjustment
        
        # Ensure minimum spread
        min_spread_decimal = Decimal(self.min_spread_bps) / Decimal("10000")
        bid_spread = max(bid_spread, min_spread_decimal)
        ask_spread = max(ask_spread, min_spread_decimal)
        
        return bid_spread, ask_spread
    
    def _place_orders(self, bid_spread: Decimal, ask_spread: Decimal) -> None:
        """Place market making orders at calculated spreads."""
        if not self.instrument or not self.mid_price:
            return
        
        # Clear existing order lists
        self.bid_orders = []
        self.ask_orders = []
        
        # Place orders at multiple levels
        for level in range(self.order_levels):
            # Calculate level adjustment (wider spreads for further levels)
            level_adjustment = Decimal(level) * Decimal("0.0005")  # 5bps per level
            
            # Calculate prices
            bid_price = self.mid_price * (Decimal("1") - bid_spread - level_adjustment)
            ask_price = self.mid_price * (Decimal("1") + ask_spread + level_adjustment)
            
            # Round to tick size
            bid_price = self._round_to_tick_size(bid_price)
            ask_price = self._round_to_tick_size(ask_price)
            
            # Calculate size (can vary by level)
            size = self.trade_size * (Decimal("1") - Decimal(level) * Decimal("0.2"))
            size = max(size, self.instrument.min_quantity)
            
            # Check position limits before placing orders
            position = self.portfolio.net_position(self.instrument_id)
            position_qty = Decimal(str(position.quantity)) if position else Decimal("0")
            
            # Only place bid if not at max long position
            if position_qty < self.max_position:
                bid_order = self.order_factory.limit(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.BUY,
                    quantity=self.instrument.make_qty(size),
                    price=self.instrument.make_price(bid_price),
                    time_in_force=TimeInForce.GTC,
                    post_only=True,  # Ensure maker fees
                )
                self.submit_order(bid_order)
                self.bid_orders.append(bid_order)
            
            # Only place ask if not at max short position
            if position_qty > -self.max_position:
                ask_order = self.order_factory.limit(
                    instrument_id=self.instrument_id,
                    order_side=OrderSide.SELL,
                    quantity=self.instrument.make_qty(size),
                    price=self.instrument.make_price(ask_price),
                    time_in_force=TimeInForce.GTC,
                    post_only=True,  # Ensure maker fees
                )
                self.submit_order(ask_order)
                self.ask_orders.append(ask_order)
        
        self.log.debug(
            f"Placed {len(self.bid_orders)} bid orders and {len(self.ask_orders)} ask orders | "
            f"Spread: {self.current_spread_bps}bps"
        )
    
    def _check_risk_limits(self) -> None:
        """Check risk limits and take action if needed."""
        position = self.portfolio.net_position(self.instrument_id)
        if not position:
            return
        
        position_qty = Decimal(str(position.quantity))
        
        # Check max position
        if abs(position_qty) >= self.max_position:
            self.log.warning(f"Position limit reached: {position_qty}")
            self._reduce_position()
        
        # Check stop loss
        if position.unrealized_pnl and self.mid_price:
            pnl_pct = float(position.unrealized_pnl) / (float(position_qty) * float(self.mid_price))
            if pnl_pct < -float(self.stop_loss_pct):
                self.log.warning(f"Stop loss triggered: {pnl_pct:.2%} loss")
                self._close_position()
    
    def _reduce_position(self) -> None:
        """Reduce position by placing aggressive orders."""
        position = self.portfolio.net_position(self.instrument_id)
        if not position or not self.mid_price:
            return
        
        position_qty = Decimal(str(position.quantity))
        
        # Cancel all orders first
        self._cancel_all_orders()
        
        # Place aggressive order to reduce position
        side = OrderSide.SELL if position_qty > 0 else OrderSide.BUY
        
        # Use more aggressive price (cross the spread)
        if side == OrderSide.SELL:
            price = self.mid_price * Decimal("0.999")  # 0.1% below mid
        else:
            price = self.mid_price * Decimal("1.001")  # 0.1% above mid
        
        price = self._round_to_tick_size(price)
        
        # Reduce by half the position
        reduce_size = abs(position_qty) / 2
        
        order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=self.instrument.make_qty(reduce_size),
            price=self.instrument.make_price(price),
            time_in_force=TimeInForce.IOC,  # Immediate or cancel
        )
        
        self.submit_order(order)
        self.log.info(f"Reducing position with {side} order for {reduce_size} @ {price}")
    
    def _close_position(self) -> None:
        """Close entire position."""
        position = self.portfolio.net_position(self.instrument_id)
        if not position or not self.mid_price:
            return
        
        position_qty = Decimal(str(position.quantity))
        
        # Cancel all orders first
        self._cancel_all_orders()
        
        # Place market order to close
        side = OrderSide.SELL if position_qty > 0 else OrderSide.BUY
        
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=side,
            quantity=self.instrument.make_qty(abs(position_qty)),
            time_in_force=TimeInForce.IOC,
        )
        
        self.submit_order(order)
        self.log.warning(f"Closing position with {side} market order for {abs(position_qty)}")
    
    def _cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        for order in self.cache.orders_open(instrument_id=self.instrument_id):
            if order.status == OrderStatus.ACCEPTED:
                self.cancel_order(order)
    
    def _round_to_tick_size(self, price: Decimal) -> Decimal:
        """Round price to instrument tick size."""
        if not self.instrument:
            return price
        
        tick_size = Decimal(str(self.instrument.price_increment))
        return (price / tick_size).quantize(Decimal("1")) * tick_size
    
    def _print_metrics(self) -> None:
        """Print performance metrics."""
        self.log.info("=" * 60)
        self.log.info("Market Making Strategy Performance Metrics")
        self.log.info("=" * 60)
        self.log.info(f"Total trades: {self.metrics['total_trades']}")
        self.log.info(f"Buy trades: {self.metrics['buy_trades']}")
        self.log.info(f"Sell trades: {self.metrics['sell_trades']}")
        self.log.info(f"Spread captured: {self.metrics['spread_captured']:.4f}")
        self.log.info(f"Max position: {self.metrics['max_position']:.4f}")
        self.log.info(f"Orderbook updates: {self.metrics['orderbook_updates']}")
        self.log.info(f"Order updates: {self.metrics['order_updates']}")
        
        if self.metrics['total_trades'] > 0:
            avg_spread = self.metrics['spread_captured'] / self.metrics['total_trades']
            self.log.info(f"Avg spread capture: {avg_spread:.4f}")
        
        self.log.info("=" * 60)