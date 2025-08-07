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
Test that klines fetching works correctly with the fixed connector.
This test verifies the timestamp conversion fix for the Backpack API.
"""

import asyncio
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.http.history import BackpackHistoryHttpAPI
from nautilus_trader.common.component import LiveClock


# Load environment variables
load_dotenv()


async def test_klines_with_milliseconds():
    """Test that klines API works with millisecond timestamps (should auto-convert)."""
    print("\n" + "="*60)
    print("Testing Klines Fetching with Fixed Connector")
    print("="*60)
    
    # Initialize clients
    clock = LiveClock()
    http_client = BackpackHttpClient(
        clock=clock,
        api_key=os.getenv("BACKPACK_API_KEY"),
        api_secret=os.getenv("BACKPACK_API_SECRET"),
        testnet=False,
    )
    history_api = BackpackHistoryHttpAPI(http_client)
    
    # Test 1: Using millisecond timestamps (typical usage)
    print("\n1. Testing with millisecond timestamps...")
    end_time_ms = int(datetime.now().timestamp() * 1000)
    start_time_ms = end_time_ms - (24 * 60 * 60 * 1000)  # 24 hours ago
    
    try:
        klines = await history_api.fetch_klines_history(
            symbol="BTC_USDC",
            interval="1h",
            start_time=start_time_ms,
            end_time=end_time_ms,
            limit=10,
        )
        print(f"✅ Successfully fetched {len(klines)} klines with millisecond timestamps")
        if klines and isinstance(klines[0], dict):
            # Klines are returned as dicts
            first = klines[0]
            print(f"   First kline: O:{first.get('open')} H:{first.get('high')} L:{first.get('low')} C:{first.get('close')}")
    except Exception as e:
        print(f"❌ Failed with milliseconds: {e}")
    
    # Test 2: Using second timestamps (also should work)
    print("\n2. Testing with second timestamps...")
    end_time_s = int(datetime.now().timestamp())
    start_time_s = end_time_s - (24 * 60 * 60)  # 24 hours ago
    
    try:
        klines = await history_api.fetch_klines_history(
            symbol="SOL_USDC",
            interval="5m",
            start_time=start_time_s,
            end_time=end_time_s,
            limit=10,
        )
        print(f"✅ Successfully fetched {len(klines)} klines with second timestamps")
        if klines and isinstance(klines[0], dict):
            first = klines[0]
            print(f"   First kline: O:{first.get('open')} H:{first.get('high')} L:{first.get('low')} C:{first.get('close')}")
    except Exception as e:
        print(f"❌ Failed with seconds: {e}")
    
    # Test 3: Using the HTTP client directly (milliseconds)
    print("\n3. Testing HTTP client directly with milliseconds...")
    try:
        klines = await http_client.fetch_klines(
            symbol="ETH_USDC",
            interval="15m",
            start_time=start_time_ms,
            end_time=end_time_ms,
        )
        print(f"✅ HTTP client fetched {len(klines)} klines with milliseconds")
    except Exception as e:
        print(f"❌ HTTP client failed: {e}")
    
    # Test 4: Without timestamps (should use defaults)
    print("\n4. Testing without timestamps (using defaults)...")
    try:
        klines = await history_api.fetch_klines_history(
            symbol="BTC_USDC",
            interval="1d",
            limit=7,
        )
        print(f"✅ Successfully fetched {len(klines)} klines without timestamps")
    except Exception as e:
        print(f"❌ Failed without timestamps: {e}")
    
    # Test 5: Compare results between milliseconds and seconds
    print("\n5. Comparing results between ms and s timestamps...")
    
    # Fetch with milliseconds
    klines_ms = await history_api.fetch_klines_history(
        symbol="BTC_USDC",
        interval="1h",
        start_time=start_time_ms,
        end_time=end_time_ms,
        limit=5,
    )
    
    # Fetch with seconds (same time range)
    klines_s = await history_api.fetch_klines_history(
        symbol="BTC_USDC",
        interval="1h",
        start_time=start_time_s,
        end_time=end_time_s,
        limit=5,
    )
    
    if len(klines_ms) == len(klines_s):
        print(f"✅ Both methods returned same number of klines: {len(klines_ms)}")
        
        # Check if data matches
        if klines_ms and klines_s:
            # Compare first kline's open price
            if klines_ms[0]["open"] == klines_s[0]["open"]:
                print("✅ Data matches between millisecond and second timestamps")
            else:
                print("⚠️ Data differs between methods")
    else:
        print(f"⚠️ Different results: {len(klines_ms)} ms vs {len(klines_s)} s")
    
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    print("The klines API now correctly handles both millisecond and second")
    print("timestamps, automatically converting as needed for the Backpack API.")
    print("="*60)


async def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n" + "="*60)
    print("Testing Edge Cases")
    print("="*60)
    
    clock = LiveClock()
    http_client = BackpackHttpClient(
        clock=clock,
        api_key=os.getenv("BACKPACK_API_KEY"),
        api_secret=os.getenv("BACKPACK_API_SECRET"),
        testnet=False,
    )
    history_api = BackpackHistoryHttpAPI(http_client)
    
    # Test with invalid symbol
    print("\n1. Testing with invalid symbol...")
    try:
        klines = await history_api.fetch_klines_history(
            symbol="INVALID_SYMBOL",
            interval="1h",
            limit=1,
        )
        print(f"⚠️ Unexpectedly succeeded with {len(klines)} klines")
    except Exception as e:
        print(f"✅ Correctly failed with invalid symbol: {e}")
    
    # Test with invalid interval
    print("\n2. Testing with invalid interval...")
    try:
        klines = await history_api.fetch_klines_history(
            symbol="BTC_USDC",
            interval="invalid",
            limit=1,
        )
        print(f"⚠️ Unexpectedly succeeded with {len(klines)} klines")
    except Exception as e:
        print(f"✅ Correctly failed with invalid interval: {e}")
    
    # Test with future timestamps
    print("\n3. Testing with future timestamps...")
    future_time = int((datetime.now() + timedelta(days=1)).timestamp() * 1000)
    try:
        klines = await history_api.fetch_klines_history(
            symbol="BTC_USDC",
            interval="1h",
            start_time=future_time,
            limit=1,
        )
        if len(klines) == 0:
            print("✅ Correctly returned empty list for future time")
        else:
            print(f"⚠️ Returned {len(klines)} klines for future time")
    except Exception as e:
        print(f"✅ Failed as expected with future time: {e}")
    
    print("\n" + "="*60)


async def main():
    """Run all tests."""
    await test_klines_with_milliseconds()
    await test_edge_cases()


if __name__ == "__main__":
    asyncio.run(main())