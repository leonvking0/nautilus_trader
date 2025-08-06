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
Capture real API responses from Backpack Exchange for test fixture updates.

This script fetches actual responses from Backpack API endpoints and saves them
as test fixtures, ensuring our mock data accurately reflects the real API.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Load .env file if it exists
from dotenv import load_dotenv
load_dotenv()

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.common.component import LiveClock


class BackpackResponseCapture:
    """Capture and save real API responses from Backpack Exchange."""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """Initialize the response capture tool."""
        self.clock = LiveClock()
        self.client = BackpackHttpClient(
            clock=self.clock,
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet,
        )
        self.captured_at = datetime.now(timezone.utc).isoformat()
        self.results = {}
        self.testnet = testnet
        
        # Output directory for captured responses
        self.output_dir = Path("tests/integration_tests/adapters/backpack/resources/real_responses")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def _wrap_response(self, data: Any, endpoint: str) -> Dict:
        """Wrap response with metadata."""
        return {
            "metadata": {
                "captured_at": self.captured_at,
                "endpoint": endpoint,
                "api_version": "v1",
                "exchange": "backpack",
                "testnet": self.testnet,
            },
            "data": data,
        }
    
    async def capture_public_endpoints(self):
        """Capture responses from public endpoints."""
        print("\n📸 Capturing Public Endpoint Responses...")
        
        # 1. Markets
        print("  - Fetching markets...")
        try:
            markets = await self.client.fetch_markets()
            if markets:
                self.results["markets"] = self._wrap_response(markets, "/api/v1/markets")
                print(f"    ✅ Captured {len(markets)} markets")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
        
        # 2. Ticker (single)
        print("  - Fetching ticker for SOL_USDC...")
        try:
            ticker = await self.client.fetch_ticker("SOL_USDC")
            if ticker:
                self.results["ticker"] = self._wrap_response(ticker, "/api/v1/ticker")
                print(f"    ✅ Captured ticker: {ticker.get('lastPrice', 'N/A')}")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
        
        # 3. Tickers (all)
        print("  - Fetching all tickers...")
        try:
            tickers = await self.client.fetch_tickers()
            if tickers:
                # Check if it's a list or dict and limit to first 5 for fixture size
                if isinstance(tickers, dict):
                    sample_tickers = dict(list(tickers.items())[:5])
                    print(f"    ✅ Captured {len(tickers)} tickers (saved 5 samples)")
                else:
                    sample_tickers = tickers[:5] if len(tickers) > 5 else tickers
                    print(f"    ✅ Captured {len(tickers)} tickers (saved {len(sample_tickers)} samples)")
                self.results["tickers"] = self._wrap_response(sample_tickers, "/api/v1/tickers")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
        
        # 4. Order Book
        print("  - Fetching order book for SOL_USDC...")
        try:
            orderbook = await self.client.fetch_order_book("SOL_USDC")
            if orderbook:
                # Limit depth for fixture size
                if "asks" in orderbook:
                    orderbook["asks"] = orderbook["asks"][:10]
                if "bids" in orderbook:
                    orderbook["bids"] = orderbook["bids"][:10]
                self.results["orderbook"] = self._wrap_response(orderbook, "/api/v1/depth")
                print(f"    ✅ Captured order book")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
        
        # 5. Recent Trades
        print("  - Fetching recent trades for SOL_USDC...")
        try:
            trades = await self.client.fetch_trades("SOL_USDC", limit=20)
            if trades:
                self.results["trades"] = self._wrap_response(trades, "/api/v1/trades")
                print(f"    ✅ Captured {len(trades)} trades")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
        
        # 6. Klines/Candles
        print("  - Fetching klines for SOL_USDC...")
        try:
            # fetch_klines doesn't have a limit parameter, use time range instead
            import time
            end_time = int(time.time() * 1000)
            start_time = end_time - (24 * 60 * 60 * 1000)  # 24 hours ago
            klines = await self.client.fetch_klines("SOL_USDC", "1h", start_time=start_time, end_time=end_time)
            if klines:
                self.results["klines"] = self._wrap_response(klines, "/api/v1/klines")
                print(f"    ✅ Captured {len(klines)} klines")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
    
    async def capture_private_endpoints(self):
        """Capture responses from private endpoints."""
        print("\n🔐 Capturing Private Endpoint Responses...")
        
        # 1. Account Balance
        print("  - Fetching account balance...")
        try:
            balance = await self.client.fetch_balance()
            if balance:
                # Sanitize sensitive values
                sanitized_balance = {}
                for asset, details in balance.items():
                    sanitized_balance[asset] = {
                        "available": "100.00",  # Use fixed test values
                        "locked": "0.00",
                        "staked": "0.00",
                    }
                self.results["balance"] = self._wrap_response(
                    sanitized_balance, 
                    "/api/v1/capital"
                )
                print(f"    ✅ Captured balance for {len(balance)} assets")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
        
        # 2. Open Orders
        print("  - Fetching open orders...")
        try:
            # Try to get any open orders
            orders = await self.client.fetch_open_orders("SOL_USDC")
            if orders:
                # Sanitize order IDs
                sanitized_orders = []
                for i, order in enumerate(orders[:3]):  # Limit to 3 samples
                    sanitized_order = order.copy()
                    sanitized_order["id"] = f"TEST_ORDER_{i+1}"
                    sanitized_order["clientOrderId"] = f"CLIENT_{i+1}"
                    sanitized_orders.append(sanitized_order)
                self.results["orders"] = self._wrap_response(
                    sanitized_orders,
                    "/api/v1/orders"
                )
                print(f"    ✅ Captured {len(orders)} open orders")
            else:
                # Create sample structure
                self.results["orders"] = self._wrap_response([], "/api/v1/orders")
                print("    ✅ No open orders (captured empty response)")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
        
        # 3. Order History
        print("  - Fetching order history...")
        try:
            history = await self.client.fetch_order_history("SOL_USDC", limit=5)
            if history:
                # Sanitize historical orders
                sanitized_history = []
                for i, order in enumerate(history[:5]):
                    sanitized_order = order.copy()
                    sanitized_order["id"] = f"HIST_ORDER_{i+1}"
                    sanitized_order["clientOrderId"] = f"HIST_CLIENT_{i+1}"
                    sanitized_history.append(sanitized_order)
                self.results["order_history"] = self._wrap_response(
                    sanitized_history,
                    "/api/v1/orderHistory"
                )
                print(f"    ✅ Captured {len(history)} historical orders")
            else:
                self.results["order_history"] = self._wrap_response([], "/api/v1/orderHistory")
                print("    ✅ No order history (captured empty response)")
        except Exception as e:
            print(f"    ❌ Failed: {e}")
    
    def save_responses(self):
        """Save captured responses to files."""
        print("\n💾 Saving Captured Responses...")
        
        for name, data in self.results.items():
            filepath = self.output_dir / f"{name}.json"
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2)
            print(f"  ✅ Saved: {filepath}")
        
        # Create summary file
        summary = {
            "capture_summary": {
                "timestamp": self.captured_at,
                "total_endpoints": len(self.results),
                "captured": list(self.results.keys()),
                "testnet": self.testnet,
            }
        }
        summary_path = self.output_dir / "capture_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"  ✅ Summary: {summary_path}")
    
    def compare_with_mock_data(self):
        """Compare captured responses with existing mock data."""
        print("\n🔍 Comparing with Existing Mock Data...")
        
        mock_dir = Path("tests/integration_tests/adapters/backpack/resources/http_responses")
        
        for name in ["markets", "ticker", "tickers", "orderbook", "trades", "balance", "orders"]:
            mock_file = mock_dir / f"{name}.json"
            real_file = self.output_dir / f"{name}.json"
            
            if mock_file.exists() and real_file.exists():
                with open(mock_file) as f:
                    mock_data = json.load(f)
                with open(real_file) as f:
                    real_data = json.load(f)
                
                # Compare structure (keys)
                if isinstance(mock_data, dict) and isinstance(real_data.get("data"), dict):
                    mock_keys = set(mock_data.keys())
                    real_keys = set(real_data["data"].keys())
                    
                    missing_in_mock = real_keys - mock_keys
                    extra_in_mock = mock_keys - real_keys
                    
                    if missing_in_mock or extra_in_mock:
                        print(f"\n  ⚠️ {name}.json differences:")
                        if missing_in_mock:
                            print(f"    Missing in mock: {missing_in_mock}")
                        if extra_in_mock:
                            print(f"    Extra in mock: {extra_in_mock}")
                    else:
                        print(f"  ✅ {name}.json structure matches")
                elif isinstance(mock_data, list) and isinstance(real_data.get("data"), list):
                    if mock_data and real_data["data"]:
                        mock_keys = set(mock_data[0].keys()) if mock_data else set()
                        real_keys = set(real_data["data"][0].keys()) if real_data["data"] else set()
                        
                        missing_in_mock = real_keys - mock_keys
                        extra_in_mock = mock_keys - real_keys
                        
                        if missing_in_mock or extra_in_mock:
                            print(f"\n  ⚠️ {name}.json differences:")
                            if missing_in_mock:
                                print(f"    Missing in mock: {missing_in_mock}")
                            if extra_in_mock:
                                print(f"    Extra in mock: {extra_in_mock}")
                        else:
                            print(f"  ✅ {name}.json structure matches")
    
    async def run(self):
        """Run the complete capture process."""
        print("="*60)
        print("BACKPACK API RESPONSE CAPTURE TOOL")
        print("="*60)
        print(f"Timestamp: {self.captured_at}")
        print(f"Testnet: {self.testnet}")
        print("="*60)
        
        try:
            # Capture public endpoints
            await self.capture_public_endpoints()
            
            # Capture private endpoints
            await self.capture_private_endpoints()
            
            # Save all responses
            self.save_responses()
            
            # Compare with existing mock data
            self.compare_with_mock_data()
            
            print("\n✅ Capture complete!")
            print(f"📁 Responses saved to: {self.output_dir}")
            
        except Exception as e:
            print(f"\n❌ Capture failed: {e}")
            raise


async def main():
    """Main entry point."""
    # Get API credentials
    api_key = os.getenv("BACKPACK_API_KEY")
    api_secret = os.getenv("BACKPACK_API_SECRET")
    
    if not api_key or not api_secret:
        print("❌ Missing BACKPACK_API_KEY or BACKPACK_API_SECRET")
        print("Please set these environment variables or add them to .env")
        return
    
    # Create capture tool
    capture = BackpackResponseCapture(
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,  # Use mainnet for real data
    )
    
    # Run capture
    await capture.run()


if __name__ == "__main__":
    asyncio.run(main())