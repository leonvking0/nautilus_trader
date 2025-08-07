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
Test klines data fetching via both REST API and WebSocket streaming.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.uuid import UUID4


# Load environment variables
load_dotenv()


class KlinesDataFetcher:
    """Fetch klines data via REST and WebSocket."""
    
    def __init__(self):
        """Initialize the klines fetcher."""
        self.api_key = os.getenv("BACKPACK_API_KEY")
        self.api_secret = os.getenv("BACKPACK_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError("Missing BACKPACK_API_KEY or BACKPACK_API_SECRET")
        
        self.clock = LiveClock()
        self.http_client = BackpackHttpClient(
            clock=self.clock,
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=False,
        )
        
        self.ws_client = BackpackWebSocketClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=False,
        )
        
        self.fixtures_dir = Path(__file__).parent / "fixtures"
        self.fixtures_dir.mkdir(exist_ok=True)
    
    async def test_rest_klines_fixed(self):
        """Test REST API klines with correct timestamp format (seconds)."""
        print("\n=== Testing REST API Klines (Fixed) ===")
        
        # Use seconds instead of milliseconds
        end_time = int(datetime.now().timestamp())  # Current time in seconds
        start_time = end_time - (24 * 60 * 60)  # 24 hours ago in seconds
        
        print(f"Start time (seconds): {start_time}")
        print(f"End time (seconds): {end_time}")
        
        try:
            # Test direct API call with curl first
            import subprocess
            curl_cmd = f'curl -s "https://api.backpack.exchange/api/v1/klines?symbol=BTC_USDC&interval=1h&startTime={start_time}&endTime={end_time}"'
            result = subprocess.run(curl_cmd, shell=True, capture_output=True, text=True)
            print(f"Curl response: {result.stdout[:200]}")
            
            # Now test with HTTP client - need to modify the params
            params = {
                "symbol": "BTC_USDC",
                "interval": "1h",
                "startTime": str(start_time),  # Convert to string
                "endTime": str(end_time),
            }
            
            raw_response = await self.http_client._get("/api/v1/klines", params=params)
            print(f"✅ Fetched klines via REST API")
            
            if raw_response:
                print(f"Number of klines: {len(raw_response) if isinstance(raw_response, list) else 'N/A'}")
                
                # Save to fixtures
                output_path = self.fixtures_dir / "rest_klines_btc.json"
                with open(output_path, "w") as f:
                    json.dump(raw_response, f, indent=2)
                print(f"Saved to {output_path}")
                
                return raw_response
                
        except Exception as e:
            print(f"❌ REST API klines failed: {e}")
            return None
    
    async def test_websocket_klines(self):
        """Test WebSocket klines streaming."""
        print("\n=== Testing WebSocket Klines Streaming ===")
        
        klines_data = []
        
        async def on_message(message: dict):
            """Handle incoming WebSocket messages."""
            print(f"Received message type: {message.get('e', 'unknown')}")
            if message.get("e") == "kline":
                klines_data.append(message)
                print(f"Kline data: {message}")
        
        try:
            # Connect to WebSocket
            await self.ws_client.connect()
            print("✅ Connected to WebSocket")
            
            # Subscribe to klines stream
            subscription = {
                "method": "SUBSCRIBE",
                "params": ["kline.1h.BTC_USDC"],  # 1 hour klines for BTC_USDC
                "id": str(UUID4()),
            }
            
            # Set message handler
            self.ws_client._on_message = on_message
            
            # Send subscription
            await self.ws_client.send(json.dumps(subscription))
            print("✅ Subscribed to kline.1h.BTC_USDC")
            
            # Wait for some data (30 seconds)
            print("Waiting for kline updates (30 seconds)...")
            await asyncio.sleep(30)
            
            # Unsubscribe
            unsubscribe = {
                "method": "UNSUBSCRIBE",
                "params": ["kline.1h.BTC_USDC"],
                "id": str(UUID4()),
            }
            await self.ws_client.send(json.dumps(unsubscribe))
            
            # Disconnect
            await self.ws_client.disconnect()
            print("✅ Disconnected from WebSocket")
            
            if klines_data:
                print(f"✅ Received {len(klines_data)} kline updates via WebSocket")
                
                # Save to fixtures
                output_path = self.fixtures_dir / "ws_klines_btc.json"
                with open(output_path, "w") as f:
                    json.dump(klines_data, f, indent=2)
                print(f"Saved to {output_path}")
            else:
                print("⚠️ No kline data received via WebSocket")
            
            return klines_data
            
        except Exception as e:
            print(f"❌ WebSocket klines failed: {e}")
            return None
    
    async def fetch_multiple_symbols_rest(self):
        """Fetch klines for multiple symbols via REST."""
        print("\n=== Fetching Multiple Symbols via REST ===")
        
        symbols = ["BTC_USDC", "SOL_USDC", "ETH_USDC"]
        intervals = ["1h", "5m", "1d"]
        
        all_klines = {}
        
        for symbol in symbols:
            for interval in intervals[:1]:  # Just test 1h for now
                end_time = int(datetime.now().timestamp())
                start_time = end_time - (7 * 24 * 60 * 60)  # 7 days ago
                
                try:
                    params = {
                        "symbol": symbol,
                        "interval": interval,
                        "startTime": str(start_time),
                        "endTime": str(end_time),
                    }
                    
                    klines = await self.http_client._get("/api/v1/klines", params=params)
                    
                    key = f"{symbol}_{interval}"
                    all_klines[key] = klines
                    
                    print(f"✅ Fetched {len(klines) if isinstance(klines, list) else 0} klines for {key}")
                    
                    # Rate limit protection
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print(f"❌ Failed to fetch {symbol} {interval}: {e}")
        
        if all_klines:
            # Save combined data
            output_path = self.fixtures_dir / "sample_klines.json"
            with open(output_path, "w") as f:
                json.dump(all_klines, f, indent=2)
            print(f"\n✅ Saved all klines to {output_path}")
        
        return all_klines
    
    async def fetch_other_market_data(self):
        """Fetch other market data for complete fixtures."""
        print("\n=== Fetching Other Market Data ===")
        
        fixtures = {}
        
        # Fetch trades
        try:
            trades_btc = await self.http_client.fetch_trades("BTC_USDC", 100)
            trades_sol = await self.http_client.fetch_trades("SOL_USDC", 100)
            
            fixtures["trades"] = {
                "BTC_USDC": trades_btc,
                "SOL_USDC": trades_sol,
            }
            print(f"✅ Fetched trades")
        except Exception as e:
            print(f"❌ Failed to fetch trades: {e}")
        
        # Fetch order books
        try:
            book_btc = await self.http_client.fetch_order_book("BTC_USDC")
            book_sol = await self.http_client.fetch_order_book("SOL_USDC")
            
            fixtures["orderbooks"] = {
                "BTC_USDC": book_btc,
                "SOL_USDC": book_sol,
            }
            print(f"✅ Fetched order books")
        except Exception as e:
            print(f"❌ Failed to fetch order books: {e}")
        
        # Fetch tickers
        try:
            tickers = await self.http_client.fetch_tickers()
            fixtures["tickers"] = [t for t in tickers if t.get("symbol") in ["BTC_USDC", "SOL_USDC", "ETH_USDC"]]
            print(f"✅ Fetched tickers")
        except Exception as e:
            print(f"❌ Failed to fetch tickers: {e}")
        
        # Save all fixtures
        for name, data in fixtures.items():
            output_path = self.fixtures_dir / f"sample_{name}.json"
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Saved {name} to {output_path}")
        
        return fixtures


async def main():
    """Main entry point."""
    fetcher = KlinesDataFetcher()
    
    print("="*60)
    print("Klines Data Fetching Test")
    print("="*60)
    
    # Test REST API with fixed timestamp format
    rest_klines = await fetcher.test_rest_klines_fixed()
    
    # Test WebSocket streaming (optional - takes 30 seconds)
    # ws_klines = await fetcher.test_websocket_klines()
    
    # Fetch multiple symbols
    multi_klines = await fetcher.fetch_multiple_symbols_rest()
    
    # Fetch other market data
    other_data = await fetcher.fetch_other_market_data()
    
    print("\n" + "="*60)
    print("Test completed!")
    print("="*60)
    
    # Validate fixtures
    fixtures_dir = fetcher.fixtures_dir
    expected_files = [
        "sample_klines.json",
        "sample_trades.json",
        "sample_orderbooks.json",
        "sample_tickers.json",
    ]
    
    print("\nValidating fixtures:")
    for filename in expected_files:
        filepath = fixtures_dir / filename
        if filepath.exists():
            size = filepath.stat().st_size
            print(f"✅ {filename}: {size} bytes")
        else:
            print(f"❌ {filename}: Missing")


if __name__ == "__main__":
    asyncio.run(main())