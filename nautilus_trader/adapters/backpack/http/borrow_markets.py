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
Backpack Exchange borrow/lend markets HTTP API endpoints.
"""

import msgspec

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.borrow_markets import BackpackBorrowMarket
from nautilus_trader.adapters.backpack.schemas.borrow_markets import BackpackBorrowMarketHistory
from nautilus_trader.adapters.backpack.schemas.borrow_markets import BackpackBorrowRates


class BackpackBorrowMarketsHttpAPI:
    """
    Provides access to Backpack borrow/lend markets HTTP REST API.
    
    Parameters
    ----------
    client : BackpackHttpClient
        The Backpack HTTP client.
    """
    
    def __init__(self, client: BackpackHttpClient) -> None:
        self._client = client
        
        # Response decoders
        self._decoder_markets = msgspec.json.Decoder(list[BackpackBorrowMarket])
        self._decoder_market = msgspec.json.Decoder(BackpackBorrowMarket)
        self._decoder_rates = msgspec.json.Decoder(BackpackBorrowRates)
        self._decoder_history = msgspec.json.Decoder(list[BackpackBorrowMarketHistory])
    
    async def fetch_borrow_markets(self) -> list[BackpackBorrowMarket]:
        """
        Fetch all borrow/lend markets.
        
        GET /api/v1/borrowLend/markets
        
        Returns
        -------
        list[BackpackBorrowMarket]
            The available borrow/lend markets.
        """
        raw = await self._client._get(
            path="/api/v1/borrowLend/markets",
            params={},
            auth=False,
        )
        return self._decoder_markets.decode(raw)
    
    async def fetch_borrow_market(self, asset: str) -> BackpackBorrowMarket:
        """
        Fetch specific borrow/lend market info.
        
        GET /api/v1/borrowLend/markets/{asset}
        
        Parameters
        ----------
        asset : str
            The asset symbol.
            
        Returns
        -------
        BackpackBorrowMarket
            The borrow/lend market information.
        """
        raw = await self._client._get(
            path=f"/api/v1/borrowLend/markets/{asset}",
            params={},
            auth=False,
        )
        return self._decoder_market.decode(raw)
    
    async def fetch_borrow_rates(self) -> BackpackBorrowRates:
        """
        Fetch current borrow rates for all assets.
        
        GET /api/v1/borrowLend/rates
        
        Returns
        -------
        BackpackBorrowRates
            The current borrow rates.
        """
        raw = await self._client._get(
            path="/api/v1/borrowLend/rates",
            params={},
            auth=False,
        )
        return self._decoder_rates.decode(raw)
    
    async def fetch_borrow_market_history(
        self,
        asset: str,
        interval: str = "1h",
        limit: int = 24,
    ) -> list[BackpackBorrowMarketHistory]:
        """
        Fetch historical borrow market data.
        
        GET /api/v1/borrowLend/markets/history
        
        Parameters
        ----------
        asset : str
            The asset symbol.
        interval : str, default "1h"
            Time interval (1h, 4h, 1d).
        limit : int, default 24
            Number of data points.
            
        Returns
        -------
        list[BackpackBorrowMarketHistory]
            The historical market data.
        """
        params = {
            "asset": asset,
            "interval": interval,
            "limit": str(limit),
        }
        
        raw = await self._client._get(
            path="/api/v1/borrowLend/markets/history",
            params=params,
            auth=False,
        )
        return self._decoder_history.decode(raw)
    
    async def fetch_max_borrowable(
        self,
        asset: str,
    ) -> dict:
        """
        Fetch maximum borrowable amount for an asset.
        
        GET /api/v1/borrowLend/maxBorrowable
        
        Parameters
        ----------
        asset : str
            The asset to check.
            
        Returns
        -------
        dict
            The maximum borrowable information.
        """
        params = {"asset": asset}
        
        raw = await self._client._get(
            path="/api/v1/borrowLend/maxBorrowable",
            params=params,
            auth=True,
            instruction="borrowLendQuery",
        )
        return msgspec.json.decode(raw)
    
    async def fetch_lending_pool_info(self) -> dict:
        """
        Fetch lending pool statistics.
        
        GET /api/v1/borrowLend/pool
        
        Returns
        -------
        dict
            The lending pool information.
        """
        raw = await self._client._get(
            path="/api/v1/borrowLend/pool",
            params={},
            auth=False,
        )
        return msgspec.json.decode(raw)