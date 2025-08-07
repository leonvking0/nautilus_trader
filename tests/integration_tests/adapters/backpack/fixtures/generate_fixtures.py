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
Generate fixture data from live Backpack API for testing.

This script fetches real data samples from Backpack Exchange and saves them
as JSON fixtures for use in tests.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.http.history import BackpackHistoryHttpAPI
from nautilus_trader.common.component import LiveClock


# Load environment variables
load_dotenv()


class BackpackFixtureGenerator:
    """Generate test fixtures from live Backpack data."""
    
    def __init__(self):
        """Initialize the fixture generator."""
        self.api_key = os.getenv("BACKPACK_API_KEY")
        self.api_secret = os.getenv("BACKPACK_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError("Missing BACKPACK_API_KEY or BACKPACK_API_SECRET in .env file")
        
        # Setup paths
        self.fixtures_dir = Path(__file__).parent
        self.fixtures_dir.mkdir(exist_ok=True)
        
        # Initialize clock
        self.clock = LiveClock()
        
        # Initialize HTTP client
        self.http_client = BackpackHttpClient(
            clock=self.clock,
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=False,  # Use mainnet for real data
        )
        
        # Initialize API clients
        self.history_api = BackpackHistoryHttpAPI(self.http_client)
    
    async def generate_klines_fixture(self) -> Dict[str, Any]:
        """Fetch and save kline data."""
        print("Fetching klines data...")
        
        # Fetch klines for multiple symbols and intervals
        fixtures = {}
        
        # BTC_USDC 1h klines
        btc_1h = await self.history_api.fetch_klines_history(
            symbol="BTC_USDC",
            interval="1h",
            limit=100,
        )
        fixtures["BTC_USDC_1h"] = btc_1h
        
        # SOL_USDC 5m klines
        sol_5m = await self.history_api.fetch_klines_history(
            symbol="SOL_USDC",
            interval="5m",
            limit=100,
        )
        fixtures["SOL_USDC_5m"] = sol_5m
        
        # ETH_USDC 1d klines
        eth_1d = await self.history_api.fetch_klines_history(
            symbol="ETH_USDC",
            interval="1d",
            limit=30,
        )
        fixtures["ETH_USDC_1d"] = eth_1d
        
        # Save to file
        output_path = self.fixtures_dir / "sample_klines.json"
        with open(output_path, "w") as f:
            json.dump(fixtures, f, indent=2)
        
        print(f"Saved klines fixture to {output_path}")
        return fixtures
    
    async def generate_trades_fixture(self) -> Dict[str, Any]:
        """Fetch and save trade data."""
        print("Fetching trades data...")
        
        fixtures = {}
        
        # Recent trades for multiple symbols
        btc_trades = await self.http_client.fetch_trades(
            symbol="BTC_USDC",
            limit=100,
        )
        fixtures["BTC_USDC"] = btc_trades
        
        sol_trades = await self.http_client.fetch_trades(
            symbol="SOL_USDC",
            limit=100,
        )
        fixtures["SOL_USDC"] = sol_trades
        
        # Save to file
        output_path = self.fixtures_dir / "sample_trades.json"
        with open(output_path, "w") as f:
            json.dump(fixtures, f, indent=2)
        
        print(f"Saved trades fixture to {output_path}")
        return fixtures
    
    async def generate_orderbook_fixture(self) -> Dict[str, Any]:
        """Fetch and save order book data."""
        print("Fetching order book data...")
        
        fixtures = {}
        
        # Order book snapshots
        btc_book = await self.http_client.fetch_order_book(
            symbol="BTC_USDC",
        )
        fixtures["BTC_USDC"] = btc_book
        
        sol_book = await self.http_client.fetch_order_book(
            symbol="SOL_USDC",
        )
        fixtures["SOL_USDC"] = sol_book
        
        # Save to file
        output_path = self.fixtures_dir / "sample_orderbook.json"
        with open(output_path, "w") as f:
            json.dump(fixtures, f, indent=2)
        
        print(f"Saved order book fixture to {output_path}")
        return fixtures
    
    async def generate_ticker_fixture(self) -> Dict[str, Any]:
        """Fetch and save ticker data."""
        print("Fetching ticker data...")
        
        # Get 24hr tickers
        tickers = await self.http_client.fetch_tickers()
        
        # Filter for test symbols
        test_symbols = ["BTC_USDC", "SOL_USDC", "ETH_USDC"]
        fixtures = {
            ticker["symbol"]: ticker 
            for ticker in tickers 
            if ticker.get("symbol") in test_symbols
        }
        
        # Save to file
        output_path = self.fixtures_dir / "sample_tickers.json"
        with open(output_path, "w") as f:
            json.dump(fixtures, f, indent=2)
        
        print(f"Saved ticker fixture to {output_path}")
        return fixtures
    
    async def generate_historical_fixtures(self) -> Dict[str, Any]:
        """Fetch and save historical data (orders, fills, PnL)."""
        print("Fetching historical data...")
        
        fixtures = {}
        
        try:
            # Try to fetch order history
            orders = await self.history_api.fetch_order_history(
                limit=50,
            )
            fixtures["orders"] = orders
        except Exception as e:
            print(f"Could not fetch order history: {e}")
            fixtures["orders"] = []
        
        try:
            # Try to fetch fill history
            fills = await self.history_api.fetch_fill_history(
                limit=50,
            )
            fixtures["fills"] = fills
        except Exception as e:
            print(f"Could not fetch fill history: {e}")
            fixtures["fills"] = []
        
        try:
            # Try to fetch PnL history
            pnl = await self.history_api.fetch_pnl_history(
                start_time=int((datetime.now() - timedelta(days=30)).timestamp() * 1000),
            )
            fixtures["pnl"] = pnl
        except Exception as e:
            print(f"Could not fetch PnL history: {e}")
            fixtures["pnl"] = []
        
        # Save to file
        output_path = self.fixtures_dir / "sample_historical.json"
        with open(output_path, "w") as f:
            json.dump(fixtures, f, indent=2)
        
        print(f"Saved historical fixture to {output_path}")
        return fixtures
    
    async def generate_all_fixtures(self):
        """Generate all fixture files."""
        print("Starting fixture generation...")
        print(f"Using API key: {self.api_key[:8]}...")
        
        try:
            # Generate all fixtures
            await self.generate_klines_fixture()
            await asyncio.sleep(0.5)  # Rate limit protection
            
            await self.generate_trades_fixture()
            await asyncio.sleep(0.5)
            
            await self.generate_orderbook_fixture()
            await asyncio.sleep(0.5)
            
            await self.generate_ticker_fixture()
            await asyncio.sleep(0.5)
            
            await self.generate_historical_fixtures()
            
            print("\n✅ All fixtures generated successfully!")
            print(f"Fixtures saved to: {self.fixtures_dir}")
            
        except Exception as e:
            print(f"\n❌ Error generating fixtures: {e}")
            raise
    
    async def validate_fixtures(self):
        """Validate that all fixture files exist and are valid JSON."""
        expected_files = [
            "sample_klines.json",
            "sample_trades.json",
            "sample_orderbook.json",
            "sample_tickers.json",
            "sample_historical.json",
        ]
        
        print("\nValidating fixtures...")
        all_valid = True
        
        for filename in expected_files:
            filepath = self.fixtures_dir / filename
            if not filepath.exists():
                print(f"❌ Missing: {filename}")
                all_valid = False
                continue
            
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    if data:
                        print(f"✅ Valid: {filename} ({len(str(data))} bytes)")
                    else:
                        print(f"⚠️  Empty: {filename}")
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON in {filename}: {e}")
                all_valid = False
        
        return all_valid


async def main():
    """Main entry point."""
    generator = BackpackFixtureGenerator()
    
    # Generate all fixtures
    await generator.generate_all_fixtures()
    
    # Validate fixtures
    if await generator.validate_fixtures():
        print("\n✅ All fixtures are valid and ready for testing!")
    else:
        print("\n⚠️  Some fixtures may need manual review")


if __name__ == "__main__":
    asyncio.run(main())