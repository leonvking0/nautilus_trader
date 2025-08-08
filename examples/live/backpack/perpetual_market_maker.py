#!/usr/bin/env python3
"""
Perpetual futures market maker strategy for Backpack Exchange.

This example demonstrates a simple market making strategy for perpetual futures
that maintains bid and ask orders around the current mark price, with risk
management and position limits.
"""

import asyncio
import os
from decimal import Decimal

from nautilus_trader.adapters.backpack.common.enums import BackpackInstrumentType
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.config import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.config import BackpackLiveExecClientFactory
from nautilus_trader.adapters.backpack.futures.providers import BackpackFuturesInstrumentProvider
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import Bar, BarType, QuoteTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.trading.strategy import Strategy


class PerpetualMarketMakerConfig(StrategyConfig):
    """Configuration for perpetual market maker strategy."""
    
    instrument_id: str = "SOL-PERP.BACKPACK"
    spread_bps: int = 20  # Spread in basis points (0.20%)
    order_size: float = 0.1  # Size per order (0.1 SOL)
    max_position: float = 1.0  # Maximum position size (1 SOL)
    rebalance_threshold: float = 0.5  # Rebalance when position > 50% of max
    order_refresh_interval: int = 10  # Refresh orders every 10 seconds
    use_reduce_only: bool = True  # Use reduce-only orders when closing


class PerpetualMarketMaker(Strategy):
    """
    Simple market making strategy for perpetual futures.
    
    The strategy:
    1. Places bid and ask orders around the current mark price
    2. Maintains a maximum position size limit
    3. Refreshes orders periodically
    4. Uses reduce-only orders when position limits are reached
    """
    
    def __init__(self, config: PerpetualMarketMakerConfig):
        super().__init__(config)
        
        # Configuration
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.spread_bps = Decimal(config.spread_bps) / Decimal("10000")
        self.order_size = Decimal(str(config.order_size))
        self.max_position = Decimal(str(config.max_position))
        self.rebalance_threshold = Decimal(str(config.rebalance_threshold))
        self.order_refresh_interval = config.order_refresh_interval
        self.use_reduce_only = config.use_reduce_only
        
        # State
        self.instrument: Instrument | None = None
        self.last_mark_price: Decimal | None = None
        self.net_position = Decimal("0")
        self.active_orders: dict[str, LimitOrder] = {}
        
    def on_start(self) -> None:
        """Actions to be performed on strategy start."""
        self.instrument = self.cache.instrument(self.instrument_id)
        
        if self.instrument is None:
            self.log.error(f"Instrument {self.instrument_id} not found in cache")
            self.stop()
            return
            
        # Subscribe to market data
        self.subscribe_quote_ticks(self.instrument_id)
        
        # Schedule periodic order refresh
        self.clock.set_timer(
            name="refresh_orders",
            interval=self.order_refresh_interval * 1_000_000_000,  # Convert to nanoseconds
            callback=self.refresh_orders,
        )
        
        self.log.info(f"Started perpetual market maker for {self.instrument_id}")
        
    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Handle quote tick updates."""
        # Update mark price (using mid price as proxy)
        if tick.bid_price and tick.ask_price:
            self.last_mark_price = (
                Decimal(str(tick.bid_price)) + Decimal(str(tick.ask_price))
            ) / Decimal("2")
            
            # Place initial orders if none exist
            if not self.active_orders:
                self.place_orders()
                
    def place_orders(self) -> None:
        """Place bid and ask orders around the current mark price."""
        if self.last_mark_price is None:
            self.log.warning("Cannot place orders: no mark price available")
            return
            
        # Cancel existing orders
        self.cancel_all_orders()
        
        # Calculate bid and ask prices
        bid_price = self.last_mark_price * (Decimal("1") - self.spread_bps)
        ask_price = self.last_mark_price * (Decimal("1") + self.spread_bps)
        
        # Determine order sizes based on position
        bid_size = self._calculate_order_size(OrderSide.BUY)
        ask_size = self._calculate_order_size(OrderSide.SELL)
        
        # Place bid order if we can buy
        if bid_size > Decimal("0"):
            bid_order = self.order_factory.limit(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str(str(bid_size)),
                price=Price.from_str(str(bid_price)),
                time_in_force=TimeInForce.GTC,
                post_only=True,
                reduce_only=False,
            )
            self.submit_order(bid_order)
            self.active_orders[str(bid_order.client_order_id)] = bid_order
            
        # Place ask order if we can sell
        if ask_size > Decimal("0"):
            # Use reduce-only if we have a long position and are at max
            reduce_only = (
                self.use_reduce_only and
                self.net_position > Decimal("0") and
                self.net_position >= self.max_position * self.rebalance_threshold
            )
            
            ask_order = self.order_factory.limit(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str(str(ask_size)),
                price=Price.from_str(str(ask_price)),
                time_in_force=TimeInForce.GTC,
                post_only=True,
                reduce_only=reduce_only,
            )
            self.submit_order(ask_order)
            self.active_orders[str(ask_order.client_order_id)] = ask_order
            
        self.log.info(
            f"Placed orders: bid={bid_price:.2f} ({bid_size}), "
            f"ask={ask_price:.2f} ({ask_size}), position={self.net_position}"
        )
        
    def _calculate_order_size(self, side: OrderSide) -> Decimal:
        """
        Calculate order size based on position limits.
        
        Args:
            side: The order side (BUY or SELL)
            
        Returns:
            The calculated order size
        """
        if side == OrderSide.BUY:
            # Check if we can increase long position
            if self.net_position >= self.max_position:
                return Decimal("0")  # At max long position
            elif self.net_position > self.max_position * self.rebalance_threshold:
                # Reduce size as we approach max
                return self.order_size * Decimal("0.5")
            else:
                return self.order_size
        else:  # SELL
            # Check if we can increase short position
            if self.net_position <= -self.max_position:
                return Decimal("0")  # At max short position
            elif self.net_position < -self.max_position * self.rebalance_threshold:
                # Reduce size as we approach max
                return self.order_size * Decimal("0.5")
            else:
                return self.order_size
                
    def refresh_orders(self, _=None) -> None:
        """Refresh orders periodically."""
        self.log.debug("Refreshing orders...")
        self.place_orders()
        
    def on_order_filled(self, event) -> None:
        """Handle order fill events."""
        # Update net position
        order = event.order
        fill_qty = Decimal(str(event.last_qty))
        
        if order.side == OrderSide.BUY:
            self.net_position += fill_qty
        else:
            self.net_position -= fill_qty
            
        self.log.info(
            f"Order filled: {order.side} {fill_qty} @ {event.last_px}, "
            f"new position={self.net_position}"
        )
        
        # Remove from active orders
        order_id = str(order.client_order_id)
        if order_id in self.active_orders:
            del self.active_orders[order_id]
            
        # Replace the filled order
        self.place_orders()
        
    def cancel_all_orders(self) -> None:
        """Cancel all active orders."""
        for order in list(self.active_orders.values()):
            self.cancel_order(order)
        self.active_orders.clear()
        
    def on_stop(self) -> None:
        """Actions to be performed on strategy stop."""
        self.cancel_all_orders()
        
        if self.net_position != Decimal("0"):
            self.log.warning(
                f"Strategy stopped with open position: {self.net_position}"
            )
            
    def on_reset(self) -> None:
        """Actions to be performed on strategy reset."""
        self.net_position = Decimal("0")
        self.active_orders.clear()
        self.last_mark_price = None


async def main():
    """Run the perpetual market maker strategy."""
    # Load environment variables
    api_key = os.getenv("BACKPACK_API_KEY")
    api_secret = os.getenv("BACKPACK_API_SECRET")
    
    if not api_key or not api_secret:
        print("Error: BACKPACK_API_KEY and BACKPACK_API_SECRET must be set")
        return
        
    # Configure the trading node
    config = TradingNodeConfig(
        trader_id="TRADER-001",
        logging=LoggingConfig(
            log_level="INFO",
            log_to_console=True,
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=1440,
        ),
        data_clients={
            "BACKPACK": BackpackDataClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                instrument_types=[BackpackInstrumentType.PERPETUAL],
                is_testnet=False,  # Set to True for testnet
            ),
        },
        exec_clients={
            "BACKPACK": BackpackExecClientConfig(
                api_key=api_key,
                api_secret=api_secret,
                instrument_types=[BackpackInstrumentType.PERPETUAL],
                is_testnet=False,  # Set to True for testnet
            ),
        },
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )
    
    # Configure strategy
    strategy_config = PerpetualMarketMakerConfig(
        instrument_id="SOL-PERP.BACKPACK",
        spread_bps=20,  # 0.20% spread
        order_size=0.1,  # 0.1 SOL per order
        max_position=1.0,  # Max 1 SOL position
        rebalance_threshold=0.5,
        order_refresh_interval=10,
        use_reduce_only=True,
    )
    
    # Create and run the trading node
    node = TradingNode(config=config)
    
    # Add the strategy
    node.trader.add_strategy(PerpetualMarketMaker(strategy_config))
    
    try:
        await node.run_async()
    except KeyboardInterrupt:
        await node.stop_async()
        

if __name__ == "__main__":
    print("\n" + "="*60)
    print("PERPETUAL MARKET MAKER STRATEGY")
    print("="*60)
    print("\nWARNING: This strategy will place REAL orders on Backpack Exchange!")
    print("Ensure you understand the risks before proceeding.")
    print("\nConfiguration:")
    print("- Symbol: SOL-PERP")
    print("- Spread: 0.20%")
    print("- Order Size: 0.1 SOL")
    print("- Max Position: 1.0 SOL")
    print("\nPress Ctrl+C to stop the strategy")
    print("="*60 + "\n")
    
    asyncio.run(main())