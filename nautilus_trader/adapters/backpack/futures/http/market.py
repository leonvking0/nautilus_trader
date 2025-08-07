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
Backpack Exchange futures market HTTP API.
"""

import msgspec

from nautilus_trader.adapters.backpack.futures.schemas.market import BackpackFundingRate
from nautilus_trader.adapters.backpack.futures.schemas.market import BackpackMarkPrice
from nautilus_trader.adapters.backpack.futures.schemas.market import BackpackOpenInterest
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient


class BackpackFuturesMarketHttpAPI:
    """
    Provides access to Backpack futures market HTTP REST API.
    
    Parameters
    ----------
    client : BackpackHttpClient
        The Backpack HTTP client.
    """
    
    def __init__(self, client: BackpackHttpClient) -> None:
        self._client = client
        
        # Response decoders
        self._decoder_mark_prices = msgspec.json.Decoder(list[BackpackMarkPrice])
        self._decoder_mark_price = msgspec.json.Decoder(BackpackMarkPrice)
        self._decoder_funding_rates = msgspec.json.Decoder(list[BackpackFundingRate])
        self._decoder_open_interest = msgspec.json.Decoder(list[BackpackOpenInterest])
    
    async def fetch_mark_prices(self, symbol: str | None = None) -> list[BackpackMarkPrice]:
        """
        Fetch mark prices for futures markets.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch mark price for. If None, fetches all.
            
        Returns
        -------
        list[BackpackMarkPrice]
            The mark price data.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        raw = await self._client._get("/api/v1/markPrices", params)
        
        if symbol:
            # Single mark price response
            mark_price = self._decoder_mark_price.decode(raw)
            return [mark_price]
        else:
            # Multiple mark prices
            return self._decoder_mark_prices.decode(raw)
    
    async def fetch_funding_rates(self, symbol: str | None = None) -> list[BackpackFundingRate]:
        """
        Fetch funding rates for futures markets.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch funding rate for. If None, fetches all.
            
        Returns
        -------
        list[BackpackFundingRate]
            The funding rate data.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        raw = await self._client._get("/api/v1/fundingRates", params)
        return self._decoder_funding_rates.decode(raw)
    
    async def fetch_open_interest(self, symbol: str | None = None) -> list[BackpackOpenInterest]:
        """
        Fetch open interest for futures markets.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch open interest for. If None, fetches all.
            
        Returns
        -------
        list[BackpackOpenInterest]
            The open interest data.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        raw = await self._client._get("/api/v1/openInterest", params)
        return self._decoder_open_interest.decode(raw)