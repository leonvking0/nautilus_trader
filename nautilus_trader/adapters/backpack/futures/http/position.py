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
Backpack Exchange futures position HTTP API.
"""

import msgspec

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.futures.schemas.position import BackpackFuturesPosition
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.core.datetime import millis_to_nanos


class BackpackFuturesPositionHttpAPI:
    """
    Provides access to Backpack futures position HTTP REST API.
    
    Parameters
    ----------
    client : BackpackHttpClient
        The Backpack HTTP client.
    """
    
    def __init__(self, client: BackpackHttpClient) -> None:
        self._client = client
        
        # Response decoders
        self._decoder_positions = msgspec.json.Decoder(list[BackpackFuturesPosition])
        self._decoder_position = msgspec.json.Decoder(BackpackFuturesPosition)
    
    async def fetch_positions(
        self,
        symbol: str | None = None,
    ) -> list[BackpackFuturesPosition]:
        """
        Fetch futures positions.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch position for. If None, fetches all positions.
            
        Returns
        -------
        list[BackpackFuturesPosition]
            The position data.
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        raw = await self._client._get_signed(
            path="/api/v1/position",
            params=params,
            instruction="positionQuery",
        )
        
        if symbol:
            # Single position response
            position = self._decoder_position.decode(raw)
            return [position]
        else:
            # Multiple positions
            return self._decoder_positions.decode(raw)
    
    async def modify_leverage(
        self,
        symbol: str,
        leverage: int,
    ) -> dict:
        """
        Modify position leverage.
        
        Parameters
        ----------
        symbol : str
            The symbol to modify leverage for.
        leverage : int
            The new leverage value (1-125).
            
        Returns
        -------
        dict
            The response from the API.
        """
        if not 1 <= leverage <= 125:
            raise ValueError(f"Leverage must be between 1 and 125, got {leverage}")
        
        data = {
            "symbol": symbol,
            "leverage": leverage,
        }
        
        raw = await self._client._post_signed(
            path="/api/v1/position/leverage",
            data=data,
            instruction="positionLeverageModify",
        )
        
        return msgspec.json.decode(raw)
    
    async def modify_margin_type(
        self,
        symbol: str,
        margin_type: str,
    ) -> dict:
        """
        Modify position margin type.
        
        Parameters
        ----------
        symbol : str
            The symbol to modify margin type for.
        margin_type : str
            The margin type (CROSS or ISOLATED).
            
        Returns
        -------
        dict
            The response from the API.
        """
        if margin_type not in ["CROSS", "ISOLATED"]:
            raise ValueError(f"Invalid margin type: {margin_type}")
        
        data = {
            "symbol": symbol,
            "marginType": margin_type,
        }
        
        raw = await self._client._post_signed(
            path="/api/v1/position/marginType",
            data=data,
            instruction="positionMarginTypeModify",
        )
        
        return msgspec.json.decode(raw)
    
    async def add_margin(
        self,
        symbol: str,
        amount: str,
    ) -> dict:
        """
        Add margin to an isolated position.
        
        Parameters
        ----------
        symbol : str
            The symbol to add margin to.
        amount : str
            The amount of margin to add.
            
        Returns
        -------
        dict
            The response from the API.
        """
        data = {
            "symbol": symbol,
            "amount": amount,
        }
        
        raw = await self._client._post_signed(
            path="/api/v1/position/margin",
            data=data,
            instruction="positionMarginAdd",
        )
        
        return msgspec.json.decode(raw)