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
Basis trading strategy for Backpack Exchange.

This strategy trades the basis (price difference) between spot and perpetual markets,
capturing the spread when it deviates from normal levels.

Strategy Logic:
1. Monitor spot and perpetual prices for the same asset
2. Calculate basis = (perpetual_price - spot_price) / spot_price
3. When basis exceeds threshold, enter delta-neutral position:
   - If basis > positive_threshold: Short perpetual, Long spot
   - If basis < negative_threshold: Long perpetual, Short spot
4. Exit when basis returns to normal range or hits stop loss
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
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.core.data import Data
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


class BasisTradingStrategy(Strategy):
    """
    Basis trading strategy for spot-perpetual arbitrage.
    
    Parameters
    ----------
    spot_symbol : str
        The spot market symbol (e.g., "SOL_USDC").
    perp_symbol : str
        The perpetual market symbol (e.g., "SOL_USDC_PERP").
    basis_entry_threshold : float
        Basis percentage to enter position (e.g., 0.005 for 0.5%).
    basis_exit_threshold : float
        Basis percentage to exit position (e.g., 0.001 for 0.1%).
    position_size_usdc : float
        Position size in USDC terms.
    max_positions : int
        Maximum number of basis positions.
    """
    
    def __init__(
        self,
        spot_symbol: str = "SOL_USDC",
        perp_symbol: str = "SOL_USDC_PERP",
        basis_entry_threshold: float = 0.005,  # 0.5%
        basis_exit_threshold: float = 0.001,   # 0.1%
        position_size_usdc: float = 100.0,
        max_positions: int = 1,
    ) -> None:
        super().__init__()
        
        # Configuration
        self.spot_symbol = spot_symbol
        self.perp_symbol = perp_symbol
        self.basis_entry_threshold = Decimal(str(basis_entry_threshold))
        self.basis_exit_threshold = Decimal(str(basis_exit_threshold))
        self.position_size_usdc = Decimal(str(position_size_usdc))
        self.max_positions = max_positions
        
        # Instrument IDs
        self.spot_id: InstrumentId | None = None
        self.perp_id: InstrumentId | None = None
        
        # Market data
        self.spot_price: Decimal | None = None
        self.perp_price: Decimal | None = None
        self.current_basis: Decimal | None = None
        
        # Position tracking
        self.basis_positions: dict[str, dict] = {}  # Track paired positions
        self.position_counter = 0
    
    def on_start(self) -> None:
        """Actions to be performed on strategy start."""
        self.log.info("Starting BasisTradingStrategy")
        
        # Set instrument IDs
        self.spot_id = InstrumentId.from_str(f"{self.spot_symbol}.{BACKPACK_VENUE}")
        self.perp_id = InstrumentId.from_str(f"{self.perp_symbol}.{BACKPACK_VENUE}")
        
        # Subscribe to market data
        self.subscribe_quote_ticks(self.spot_id)
        self.subscribe_quote_ticks(self.perp_id)
        self.subscribe_trade_ticks(self.spot_id)
        self.subscribe_trade_ticks(self.perp_id)
        
        self.log.info(f"Monitoring basis between {self.spot_symbol} and {self.perp_symbol}")
        self.log.info(f"Entry threshold: {float(self.basis_entry_threshold * 100):.2f}%")
        self.log.info(f"Exit threshold: {float(self.basis_exit_threshold * 100):.2f}%")
    
    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Handle quote tick updates."""
        # Update prices
        if tick.instrument_id == self.spot_id:
            self.spot_price = (tick.ask_price.as_decimal() + tick.bid_price.as_decimal()) / 2
        elif tick.instrument_id == self.perp_id:
            self.perp_price = (tick.ask_price.as_decimal() + tick.bid_price.as_decimal()) / 2
        
        # Calculate and check basis
        self._calculate_basis()
        self._check_basis_opportunities()
    
    def on_trade_tick(self, tick: TradeTick) -> None:
        """Handle trade tick updates."""
        # Alternative price update from trades
        if tick.instrument_id == self.spot_id:
            self.spot_price = tick.price.as_decimal()
        elif tick.instrument_id == self.perp_id:
            self.perp_price = tick.price.as_decimal()
        
        self._calculate_basis()
    
    def _calculate_basis(self) -> None:
        """Calculate current basis spread."""
        if self.spot_price and self.perp_price and self.spot_price > 0:
            self.current_basis = (self.perp_price - self.spot_price) / self.spot_price
            
            # Log basis periodically
            if self.clock.timestamp_ns() % 60_000_000_000 == 0:  # Every minute
                self.log.info(
                    f"Current basis: {float(self.current_basis * 100):.3f}% "
                    f"(Spot: {self.spot_price}, Perp: {self.perp_price})",
                )
    
    def _check_basis_opportunities(self) -> None:
        """Check for basis trading opportunities."""
        if not self.current_basis:
            return
        
        # Check if we can enter a new position
        if len(self.basis_positions) >= self.max_positions:
            return
        
        # Check for positive basis opportunity (perp > spot)
        if self.current_basis > self.basis_entry_threshold:
            self._enter_basis_position(is_positive_basis=True)
        
        # Check for negative basis opportunity (perp < spot)
        elif self.current_basis < -self.basis_entry_threshold:
            self._enter_basis_position(is_positive_basis=False)
        
        # Check existing positions for exit
        self._check_exit_conditions()
    
    def _enter_basis_position(self, is_positive_basis: bool) -> None:
        """
        Enter a basis position.
        
        Parameters
        ----------
        is_positive_basis : bool
            True if perpetual > spot (short perp, long spot).
        """
        position_id = f"basis_{self.position_counter}"
        self.position_counter += 1
        
        # Calculate position sizes
        spot_instrument = self.cache.instrument(self.spot_id)
        perp_instrument = self.cache.instrument(self.perp_id)
        
        if not spot_instrument or not perp_instrument:
            self.log.error("Instruments not found in cache")
            return
        
        # Calculate quantities
        spot_qty = self.position_size_usdc / self.spot_price
        perp_qty = self.position_size_usdc / self.perp_price
        
        # Round to instrument precision
        spot_qty = Quantity(spot_qty, spot_instrument.size_precision)
        perp_qty = Quantity(perp_qty, perp_instrument.size_precision)
        
        # Determine sides based on basis
        if is_positive_basis:
            # Positive basis: Short perp, Long spot
            spot_side = OrderSide.BUY
            perp_side = OrderSide.SELL
            position_type = "positive_basis"
        else:
            # Negative basis: Long perp, Short spot
            spot_side = OrderSide.SELL
            perp_side = OrderSide.BUY
            position_type = "negative_basis"
        
        self.log.info(
            f"Entering {position_type} position {position_id} "
            f"at basis {float(self.current_basis * 100):.3f}%",
        )
        
        # Place orders
        spot_order = self.order_factory.limit(
            instrument_id=self.spot_id,
            order_side=spot_side,
            quantity=spot_qty,
            price=Price(self.spot_price * Decimal("1.001") if spot_side == OrderSide.BUY 
                       else self.spot_price * Decimal("0.999"), 
                       spot_instrument.price_precision),
            time_in_force=TimeInForce.IOC,
        )
        
        perp_order = self.order_factory.limit(
            instrument_id=self.perp_id,
            order_side=perp_side,
            quantity=perp_qty,
            price=Price(self.perp_price * Decimal("1.001") if perp_side == OrderSide.BUY 
                       else self.perp_price * Decimal("0.999"),
                       perp_instrument.price_precision),
            time_in_force=TimeInForce.IOC,
            reduce_only=False,  # Allow opening new positions
        )
        
        # Submit orders
        self.submit_order(spot_order)
        self.submit_order(perp_order)
        
        # Track position
        self.basis_positions[position_id] = {
            "type": position_type,
            "entry_basis": self.current_basis,
            "spot_order_id": spot_order.client_order_id,
            "perp_order_id": perp_order.client_order_id,
            "spot_side": spot_side,
            "perp_side": perp_side,
            "spot_qty": spot_qty,
            "perp_qty": perp_qty,
            "entry_time": self.clock.timestamp_ns(),
        }
    
    def _check_exit_conditions(self) -> None:
        """Check if any positions should be exited."""
        if not self.current_basis:
            return
        
        positions_to_exit = []
        
        for position_id, position_info in self.basis_positions.items():
            entry_basis = position_info["entry_basis"]
            position_type = position_info["type"]
            
            # Check exit conditions
            should_exit = False
            
            if position_type == "positive_basis":
                # Exit when basis reduces to threshold
                if self.current_basis <= self.basis_exit_threshold:
                    should_exit = True
                    self.log.info(
                        f"Exiting {position_id}: Basis reduced to "
                        f"{float(self.current_basis * 100):.3f}%",
                    )
            else:  # negative_basis
                # Exit when basis increases to threshold
                if self.current_basis >= -self.basis_exit_threshold:
                    should_exit = True
                    self.log.info(
                        f"Exiting {position_id}: Basis increased to "
                        f"{float(self.current_basis * 100):.3f}%",
                    )
            
            # Also exit if basis moved significantly against us (stop loss)
            basis_change = abs(self.current_basis - entry_basis)
            if basis_change > self.basis_entry_threshold * 2:
                should_exit = True
                self.log.warning(
                    f"Stop loss triggered for {position_id}: "
                    f"Basis moved {float(basis_change * 100):.3f}%",
                )
            
            if should_exit:
                positions_to_exit.append(position_id)
        
        # Exit positions
        for position_id in positions_to_exit:
            self._exit_basis_position(position_id)
    
    def _exit_basis_position(self, position_id: str) -> None:
        """
        Exit a basis position.
        
        Parameters
        ----------
        position_id : str
            The position identifier to exit.
        """
        position_info = self.basis_positions.get(position_id)
        if not position_info:
            return
        
        spot_instrument = self.cache.instrument(self.spot_id)
        perp_instrument = self.cache.instrument(self.perp_id)
        
        # Reverse the positions
        spot_exit_side = (OrderSide.SELL if position_info["spot_side"] == OrderSide.BUY 
                         else OrderSide.BUY)
        perp_exit_side = (OrderSide.SELL if position_info["perp_side"] == OrderSide.BUY 
                         else OrderSide.BUY)
        
        # Place exit orders
        spot_exit_order = self.order_factory.limit(
            instrument_id=self.spot_id,
            order_side=spot_exit_side,
            quantity=position_info["spot_qty"],
            price=Price(self.spot_price * Decimal("0.999") if spot_exit_side == OrderSide.SELL 
                       else self.spot_price * Decimal("1.001"),
                       spot_instrument.price_precision),
            time_in_force=TimeInForce.IOC,
        )
        
        perp_exit_order = self.order_factory.limit(
            instrument_id=self.perp_id,
            order_side=perp_exit_side,
            quantity=position_info["perp_qty"],
            price=Price(self.perp_price * Decimal("0.999") if perp_exit_side == OrderSide.SELL 
                       else self.perp_price * Decimal("1.001"),
                       perp_instrument.price_precision),
            time_in_force=TimeInForce.IOC,
            reduce_only=True,  # This is closing a position
        )
        
        self.submit_order(spot_exit_order)
        self.submit_order(perp_exit_order)
        
        # Calculate approximate P&L
        basis_change = self.current_basis - position_info["entry_basis"]
        if position_info["type"] == "positive_basis":
            # We profit when basis decreases
            pnl_pct = -basis_change
        else:
            # We profit when basis increases
            pnl_pct = basis_change
        
        self.log.info(
            f"Exited {position_id}: Entry basis {float(position_info['entry_basis'] * 100):.3f}%, "
            f"Exit basis {float(self.current_basis * 100):.3f}%, "
            f"Estimated P&L: {float(pnl_pct * 100):.3f}%",
        )
        
        # Remove from tracking
        del self.basis_positions[position_id]
    
    def on_stop(self) -> None:
        """Actions to be performed on strategy stop."""
        self.log.info("Stopping BasisTradingStrategy")
        
        # Close all open positions
        for position_id in list(self.basis_positions.keys()):
            self.log.info(f"Closing position {position_id} on strategy stop")
            self._exit_basis_position(position_id)
        
        self.log.info("BasisTradingStrategy stopped")


async def main():
    """Run the basis trading strategy."""
    # Configuration
    config = TradingNodeConfig(
        trader_id="TRADER-001",
        logging=LoggingConfig(
            log_level="INFO",
            log_colors=True,
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=False,
            inflight_check_interval_ms=0,
        ),
        data_clients={
            BACKPACK_VENUE.value: BackpackDataClientConfig(
                api_key=os.getenv("BACKPACK_API_KEY"),
                api_secret=os.getenv("BACKPACK_API_SECRET"),
                base_url_http="https://api.backpack.exchange",
                base_url_ws="wss://ws.backpack.exchange",
                us_resident=False,
                testnet=False,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
        exec_clients={
            BACKPACK_VENUE.value: BackpackExecClientConfig(
                api_key=os.getenv("BACKPACK_API_KEY"),
                api_secret=os.getenv("BACKPACK_API_SECRET"),
                base_url_http="https://api.backpack.exchange",
                base_url_ws="wss://ws.backpack.exchange",
                us_resident=False,
                testnet=False,
                instrument_provider=InstrumentProviderConfig(load_all=True),
            ),
        },
    )
    
    # Create trading node
    node = TradingNode(config=config)
    
    # Create and add strategy
    strategy = BasisTradingStrategy(
        spot_symbol="SOL_USDC",
        perp_symbol="SOL_USDC_PERP",
        basis_entry_threshold=0.003,  # 0.3% entry
        basis_exit_threshold=0.0005,  # 0.05% exit
        position_size_usdc=50.0,      # $50 per position
        max_positions=2,               # Max 2 concurrent positions
    )
    
    node.trader.add_strategy(strategy)
    
    # Build and run
    try:
        node.build()
        await node.run_async()
    except KeyboardInterrupt:
        node.log.info("Interrupted by user")
    finally:
        await node.stop_async()
        await node.dispose_async()


if __name__ == "__main__":
    asyncio.run(main())