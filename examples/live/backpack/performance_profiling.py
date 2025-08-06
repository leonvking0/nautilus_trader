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
Performance Profiling for Backpack Adapter

This script profiles the performance of critical paths in the Backpack adapter:
1. WebSocket message parsing
2. Order book updates
3. Trade execution paths
4. Data serialization/deserialization

Run with: python -m cProfile -o backpack_profile.stats performance_profiling.py
Analyze with: python -m pstats backpack_profile.stats
"""

import asyncio
import json
import time
from decimal import Decimal
from typing import Any

import msgspec

from nautilus_trader.adapters.backpack.parsing import parse_order_book
from nautilus_trader.adapters.backpack.parsing import parse_trade
from nautilus_trader.adapters.backpack.schemas.market import BackpackOrderBook
from nautilus_trader.adapters.backpack.schemas.market import BackpackTrade
from nautilus_trader.adapters.backpack.schemas.websocket import BackpackWsDepthUpdate
from nautilus_trader.adapters.backpack.schemas.websocket import BackpackWsTradeUpdate
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue


class PerformanceProfiler:
    """Profile performance of Backpack adapter components."""
    
    def __init__(self):
        self.results = {}
        self.instrument_id = InstrumentId(Symbol("SOL_USDC"), Venue("BACKPACK"))
        self.decoder = msgspec.json.Decoder()
        self.encoder = msgspec.json.Encoder()
    
    def profile_parsing(self, iterations: int = 10000):
        """Profile parsing performance."""
        print(f"\nProfiling parsing performance ({iterations} iterations)...")
        
        # Sample data
        orderbook_data = {
            "last_update_id": 123456789,
            "bids": [["150.50", "10.5"], ["150.45", "25.0"], ["150.40", "50.0"]],
            "asks": [["150.55", "15.0"], ["150.60", "30.0"], ["150.65", "45.0"]],
            "timestamp": 1234567890123,
        }
        
        trade_data = {
            "id": 987654321,
            "price": "150.52",
            "quantity": "5.25",
            "quote_quantity": "789.48",
            "timestamp": 1234567890123,
            "is_buyer_maker": True,
        }
        
        # Profile order book parsing
        start = time.perf_counter()
        for _ in range(iterations):
            orderbook = BackpackOrderBook(**orderbook_data)
            parsed = parse_order_book(
                instrument_id=self.instrument_id,
                data=orderbook,
                ts_event=millis_to_nanos(orderbook.timestamp or 0),
                ts_init=millis_to_nanos(int(time.time() * 1000)),
            )
        orderbook_time = time.perf_counter() - start
        
        # Profile trade parsing
        start = time.perf_counter()
        for _ in range(iterations):
            trade = BackpackTrade(**trade_data)
            parsed = parse_trade(
                instrument_id=self.instrument_id,
                data=trade,
                ts_event=millis_to_nanos(trade.timestamp),
                ts_init=millis_to_nanos(int(time.time() * 1000)),
            )
        trade_time = time.perf_counter() - start
        
        self.results["orderbook_parsing"] = {
            "total_time": orderbook_time,
            "iterations": iterations,
            "avg_time_ms": (orderbook_time / iterations) * 1000,
            "throughput": iterations / orderbook_time,
        }
        
        self.results["trade_parsing"] = {
            "total_time": trade_time,
            "iterations": iterations,
            "avg_time_ms": (trade_time / iterations) * 1000,
            "throughput": iterations / trade_time,
        }
        
        print(f"  OrderBook parsing: {self.results['orderbook_parsing']['avg_time_ms']:.4f}ms avg")
        print(f"  Trade parsing: {self.results['trade_parsing']['avg_time_ms']:.4f}ms avg")
    
    def profile_websocket_processing(self, iterations: int = 10000):
        """Profile WebSocket message processing."""
        print(f"\nProfiling WebSocket processing ({iterations} iterations)...")
        
        # Sample WebSocket messages
        depth_message = {
            "stream": "depth.SOL_USDC",
            "data": {
                "symbol": "SOL_USDC",
                "U": 123456788,
                "u": 123456789,
                "b": [["150.50", "10.5"], ["150.45", "25.0"]],
                "a": [["150.55", "15.0"], ["150.60", "30.0"]],
                "timestamp": 1234567890123,
            },
        }
        
        trade_message = {
            "stream": "trade.SOL_USDC",
            "data": {
                "symbol": "SOL_USDC",
                "id": 987654321,
                "price": "150.52",
                "quantity": "5.25",
                "timestamp": 1234567890123,
                "is_buyer_maker": True,
            },
        }
        
        # Profile depth update processing
        start = time.perf_counter()
        for _ in range(iterations):
            # Simulate full processing pipeline
            json_str = json.dumps(depth_message)
            parsed = json.loads(json_str)
            if "data" in parsed:
                data = BackpackWsDepthUpdate(**parsed["data"])
                # Would normally trigger order book update here
        depth_time = time.perf_counter() - start
        
        # Profile trade update processing
        start = time.perf_counter()
        for _ in range(iterations):
            json_str = json.dumps(trade_message)
            parsed = json.loads(json_str)
            if "data" in parsed:
                data = BackpackWsTradeUpdate(**parsed["data"])
                # Would normally trigger trade tick creation here
        trade_ws_time = time.perf_counter() - start
        
        self.results["websocket_depth"] = {
            "total_time": depth_time,
            "iterations": iterations,
            "avg_time_ms": (depth_time / iterations) * 1000,
            "throughput": iterations / depth_time,
        }
        
        self.results["websocket_trade"] = {
            "total_time": trade_ws_time,
            "iterations": iterations,
            "avg_time_ms": (trade_ws_time / iterations) * 1000,
            "throughput": iterations / trade_ws_time,
        }
        
        print(f"  Depth update: {self.results['websocket_depth']['avg_time_ms']:.4f}ms avg")
        print(f"  Trade update: {self.results['websocket_trade']['avg_time_ms']:.4f}ms avg")
    
    def profile_serialization(self, iterations: int = 10000):
        """Profile msgspec serialization performance."""
        print(f"\nProfiling serialization ({iterations} iterations)...")
        
        # Sample data structures
        complex_data = {
            "orders": [
                {"id": i, "price": f"{150.0 + i * 0.01}", "quantity": f"{i * 0.5}"}
                for i in range(50)
            ],
            "trades": [
                {"id": i, "price": f"{150.0 + i * 0.02}", "quantity": f"{i * 0.25}"}
                for i in range(100)
            ],
            "balances": {
                "SOL": {"free": "100.5", "locked": "10.0"},
                "USDC": {"free": "5000.0", "locked": "500.0"},
            },
        }
        
        # Profile encoding
        start = time.perf_counter()
        for _ in range(iterations):
            encoded = self.encoder.encode(complex_data)
        encode_time = time.perf_counter() - start
        
        # Profile decoding
        encoded_data = self.encoder.encode(complex_data)
        start = time.perf_counter()
        for _ in range(iterations):
            decoded = self.decoder.decode(encoded_data)
        decode_time = time.perf_counter() - start
        
        self.results["msgspec_encode"] = {
            "total_time": encode_time,
            "iterations": iterations,
            "avg_time_ms": (encode_time / iterations) * 1000,
            "throughput": iterations / encode_time,
            "data_size_bytes": len(encoded_data),
        }
        
        self.results["msgspec_decode"] = {
            "total_time": decode_time,
            "iterations": iterations,
            "avg_time_ms": (decode_time / iterations) * 1000,
            "throughput": iterations / decode_time,
        }
        
        print(f"  Encoding: {self.results['msgspec_encode']['avg_time_ms']:.4f}ms avg")
        print(f"  Decoding: {self.results['msgspec_decode']['avg_time_ms']:.4f}ms avg")
        print(f"  Data size: {self.results['msgspec_encode']['data_size_bytes']} bytes")
    
    def print_summary(self):
        """Print performance summary."""
        print("\n" + "="*60)
        print("PERFORMANCE SUMMARY")
        print("="*60)
        
        for test_name, metrics in self.results.items():
            print(f"\n{test_name.upper()}:")
            print(f"  Average latency: {metrics['avg_time_ms']:.4f}ms")
            print(f"  Throughput: {metrics['throughput']:.0f} ops/sec")
            
            # Check against performance targets
            if "orderbook" in test_name:
                target = 1.0  # 1ms target for order book updates
                status = "✅ PASS" if metrics['avg_time_ms'] < target else "❌ FAIL"
                print(f"  Target: <{target}ms {status}")
            elif "trade" in test_name:
                target = 0.5  # 0.5ms target for trade parsing
                status = "✅ PASS" if metrics['avg_time_ms'] < target else "❌ FAIL"
                print(f"  Target: <{target}ms {status}")
        
        # Overall message throughput estimate
        if "websocket_depth" in self.results:
            total_throughput = min(
                self.results["websocket_depth"]["throughput"],
                self.results["websocket_trade"]["throughput"],
            )
            print(f"\nEstimated message throughput: {total_throughput:.0f} msg/sec")
            
            target_throughput = 10000  # Target: 10,000 messages/second
            status = "✅ PASS" if total_throughput > target_throughput else "❌ NEEDS OPTIMIZATION"
            print(f"Target: >{target_throughput} msg/sec {status}")
        
        # Memory usage estimate (simplified)
        print(f"\nMemory usage estimate:")
        print(f"  Per order book update: ~{self.results.get('msgspec_encode', {}).get('data_size_bytes', 0) / 1024:.1f}KB")
        print(f"  For 1000 updates: ~{self.results.get('msgspec_encode', {}).get('data_size_bytes', 0) / 1024 * 1000:.1f}KB")
    
    def identify_bottlenecks(self):
        """Identify performance bottlenecks."""
        print("\n" + "="*60)
        print("BOTTLENECK ANALYSIS")
        print("="*60)
        
        bottlenecks = []
        
        # Check parsing performance
        if "orderbook_parsing" in self.results:
            if self.results["orderbook_parsing"]["avg_time_ms"] > 1.0:
                bottlenecks.append(("Order book parsing", self.results["orderbook_parsing"]["avg_time_ms"]))
        
        # Check WebSocket processing
        if "websocket_depth" in self.results:
            if self.results["websocket_depth"]["avg_time_ms"] > 2.0:
                bottlenecks.append(("WebSocket depth processing", self.results["websocket_depth"]["avg_time_ms"]))
        
        # Check serialization
        if "msgspec_decode" in self.results:
            if self.results["msgspec_decode"]["avg_time_ms"] > 0.5:
                bottlenecks.append(("Message decoding", self.results["msgspec_decode"]["avg_time_ms"]))
        
        if bottlenecks:
            print("\nIdentified bottlenecks (requiring optimization):")
            for name, latency in sorted(bottlenecks, key=lambda x: x[1], reverse=True):
                print(f"  - {name}: {latency:.4f}ms")
            print("\nRecommendation: Consider Rust implementation for these components")
        else:
            print("\n✅ No significant bottlenecks identified")
            print("Current Python implementation meets performance targets")


async def main():
    """Run performance profiling."""
    profiler = PerformanceProfiler()
    
    print("Starting Backpack Adapter Performance Profiling...")
    print("="*60)
    
    # Run profiling tests
    profiler.profile_parsing(iterations=10000)
    profiler.profile_websocket_processing(iterations=10000)
    profiler.profile_serialization(iterations=10000)
    
    # Print results
    profiler.print_summary()
    profiler.identify_bottlenecks()
    
    print("\n" + "="*60)
    print("Profiling complete!")
    print("\nNext steps:")
    print("1. Review bottleneck analysis above")
    print("2. If optimization needed, implement Rust components")
    print("3. Re-run profiling to verify improvements")


if __name__ == "__main__":
    asyncio.run(main())