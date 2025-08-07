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
Historical data HTTP API endpoints for Backpack Exchange.

This module provides access to:
- Historical klines/candles
- Historical trades
- Order history
- Fill history
- PnL history
- Funding payment history
- Interest payment history
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import msgspec

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_INSTRUCTIONS


if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient


class BackpackHistoryHttpAPI:
    """
    Provides access to Backpack historical data HTTP endpoints.
    
    Parameters
    ----------
    client : BackpackHttpClient
        The Backpack HTTP client.
    """

    def __init__(self, client: BackpackHttpClient) -> None:
        """Initialize the BackpackHistoryHttpAPI."""
        self._client = client

    async def fetch_klines_history(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[list[Any]]:
        """
        Fetch historical klines (candlesticks) with pagination support.
        
        GET /api/v1/klines
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol (e.g., 'BTC_USDC').
        interval : str
            The kline interval (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M).
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 1000
            Maximum number of klines to return (max 1000).
            
        Returns
        -------
        list[list[Any]]
            List of klines in format:
            [timestamp, open, high, low, close, volume, close_time, 
             quote_volume, trades_count, taker_buy_volume, taker_buy_quote_volume]
        
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": str(limit),
        }
        if start_time:
            # Backpack API expects timestamps in seconds, not milliseconds
            # If timestamp appears to be in milliseconds (> year 2100 in seconds), convert it
            if start_time > 4102444800:  # Jan 1, 2100 in seconds
                params["startTime"] = str(start_time // 1000)
            else:
                params["startTime"] = str(start_time)
        if end_time:
            # Same conversion for end_time
            if end_time > 4102444800:
                params["endTime"] = str(end_time // 1000)
            else:
                params["endTime"] = str(end_time)
        
        # _get already returns decoded JSON
        return await self._client._get(
            path="/api/v1/klines",
            params=params,
        )

    async def fetch_trades_history(
        self,
        symbol: str,
        from_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Fetch historical trades.
        
        GET /api/v1/trades/history
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        from_id : int, optional
            Trade ID to fetch from (exclusive).
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 1000
            Maximum number of trades to return.
            
        Returns
        -------
        list[dict[str, Any]]
            List of historical trades.
        
        """
        params = {"symbol": symbol, "limit": str(limit)}
        if from_id:
            params["fromId"] = str(from_id)
        if start_time:
            params["startTime"] = str(start_time)
        if end_time:
            params["endTime"] = str(end_time)
        
        raw = await self._client._get(
            path="/api/v1/trades/history",
            params=params,
        )
        return msgspec.json.decode(raw)

    async def fetch_order_history(
        self,
        symbol: str | None = None,
        order_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Fetch order history.
        
        GET /wapi/v1/history/orders
        
        Requires signing with instruction: orderHistoryQueryAll
        
        Parameters
        ----------
        symbol : str, optional
            Filter by trading pair symbol.
        order_id : int, optional
            Filter by specific order ID.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of orders to return.
        offset : int, default 0
            Pagination offset.
            
        Returns
        -------
        list[dict[str, Any]]
            List of historical orders.
        
        """
        params = {"limit": str(limit), "offset": str(offset)}
        if symbol:
            params["symbol"] = symbol
        if order_id:
            params["orderId"] = str(order_id)
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/orders",
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["order_history_query_all"],
        )
        return msgspec.json.decode(raw)

    async def fetch_fill_history(
        self,
        symbol: str | None = None,
        order_id: int | None = None,
        fill_type: str | None = None,
        market_type: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Fetch fill/trade history.
        
        GET /wapi/v1/history/fills
        
        Requires signing with instruction: fillHistoryQueryAll
        
        Parameters
        ----------
        symbol : str, optional
            Filter by trading pair symbol.
        order_id : int, optional
            Filter by order ID.
        fill_type : str, optional
            Filter by fill type ('User', 'Liquidation', 'ADL', 'Settlement').
        market_type : str, optional
            Filter by market type ('Spot', 'Perpetual').
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of fills to return.
        offset : int, default 0
            Pagination offset.
            
        Returns
        -------
        list[dict[str, Any]]
            List of historical fills.
        
        """
        params = {"limit": str(limit), "offset": str(offset)}
        if symbol:
            params["symbol"] = symbol
        if order_id:
            params["orderId"] = str(order_id)
        if fill_type:
            params["fillType"] = fill_type
        if market_type:
            params["marketType"] = market_type
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/fills",
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["fill_history_query_all"],
        )
        return msgspec.json.decode(raw)

    async def fetch_pnl_history(
        self,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Fetch PnL history.
        
        GET /wapi/v1/history/pnl
        
        Requires signing with instruction: pnlHistoryQueryAll
        
        Parameters
        ----------
        symbol : str, optional
            Filter by trading pair symbol.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of PnL records to return.
        offset : int, default 0
            Pagination offset.
            
        Returns
        -------
        list[dict[str, Any]]
            List of PnL history records.
        
        """
        params = {"limit": str(limit), "offset": str(offset)}
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/pnl",
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["pnl_history_query_all"],
        )
        return msgspec.json.decode(raw)

    async def fetch_funding_history(
        self,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Fetch funding payment history.
        
        GET /wapi/v1/history/funding
        
        Requires signing with instruction: fundingHistoryQueryAll
        
        Parameters
        ----------
        symbol : str, optional
            Filter by perpetual symbol.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of funding records to return.
        offset : int, default 0
            Pagination offset.
            
        Returns
        -------
        list[dict[str, Any]]
            List of funding payment history.
        
        """
        params = {"limit": str(limit), "offset": str(offset)}
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/funding",
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["funding_history_query_all"],
        )
        return msgspec.json.decode(raw)

    async def fetch_interest_history(
        self,
        asset: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Fetch interest payment history.
        
        GET /wapi/v1/history/interest
        
        Requires signing with instruction: interestHistoryQueryAll
        
        Parameters
        ----------
        asset : str, optional
            Filter by asset (e.g., 'USDC', 'BTC').
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of interest records to return.
        offset : int, default 0
            Pagination offset.
            
        Returns
        -------
        list[dict[str, Any]]
            List of interest payment history.
        
        """
        params = {"limit": str(limit), "offset": str(offset)}
        if asset:
            params["asset"] = asset
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/interest",
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["interest_history_query_all"],
        )
        return msgspec.json.decode(raw)

    async def fetch_dust_history(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Fetch dust conversion history.
        
        GET /wapi/v1/history/dust
        
        Requires signing
        
        Parameters
        ----------
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of dust records to return.
        offset : int, default 0
            Pagination offset.
            
        Returns
        -------
        list[dict[str, Any]]
            List of dust conversion history.
        
        """
        params = {"limit": str(limit), "offset": str(offset)}
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/dust",
            params=params,
            auth=True,
            instruction="dustHistoryQueryAll",
        )
        return msgspec.json.decode(raw)

    async def fetch_all_historical_data(
        self,
        symbol: str,
        data_types: list[str] | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict[str, Any]:
        """
        Fetch all available historical data for a symbol.
        
        This is a convenience method that fetches multiple types
        of historical data in parallel.
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        data_types : list[str], optional
            Types of data to fetch. Options: 'orders', 'fills', 'pnl', 
            'funding', 'interest'. If None, fetches all.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
            
        Returns
        -------
        dict[str, Any]
            Dictionary with keys for each data type and their results.
        
        """
        import asyncio
        
        if data_types is None:
            data_types = ['orders', 'fills', 'pnl', 'funding', 'interest']
        
        tasks = {}
        
        if 'orders' in data_types:
            tasks['orders'] = self.fetch_order_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
            )
        
        if 'fills' in data_types:
            tasks['fills'] = self.fetch_fill_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
            )
        
        if 'pnl' in data_types:
            tasks['pnl'] = self.fetch_pnl_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
            )
        
        if 'funding' in data_types:
            tasks['funding'] = self.fetch_funding_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
            )
        
        if 'interest' in data_types:
            tasks['interest'] = self.fetch_interest_history(
                start_time=start_time,
                end_time=end_time,
            )
        
        # Execute all tasks in parallel
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # Map results back to their types
        return dict(zip(tasks.keys(), results))