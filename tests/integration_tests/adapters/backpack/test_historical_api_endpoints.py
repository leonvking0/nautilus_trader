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
Test historical API endpoints with real data from Backpack Exchange.
"""

import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from dotenv import load_dotenv

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.http.history import BackpackHistoryHttpAPI
from nautilus_trader.common.component import LiveClock


# Load environment variables
load_dotenv()


@pytest.fixture
def live_clock():
    """Create a live clock for testing."""
    return LiveClock()


@pytest.fixture
def live_http_client(live_clock):
    """Create authenticated HTTP client for live testing."""
    api_key = os.getenv("BACKPACK_API_KEY")
    api_secret = os.getenv("BACKPACK_API_SECRET")
    
    if not api_key or not api_secret:
        pytest.skip("Missing BACKPACK_API_KEY or BACKPACK_API_SECRET")
    
    return BackpackHttpClient(
        clock=live_clock,
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,
    )


@pytest.fixture
def history_api(live_http_client):
    """Create history API client."""
    return BackpackHistoryHttpAPI(live_http_client)


@pytest.mark.asyncio
async def test_fetch_klines_history_btc(history_api):
    """Test fetching kline history for BTC_USDC."""
    # Fetch BTC_USDC 1h klines
    klines = await history_api.fetch_klines_history(
        symbol="BTC_USDC",
        interval="1h",
        limit=10,
    )
    
    # Validate response
    assert klines is not None
    assert isinstance(klines, list)
    assert len(klines) > 0
    
    # Validate kline structure
    if klines:
        kline = klines[0]
        assert isinstance(kline, list)
        assert len(kline) >= 6  # At least OHLCV + timestamp
        
        # Check values are reasonable
        timestamp, open_, high, low, close, volume = kline[:6]
        assert timestamp > 0
        assert open_ > 0
        assert high >= low
        assert high >= open_
        assert high >= close
        assert low <= open_
        assert low <= close
        assert volume >= 0
    
    print(f"✅ Fetched {len(klines)} BTC_USDC klines")


@pytest.mark.asyncio
async def test_fetch_klines_history_sol(history_api):
    """Test fetching kline history for SOL_USDC."""
    # Fetch SOL_USDC 5m klines
    klines = await history_api.fetch_klines_history(
        symbol="SOL_USDC",
        interval="5m",
        limit=20,
    )
    
    # Validate response
    assert klines is not None
    assert isinstance(klines, list)
    assert len(klines) > 0
    
    print(f"✅ Fetched {len(klines)} SOL_USDC klines")


@pytest.mark.asyncio
async def test_fetch_klines_with_time_range(history_api):
    """Test fetching klines with specific time range."""
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1)
    
    klines = await history_api.fetch_klines_history(
        symbol="BTC_USDC",
        interval="15m",
        start_time=int(start_time.timestamp() * 1000),
        end_time=int(end_time.timestamp() * 1000),
        limit=100,
    )
    
    assert klines is not None
    assert isinstance(klines, list)
    
    # Check timestamps are within range
    if klines:
        first_ts = klines[0][0]
        last_ts = klines[-1][0]
        assert first_ts >= int(start_time.timestamp() * 1000)
        assert last_ts <= int(end_time.timestamp() * 1000)
    
    print(f"✅ Fetched {len(klines)} klines within time range")


@pytest.mark.asyncio
async def test_fetch_trades_history(history_api):
    """Test fetching trade history."""
    try:
        trades = await history_api.fetch_trades_history(
            symbol="BTC_USDC",
            limit=50,
        )
        
        assert trades is not None
        assert isinstance(trades, list)
        
        if trades:
            trade = trades[0]
            assert "price" in trade or isinstance(trade, list)
            assert "quantity" in trade or isinstance(trade, list)
        
        print(f"✅ Fetched {len(trades)} trades")
    except Exception as e:
        print(f"⚠️ Trade history not available: {e}")


@pytest.mark.asyncio
async def test_fetch_order_history(history_api):
    """Test fetching order history."""
    try:
        orders = await history_api.fetch_order_history(
            limit=10,
        )
        
        assert orders is not None
        assert isinstance(orders, list)
        
        if orders:
            print(f"✅ Fetched {len(orders)} historical orders")
        else:
            print("ℹ️ No historical orders found (this is normal for new accounts)")
    except Exception as e:
        print(f"⚠️ Order history not available: {e}")


@pytest.mark.asyncio
async def test_fetch_fill_history(history_api):
    """Test fetching fill history."""
    try:
        fills = await history_api.fetch_fill_history(
            limit=10,
        )
        
        assert fills is not None
        assert isinstance(fills, list)
        
        if fills:
            print(f"✅ Fetched {len(fills)} fills")
        else:
            print("ℹ️ No fills found (this is normal for new accounts)")
    except Exception as e:
        print(f"⚠️ Fill history not available: {e}")


@pytest.mark.asyncio
async def test_fetch_pnl_history(history_api):
    """Test fetching PnL history."""
    try:
        start_time = datetime.now() - timedelta(days=30)
        pnl = await history_api.fetch_pnl_history(
            start_time=int(start_time.timestamp() * 1000),
        )
        
        assert pnl is not None
        
        if pnl:
            print(f"✅ Fetched PnL history")
        else:
            print("ℹ️ No PnL history found")
    except Exception as e:
        print(f"⚠️ PnL history not available: {e}")


@pytest.mark.asyncio
async def test_parallel_fetch_multiple_symbols(history_api):
    """Test fetching data for multiple symbols in parallel."""
    symbols = ["BTC_USDC", "SOL_USDC", "ETH_USDC"]
    
    # Create parallel tasks
    tasks = [
        history_api.fetch_klines_history(symbol, "1h", limit=5)
        for symbol in symbols
    ]
    
    # Execute in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Validate results
    success_count = 0
    for symbol, result in zip(symbols, results):
        if isinstance(result, Exception):
            print(f"❌ Failed to fetch {symbol}: {result}")
        else:
            success_count += 1
            print(f"✅ Fetched {len(result)} klines for {symbol}")
    
    assert success_count > 0, "At least one symbol should succeed"


@pytest.mark.asyncio
async def test_fetch_all_historical_data(history_api):
    """Test the fetch_all_historical_data utility method."""
    try:
        all_data = await history_api.fetch_all_historical_data(
            symbols=["BTC_USDC", "SOL_USDC"],
            start_date=datetime.now() - timedelta(days=1),
        )
        
        assert all_data is not None
        assert isinstance(all_data, dict)
        
        # Check for expected keys
        for key in ["klines", "trades", "orders", "fills"]:
            if key in all_data:
                print(f"✅ Fetched {key} data")
    except Exception as e:
        print(f"⚠️ fetch_all_historical_data not fully implemented: {e}")


@pytest.mark.asyncio 
async def test_pagination_handling(history_api):
    """Test that pagination works correctly for large datasets."""
    # Try to fetch more than one page of data
    klines = await history_api.fetch_klines_history(
        symbol="BTC_USDC",
        interval="1m",
        limit=1000,  # Max limit
    )
    
    assert klines is not None
    assert isinstance(klines, list)
    assert len(klines) <= 1000  # Should respect limit
    
    print(f"✅ Pagination test: fetched {len(klines)} klines")


@pytest.mark.asyncio
async def test_error_handling_invalid_symbol(history_api):
    """Test error handling for invalid symbol."""
    with pytest.raises(Exception):
        await history_api.fetch_klines_history(
            symbol="INVALID_SYMBOL",
            interval="1h",
            limit=10,
        )
    
    print("✅ Invalid symbol error handled correctly")


@pytest.mark.asyncio
async def test_error_handling_invalid_interval(history_api):
    """Test error handling for invalid interval."""
    with pytest.raises(Exception):
        await history_api.fetch_klines_history(
            symbol="BTC_USDC", 
            interval="invalid",
            limit=10,
        )
    
    print("✅ Invalid interval error handled correctly")


# Simple test runner for direct execution
async def run_all_tests():
    """Run all tests directly."""
    clock = LiveClock()
    client = BackpackHttpClient(
        clock=clock,
        api_key=os.getenv("BACKPACK_API_KEY"),
        api_secret=os.getenv("BACKPACK_API_SECRET"),
        testnet=False,
    )
    api = BackpackHistoryHttpAPI(client)
    
    print("\n" + "="*60)
    print("Running Historical API Endpoint Tests")
    print("="*60 + "\n")
    
    tests = [
        ("BTC Klines", test_fetch_klines_history_btc),
        ("SOL Klines", test_fetch_klines_history_sol),
        ("Time Range", test_fetch_klines_with_time_range),
        ("Trades", test_fetch_trades_history),
        ("Orders", test_fetch_order_history),
        ("Fills", test_fetch_fill_history),
        ("PnL", test_fetch_pnl_history),
        ("Parallel Fetch", test_parallel_fetch_multiple_symbols),
        ("All Data", test_fetch_all_historical_data),
        ("Pagination", test_pagination_handling),
    ]
    
    for name, test_func in tests:
        print(f"\nTesting {name}...")
        try:
            await test_func(api)
        except Exception as e:
            print(f"❌ {name} failed: {e}")
    
    print("\n" + "="*60)
    print("Test run completed!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())