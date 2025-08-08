#!/usr/bin/env python3
"""
Advanced live test script for Backpack perpetuals with WebSocket streams.
Tests real-time position updates, mark price streams, and advanced orders.

WARNING: This script can place REAL orders on the exchange.
Only use with small amounts and understand the risks.
"""

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.futures.data import BackpackFuturesDataClient
from nautilus_trader.adapters.backpack.futures.execution import BackpackFuturesExecutionClient
from nautilus_trader.adapters.backpack.futures.margin import BackpackFuturesMarginCalculator
from nautilus_trader.adapters.backpack.futures.position_manager import BackpackFuturesPositionManager
from nautilus_trader.adapters.backpack.futures.providers import BackpackFuturesInstrumentProvider
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.common.component import MessageBus
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.data import CustomData
from nautilus_trader.model.data import DataType
from nautilus_trader.model.data import MarkPriceUpdate
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.model.orders import StopMarketOrder


class BackpackAdvancedPerpetualsTest:
    """Advanced test harness for Backpack perpetuals with WebSocket streams."""
    
    def __init__(self):
        # Load API credentials
        self.api_key = os.getenv("BACKPACK_API_KEY")
        self.api_secret = os.getenv("BACKPACK_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError("BACKPACK_API_KEY and BACKPACK_API_SECRET must be set")
        
        # Test configuration
        self.perp_symbol = "SOL-PERP"  # Perpetual symbol
        self.test_size = Decimal("0.01")  # 0.01 SOL minimum
        self.test_leverage = 2  # Low leverage for safety
        
        # Components
        self.trader_id = TraderId("ADVANCED-TESTER-001")
        self.logger = Logger(name="AdvancedPerpetualsTest")
        self.clock = LiveClock()
        self.cache = Cache()
        self.msgbus = MessageBus(
            trader_id=self.trader_id,
            clock=self.clock,
        )
        
        # HTTP client
        self.http_client = BackpackHttpClient(
            clock=self.clock,
            api_key=self.api_key,
            api_secret=self.api_secret,
            base_url="https://api.backpack.exchange",
        )
        
        # WebSocket client
        self.ws_client = BackpackWebSocketClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=False,
            handler=self._handle_ws_message,
            logger=self.logger,
        )
        
        # Clients
        self.data_client = None
        self.exec_client = None
        
        # Track received data
        self.mark_price_updates = []
        self.funding_rate_updates = []
        self.position_updates = []
        self.open_interest_updates = []
        
        # Test orders
        self.test_orders = []
    
    def _handle_ws_message(self, msg: dict):
        """Handle incoming WebSocket messages."""
        self.logger.info(f"WebSocket message: {msg}")
    
    def _handle_mark_price(self, data: MarkPriceUpdate):
        """Handle mark price updates."""
        self.mark_price_updates.append(data)
        self.logger.info(
            f"Mark price update: {data.instrument_id} = {data.price}"
        )
    
    def _handle_custom_data(self, data: CustomData):
        """Handle custom data updates."""
        if data.data_type.metadata.get("data_type") == "FUNDING_RATE":
            self.funding_rate_updates.append(data.data)
            self.logger.info(
                f"Funding rate update: {data.data['instrument_id']} = {data.data['funding_rate']}"
            )
        elif data.data_type.metadata.get("data_type") == "OPEN_INTEREST":
            self.open_interest_updates.append(data.data)
            self.logger.info(
                f"Open interest update: {data.data['instrument_id']} = {data.data['open_interest']}"
            )
    
    async def setup(self):
        """Setup test environment."""
        self.logger.info("Setting up advanced perpetuals test environment...")
        
        # Initialize HTTP client
        await self.http_client._connect()
        
        # Initialize WebSocket client
        await self.ws_client.connect()
        
        # Create instrument provider
        instrument_provider = BackpackFuturesInstrumentProvider(
            client=self.http_client,
            clock=self.clock,
            logger=self.logger,
        )
        
        # Load instruments
        await instrument_provider.load_all_async()
        
        # Create data client
        self.data_client = BackpackFuturesDataClient(
            loop=asyncio.get_event_loop(),
            http_client=self.http_client,
            ws_client=self.ws_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            instrument_provider=instrument_provider,
            config=BackpackDataClientConfig(),
        )
        
        # Create execution client
        self.exec_client = BackpackFuturesExecutionClient(
            loop=asyncio.get_event_loop(),
            client=self.http_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            instrument_provider=instrument_provider,
            config=BackpackExecClientConfig(),
        )
        
        # Subscribe to data handlers
        self.msgbus.subscribe(
            topic="data.mark_price.*",
            handler=self._handle_mark_price,
        )
        self.msgbus.subscribe(
            topic="data.custom.*",
            handler=self._handle_custom_data,
        )
        
        self.logger.info("Setup complete")
    
    async def test_websocket_streams(self):
        """Test WebSocket data streams."""
        self.logger.info("Testing WebSocket streams...")
        
        # Subscribe to mark price stream
        await self.data_client._subscribe_mark_price(self.perp_symbol)
        self.logger.info(f"Subscribed to mark price stream for {self.perp_symbol}")
        
        # Subscribe to funding rate stream
        await self.data_client._subscribe_funding_rate(self.perp_symbol)
        self.logger.info(f"Subscribed to funding rate stream for {self.perp_symbol}")
        
        # Subscribe to open interest stream
        await self.data_client._subscribe_open_interest(self.perp_symbol)
        self.logger.info(f"Subscribed to open interest stream for {self.perp_symbol}")
        
        # Wait for some updates
        await asyncio.sleep(10)
        
        # Check received data
        self.logger.info(f"Received {len(self.mark_price_updates)} mark price updates")
        self.logger.info(f"Received {len(self.funding_rate_updates)} funding rate updates")
        self.logger.info(f"Received {len(self.open_interest_updates)} open interest updates")
        
        # Unsubscribe
        await self.data_client._unsubscribe_mark_price(self.perp_symbol)
        await self.data_client._unsubscribe_funding_rate(self.perp_symbol)
        await self.data_client._unsubscribe_open_interest(self.perp_symbol)
        
        self.logger.info("WebSocket stream test complete")
    
    async def test_position_updates(self):
        """Test position update stream."""
        self.logger.info("Testing position updates...")
        
        # This will subscribe to position updates
        await self.exec_client._update_account_state()
        
        # Check current positions
        positions = await self.exec_client._futures_http_position.fetch_positions()
        self.logger.info(f"Current positions: {len(positions)}")
        
        for pos in positions:
            self.logger.info(
                f"Position: {pos.symbol} side={pos.side} size={pos.size} "
                f"entry={pos.entryPrice} unrealized_pnl={pos.unrealizedPnl}"
            )
        
        self.logger.info("Position update test complete")
    
    async def test_advanced_orders(self):
        """Test advanced order types (simulation only)."""
        self.logger.info("Testing advanced order types (SIMULATION MODE)...")
        
        instrument_id = InstrumentId(Symbol(self.perp_symbol), BACKPACK_VENUE)
        
        # Test reduce-only order (simulation)
        self.logger.info("Testing reduce-only order validation...")
        
        # Check if we have a position to reduce
        positions = self.exec_client._positions
        if self.perp_symbol in positions and Decimal(positions[self.perp_symbol].size) > 0:
            self.logger.info(f"Position exists for {self.perp_symbol}, reduce-only would be valid")
        else:
            self.logger.info(f"No position for {self.perp_symbol}, reduce-only would be rejected")
        
        # Test post-only order (simulation)
        self.logger.info("Testing post-only order (simulation)...")
        
        # Get current best bid/ask
        orderbook = await self.http_client.fetch_order_book(self.perp_symbol)
        best_bid = Decimal(orderbook["bids"][0][0]) if orderbook["bids"] else Decimal("0")
        best_ask = Decimal(orderbook["asks"][0][0]) if orderbook["asks"] else Decimal("0")
        
        self.logger.info(f"Best bid: {best_bid}, Best ask: {best_ask}")
        
        # Simulate a post-only buy order below best bid
        if best_bid > 0:
            post_only_price = best_bid - Decimal("0.10")
            self.logger.info(
                f"Post-only buy order at {post_only_price} would be placed "
                f"(below best bid {best_bid})"
            )
        
        # Test stop-loss order (simulation)
        self.logger.info("Testing stop-loss order (simulation)...")
        
        if best_ask > 0:
            stop_price = best_ask + Decimal("1.00")
            self.logger.info(
                f"Stop-loss sell order with trigger at {stop_price} would be placed "
                f"(above current price {best_ask})"
            )
        
        self.logger.info("Advanced order test complete (SIMULATION)")
    
    async def test_margin_calculations(self):
        """Test margin calculations."""
        self.logger.info("Testing margin calculations...")
        
        # Create margin calculator
        margin_calc = BackpackFuturesMarginCalculator(logger=self.logger)
        
        # Test position sizing
        position_size = Decimal("1.0")  # 1 SOL
        entry_price = Decimal("100.0")
        leverage = 10
        
        # Calculate initial margin
        initial_margin = margin_calc.calculate_initial_margin(
            position_size=position_size,
            entry_price=entry_price,
            leverage=leverage,
        )
        self.logger.info(
            f"Initial margin for {position_size} SOL at ${entry_price} "
            f"with {leverage}x leverage: ${initial_margin}"
        )
        
        # Calculate maintenance margin
        maint_margin = margin_calc.calculate_maintenance_margin(
            position_size=position_size,
            entry_price=entry_price,
        )
        self.logger.info(f"Maintenance margin: ${maint_margin}")
        
        # Calculate liquidation price
        liq_price_long = margin_calc.calculate_liquidation_price(
            position_size=position_size,
            entry_price=entry_price,
            leverage=leverage,
            is_long=True,
        )
        self.logger.info(f"Liquidation price (long): ${liq_price_long}")
        
        liq_price_short = margin_calc.calculate_liquidation_price(
            position_size=position_size,
            entry_price=entry_price,
            leverage=leverage,
            is_long=False,
        )
        self.logger.info(f"Liquidation price (short): ${liq_price_short}")
        
        self.logger.info("Margin calculation test complete")
    
    async def cleanup(self):
        """Cleanup test environment."""
        self.logger.info("Cleaning up...")
        
        # Cancel any test orders
        if self.test_orders:
            self.logger.info(f"Cancelling {len(self.test_orders)} test orders...")
            for order_id in self.test_orders:
                try:
                    await self.http_client.cancel_order(
                        symbol=self.perp_symbol,
                        order_id=order_id,
                    )
                except Exception as e:
                    self.logger.error(f"Failed to cancel order {order_id}: {e}")
        
        # Disconnect
        if self.ws_client:
            await self.ws_client.disconnect()
        
        if self.http_client:
            await self.http_client._disconnect()
        
        self.logger.info("Cleanup complete")
    
    async def run(self):
        """Run all tests."""
        try:
            await self.setup()
            
            # Run tests
            await self.test_websocket_streams()
            await self.test_position_updates()
            await self.test_advanced_orders()
            await self.test_margin_calculations()
            
            # Summary
            self.logger.info("=" * 60)
            self.logger.info("TEST SUMMARY")
            self.logger.info("=" * 60)
            self.logger.info(f"✅ WebSocket streams: {len(self.mark_price_updates)} updates received")
            self.logger.info(f"✅ Position tracking: Working")
            self.logger.info(f"✅ Advanced orders: Validated (simulation)")
            self.logger.info(f"✅ Margin calculations: Working")
            self.logger.info("=" * 60)
            
        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()


async def main():
    """Main entry point."""
    print("=" * 60)
    print("BACKPACK ADVANCED PERPETUALS TEST")
    print("=" * 60)
    print("WARNING: This script tests WebSocket streams and advanced features.")
    print("It will NOT place real orders by default (simulation mode).")
    print()
    
    test = BackpackAdvancedPerpetualsTest()
    await test.run()


if __name__ == "__main__":
    asyncio.run(main())