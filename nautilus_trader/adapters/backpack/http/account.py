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
Backpack Exchange account HTTP API endpoints.
"""

import msgspec

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.account import BackpackAccount
from nautilus_trader.adapters.backpack.schemas.account import BackpackAccountLimits
from nautilus_trader.adapters.backpack.schemas.account import BackpackBorrowPosition
from nautilus_trader.adapters.backpack.schemas.account import BackpackCapital
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateral
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateralDetail
from nautilus_trader.adapters.backpack.schemas.account import BackpackSubaccount
from nautilus_trader.adapters.backpack.schemas.margin import BackpackBorrowHistory
from nautilus_trader.adapters.backpack.schemas.margin import BackpackInterestHistory


class BackpackAccountHttpAPI:
    """
    Provides access to Backpack account HTTP REST API.
    
    Parameters
    ----------
    client : BackpackHttpClient
        The Backpack HTTP client.
    """
    
    def __init__(self, client: BackpackHttpClient) -> None:
        self._client = client
        
        # Response decoders
        self._decoder_account = msgspec.json.Decoder(BackpackAccount)
        self._decoder_capital = msgspec.json.Decoder(BackpackCapital)
        self._decoder_collateral = msgspec.json.Decoder(BackpackCollateral)
        self._decoder_collateral_details = msgspec.json.Decoder(list[BackpackCollateralDetail])
        self._decoder_borrow_positions = msgspec.json.Decoder(list[BackpackBorrowPosition])
        self._decoder_account_limits = msgspec.json.Decoder(BackpackAccountLimits)
        self._decoder_subaccounts = msgspec.json.Decoder(list[BackpackSubaccount])
        self._decoder_borrow_history = msgspec.json.Decoder(list[BackpackBorrowHistory])
        self._decoder_interest_history = msgspec.json.Decoder(list[BackpackInterestHistory])
    
    async def fetch_account(self) -> BackpackAccount:
        """
        Fetch account information.
        
        GET /api/v1/account
        
        Returns
        -------
        BackpackAccount
            The account information.
        """
        raw = await self._client._get(
            path="/api/v1/account",
            params={},
            auth=True,
            instruction="accountQuery",
        )
        return self._decoder_account.decode(raw)
    
    async def fetch_capital(self) -> BackpackCapital:
        """
        Fetch capital and margin information.
        
        GET /api/v1/capital
        
        Returns
        -------
        BackpackCapital
            The capital information including collateral and margin rates.
        """
        raw = await self._client._get(
            path="/api/v1/capital",
            params={},
            auth=True,
            instruction="balanceQuery",
        )
        return self._decoder_capital.decode(raw)
    
    async def fetch_collateral(self) -> BackpackCollateral:
        """
        Fetch collateral weights for all assets.
        
        GET /api/v1/collateral
        
        Returns
        -------
        BackpackCollateral
            The collateral weights for each asset.
        """
        raw = await self._client._get(
            path="/api/v1/collateral",
            params={},
            auth=True,
            instruction="collateralQuery",
        )
        return self._decoder_collateral.decode(raw)
    
    async def fetch_collateral_details(self) -> list[BackpackCollateralDetail]:
        """
        Fetch detailed collateral information per asset.
        
        GET /api/v1/capital/collateral
        
        Returns
        -------
        list[BackpackCollateralDetail]
            The detailed collateral information for each asset.
        """
        raw = await self._client._get(
            path="/api/v1/capital/collateral",
            params={},
            auth=True,
            instruction="collateralQuery",
        )
        return self._decoder_collateral_details.decode(raw)
    
    async def fetch_borrow_positions(self) -> list[BackpackBorrowPosition]:
        """
        Fetch active borrow positions.
        
        GET /api/v1/borrowLend/positions
        
        Returns
        -------
        list[BackpackBorrowPosition]
            The active borrow positions.
        """
        raw = await self._client._get(
            path="/api/v1/borrowLend/positions",
            params={},
            auth=True,
            instruction="borrowPositionHistoryQueryAll",
        )
        return self._decoder_borrow_positions.decode(raw)
    
    async def fetch_account_limits(self) -> BackpackAccountLimits:
        """
        Fetch account trading limits.
        
        GET /api/v1/account/limits/order
        
        Returns
        -------
        BackpackAccountLimits
            The account limits.
        """
        raw = await self._client._get(
            path="/api/v1/account/limits/order",
            params={},
            auth=True,
            instruction="accountQuery",
        )
        return self._decoder_account_limits.decode(raw)
    
    async def fetch_borrow_limit(self) -> dict:
        """
        Fetch borrow limits.
        
        GET /api/v1/account/limits/borrow
        
        Returns
        -------
        dict
            The borrow limits.
        """
        raw = await self._client._get(
            path="/api/v1/account/limits/borrow",
            params={},
            auth=True,
            instruction="accountQuery",
        )
        return msgspec.json.decode(raw)
    
    async def fetch_withdrawal_limit(self) -> dict:
        """
        Fetch withdrawal limits.
        
        GET /api/v1/account/limits/withdrawal
        
        Returns
        -------
        dict
            The withdrawal limits.
        """
        raw = await self._client._get(
            path="/api/v1/account/limits/withdrawal",
            params={},
            auth=True,
            instruction="accountQuery",
        )
        return msgspec.json.decode(raw)
    
    async def convert_dust(
        self,
        assets: list[str],
    ) -> dict:
        """
        Convert small balances (dust) to USDC.
        
        POST /api/v1/account/convertDust
        
        Parameters
        ----------
        assets : list[str]
            The assets to convert to USDC.
            
        Returns
        -------
        dict
            The conversion result.
        """
        data = {
            "assets": ",".join(assets),
        }
        
        raw = await self._client._post(
            path="/api/v1/account/convertDust",
            data=data,
            auth=True,
            instruction="accountExecute",
        )
        return msgspec.json.decode(raw)
    
    async def execute_borrow(
        self,
        asset: str,
        amount: str,
    ) -> dict:
        """
        Execute a borrow operation.
        
        POST /api/v1/borrowLend
        
        Parameters
        ----------
        asset : str
            The asset to borrow.
        amount : str
            The amount to borrow.
            
        Returns
        -------
        dict
            The borrow execution result.
        """
        data = {
            "asset": asset,
            "amount": amount,
            "type": "BORROW",
        }
        
        raw = await self._client._post(
            path="/api/v1/borrowLend",
            data=data,
            auth=True,
            instruction="borrowLendExecute",
        )
        return msgspec.json.decode(raw)
    
    async def execute_repay(
        self,
        asset: str,
        amount: str,
    ) -> dict:
        """
        Execute a repay operation.
        
        POST /api/v1/borrowLend
        
        Parameters
        ----------
        asset : str
            The asset to repay.
        amount : str
            The amount to repay.
            
        Returns
        -------
        dict
            The repay execution result.
        """
        data = {
            "asset": asset,
            "amount": amount,
            "type": "REPAY",
        }
        
        raw = await self._client._post(
            path="/api/v1/borrowLend",
            data=data,
            auth=True,
            instruction="borrowLendExecute",
        )
        return msgspec.json.decode(raw)
    
    async def fetch_borrow_history(
        self,
        asset: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[BackpackBorrowHistory]:
        """
        Fetch borrow/repay history.
        
        GET /wapi/v1/history/borrowLend
        
        Parameters
        ----------
        asset : str, optional
            Filter by asset.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[BackpackBorrowHistory]
            The borrow/repay history records.
        """
        params = {"limit": str(limit)}
        if asset:
            params["asset"] = asset
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/borrowLend",
            params=params,
            auth=True,
            instruction="borrowHistoryQueryAll",
        )
        return self._decoder_borrow_history.decode(raw)
    
    async def fetch_interest_history(
        self,
        asset: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[BackpackInterestHistory]:
        """
        Fetch interest payment history.
        
        GET /wapi/v1/history/interest
        
        Parameters
        ----------
        asset : str, optional
            Filter by asset.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[BackpackInterestHistory]
            The interest payment history.
        """
        params = {"limit": str(limit)}
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
            instruction="interestHistoryQueryAll",
        )
        return self._decoder_interest_history.decode(raw)
    
    async def fetch_borrow_position_history(
        self,
        position_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch borrow position history per position.
        
        GET /wapi/v1/history/borrowLend/positions
        
        Parameters
        ----------
        position_id : str, optional
            Filter by position ID.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[dict]
            The borrow position history.
        """
        params = {"limit": str(limit)}
        if position_id:
            params["positionId"] = position_id
        
        raw = await self._client._get(
            path="/wapi/v1/history/borrowLend/positions",
            params=params,
            auth=True,
            instruction="borrowPositionHistoryQueryAll",
        )
        return msgspec.json.decode(raw)
    
    async def fetch_subaccounts(self) -> list[BackpackSubaccount]:
        """
        Fetch all subaccounts.
        
        GET /api/v1/account/subaccounts
        
        Returns
        -------
        list[BackpackSubaccount]
            The list of subaccounts.
        """
        raw = await self._client._get(
            path="/api/v1/account/subaccounts",
            params={},
            auth=True,
            instruction="accountQuery",
        )
        return self._decoder_subaccounts.decode(raw)
    
    async def create_subaccount(
        self,
        name: str,
    ) -> dict:
        """
        Create a new subaccount (max 10).
        
        POST /api/v1/account/subaccount
        
        Parameters
        ----------
        name : str
            The name for the subaccount.
            
        Returns
        -------
        dict
            The created subaccount info.
        """
        data = {
            "name": name,
        }
        
        raw = await self._client._post(
            path="/api/v1/account/subaccount",
            data=data,
            auth=True,
            instruction="accountExecute",
        )
        return msgspec.json.decode(raw)
    
    async def switch_subaccount(
        self,
        subaccount_id: str,
    ) -> dict:
        """
        Switch to a different subaccount.
        
        POST /api/v1/account/subaccount/switch
        
        Parameters
        ----------
        subaccount_id : str
            The subaccount ID to switch to.
            
        Returns
        -------
        dict
            The switch result.
        """
        data = {
            "subaccountId": subaccount_id,
        }
        
        raw = await self._client._post(
            path="/api/v1/account/subaccount/switch",
            data=data,
            auth=True,
            instruction="accountExecute",
        )
        return msgspec.json.decode(raw)
    
    async def execute_collateral_conversion(
        self,
        from_asset: str,
        to_asset: str,
        amount: str,
    ) -> dict:
        """
        Execute collateral conversion to manage risk.
        
        POST /api/v1/collateral/convert
        
        Parameters
        ----------
        from_asset : str
            The asset to convert from.
        to_asset : str
            The asset to convert to.
        amount : str
            The amount to convert.
            
        Returns
        -------
        dict
            The conversion result.
        """
        data = {
            "fromAsset": from_asset,
            "toAsset": to_asset,
            "amount": amount,
        }
        
        raw = await self._client._post(
            path="/api/v1/collateral/convert",
            data=data,
            auth=True,
            instruction="collateralConvert",
        )
        return msgspec.json.decode(raw)
    
    async def get_conversion_quote(
        self,
        from_asset: str,
        to_asset: str,
        amount: str,
    ) -> dict:
        """
        Get a quote for collateral conversion.
        
        GET /api/v1/collateral/quote
        
        Parameters
        ----------
        from_asset : str
            The asset to convert from.
        to_asset : str
            The asset to convert to.
        amount : str
            The amount to convert.
            
        Returns
        -------
        dict
            The conversion quote.
        """
        params = {
            "fromAsset": from_asset,
            "toAsset": to_asset,
            "amount": amount,
        }
        
        raw = await self._client._get(
            path="/api/v1/collateral/quote",
            params=params,
            auth=True,
            instruction="collateralQuery",
        )
        return msgspec.json.decode(raw)
    
    async def fetch_conversion_history(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch collateral conversion history.
        
        GET /wapi/v1/history/collateral/conversions
        
        Parameters
        ----------
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[dict]
            The conversion history.
        """
        params = {"limit": str(limit)}
        if start_time:
            params["from"] = str(start_time)
        if end_time:
            params["to"] = str(end_time)
        
        raw = await self._client._get(
            path="/wapi/v1/history/collateral/conversions",
            params=params,
            auth=True,
            instruction="collateralHistoryQuery",
        )
        return msgspec.json.decode(raw)