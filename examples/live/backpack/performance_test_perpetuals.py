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
Performance testing suite for Backpack Exchange perpetuals integration.

This script tests the performance and stability of the perpetuals integration
including WebSocket streams, order execution, and position management.
"""

import asyncio
import gc
import os
import time
import tracemalloc
from collections import deque
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import psutil

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
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class PerformanceTestStrategy(Strategy):
    """
    Performance testing strategy for perpetuals.
    
    Tracks message rates, latencies, memory usage, and stability metrics.
    """
    
    def __init__(
        self,
        test_duration_hours: float = 1.0,
        enable_trading: bool = False,
        order_interval_seconds: int = 300,
        symbols: list[str] | None = None,
    ) -> None:
        super().__init__()
        
        # Configuration
        self.test_duration_hours = test_duration_hours
        self.enable_trading = enable_trading
        self.order_interval_seconds = order_interval_seconds
        self.symbols = symbols or ["SOL_USDC_PERP", "BTC_USDC_PERP", "ETH_USDC_PERP"]
        
        # Performance metrics
        self.start_time: datetime | None = None
        self.message_counts: dict[str, int] = {}
        self.message_rates: deque = deque(maxlen=60)  # Last 60 seconds
        self.latencies: deque = deque(maxlen=1000)  # Last 1000 messages
        self.memory_usage: deque = deque(maxlen=60)  # Last 60 measurements
        self.cpu_usage: deque = deque(maxlen=60)
        
        # Error tracking
        self.errors: list[dict] = []
        self.disconnections = 0
        self.reconnections = 0
        
        # Trading metrics
        self.orders_sent = 0
        self.orders_filled = 0
        self.orders_rejected = 0
        
        # Monitoring
        self.last_order_time = 0
        self.last_metric_time = 0
        self.process = psutil.Process()
    
    def on_start(self) -> None:
        """Initialize performance test."""
        self.log.info("=" * 80)
        self.log.info("STARTING PERPETUALS PERFORMANCE TEST")
        self.log.info(f"Duration: {self.test_duration_hours} hours")
        self.log.info(f"Trading Enabled: {self.enable_trading}")
        self.log.info(f"Symbols: {', '.join(self.symbols)}")
        self.log.info("=" * 80)
        
        self.start_time = datetime.now()
        
        # Start memory tracking
        tracemalloc.start()
        
        # Subscribe to all data streams for each symbol
        for symbol in self.symbols:
            instrument_id = InstrumentId.from_str(f"{symbol}.{BACKPACK_VENUE}")
            
            # Market data streams
            self.subscribe_quote_ticks(instrument_id)
            self.subscribe_trade_ticks(instrument_id)
            self.subscribe_order_book_deltas(instrument_id)
            
            self.log.info(f"Subscribed to all streams for {symbol}")
        
        # Schedule periodic tasks
        self.clock.set_timer(
            name="metrics",
            interval_ns=1_000_000_000,  # Every second
            callback=self._collect_metrics,
        )
        
        self.clock.set_timer(
            name="report",
            interval_ns=60_000_000_000,  # Every minute
            callback=self._generate_report,
        )
        
        if self.enable_trading:
            self.clock.set_timer(
                name="trading",
                interval_ns=self.order_interval_seconds * 1_000_000_000,
                callback=self._place_test_order,
            )
    
    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Track quote tick performance."""
        self._record_message("quote_tick", tick)
    
    def on_trade_tick(self, tick: TradeTick) -> None:
        """Track trade tick performance."""
        self._record_message("trade_tick", tick)
    
    def on_data(self, data: Data) -> None:
        """Track custom data performance."""
        data_type = data.__class__.__name__
        self._record_message(data_type, data)
    
    def on_order_filled(self, event) -> None:
        """Track order fill performance."""
        self.orders_filled += 1
        latency = (self.clock.timestamp_ns() - event.ts_event) / 1_000_000  # ms
        self.latencies.append(latency)
        self.log.info(f"Order filled in {latency:.2f}ms")
    
    def on_order_rejected(self, event) -> None:
        """Track order rejections."""
        self.orders_rejected += 1
        self.log.warning(f"Order rejected: {event.reason}")
    
    def _record_message(self, msg_type: str, data: Any) -> None:
        """Record message for performance tracking."""
        # Update counts
        if msg_type not in self.message_counts:
            self.message_counts[msg_type] = 0
        self.message_counts[msg_type] += 1
        
        # Calculate latency if timestamp available
        if hasattr(data, "ts_event"):
            latency = (self.clock.timestamp_ns() - data.ts_event) / 1_000_000  # ms
            self.latencies.append(latency)
    
    def _collect_metrics(self, event) -> None:
        """Collect performance metrics every second."""
        now = time.time()
        
        # Calculate message rate
        total_messages = sum(self.message_counts.values())
        if self.last_metric_time > 0:
            rate = total_messages / (now - self.start_time.timestamp())
            self.message_rates.append(rate)
        
        # Memory usage
        memory_info = self.process.memory_info()
        self.memory_usage.append(memory_info.rss / 1024 / 1024)  # MB
        
        # CPU usage
        self.cpu_usage.append(self.process.cpu_percent())
        
        self.last_metric_time = now
    
    def _place_test_order(self, event) -> None:
        """Place a test order for performance measurement."""
        if not self.enable_trading:
            return
        
        # Use first symbol for testing
        symbol = self.symbols[0]
        instrument_id = InstrumentId.from_str(f"{symbol}.{BACKPACK_VENUE}")
        instrument = self.cache.instrument(instrument_id)
        
        if not instrument:
            self.log.error(f"Instrument {instrument_id} not found")
            return
        
        # Get current price
        quote = self.cache.quote_tick(instrument_id)
        if not quote:
            self.log.warning("No quote available for test order")
            return
        
        # Place a far-from-market limit order (won't fill)
        side = OrderSide.BUY
        price = quote.bid_price.as_decimal() * Decimal("0.95")  # 5% below bid
        
        order = self.order_factory.limit(
            instrument_id=instrument_id,
            order_side=side,
            quantity=Quantity(0.01, instrument.size_precision),  # Minimum size
            price=Price(price, instrument.price_precision),
            time_in_force=TimeInForce.GTT,
            expire_time_ns=self.clock.timestamp_ns() + 30_000_000_000,  # 30s expiry
        )
        
        self.log.info(f"Placing test order: {order}")
        self.submit_order(order)
        self.orders_sent += 1
    
    def _generate_report(self, event) -> None:
        """Generate performance report every minute."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        # Message statistics
        total_messages = sum(self.message_counts.values())
        avg_rate = total_messages / elapsed if elapsed > 0 else 0
        
        # Latency statistics
        if self.latencies:
            avg_latency = sum(self.latencies) / len(self.latencies)
            max_latency = max(self.latencies)
            min_latency = min(self.latencies)
        else:
            avg_latency = max_latency = min_latency = 0
        
        # Memory statistics
        if self.memory_usage:
            current_memory = self.memory_usage[-1]
            max_memory = max(self.memory_usage)
            avg_memory = sum(self.memory_usage) / len(self.memory_usage)
        else:
            current_memory = max_memory = avg_memory = 0
        
        # CPU statistics
        if self.cpu_usage:
            avg_cpu = sum(self.cpu_usage) / len(self.cpu_usage)
            max_cpu = max(self.cpu_usage)
        else:
            avg_cpu = max_cpu = 0
        
        # Generate report
        self.log.info("=" * 80)
        self.log.info("PERFORMANCE REPORT")
        self.log.info(f"Elapsed Time: {elapsed:.1f}s ({elapsed/3600:.2f}h)")
        self.log.info("-" * 40)
        
        self.log.info("MESSAGE STATISTICS:")
        self.log.info(f"  Total Messages: {total_messages:,}")
        self.log.info(f"  Average Rate: {avg_rate:.1f} msg/s")
        for msg_type, count in sorted(self.message_counts.items()):
            self.log.info(f"  {msg_type}: {count:,}")
        
        self.log.info("-" * 40)
        self.log.info("LATENCY STATISTICS:")
        self.log.info(f"  Average: {avg_latency:.2f}ms")
        self.log.info(f"  Min: {min_latency:.2f}ms")
        self.log.info(f"  Max: {max_latency:.2f}ms")
        
        self.log.info("-" * 40)
        self.log.info("RESOURCE USAGE:")
        self.log.info(f"  Memory (Current): {current_memory:.1f} MB")
        self.log.info(f"  Memory (Average): {avg_memory:.1f} MB")
        self.log.info(f"  Memory (Max): {max_memory:.1f} MB")
        self.log.info(f"  CPU (Average): {avg_cpu:.1f}%")
        self.log.info(f"  CPU (Max): {max_cpu:.1f}%")
        
        if self.enable_trading:
            self.log.info("-" * 40)
            self.log.info("TRADING STATISTICS:")
            self.log.info(f"  Orders Sent: {self.orders_sent}")
            self.log.info(f"  Orders Filled: {self.orders_filled}")
            self.log.info(f"  Orders Rejected: {self.orders_rejected}")
        
        if self.errors:
            self.log.info("-" * 40)
            self.log.info(f"ERRORS: {len(self.errors)}")
            for error in self.errors[-5:]:  # Show last 5 errors
                self.log.error(f"  {error['time']}: {error['message']}")
        
        self.log.info("=" * 80)
        
        # Check if test duration reached
        if elapsed >= self.test_duration_hours * 3600:
            self._complete_test()
    
    def _complete_test(self) -> None:
        """Complete the performance test and generate final report."""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        # Stop memory tracking
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Final statistics
        total_messages = sum(self.message_counts.values())
        avg_rate = total_messages / elapsed if elapsed > 0 else 0
        
        # Generate final report
        self.log.info("=" * 80)
        self.log.info("PERFORMANCE TEST COMPLETED")
        self.log.info("=" * 80)
        self.log.info(f"Test Duration: {elapsed/3600:.2f} hours")
        self.log.info(f"Total Messages: {total_messages:,}")
        self.log.info(f"Average Rate: {avg_rate:.1f} msg/s")
        self.log.info(f"Peak Memory: {peak/1024/1024:.1f} MB")
        self.log.info(f"Error Count: {len(self.errors)}")
        
        if self.enable_trading:
            fill_rate = (self.orders_filled / self.orders_sent * 100) if self.orders_sent > 0 else 0
            self.log.info(f"Order Fill Rate: {fill_rate:.1f}%")
        
        # Success criteria
        success = True
        if avg_rate < 100:
            self.log.warning("⚠️ Low message rate detected")
            success = False
        if peak / 1024 / 1024 > 500:
            self.log.warning("⚠️ High memory usage detected")
            success = False
        if len(self.errors) > 10:
            self.log.warning("⚠️ High error count detected")
            success = False
        
        if success:
            self.log.info("✅ PERFORMANCE TEST PASSED")
        else:
            self.log.error("❌ PERFORMANCE TEST FAILED")
        
        self.log.info("=" * 80)
        
        # Stop the node
        self.stop()
    
    def on_stop(self) -> None:
        """Clean up on strategy stop."""
        self.log.info("Stopping performance test strategy")


async def main():
    """Run the perpetuals performance test."""
    print("\n" + "=" * 80)
    print("BACKPACK PERPETUALS PERFORMANCE TEST")
    print("=" * 80)
    
    # Configuration options
    test_duration = float(input("Test duration (hours) [1.0]: ") or "1.0")
    enable_trading = input("Enable test trading? (y/n) [n]: ").lower() == "y"
    
    if enable_trading:
        print("\n⚠️  WARNING: Test trading will place real orders (far from market)")
        confirm = input("Continue? (y/n): ").lower()
        if confirm != "y":
            enable_trading = False
    
    # Node configuration
    config = TradingNodeConfig(
        trader_id="PERF-TEST-001",
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
        } if enable_trading else {},
    )
    
    # Create trading node
    node = TradingNode(config=config)
    
    # Create and add strategy
    strategy = PerformanceTestStrategy(
        test_duration_hours=test_duration,
        enable_trading=enable_trading,
        order_interval_seconds=300,  # Every 5 minutes
        symbols=["SOL_USDC_PERP", "BTC_USDC_PERP", "ETH_USDC_PERP"],
    )
    
    node.trader.add_strategy(strategy)
    
    # Run test
    try:
        print("\nStarting performance test...")
        print("Press Ctrl+C to stop early\n")
        
        node.build()
        await node.run_async()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\nShutting down...")
        await node.stop_async()
        await node.dispose_async()
        
        # Force garbage collection
        gc.collect()
        
        print("\nPerformance test complete!")


if __name__ == "__main__":
    asyncio.run(main())