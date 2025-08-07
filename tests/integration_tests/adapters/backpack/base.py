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

"""Base test class for Backpack adapter with dual-mode support."""

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.core.nautilus_pyo3 import Quota

from .conftest import TestMode


class BackpackTestBase:
    """
    Base test class for Backpack adapter tests with dual-mode support.
    
    This class provides a foundation for tests that can run in either:
    - MOCK mode: Using mock clients and fixture data
    - LIVE mode: Using real API connections (with safety measures)
    - HYBRID mode: Using mock by default, live when specified
    """
    
    @classmethod
    def setup_class(cls):
        """Set up test class based on configured test mode."""
        cls.test_mode = TestMode(os.getenv("BACKPACK_TEST_MODE", "mock"))
        cls.clock = LiveClock()
        cls.logger = Logger(cls.__name__)
        
        # Set up clients based on test mode
        if cls.test_mode == TestMode.LIVE:
            cls.http_client = cls._create_live_http_client()
            cls.ws_client = cls._create_live_ws_client()
        else:
            cls.http_client = cls._create_mock_http_client()
            cls.ws_client = cls._create_mock_ws_client()
    
    @classmethod
    def _create_live_http_client(cls) -> BackpackHttpClient:
        """
        Create a live HTTP client with safety measures.
        
        Safety measures:
        - Uses testnet if available
        - Rate limiting configured
        - Requires test API keys from environment
        """
        api_key = os.getenv("BACKPACK_TEST_API_KEY")
        api_secret = os.getenv("BACKPACK_TEST_API_SECRET")
        
        if not api_key or not api_secret:
            pytest.skip("Live testing requires BACKPACK_TEST_API_KEY and BACKPACK_TEST_API_SECRET")
        
        # Rate limiting: 100 requests per minute for testing
        test_quota = Quota(
            rate=100,
            interval_ns=60_000_000_000,  # 60 seconds in nanoseconds
        )
        
        return BackpackHttpClient(
            clock=cls.clock,
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,  # Always use testnet for safety
            ratelimiter_default_quota=test_quota,
        )
    
    @classmethod
    def _create_live_ws_client(cls) -> BackpackWebSocketClient:
        """
        Create a live WebSocket client with safety measures.
        
        Safety measures:
        - Uses testnet if available
        - Configured with test credentials
        """
        api_key = os.getenv("BACKPACK_TEST_API_KEY")
        api_secret = os.getenv("BACKPACK_TEST_API_SECRET")
        
        if not api_key or not api_secret:
            pytest.skip("Live testing requires BACKPACK_TEST_API_KEY and BACKPACK_TEST_API_SECRET")
        
        return BackpackWebSocketClient(
            clock=cls.clock,
            api_key=api_key,
            api_secret=api_secret,
            testnet=True,  # Always use testnet for safety
        )
    
    @classmethod
    def _create_mock_http_client(cls) -> MagicMock:
        """Create a mock HTTP client for testing."""
        mock_client = MagicMock(spec=BackpackHttpClient)
        mock_client._request = AsyncMock()
        mock_client.get_markets = AsyncMock()
        mock_client.get_ticker = AsyncMock()
        mock_client.get_depth = AsyncMock()
        mock_client.get_trades = AsyncMock()
        mock_client.get_capital = AsyncMock()
        mock_client.get_orders = AsyncMock()
        mock_client.place_order = AsyncMock()
        mock_client.cancel_order = AsyncMock()
        return mock_client
    
    @classmethod
    def _create_mock_ws_client(cls) -> MagicMock:
        """Create a mock WebSocket client for testing."""
        mock_client = MagicMock(spec=BackpackWebSocketClient)
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.subscribe_depth = AsyncMock()
        mock_client.subscribe_trades = AsyncMock()
        mock_client.subscribe_ticker = AsyncMock()
        mock_client.subscribe_orders = AsyncMock()
        return mock_client
    
    def require_live_mode(self):
        """Skip test if not in live mode."""
        if self.test_mode != TestMode.LIVE:
            pytest.skip("Test requires LIVE mode")
    
    def require_mock_mode(self):
        """Skip test if not in mock mode."""
        if self.test_mode != TestMode.MOCK:
            pytest.skip("Test requires MOCK mode")
    
    @staticmethod
    def is_safe_test_order(price: float, market_price: float) -> bool:
        """
        Check if an order price is safe for testing.
        
        Parameters
        ----------
        price : float
            The order price
        market_price : float
            The current market price
        
        Returns
        -------
        bool
            True if the order is at least 10% away from market price
        """
        price_diff_pct = abs(price - market_price) / market_price * 100
        return price_diff_pct >= 10.0
    
    @staticmethod
    def get_safe_test_price(market_price: float, is_buy: bool) -> float:
        """
        Get a safe test price that's 10% away from market.
        
        Parameters
        ----------
        market_price : float
            The current market price
        is_buy : bool
            True for buy orders, False for sell orders
        
        Returns
        -------
        float
            A price that's 10% below market for buys, 10% above for sells
        """
        if is_buy:
            return market_price * 0.9  # 10% below market
        else:
            return market_price * 1.1  # 10% above market


# Test decorators for marking test requirements
def live_only(func):
    """Decorator to mark tests that should only run in LIVE mode."""
    return pytest.mark.skipif(
        os.getenv("BACKPACK_TEST_MODE", "mock") != "live",
        reason="Test requires LIVE mode",
    )(func)


def mock_only(func):
    """Decorator to mark tests that should only run in MOCK mode."""
    return pytest.mark.skipif(
        os.getenv("BACKPACK_TEST_MODE", "mock") != "mock",
        reason="Test requires MOCK mode",
    )(func)


def dual_mode(func):
    """Decorator to mark tests that can run in both MOCK and LIVE modes."""
    # No skip condition - test runs in all modes
    return func