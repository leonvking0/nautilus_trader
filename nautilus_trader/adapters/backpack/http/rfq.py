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
Backpack RFQ (Request for Quote) HTTP API client.

Handles large block trades through RFQ system.
"""

from decimal import Decimal
from typing import Any

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.rfq import BackpackRFQQuote
from nautilus_trader.adapters.backpack.schemas.rfq import BackpackRFQRequest
from nautilus_trader.adapters.backpack.schemas.rfq import BackpackRFQExecution


class BackpackRFQHttpAPI:
    """
    HTTP API client for Backpack RFQ operations.
    
    RFQ (Request for Quote) allows for large block trades with
    guaranteed prices and reduced slippage.
    """
    
    def __init__(self, client: BackpackHttpClient):
        """
        Initialize the RFQ HTTP API.
        
        Parameters
        ----------
        client : BackpackHttpClient
            The HTTP client for making requests.
        """
        self._client = client
    
    async def request_quote(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        quote_asset_quantity: Decimal | None = None,
    ) -> BackpackRFQRequest:
        """
        Request a quote for a large trade.
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        side : str
            BUY or SELL.
        quantity : Decimal
            The base asset quantity.
        quote_asset_quantity : Decimal, optional
            The quote asset quantity (for market-like RFQ).
        
        Returns
        -------
        BackpackRFQRequest
            The RFQ request with quote ID.
        """
        data = {
            "symbol": symbol,
            "side": side,
            "quantity": str(quantity),
        }
        
        if quote_asset_quantity:
            data["quoteAssetQuantity"] = str(quote_asset_quantity)
        
        response = await self._client._post(
            path="/api/v1/rfq/request",
            data=data,
            auth=True,
        )
        
        return BackpackRFQRequest.from_dict(response)
    
    async def get_quote(self, quote_id: str) -> BackpackRFQQuote:
        """
        Get details of a specific quote.
        
        Parameters
        ----------
        quote_id : str
            The quote ID.
        
        Returns
        -------
        BackpackRFQQuote
            The quote details.
        """
        response = await self._client._get(
            path=f"/api/v1/rfq/quotes/{quote_id}",
            auth=True,
        )
        
        return BackpackRFQQuote.from_dict(response)
    
    async def accept_quote(
        self,
        quote_id: str,
        client_order_id: str | None = None,
    ) -> BackpackRFQExecution:
        """
        Accept a quote and execute the trade.
        
        Parameters
        ----------
        quote_id : str
            The quote ID to accept.
        client_order_id : str, optional
            Custom client order ID.
        
        Returns
        -------
        BackpackRFQExecution
            The execution details.
        """
        data = {"quoteId": quote_id}
        
        if client_order_id:
            data["clientOrderId"] = client_order_id
        
        response = await self._client._post(
            path="/api/v1/rfq/accept",
            data=data,
            auth=True,
        )
        
        return BackpackRFQExecution.from_dict(response)
    
    async def reject_quote(self, quote_id: str) -> dict:
        """
        Reject a quote.
        
        Parameters
        ----------
        quote_id : str
            The quote ID to reject.
        
        Returns
        -------
        dict
            Rejection confirmation.
        """
        response = await self._client._post(
            path="/api/v1/rfq/reject",
            data={"quoteId": quote_id},
            auth=True,
        )
        
        return response
    
    async def refresh_quote(self, quote_id: str) -> BackpackRFQQuote:
        """
        Refresh an existing quote to get updated pricing.
        
        Parameters
        ----------
        quote_id : str
            The quote ID to refresh.
        
        Returns
        -------
        BackpackRFQQuote
            The refreshed quote.
        """
        response = await self._client._post(
            path="/api/v1/rfq/refresh",
            data={"quoteId": quote_id},
            auth=True,
        )
        
        return BackpackRFQQuote.from_dict(response)
    
    async def cancel_rfq(self, quote_id: str) -> dict:
        """
        Cancel an RFQ request.
        
        Parameters
        ----------
        quote_id : str
            The quote ID to cancel.
        
        Returns
        -------
        dict
            Cancellation confirmation.
        """
        response = await self._client._delete(
            path=f"/api/v1/rfq/quotes/{quote_id}",
            auth=True,
        )
        
        return response
    
    async def get_rfq_history(
        self,
        symbol: str | None = None,
        status: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BackpackRFQQuote]:
        """
        Get RFQ history.
        
        Parameters
        ----------
        symbol : str, optional
            Filter by symbol.
        status : str, optional
            Filter by status (PENDING, ACCEPTED, REJECTED, EXPIRED, CANCELLED).
        start_time : int, optional
            Start time in milliseconds.
        end_time : int, optional
            End time in milliseconds.
        limit : int, default 100
            Maximum number of records.
        offset : int, default 0
            Pagination offset.
        
        Returns
        -------
        list[BackpackRFQQuote]
            List of historical RFQ quotes.
        """
        params = {
            "limit": limit,
            "offset": offset,
        }
        
        if symbol:
            params["symbol"] = symbol
        if status:
            params["status"] = status
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        response = await self._client._get(
            path="/api/v1/rfq/history",
            params=params,
            auth=True,
        )
        
        return [BackpackRFQQuote.from_dict(q) for q in response]
    
    async def get_rfq_limits(self) -> dict:
        """
        Get RFQ trading limits and requirements.
        
        Returns
        -------
        dict
            RFQ limits and requirements.
        """
        response = await self._client._get(
            path="/api/v1/rfq/limits",
            auth=True,
        )
        
        return response
    
    async def get_active_quotes(self) -> list[BackpackRFQQuote]:
        """
        Get all active quotes.
        
        Returns
        -------
        list[BackpackRFQQuote]
            List of active quotes.
        """
        response = await self._client._get(
            path="/api/v1/rfq/active",
            auth=True,
        )
        
        return [BackpackRFQQuote.from_dict(q) for q in response]