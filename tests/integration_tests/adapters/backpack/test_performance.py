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

"""Performance validation tests for Backpack adapter."""

import asyncio
import gc
import resource
import time
from collections import deque
from decimal import Decimal
from typing import Dict, List, Any

import pytest

from nautilus_trader.core.uuid import UUID4

from .base import BackpackTestBase, live_only, dual_mode


class TestBackpackPerformance(BackpackTestBase):
    """Performance validation tests for Backpack adapter."""
    
    @live_only
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_order_latency(self):
        """Measure round-trip order placement latency."""
        self.require_live_mode()
        
        latencies = []
        
        # Get market price for safe order placement
        ticker = await self.http_client.get_ticker("SOL_USDC")
        market_price = Decimal(ticker["lastPrice"])
        test_price = Decimal(str(round(float(market_price) * 0.9, 2)))
        
        # Measure latency for multiple orders
        for i in range(5):
            order_params = {
                "symbol": "SOL_USDC",
                "side": "Bid",
                "orderType": "Limit",
                "price": str(test_price - Decimal(str(i))),  # Different prices
                "quantity": "0.1",
                "timeInForce": "GTC",
                "clientOrderId": f"PERF_TEST_{i}_{UUID4()}",
            }
            
            # Measure placement time
            start_time = time.perf_counter()
            try:
                result = await self.http_client.place_order(**order_params)
                end_time = time.perf_counter()
                
                latency_ms = (end_time - start_time) * 1000
                latencies.append(latency_ms)
                
                # Clean up order
                if "id" in result:
                    await self.http_client.cancel_order("SOL_USDC", result["id"])
            except Exception as e:
                print(f"Order placement failed: {e}")
            
            # Brief delay between orders
            await asyncio.sleep(0.1)
        
        # Calculate statistics
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            
            print(f"\nOrder Latency Statistics:")
            print(f"  Average: {avg_latency:.2f}ms")
            print(f"  Min: {min_latency:.2f}ms")
            print(f"  Max: {max_latency:.2f}ms")
            
            # Performance assertions
            assert avg_latency < 200, f"Average latency {avg_latency}ms exceeds 200ms target"
            assert min_latency < 100, f"Minimum latency {min_latency}ms exceeds 100ms target"
    
    @live_only
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_websocket_throughput(self):
        """Test WebSocket message processing throughput."""
        self.require_live_mode()
        
        message_count = 0
        message_sizes = []
        start_time = None
        
        async def message_handler(message: Dict[str, Any]):
            nonlocal message_count, start_time
            if start_time is None:
                start_time = time.perf_counter()
            message_count += 1
            message_sizes.append(len(str(message)))
        
        # Connect and subscribe to high-volume streams
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        
        # Subscribe to multiple streams for higher volume
        symbols = ["SOL_USDC", "BTC_USDC", "ETH_USDC"]
        for symbol in symbols:
            try:
                await self.ws_client.subscribe_depth(symbol)
                await self.ws_client.subscribe_trades(symbol)
            except Exception:
                pass  # Some symbols might not be available
        
        # Collect messages for 10 seconds
        test_duration = 10
        await asyncio.sleep(test_duration)
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Calculate throughput
        if message_count > 0:
            elapsed_time = time.perf_counter() - start_time
            throughput = message_count / elapsed_time
            avg_size = sum(message_sizes) / len(message_sizes)
            
            print(f"\nWebSocket Throughput Statistics:")
            print(f"  Messages received: {message_count}")
            print(f"  Duration: {elapsed_time:.2f}s")
            print(f"  Throughput: {throughput:.2f} msg/sec")
            print(f"  Average message size: {avg_size:.0f} bytes")
            
            # Performance assertion (relaxed for variable market conditions)
            assert throughput > 1, f"Throughput {throughput} msg/sec below minimum"
    
    @dual_mode
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_memory_usage(self):
        """Profile memory usage under load."""
        if self.test_mode.value == "mock":
            pytest.skip("Memory profiling requires live connection")
        
        self.require_live_mode()
        
        # Get initial memory usage
        gc.collect()
        initial_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        
        # Store messages to simulate real usage
        message_buffer = deque(maxlen=10000)
        
        async def message_handler(message: Dict[str, Any]):
            message_buffer.append(message)
        
        # Connect and run for extended period
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        await self.ws_client.subscribe_depth("SOL_USDC")
        await self.ws_client.subscribe_trades("SOL_USDC")
        
        # Run for 30 seconds
        await asyncio.sleep(30)
        
        # Check memory after load
        gc.collect()
        final_memory = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Calculate memory growth
        memory_growth_mb = (final_memory - initial_memory) / 1024 / 1024
        
        print(f"\nMemory Usage Statistics:")
        print(f"  Initial: {initial_memory / 1024 / 1024:.2f} MB")
        print(f"  Final: {final_memory / 1024 / 1024:.2f} MB")
        print(f"  Growth: {memory_growth_mb:.2f} MB")
        print(f"  Messages buffered: {len(message_buffer)}")
        
        # Memory assertion (allowing reasonable growth)
        assert memory_growth_mb < 100, f"Memory growth {memory_growth_mb}MB exceeds 100MB limit"
    
    @live_only
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test performance with concurrent API requests."""
        self.require_live_mode()
        
        # Prepare concurrent requests
        symbols = ["SOL_USDC", "BTC_USDC", "ETH_USDC"]
        request_types = ["ticker", "depth", "trades"]
        
        async def make_request(symbol: str, request_type: str):
            start = time.perf_counter()
            try:
                if request_type == "ticker":
                    await self.http_client.get_ticker(symbol)
                elif request_type == "depth":
                    await self.http_client.get_depth(symbol)
                elif request_type == "trades":
                    await self.http_client.get_trades(symbol)
                return time.perf_counter() - start
            except Exception:
                return None
        
        # Make concurrent requests
        tasks = []
        for symbol in symbols:
            for request_type in request_types:
                tasks.append(make_request(symbol, request_type))
        
        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.perf_counter() - start_time
        
        # Filter successful requests
        latencies = [r for r in results if isinstance(r, float)]
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies) * 1000
            max_latency = max(latencies) * 1000
            
            print(f"\nConcurrent Request Statistics:")
            print(f"  Total requests: {len(tasks)}")
            print(f"  Successful: {len(latencies)}")
            print(f"  Total time: {total_time:.2f}s")
            print(f"  Average latency: {avg_latency:.2f}ms")
            print(f"  Max latency: {max_latency:.2f}ms")
            
            # Performance assertions
            assert total_time < 5, f"Total time {total_time}s exceeds 5s for {len(tasks)} requests"
            assert avg_latency < 500, f"Average latency {avg_latency}ms exceeds 500ms"
    
    @live_only
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_order_book_update_frequency(self):
        """Measure order book update frequency."""
        self.require_live_mode()
        
        update_times = []
        last_update_time = None
        
        async def message_handler(message: Dict[str, Any]):
            nonlocal last_update_time
            if message.get("stream") == "depth":
                current_time = time.perf_counter()
                if last_update_time is not None:
                    update_times.append(current_time - last_update_time)
                last_update_time = current_time
        
        # Connect and subscribe
        self.ws_client.on_message = message_handler
        await self.ws_client.connect()
        await self.ws_client.subscribe_depth("SOL_USDC")
        
        # Collect updates for 10 seconds
        await asyncio.sleep(10)
        
        # Disconnect
        await self.ws_client.disconnect()
        
        # Calculate statistics
        if update_times:
            avg_interval = sum(update_times) / len(update_times) * 1000
            min_interval = min(update_times) * 1000
            max_interval = max(update_times) * 1000
            updates_per_second = 1000 / avg_interval if avg_interval > 0 else 0
            
            print(f"\nOrder Book Update Frequency:")
            print(f"  Updates received: {len(update_times)}")
            print(f"  Average interval: {avg_interval:.2f}ms")
            print(f"  Min interval: {min_interval:.2f}ms")
            print(f"  Max interval: {max_interval:.2f}ms")
            print(f"  Updates/second: {updates_per_second:.2f}")
            
            # Performance assertions
            assert updates_per_second > 0.1, "Should receive at least 0.1 updates per second"
    
    @live_only
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_reconnection_speed(self):
        """Test speed of reconnection after disconnect."""
        self.require_live_mode()
        
        reconnection_times = []
        
        for i in range(3):
            # Connect
            start_time = time.perf_counter()
            await self.ws_client.connect()
            connect_time = time.perf_counter() - start_time
            
            # Subscribe
            await self.ws_client.subscribe_depth("SOL_USDC")
            
            # Brief operation
            await asyncio.sleep(1)
            
            # Disconnect
            await self.ws_client.disconnect()
            
            # Measure reconnection
            start_time = time.perf_counter()
            await self.ws_client.connect()
            reconnect_time = time.perf_counter() - start_time
            reconnection_times.append(reconnect_time)
            
            # Cleanup
            await self.ws_client.disconnect()
            await asyncio.sleep(0.5)
        
        # Calculate statistics
        avg_reconnect = sum(reconnection_times) / len(reconnection_times) * 1000
        max_reconnect = max(reconnection_times) * 1000
        
        print(f"\nReconnection Speed Statistics:")
        print(f"  Tests run: {len(reconnection_times)}")
        print(f"  Average reconnection: {avg_reconnect:.2f}ms")
        print(f"  Max reconnection: {max_reconnect:.2f}ms")
        
        # Performance assertions
        assert avg_reconnect < 2000, f"Average reconnection {avg_reconnect}ms exceeds 2000ms"
        assert max_reconnect < 5000, f"Max reconnection {max_reconnect}ms exceeds 5000ms"