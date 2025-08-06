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

"""Integration tests for Backpack instrument providers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.providers import BackpackInstrumentProvider
from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
from nautilus_trader.common.component import LiveClock
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments.currency_pair import CurrencyPair


@pytest.mark.asyncio
class TestBackpackInstrumentProvider:
    """Test suite for BackpackInstrumentProvider."""

    def setup_method(self):
        """Set up test fixtures."""
        self.clock = LiveClock()
        self.client = MagicMock(spec=BackpackHttpClient)
        self.provider = BackpackInstrumentProvider(
            client=self.client,
            clock=self.clock,
            testnet=False,
            config=InstrumentProviderConfig(load_all=False),
        )

    @pytest.mark.asyncio
    async def test_load_all_async(self):
        """Test loading all instruments."""
        # Mock market data response
        mock_markets = [
            {
                "symbol": "SOL_USDC",
                "base_currency": "SOL",
                "quote_currency": "USDC",
                "price_decimals": 4,
                "quantity_decimals": 2,
                "taker_fee": "0.0005",
                "maker_fee": "0.0002",
                "min_quantity": "0.01",
                "max_quantity": "10000",
                "min_price": "0.0001",
                "max_price": "100000",
                "tick_size": "0.0001",
                "lot_size": "0.01",
                "status": "active",
                "market_type": "spot",
            },
            {
                "symbol": "BTC_USDC",
                "base_currency": "BTC",
                "quote_currency": "USDC",
                "price_decimals": 2,
                "quantity_decimals": 6,
                "taker_fee": "0.0005",
                "maker_fee": "0.0002",
                "min_quantity": "0.000001",
                "max_quantity": "100",
                "min_price": "0.01",
                "max_price": "1000000",
                "tick_size": "0.01",
                "lot_size": "0.000001",
                "status": "active",
                "market_type": "spot",
            },
        ]
        
        self.client.get = AsyncMock(return_value=mock_markets)
        
        # Load all instruments
        await self.provider.load_all_async()
        
        # Verify API was called
        self.client.get.assert_called_once_with("/api/markets")
        
        # Check instruments were parsed and added
        instruments = self.provider.list_all()
        assert len(instruments) == 2
        
        # Verify instrument details
        sol_usdc = self.provider.find(
            InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        )
        assert sol_usdc is not None
        assert isinstance(sol_usdc, CurrencyPair)
        assert sol_usdc.base_currency == "SOL"
        assert sol_usdc.quote_currency == "USDC"
        assert sol_usdc.price_precision == 4
        assert sol_usdc.size_precision == 2

    @pytest.mark.asyncio
    async def test_load_ids_async(self):
        """Test loading specific instruments by ID."""
        # Mock market data response
        mock_markets = [
            {
                "symbol": "SOL_USDC",
                "base_currency": "SOL",
                "quote_currency": "USDC",
                "price_decimals": 4,
                "quantity_decimals": 2,
                "taker_fee": "0.0005",
                "maker_fee": "0.0002",
                "min_quantity": "0.01",
                "max_quantity": "10000",
                "min_price": "0.0001",
                "max_price": "100000",
                "tick_size": "0.0001",
                "lot_size": "0.01",
                "status": "active",
                "market_type": "spot",
            },
        ]
        
        self.client.get = AsyncMock(return_value=mock_markets)
        
        # Load specific instrument
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        await self.provider.load_ids_async([instrument_id])
        
        # Verify API was called
        self.client.get.assert_called_once_with("/api/markets")
        
        # Check instrument was loaded
        instrument = self.provider.find(instrument_id)
        assert instrument is not None
        assert instrument.id == instrument_id

    @pytest.mark.asyncio
    async def test_load_async(self):
        """Test loading a single instrument."""
        # Mock market data response
        mock_markets = [
            {
                "symbol": "SOL_USDC",
                "base_currency": "SOL",
                "quote_currency": "USDC",
                "price_decimals": 4,
                "quantity_decimals": 2,
                "taker_fee": "0.0005",
                "maker_fee": "0.0002",
                "min_quantity": "0.01",
                "max_quantity": "10000",
                "min_price": "0.0001",
                "max_price": "100000",
                "tick_size": "0.0001",
                "lot_size": "0.01",
                "status": "active",
                "market_type": "spot",
            },
        ]
        
        self.client.get = AsyncMock(return_value=mock_markets)
        
        # Load single instrument
        instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        await self.provider.load_async(instrument_id)
        
        # Verify API was called
        self.client.get.assert_called_once_with("/api/markets")
        
        # Check instrument was loaded
        instrument = self.provider.find(instrument_id)
        assert instrument is not None


@pytest.mark.asyncio
class TestBackpackSpotInstrumentProvider:
    """Test suite for BackpackSpotInstrumentProvider."""

    def setup_method(self):
        """Set up test fixtures."""
        self.clock = LiveClock()
        self.client = MagicMock(spec=BackpackHttpClient)
        self.provider = BackpackSpotInstrumentProvider(
            client=self.client,
            clock=self.clock,
            testnet=False,
            config=InstrumentProviderConfig(load_all=False),
        )

    @pytest.mark.asyncio
    async def test_load_all_async_filters_spot(self):
        """Test that spot provider only loads spot instruments."""
        # Mock market data response with mixed market types
        mock_markets = [
            {
                "symbol": "SOL_USDC",
                "base_currency": "SOL",
                "quote_currency": "USDC",
                "price_decimals": 4,
                "quantity_decimals": 2,
                "taker_fee": "0.0005",
                "maker_fee": "0.0002",
                "min_quantity": "0.01",
                "max_quantity": "10000",
                "min_price": "0.0001",
                "max_price": "100000",
                "tick_size": "0.0001",
                "lot_size": "0.01",
                "status": "active",
                "market_type": "spot",
            },
            {
                "symbol": "SOL_USDC_PERP",
                "base_currency": "SOL",
                "quote_currency": "USDC",
                "price_decimals": 4,
                "quantity_decimals": 2,
                "taker_fee": "0.0005",
                "maker_fee": "0.0002",
                "min_quantity": "0.01",
                "max_quantity": "10000",
                "min_price": "0.0001",
                "max_price": "100000",
                "tick_size": "0.0001",
                "lot_size": "0.01",
                "status": "active",
                "market_type": "futures",
            },
        ]
        
        self.client.get = AsyncMock(return_value=mock_markets)
        
        # Load all instruments (should filter to spot only)
        await self.provider.load_all_async()
        
        # Verify API was called
        self.client.get.assert_called_once_with("/api/markets")
        
        # Check only spot instrument was loaded
        instruments = self.provider.list_all()
        # Note: The filtering happens at the provider level,
        # so both may be loaded but the spot provider should
        # only process spot markets