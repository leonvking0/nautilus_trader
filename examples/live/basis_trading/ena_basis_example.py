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
Basis Trading Example: ENA Perpetuals on Binance and Backpack

This example demonstrates:
1. Connecting to multiple exchanges simultaneously
2. Fetching live market data from perpetual futures
3. Calculating basis spread between instruments
4. Using NautilusTrader components for data management
"""

import asyncio
import os
from decimal import Decimal
from typing import Optional

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.factories import BackpackLiveDataClientFactory
from nautilus_trader.adapters.binance import BINANCE
from nautilus_trader.adapters.binance import BinanceAccountType
from nautilus_trader.adapters.binance import BinanceDataClientConfig
from nautilus_trader.adapters.binance import BinanceLiveDataClientFactory
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.common.component import init_logging
from nautilus_trader.common.enums import LogLevel
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TraderId


class BasisMonitor:
    """
    Monitors basis spread between two perpetual instruments.
    """
    
    def __init__(
        self,
        cache: Cache,
        binance_instrument_id: InstrumentId,
        backpack_instrument_id: InstrumentId,
    ):
        self.cache = cache
        self.binance_instrument_id = binance_instrument_id
        self.backpack_instrument_id = backpack_instrument_id
        
        # Store latest quotes
        self.binance_bid: Optional[Decimal] = None
        self.binance_ask: Optional[Decimal] = None
        self.backpack_bid: Optional[Decimal] = None
        self.backpack_ask: Optional[Decimal] = None
        
        # Basis tracking
        self.basis_history = []
        self.max_basis = None
        self.min_basis = None
        
    def update_binance_quote(self, bid: Decimal, ask: Decimal):
        """Update Binance quote prices."""
        self.binance_bid = bid
        self.binance_ask = ask
        self._calculate_basis()
        
    def update_backpack_quote(self, bid: Decimal, ask: Decimal):
        """Update Backpack quote prices."""
        self.backpack_bid = bid
        self.backpack_ask = ask
        self._calculate_basis()
        
    def _calculate_basis(self):
        """Calculate and log the basis spread."""
        if all([self.binance_bid, self.binance_ask, self.backpack_bid, self.backpack_ask]):
            # Calculate mid prices
            binance_mid = (self.binance_bid + self.binance_ask) / 2
            backpack_mid = (self.backpack_bid + self.backpack_ask) / 2
            
            # Calculate basis (Backpack - Binance)
            # Note: This assumes USDC ≈ USDT for simplicity
            basis = backpack_mid - binance_mid
            basis_bps = (basis / binance_mid) * 10000  # Basis points
            
            # Track history
            self.basis_history.append({
                'binance_mid': float(binance_mid),
                'backpack_mid': float(backpack_mid),
                'basis': float(basis),
                'basis_bps': float(basis_bps),
            })
            
            # Update extremes
            if self.max_basis is None or basis > self.max_basis:
                self.max_basis = basis
            if self.min_basis is None or basis < self.min_basis:
                self.min_basis = basis
            
            # Log current state
            print(f"\n{'='*60}")
            print(f"BASIS SPREAD MONITOR - ENA PERPETUALS")
            print(f"{'='*60}")
            print(f"Binance ENA-USDT Perp:")
            print(f"  Bid: ${self.binance_bid:.4f} | Ask: ${self.binance_ask:.4f} | Mid: ${binance_mid:.4f}")
            print(f"Backpack ENA-USDC Perp:")
            print(f"  Bid: ${self.backpack_bid:.4f} | Ask: ${self.backpack_ask:.4f} | Mid: ${backpack_mid:.4f}")
            print(f"{'='*60}")
            print(f"Current Basis: ${basis:.4f} ({basis_bps:.2f} bps)")
            print(f"Session Range: ${self.min_basis:.4f} to ${self.max_basis:.4f}")
            
            # Check for arbitrage opportunities
            self._check_arbitrage()
    
    def _check_arbitrage(self):
        """Check for potential arbitrage opportunities."""
        if all([self.binance_bid, self.binance_ask, self.backpack_bid, self.backpack_ask]):
            # Buy Binance, Sell Backpack
            if self.backpack_bid > self.binance_ask:
                spread = self.backpack_bid - self.binance_ask
                spread_pct = (spread / self.binance_ask) * 100
                print(f"\n⚠️  ARBITRAGE OPPORTUNITY DETECTED!")
                print(f"  Buy Binance at ${self.binance_ask:.4f}")
                print(f"  Sell Backpack at ${self.backpack_bid:.4f}")
                print(f"  Profit: ${spread:.4f} ({spread_pct:.3f}%)")
            
            # Buy Backpack, Sell Binance
            elif self.binance_bid > self.backpack_ask:
                spread = self.binance_bid - self.backpack_ask
                spread_pct = (spread / self.backpack_ask) * 100
                print(f"\n⚠️  ARBITRAGE OPPORTUNITY DETECTED!")
                print(f"  Buy Backpack at ${self.backpack_ask:.4f}")
                print(f"  Sell Binance at ${self.binance_bid:.4f}")
                print(f"  Profit: ${spread:.4f} ({spread_pct:.3f}%)")


async def main():
    """
    Main function to run the basis trading monitor.
    """
    
    # Initialize logging
    init_logging(level_stdout=LogLevel.INFO)
    
    # Create core components
    clock = LiveClock()
    trader_id = TraderId("BASIS-TRADER-001")
    
    msgbus = MessageBus(
        trader_id=trader_id,
        clock=clock,
    )
    
    cache = Cache()
    
    data_engine = DataEngine(
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    
    # Define instruments
    binance_instrument_id = InstrumentId(
        Symbol("ENAUSDT"),  # Binance uses ENAUSDT for the perpetual
        BINANCE,
    )
    
    backpack_instrument_id = InstrumentId(
        Symbol("ENA_USDC_PERP"),  # Backpack perpetual symbol
        BACKPACK_VENUE,
    )
    
    # Create basis monitor
    monitor = BasisMonitor(
        cache=cache,
        binance_instrument_id=binance_instrument_id,
        backpack_instrument_id=backpack_instrument_id,
    )
    
    # Configure Binance data client
    binance_config = BinanceDataClientConfig(
        api_key=os.getenv("BINANCE_API_KEY"),
        api_secret=os.getenv("BINANCE_API_SECRET"),
        account_type=BinanceAccountType.USDT_FUTURE,
        testnet=False,  # Use mainnet for real data
        instrument_provider=InstrumentProviderConfig(load_all=False),
    )
    
    # Configure Backpack data client
    backpack_config = BackpackDataClientConfig(
        api_key=os.getenv("BACKPACK_API_KEY"),
        api_secret=os.getenv("BACKPACK_API_SECRET"),
        testnet=False,  # Use mainnet for real data
        instrument_provider=InstrumentProviderConfig(load_all=False),
    )
    
    # Create data client factories
    binance_factory = BinanceLiveDataClientFactory()
    backpack_factory = BackpackLiveDataClientFactory()
    
    # Create data clients
    binance_client = await binance_factory.create_async(
        loop=asyncio.get_event_loop(),
        name="BINANCE",
        config=binance_config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    
    backpack_client = await backpack_factory.create_async(
        loop=asyncio.get_event_loop(),
        name="BACKPACK",
        config=backpack_config,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    
    # Register clients with data engine
    data_engine.register_client(binance_client)
    data_engine.register_client(backpack_client)
    
    # Start the data engine
    data_engine.start()
    
    # Connect clients
    await binance_client.connect()
    await backpack_client.connect()
    
    print("\n" + "="*60)
    print("BASIS TRADING MONITOR STARTED")
    print("Monitoring: ENA perpetuals on Binance and Backpack")
    print("="*60)
    
    # Subscribe to quote ticks for both instruments
    data_engine.subscribe_quote_ticks(binance_instrument_id)
    data_engine.subscribe_quote_ticks(backpack_instrument_id)
    
    # Process quotes and update monitor
    async def process_quotes():
        """Process incoming quotes and update the monitor."""
        while True:
            # Get latest quotes from cache
            binance_quotes = cache.quote_ticks(binance_instrument_id)
            backpack_quotes = cache.quote_ticks(backpack_instrument_id)
            
            # Update monitor with latest quotes
            if binance_quotes:
                latest_binance = binance_quotes[-1]
                monitor.update_binance_quote(
                    Decimal(str(latest_binance.bid_price)),
                    Decimal(str(latest_binance.ask_price)),
                )
            
            if backpack_quotes:
                latest_backpack = backpack_quotes[-1]
                monitor.update_backpack_quote(
                    Decimal(str(latest_backpack.bid_price)),
                    Decimal(str(latest_backpack.ask_price)),
                )
            
            await asyncio.sleep(1)  # Update every second
    
    # Run the monitor
    try:
        await process_quotes()
    except KeyboardInterrupt:
        print("\n\nShutting down basis monitor...")
        
        # Display summary
        if monitor.basis_history:
            print("\n" + "="*60)
            print("SESSION SUMMARY")
            print("="*60)
            print(f"Total updates: {len(monitor.basis_history)}")
            print(f"Min basis: ${monitor.min_basis:.4f}")
            print(f"Max basis: ${monitor.max_basis:.4f}")
            
            # Calculate average basis
            avg_basis = sum(h['basis'] for h in monitor.basis_history) / len(monitor.basis_history)
            print(f"Average basis: ${avg_basis:.4f}")
            print("="*60)
    
    finally:
        # Cleanup
        data_engine.stop()
        await binance_client.disconnect()
        await backpack_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())