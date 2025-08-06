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

"""HTTP client for Backpack exchange."""

import base64
import json
from typing import Any

import msgspec

import nautilus_trader
from nautilus_trader.adapters.backpack.common.auth import sign_batch_order_request
from nautilus_trader.adapters.backpack.common.auth import sign_request
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_API_PATHS
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_BASE_URL_PROD
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_DEFAULT_WINDOW
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_INSTRUCTIONS
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_RETRY_ERRORS
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import Logger
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core.nautilus_pyo3 import HttpClient
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from nautilus_trader.core.nautilus_pyo3 import HttpResponse
from nautilus_trader.core.nautilus_pyo3 import Quota


class BackpackHttpClient:
    """
    Provides a Backpack asynchronous HTTP client.

    Parameters
    ----------
    clock : LiveClock
        The clock for the client.
    api_key : str
        The Backpack API key (base64 encoded public key).
    api_secret : str
        The Backpack API secret (base64 encoded private key).
    base_url : str, optional
        The base endpoint URL for the client.
    testnet : bool, default False
        Whether to use testnet environment.
    ratelimiter_quotas : list[tuple[str, Quota]], optional
        The keyed rate limiter quotas for the client.
    ratelimiter_default_quota : Quota, optional
        The default rate limiter quota for the client.

    """

    def __init__(
        self,
        clock: LiveClock,
        api_key: str,
        api_secret: str,
        base_url: str | None = None,
        testnet: bool = False,
        ratelimiter_quotas: list[tuple[str, Quota]] | None = None,
        ratelimiter_default_quota: Quota | None = None,
    ) -> None:
        self._clock = clock
        self._log = Logger(type(self).__name__)
        
        # API credentials
        self._api_key = api_key
        # Decode the base64 encoded private key to get the raw 32 bytes
        self._private_key = base64.b64decode(api_secret)
        if len(self._private_key) != 32:
            # If it's longer, it might be in ASN.1/DER format, extract the last 32 bytes
            if len(self._private_key) > 32:
                self._private_key = self._private_key[-32:]
            else:
                raise ValueError(f"Invalid private key length: {len(self._private_key)}, expected 32 bytes")
        
        # Base URL
        self._base_url = base_url or BACKPACK_BASE_URL_PROD
        self._testnet = testnet
        
        # Default headers
        self._headers = {
            "Content-Type": "application/json",
            "User-Agent": nautilus_trader.NAUTILUS_USER_AGENT,
            "X-API-Key": api_key,
        }
        
        # HTTP client
        self._client = HttpClient(
            keyed_quotas=ratelimiter_quotas or [],
            default_quota=ratelimiter_default_quota,
        )
        
        self._decoder = msgspec.json.Decoder()
        self._encoder = msgspec.json.Encoder()

    async def _request(
        self,
        method: HttpMethod,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | list[dict[str, Any]] | None = None,
        auth: bool = False,
        instruction: str | None = None,
    ) -> Any:
        """
        Send an HTTP request to Backpack API.

        Parameters
        ----------
        method : HttpMethod
            The HTTP method.
        path : str
            The API endpoint path.
        params : dict[str, Any], optional
            Query parameters.
        data : dict[str, Any] or list[dict[str, Any]], optional
            Request body data.
        auth : bool, default False
            Whether the request requires authentication.
        instruction : str, optional
            The instruction type for signing.

        Returns
        -------
        Any
            The response data.

        """
        # Build URL with query parameters
        url = f"{self._base_url}{path}"
        if params:
            from urllib.parse import urlencode
            query_string = urlencode(params)
            url = f"{url}?{query_string}"
        
        headers = self._headers.copy()
        
        # Handle authentication
        if auth:
            if not instruction:
                raise ValueError("Instruction type required for authenticated requests")
            
            # Determine what to sign based on method
            sign_params = None
            if method == HttpMethod.GET or method == HttpMethod.DELETE:
                sign_params = params
            elif data and not isinstance(data, list):
                sign_params = data
            
            # Handle batch orders specially
            if instruction == "orderExecute" and isinstance(data, list):
                signature, timestamp, window = sign_batch_order_request(
                    self._private_key,
                    data,
                )
            else:
                signature, timestamp, window = sign_request(
                    self._private_key,
                    instruction,
                    sign_params,
                )
            
            # Add authentication headers
            headers["X-Timestamp"] = str(timestamp)
            headers["X-Window"] = str(window)
            headers["X-Signature"] = signature
        
        # Prepare request body
        body = None
        if data is not None:
            if isinstance(data, (dict, list)):
                body = self._encoder.encode(data)
            else:
                body = data
        
        # Send request (HttpClient doesn't accept params, they're already in URL)
        response: HttpResponse = await self._client.request(
            method=method,
            url=url,
            headers=headers,
            body=body,
        )
        
        # Handle response
        if response.status >= 400:
            error_data = self._decoder.decode(response.body) if response.body else {}
            error_code = error_data.get("code", -1)
            error_msg = error_data.get("msg", "Unknown error")
            
            # Check if error warrants a retry
            if error_code in BACKPACK_RETRY_ERRORS:
                self._log.warning(
                    f"Backpack API error (retryable): {error_code} - {error_msg}",
                    LogColor.YELLOW,
                )
            
            raise Exception(f"Backpack API error: {error_code} - {error_msg}")
        
        # Parse response
        if response.body:
            return self._decoder.decode(response.body)
        return None

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        auth: bool = False,
        instruction: str | None = None,
    ) -> Any:
        """Send a GET request."""
        return await self._request(
            method=HttpMethod.GET,
            path=path,
            params=params,
            auth=auth,
            instruction=instruction,
        )

    async def _post(
        self,
        path: str,
        data: dict[str, Any] | list[dict[str, Any]] | None = None,
        auth: bool = False,
        instruction: str | None = None,
    ) -> Any:
        """Send a POST request."""
        return await self._request(
            method=HttpMethod.POST,
            path=path,
            data=data,
            auth=auth,
            instruction=instruction,
        )

    async def _delete(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        auth: bool = False,
        instruction: str | None = None,
    ) -> Any:
        """Send a DELETE request."""
        return await self._request(
            method=HttpMethod.DELETE,
            path=path,
            params=params,
            auth=auth,
            instruction=instruction,
        )

    # Public API methods
    async def fetch_markets(self) -> list[dict[str, Any]]:
        """Fetch all markets."""
        return await self._get(BACKPACK_API_PATHS["markets"])

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        """Fetch ticker for a symbol."""
        params = {"symbol": symbol}
        return await self._get(BACKPACK_API_PATHS["ticker"], params=params)

    async def fetch_tickers(self) -> list[dict[str, Any]]:
        """Fetch all tickers."""
        return await self._get(BACKPACK_API_PATHS["tickers"])

    async def fetch_order_book(self, symbol: str) -> dict[str, Any]:
        """Fetch order book for a symbol."""
        params = {"symbol": symbol}
        return await self._get(BACKPACK_API_PATHS["depth"], params=params)

    async def fetch_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch recent trades for a symbol."""
        params = {"symbol": symbol, "limit": limit}
        return await self._get(BACKPACK_API_PATHS["trades"], params=params)

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[list[Any]]:
        """Fetch klines (candlesticks) for a symbol."""
        params = {"symbol": symbol, "interval": interval}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._get(BACKPACK_API_PATHS["klines"], params=params)

    # Private API methods
    async def fetch_balance(self) -> dict[str, Any]:
        """Fetch account balance."""
        return await self._get(
            BACKPACK_API_PATHS["capital"],
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["balance_query"],
        )

    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: str | None = None,
        time_in_force: str = "GTC",
        client_id: str | None = None,
        post_only: bool = False,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Create a new order."""
        data = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "quantity": quantity,
        }
        
        if price:
            data["price"] = price
        if time_in_force:
            data["timeInForce"] = time_in_force
        if client_id:
            data["clientId"] = client_id
        if post_only:
            data["postOnly"] = post_only
        if reduce_only:
            data["reduceOnly"] = reduce_only
        
        return await self._post(
            BACKPACK_API_PATHS["order"],
            data=data,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["order_execute"],
        )

    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel an order."""
        data = {"symbol": symbol}
        if order_id:
            data["orderId"] = order_id
        if client_id:
            data["clientId"] = client_id
        
        # Cancel endpoint expects data in body for DELETE request
        return await self._request(
            method=HttpMethod.DELETE,
            path=BACKPACK_API_PATHS["order"],
            data=data,  # Pass as data, not params
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["order_cancel"],
        )

    async def fetch_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a specific order."""
        params = {"symbol": symbol}
        if order_id:
            params["orderId"] = order_id
        if client_id:
            params["clientId"] = client_id
        
        return await self._get(
            BACKPACK_API_PATHS["order"],
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["order_query"],
        )

    async def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Fetch open orders."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        return await self._get(
            BACKPACK_API_PATHS["orders"],
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["order_query_all"],
        )

    async def fetch_order_history(
        self,
        symbol: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch order history."""
        params = {"limit": limit, "offset": offset}
        if symbol:
            params["symbol"] = symbol
        
        return await self._get(
            BACKPACK_API_PATHS["order_history"],
            params=params,
            auth=True,
            instruction=BACKPACK_INSTRUCTIONS["order_history_query_all"],
        )