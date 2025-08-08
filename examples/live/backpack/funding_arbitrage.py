#!/usr/bin/env python3
"""
Funding rate arbitrage strategy for Backpack Exchange.

This example demonstrates a funding arbitrage strategy that captures funding
rate payments by taking positions when funding rates are favorable.
"""

import asyncio
import os
from decimal import Decimal
from typing import Dict

from nautilus_trader.adapters.backpack.common.enums import BackpackInstrumentType
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.config import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.config import BackpackLiveExecClientFactory
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import StrategyConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.core.data import Data
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy


class FundingArbitrageConfig(StrategyConfig):
    """Configuration for funding arbitrage strategy."""
    
    instrument_ids: list[str] = ["SOL-PERP.BACKPACK", "BTC-PERP.BACKPACK"]
    min_funding_rate_bps: float = 10.0  # Minimum funding rate in basis points (0.10%)
    position_size_pct: float = 0.1  # Position size as % of available balance
    max_positions: int = 3  # Maximum number of concurrent positions
    funding_interval_hours: int = 8  # Funding interval (typically 8 hours)
    close_before_funding_mins: int = 5  # Close position X minutes before funding
    use_market_orders: bool = True  # Use market orders for immediate execution


class FundingArbitrage(Strategy):
    """
    Funding rate arbitrage strategy.
    
    The strategy:
    1. Monitors funding rates across perpetual futures
    2. Takes positions when funding rates exceed threshold
    3. Goes long when funding is negative (receive payment)
    4. Goes short when funding is positive (receive payment)
    5. Closes positions before next funding time to avoid reversal
    """
    
    def __init__(self, config: FundingArbitrageConfig):
        super().__init__(config)
        
        # Configuration
        self.instrument_ids = [
            InstrumentId.from_str(id_str) for id_str in config.instrument_ids
        ]
        self.min_funding_rate = Decimal(config.min_funding_rate_bps) / Decimal("10000")
        self.position_size_pct = Decimal(str(config.position_size_pct))
        self.max_positions = config.max_positions
        self.funding_interval_hours = config.funding_interval_hours
        self.close_before_funding_mins = config.close_before_funding_mins
        self.use_market_orders = config.use_market_orders
        
        # State
        self.instruments: Dict[InstrumentId, Instrument] = {}
        self.funding_rates: Dict[InstrumentId, Decimal] = {}
        self.next_funding_times: Dict[InstrumentId, int] = {}
        self.active_positions: Dict[InstrumentId, Dict] = {}
        
    def on_start(self) -> None:
        """Actions to be performed on strategy start."""
        # Load instruments
        for instrument_id in self.instrument_ids:
            instrument = self.cache.instrument(instrument_id)
            if instrument:
                self.instruments[instrument_id] = instrument
                # Subscribe to custom data for funding rates
                self.subscribe_data(
                    data_type=CustomData,
                    client_id=instrument_id.venue,
                )
            else:
                self.log.error(f"Instrument {instrument_id} not found")
                
        if not self.instruments:
            self.log.error("No instruments available")
            self.stop()
            return
            
        # Schedule periodic position check
        self.clock.set_timer(
            name="check_positions",
            interval=60_000_000_000,  # Check every minute
            callback=self.check_positions,
        )
        
        self.log.info(
            f"Started funding arbitrage for {len(self.instruments)} instruments"
        )
        
    def on_data(self, data: Data) -> None:
        """Handle custom data updates."""
        if isinstance(data, CustomData):
            # Check if this is a funding rate update
            if data.data_type.value == "FundingRateUpdate":
                self.handle_funding_rate_update(data)
                
    def handle_funding_rate_update(self, data: CustomData) -> None:
        """Handle funding rate updates."""
        try:
            # Parse funding rate data
            funding_data = data.value
            symbol = funding_data.get("symbol")
            funding_rate = Decimal(funding_data.get("fundingRate", "0"))
            next_funding_time = funding_data.get("nextFundingTime", 0)
            
            # Find matching instrument
            instrument_id = None
            for inst_id in self.instrument_ids:
                if inst_id.symbol.value == symbol:
                    instrument_id = inst_id
                    break
                    
            if instrument_id:
                self.funding_rates[instrument_id] = funding_rate
                self.next_funding_times[instrument_id] = next_funding_time
                
                self.log.info(
                    f"Funding rate update for {symbol}: {funding_rate:.4%}, "
                    f"next funding in {self.time_until_funding(next_funding_time)} mins"
                )
                
                # Check if we should open a position
                self.evaluate_funding_opportunity(instrument_id)
                
        except Exception as e:
            self.log.error(f"Error handling funding rate update: {e}")
            
    def time_until_funding(self, funding_timestamp: int) -> int:
        """Calculate minutes until next funding."""
        current_time = self.clock.timestamp_ns() // 1_000_000  # Convert to ms
        time_diff_ms = funding_timestamp - current_time
        return max(0, time_diff_ms // 60_000)  # Convert to minutes
        
    def evaluate_funding_opportunity(self, instrument_id: InstrumentId) -> None:
        """Evaluate if funding rate presents an arbitrage opportunity."""
        # Skip if we already have a position
        if instrument_id in self.active_positions:
            return
            
        # Skip if we're at max positions
        if len(self.active_positions) >= self.max_positions:
            return
            
        funding_rate = self.funding_rates.get(instrument_id, Decimal("0"))
        next_funding_time = self.next_funding_times.get(instrument_id, 0)
        
        # Check if funding rate exceeds threshold
        if abs(funding_rate) < self.min_funding_rate:
            return
            
        # Check if we have enough time before funding
        time_to_funding = self.time_until_funding(next_funding_time)
        if time_to_funding < 30:  # Need at least 30 minutes
            self.log.debug(
                f"Not enough time for {instrument_id}: {time_to_funding} mins"
            )
            return
            
        # Determine position side based on funding rate
        # If funding > 0: shorts receive, longs pay -> go short
        # If funding < 0: longs receive, shorts pay -> go long
        if funding_rate > Decimal("0"):
            position_side = OrderSide.SELL
            expected_payment = funding_rate  # We receive as short
        else:
            position_side = OrderSide.BUY
            expected_payment = -funding_rate  # We receive as long
            
        self.log.info(
            f"Funding opportunity detected for {instrument_id}: "
            f"rate={funding_rate:.4%}, side={position_side}, "
            f"expected payment={expected_payment:.4%}"
        )
        
        # Open position
        self.open_funding_position(instrument_id, position_side, expected_payment)
        
    def open_funding_position(
        self,
        instrument_id: InstrumentId,
        side: OrderSide,
        expected_payment: Decimal,
    ) -> None:
        """Open a position to capture funding."""
        try:
            # Calculate position size based on available balance
            # This is simplified - in reality, you'd check actual available balance
            position_size = self.calculate_position_size(instrument_id)
            
            if position_size <= Decimal("0"):
                self.log.warning(f"Insufficient balance for {instrument_id}")
                return
                
            # Create order
            if self.use_market_orders:
                order = self.order_factory.market(
                    instrument_id=instrument_id,
                    order_side=side,
                    quantity=Quantity.from_str(str(position_size)),
                    time_in_force=TimeInForce.IOC,
                )
            else:
                # Use limit order at current price (simplified)
                # In reality, you'd get the current bid/ask
                order = self.order_factory.limit(
                    instrument_id=instrument_id,
                    order_side=side,
                    quantity=Quantity.from_str(str(position_size)),
                    price=Price.from_str("100.00"),  # Placeholder
                    time_in_force=TimeInForce.GTC,
                    post_only=True,
                )
                
            # Submit order
            self.submit_order(order)
            
            # Track position
            self.active_positions[instrument_id] = {
                "side": side,
                "size": position_size,
                "expected_payment": expected_payment,
                "entry_time": self.clock.timestamp_ns(),
                "next_funding": self.next_funding_times.get(instrument_id, 0),
                "order": order,
            }
            
            self.log.info(
                f"Opened funding position: {side} {position_size} {instrument_id}"
            )
            
        except Exception as e:
            self.log.error(f"Error opening position: {e}")
            
    def calculate_position_size(self, instrument_id: InstrumentId) -> Decimal:
        """Calculate position size based on available balance."""
        # Simplified calculation - in reality, you'd check actual balance
        # and consider margin requirements
        instrument = self.instruments.get(instrument_id)
        if not instrument:
            return Decimal("0")
            
        # Use a small fixed size for this example
        if "SOL" in instrument_id.symbol.value:
            return Decimal("0.1")  # 0.1 SOL
        elif "BTC" in instrument_id.symbol.value:
            return Decimal("0.001")  # 0.001 BTC
        else:
            return Decimal("1")  # 1 unit
            
    def check_positions(self, _=None) -> None:
        """Check if any positions should be closed."""
        positions_to_close = []
        
        for instrument_id, position_info in self.active_positions.items():
            next_funding = position_info["next_funding"]
            time_to_funding = self.time_until_funding(next_funding)
            
            # Close position if we're close to funding time
            if time_to_funding <= self.close_before_funding_mins:
                self.log.info(
                    f"Closing position for {instrument_id}: "
                    f"{time_to_funding} mins until funding"
                )
                positions_to_close.append(instrument_id)
                
        # Close positions
        for instrument_id in positions_to_close:
            self.close_funding_position(instrument_id)
            
    def close_funding_position(self, instrument_id: InstrumentId) -> None:
        """Close a funding position."""
        position_info = self.active_positions.get(instrument_id)
        if not position_info:
            return
            
        try:
            # Determine close side (opposite of position)
            position_side = position_info["side"]
            close_side = OrderSide.BUY if position_side == OrderSide.SELL else OrderSide.SELL
            position_size = position_info["size"]
            
            # Create close order
            if self.use_market_orders:
                order = self.order_factory.market(
                    instrument_id=instrument_id,
                    order_side=close_side,
                    quantity=Quantity.from_str(str(position_size)),
                    time_in_force=TimeInForce.IOC,
                    reduce_only=True,
                )
            else:
                order = self.order_factory.limit(
                    instrument_id=instrument_id,
                    order_side=close_side,
                    quantity=Quantity.from_str(str(position_size)),
                    price=Price.from_str("100.00"),  # Placeholder
                    time_in_force=TimeInForce.GTC,
                    reduce_only=True,
                )
                
            # Submit order
            self.submit_order(order)
            
            # Remove from active positions
            del self.active_positions[instrument_id]
            
            self.log.info(
                f"Closed funding position: {close_side} {position_size} {instrument_id}"
            )
            
        except Exception as e:
            self.log.error(f"Error closing position: {e}")
            
    def on_order_filled(self, event) -> None:
        """Handle order fill events."""
        order = event.order
        instrument_id = order.instrument_id
        
        self.log.info(
            f"Order filled: {order.side} {event.last_qty} {instrument_id} @ {event.last_px}"
        )
        
    def on_stop(self) -> None:
        """Actions to be performed on strategy stop."""
        # Close all positions
        for instrument_id in list(self.active_positions.keys()):
            self.close_funding_position(instrument_id)
            
        self.log.info("Funding arbitrage strategy stopped")
        
    def on_reset(self) -> None:
        """Actions to be performed on strategy reset."""
        self.funding_rates.clear()
        self.next_funding_times.clear()
        self.active_positions.clear()


async def main():
    """Run the funding arbitrage strategy."""
    # Load environment variables
    api_key = os.getenv("BACKPACK_API_KEY")
    api_secret = os.getenv("BACKPACK_API_SECRET")
    
    if not api_key or not api_secret:
        print("Error: BACKPACK_API_KEY and BACKPACK_API_SECRET must be set")
        return
        
    # Configure the trading node
    config = TradingNodeConfig(
        trader_id="TRADER-002",
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
    strategy_config = FundingArbitrageConfig(
        instrument_ids=["SOL-PERP.BACKPACK", "BTC-PERP.BACKPACK"],
        min_funding_rate_bps=10.0,  # 0.10% minimum
        position_size_pct=0.1,  # 10% of balance
        max_positions=3,
        funding_interval_hours=8,
        close_before_funding_mins=5,
        use_market_orders=True,
    )
    
    # Create and run the trading node
    node = TradingNode(config=config)
    
    # Add the strategy
    node.trader.add_strategy(FundingArbitrage(strategy_config))
    
    try:
        await node.run_async()
    except KeyboardInterrupt:
        await node.stop_async()
        

if __name__ == "__main__":
    print("\n" + "="*60)
    print("FUNDING ARBITRAGE STRATEGY")
    print("="*60)
    print("\nWARNING: This strategy will place REAL orders on Backpack Exchange!")
    print("Ensure you understand the risks before proceeding.")
    print("\nConfiguration:")
    print("- Instruments: SOL-PERP, BTC-PERP")
    print("- Min Funding Rate: 0.10%")
    print("- Position Size: 10% of balance")
    print("- Max Positions: 3")
    print("\nStrategy Logic:")
    print("- Takes short positions when funding > threshold (shorts receive)")
    print("- Takes long positions when funding < -threshold (longs receive)")
    print("- Closes positions before next funding time")
    print("\nPress Ctrl+C to stop the strategy")
    print("="*60 + "\n")
    
    asyncio.run(main())