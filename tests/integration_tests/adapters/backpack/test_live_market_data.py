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

"""Live market data validation tests for Backpack adapter."""

import asyncio
import time
from decimal import Decimal

import pytest

from .base import BackpackTestBase, live_only, dual_mode


class TestBackpackLiveMarketData(BackpackTestBase):
    """Test cases for validating market data against live Backpack API."""
    
    @live_only
    @pytest.mark.asyncio
    async def test_market_data_accuracy(self):
        """Validate market data accuracy against live API."""
        self.require_live_mode()
        
        # Fetch market data from multiple endpoints
        markets = await self.http_client.get_markets()
        ticker = await self.http_client.get_ticker("SOL_USDC")
        depth = await self.http_client.get_depth("SOL_USDC")
        trades = await self.http_client.get_trades("SOL_USDC")
        
        # Validate markets response
        assert isinstance(markets, list), "Markets should be a list"
        assert len(markets) > 0, "Should have at least one market"
        
        sol_market = next((m for m in markets if m["symbol"] == "SOL_USDC"), None)
        assert sol_market is not None, "SOL_USDC market should exist"
        assert "baseSymbol" in sol_market
        assert "quoteSymbol" in sol_market
        assert "filters" in sol_market
        
        # Validate ticker response
        assert isinstance(ticker, dict), "Ticker should be a dict"
        assert ticker["symbol"] == "SOL_USDC"
        assert "lastPrice" in ticker
        assert "volume" in ticker
        assert "high" in ticker
        assert "low" in ticker
        
        # Validate depth response
        assert isinstance(depth, dict), "Depth should be a dict"
        assert "bids" in depth
        assert "asks" in depth
        assert len(depth["bids"]) > 0, "Should have bid levels"
        assert len(depth["asks"]) > 0, "Should have ask levels"
        
        # Validate bid/ask spread
        best_bid = Decimal(depth["bids"][0][0])
        best_ask = Decimal(depth["asks"][0][0])
        spread = best_ask - best_bid
        assert spread > 0, "Spread should be positive"
        assert spread / best_bid < Decimal("0.01"), "Spread should be < 1%"
        
        # Validate trades response
        assert isinstance(trades, list), "Trades should be a list"
        if trades:  # May be empty outside trading hours
            trade = trades[0]
            assert "price" in trade
            assert "quantity" in trade
            assert "timestamp" in trade
            assert "isBuyerMaker" in trade
    
    @dual_mode
    @pytest.mark.asyncio
    async def test_ticker_consistency(self):
        """Test that ticker data is internally consistent."""
        if self.test_mode.value == "mock":
            # Use mock data
            ticker = {
                "symbol": "SOL_USDC",
                "lastPrice": "168.52",
                "high": "169.94",
                "low": "161.20",
                "volume": "168140.32",
            }
        else:
            # Use live data
            ticker = await self.http_client.get_ticker("SOL_USDC")
        
        # Validate ticker consistency
        last_price = Decimal(ticker["lastPrice"])
        high = Decimal(ticker["high"])
        low = Decimal(ticker["low"])
        
        assert low <= last_price <= high, "Last price should be between high and low"
        assert low < high, "Low should be less than high"
        assert Decimal(ticker["volume"]) >= 0, "Volume should be non-negative"
    
    @dual_mode
    @pytest.mark.asyncio
    async def test_orderbook_integrity(self):
        """Test orderbook data integrity and ordering."""
        if self.test_mode.value == "mock":
            # Use mock orderbook from fixtures
            from .conftest import load_fixture
            from pathlib import Path
            responses_dir = Path(__file__).parent / "resources" / "http_responses"
            depth = load_fixture(responses_dir / "orderbook.json")
        else:
            # Use live data
            depth = await self.http_client.get_depth("SOL_USDC")
        
        # Check bid prices are descending
        bids = depth["bids"]
        for i in range(1, min(len(bids), 10)):
            assert Decimal(bids[i][0]) < Decimal(bids[i-1][0]), \
                f"Bid prices should be descending: {bids[i][0]} >= {bids[i-1][0]}"
        
        # Check ask prices are ascending
        asks = depth["asks"]
        for i in range(1, min(len(asks), 10)):
            assert Decimal(asks[i][0]) > Decimal(asks[i-1][0]), \
                f"Ask prices should be ascending: {asks[i][0]} <= {asks[i-1][0]}"
        
        # Check bid/ask spread
        if bids and asks:
            best_bid = Decimal(bids[0][0])
            best_ask = Decimal(asks[0][0])
            assert best_bid < best_ask, "Best bid should be less than best ask"
    
    @live_only
    @pytest.mark.asyncio
    async def test_trades_chronological_order(self):
        """Test that trades are returned in chronological order."""
        self.require_live_mode()
        
        trades = await self.http_client.get_trades("SOL_USDC", limit=20)
        
        if len(trades) > 1:
            # Check trades are ordered by timestamp (most recent first)
            for i in range(1, len(trades)):
                assert trades[i]["timestamp"] <= trades[i-1]["timestamp"], \
                    "Trades should be ordered by timestamp (most recent first)"
    
    @live_only
    @pytest.mark.asyncio
    async def test_multiple_symbols_consistency(self):
        """Test data consistency across multiple symbols."""
        self.require_live_mode()
        
        symbols = ["SOL_USDC", "BTC_USDC", "ETH_USDC"]
        results = {}
        
        for symbol in symbols:
            try:
                ticker = await self.http_client.get_ticker(symbol)
                depth = await self.http_client.get_depth(symbol)
                
                results[symbol] = {
                    "ticker": ticker,
                    "depth": depth,
                }
            except Exception as e:
                # Some symbols might not be available
                print(f"Failed to get data for {symbol}: {e}")
                continue
        
        # Validate at least one symbol worked
        assert len(results) > 0, "Should get data for at least one symbol"
        
        # Validate data structure consistency across symbols
        for symbol, data in results.items():
            ticker = data["ticker"]
            depth = data["depth"]
            
            # All tickers should have same structure
            assert "lastPrice" in ticker
            assert "volume" in ticker
            
            # All orderbooks should have same structure
            assert "bids" in depth
            assert "asks" in depth
    
    @live_only
    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test that rate limiting is properly handled."""
        self.require_live_mode()
        
        # Make rapid requests to test rate limiting
        requests = []
        for i in range(10):
            requests.append(self.http_client.get_ticker("SOL_USDC"))
        
        # Should complete without errors due to rate limiting in client
        results = await asyncio.gather(*requests, return_exceptions=True)
        
        # Check that all requests succeeded or were rate limited gracefully
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Rate limiting not handled properly: {errors}"
    
    @dual_mode
    @pytest.mark.asyncio
    async def test_market_filters_validation(self):
        """Test that market filters are properly structured."""
        if self.test_mode.value == "mock":
            from .conftest import load_fixture
            from pathlib import Path
            responses_dir = Path(__file__).parent / "resources" / "http_responses"
            markets = load_fixture(responses_dir / "markets.json")
        else:
            markets = await self.http_client.get_markets()
        
        # Get first market
        market = markets[0] if isinstance(markets, list) else markets["data"][0]
        
        # Validate filter structure
        assert "filters" in market
        filters = market["filters"]
        
        # Price filter validation
        assert "price" in filters
        price_filter = filters["price"]
        assert "tickSize" in price_filter
        assert "minPrice" in price_filter
        
        # Quantity filter validation
        assert "quantity" in filters
        qty_filter = filters["quantity"]
        assert "stepSize" in qty_filter
        assert "minQuantity" in qty_filter
        
        # Validate filter values are numeric and positive
        tick_size = Decimal(price_filter["tickSize"])
        step_size = Decimal(qty_filter["stepSize"])
        min_qty = Decimal(qty_filter["minQuantity"])
        
        assert tick_size > 0, "Tick size should be positive"
        assert step_size > 0, "Step size should be positive"
        assert min_qty > 0, "Min quantity should be positive"