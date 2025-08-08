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
Test script to validate the Backpack connector approach for the tutorial.
This tests all the components we'll use in the notebook.
"""

import asyncio
import base64
import os
from datetime import datetime, timedelta, timezone

# Test imports first
print("Testing imports...")

try:
    from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
    print("✓ BACKPACK_VENUE imported")
except ImportError as e:
    print(f"✗ Failed to import BACKPACK_VENUE: {e}")

try:
    from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
    print("✓ BackpackHttpClient imported")
except ImportError as e:
    print(f"✗ Failed to import BackpackHttpClient: {e}")

try:
    from nautilus_trader.adapters.backpack.http.history import BackpackHistoryHttpAPI
    print("✓ BackpackHistoryHttpAPI imported")
except ImportError as e:
    print(f"✗ Failed to import BackpackHistoryHttpAPI: {e}")

try:
    from nautilus_trader.adapters.backpack.backtest import BackpackBacktestDataProvider
    print("✓ BackpackBacktestDataProvider imported")
except ImportError as e:
    print(f"✗ Failed to import BackpackBacktestDataProvider: {e}")

try:
    from nautilus_trader.adapters.backpack.providers import BackpackInstrumentProvider
    print("✓ BackpackInstrumentProvider imported")
except ImportError as e:
    print(f"✗ Failed to import BackpackInstrumentProvider: {e}")

try:
    from nautilus_trader.common.component import LiveClock
    print("✓ LiveClock imported")
except ImportError as e:
    print(f"✗ Failed to import LiveClock: {e}")

try:
    from nautilus_trader.config import InstrumentProviderConfig
    print("✓ InstrumentProviderConfig imported")
except ImportError as e:
    print(f"✗ Failed to import InstrumentProviderConfig: {e}")

try:
    from nautilus_trader.model.identifiers import InstrumentId, Symbol
    print("✓ Identifiers imported")
except ImportError as e:
    print(f"✗ Failed to import identifiers: {e}")

print("\n" + "="*60)
print("Testing component initialization...")
print("="*60)


async def test_connector():
    """Test the Backpack connector components."""
    
    # Create a dummy base64 encoded secret for testing
    # This is just a placeholder - the API will reject it but won't crash
    dummy_secret = base64.b64encode(b"0" * 32).decode('utf-8')
    
    # 1. Test LiveClock
    try:
        clock = LiveClock()
        print("✓ LiveClock created")
    except Exception as e:
        print(f"✗ Failed to create LiveClock: {e}")
        return
    
    # 2. Test BackpackHttpClient with dummy credentials
    try:
        http_client = BackpackHttpClient(
            clock=clock,
            api_key="dummy_api_key",
            api_secret=dummy_secret,
            base_url="https://api.backpack.exchange",
        )
        print("✓ BackpackHttpClient created")
    except Exception as e:
        print(f"✗ Failed to create BackpackHttpClient: {e}")
        return
    
    # 3. Test BackpackInstrumentProvider
    try:
        instrument_provider = BackpackInstrumentProvider(
            client=http_client,
            clock=clock,
            config=InstrumentProviderConfig(
                load_all=False,
                log_warnings=False,
            ),
        )
        print("✓ BackpackInstrumentProvider created")
    except Exception as e:
        print(f"✗ Failed to create BackpackInstrumentProvider: {e}")
        return
    
    # 4. Test BackpackHistoryHttpAPI
    try:
        history_api = BackpackHistoryHttpAPI(http_client)
        print("✓ BackpackHistoryHttpAPI created")
    except Exception as e:
        print(f"✗ Failed to create BackpackHistoryHttpAPI: {e}")
        return
    
    # 5. Test fetching public data (klines)
    print("\n" + "="*60)
    print("Testing public API access...")
    print("="*60)
    
    try:
        # Try to fetch klines - this should work even with dummy credentials
        # since it's a public endpoint
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=1)
        
        # Convert to seconds (Backpack uses seconds)
        start_ts = int(start_time.timestamp())
        end_ts = int(end_time.timestamp())
        
        print(f"Fetching BTC_USDC klines from {start_time} to {end_time}")
        
        klines = await history_api.fetch_klines_history(
            symbol="BTC_USDC",
            interval="1h",
            start_time=start_ts,
            end_time=end_ts,
            limit=24,
        )
        
        if klines:
            print(f"✓ Fetched {len(klines)} klines from Backpack API")
            print(f"  First kline: {klines[0] if isinstance(klines[0], dict) else klines[0][:6]}")
        else:
            print("✗ No klines returned (API might be down or credentials issue)")
            
    except Exception as e:
        print(f"✗ Failed to fetch klines: {e}")
        print("  This is expected if the API requires valid credentials even for public endpoints")
    
    # 6. Test BackpackBacktestDataProvider (if it requires valid instrument)
    try:
        from nautilus_trader.adapters.backpack.backtest import BackpackBacktestDataProvider
        from pathlib import Path
        
        data_provider = BackpackBacktestDataProvider(
            http_client=http_client,
            instrument_provider=instrument_provider,
            cache_dir=Path.home() / ".nautilus" / "backpack" / "test_cache",
        )
        print("✓ BackpackBacktestDataProvider created")
    except Exception as e:
        print(f"✗ Failed to create BackpackBacktestDataProvider: {e}")
    
    # Clean up
    try:
        await http_client.close()
        print("\n✓ HTTP client closed successfully")
    except Exception as e:
        print(f"\n✗ Failed to close HTTP client: {e}")
    
    print("\n" + "="*60)
    print("Test completed!")
    print("="*60)


if __name__ == "__main__":
    print("Starting Backpack connector test...\n")
    asyncio.run(test_connector())