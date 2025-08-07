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
Backpack wallet management HTTP API client.

Handles deposits, withdrawals, transfers, and wallet operations.
"""

import time
from decimal import Decimal
from typing import Any

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.schemas.wallet import BackpackDepositAddress
from nautilus_trader.adapters.backpack.schemas.wallet import BackpackDepositHistory
from nautilus_trader.adapters.backpack.schemas.wallet import BackpackInternalTransfer
from nautilus_trader.adapters.backpack.schemas.wallet import BackpackWithdrawal
from nautilus_trader.adapters.backpack.schemas.wallet import BackpackWithdrawalHistory
from nautilus_trader.adapters.backpack.schemas.wallet import BackpackBalanceSnapshot


class BackpackWalletHttpAPI:
    """
    HTTP API client for Backpack wallet management.
    
    Provides methods for:
    - Deposit address generation
    - Withdrawal requests
    - Internal transfers between accounts
    - Transaction history
    - Balance snapshots
    """
    
    def __init__(self, client: BackpackHttpClient):
        """
        Initialize the wallet HTTP API.
        
        Parameters
        ----------
        client : BackpackHttpClient
            The HTTP client for making requests.
        """
        self._client = client
    
    async def get_deposit_address(
        self,
        currency: str,
        blockchain: str | None = None,
    ) -> BackpackDepositAddress:
        """
        Get or generate a deposit address for a currency.
        
        Parameters
        ----------
        currency : str
            The currency code (e.g., "BTC", "ETH", "USDC").
        blockchain : str, optional
            The blockchain network (e.g., "solana", "ethereum").
            If not specified, uses the default for the currency.
        
        Returns
        -------
        BackpackDepositAddress
            The deposit address information.
        """
        params = {"currency": currency}
        if blockchain:
            params["blockchain"] = blockchain
            
        response = await self._client._get(
            path="/api/v1/wallet/deposit_address",
            params=params,
            auth=True,
        )
        
        return BackpackDepositAddress.from_dict(response)
    
    async def get_deposit_history(
        self,
        currency: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BackpackDepositHistory]:
        """
        Get deposit history.
        
        Parameters
        ----------
        currency : str, optional
            Filter by currency.
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
        list[BackpackDepositHistory]
            List of deposit records.
        """
        params = {
            "limit": limit,
            "offset": offset,
        }
        
        if currency:
            params["currency"] = currency
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        response = await self._client._get(
            path="/api/v1/wallet/deposits",
            params=params,
            auth=True,
        )
        
        return [BackpackDepositHistory.from_dict(d) for d in response]
    
    async def request_withdrawal(
        self,
        currency: str,
        amount: Decimal,
        address: str,
        blockchain: str | None = None,
        memo: str | None = None,
        two_fa_token: str | None = None,
    ) -> BackpackWithdrawal:
        """
        Request a withdrawal.
        
        Parameters
        ----------
        currency : str
            The currency to withdraw.
        amount : Decimal
            The amount to withdraw.
        address : str
            The destination address.
        blockchain : str, optional
            The blockchain network.
        memo : str, optional
            Memo/tag for the withdrawal.
        two_fa_token : str, optional
            2FA token if required.
        
        Returns
        -------
        BackpackWithdrawal
            The withdrawal request details.
        """
        data = {
            "currency": currency,
            "amount": str(amount),
            "address": address,
        }
        
        if blockchain:
            data["blockchain"] = blockchain
        if memo:
            data["memo"] = memo
        if two_fa_token:
            data["twoFaToken"] = two_fa_token
        
        response = await self._client._post(
            path="/api/v1/wallet/withdraw",
            data=data,
            auth=True,
        )
        
        return BackpackWithdrawal.from_dict(response)
    
    async def cancel_withdrawal(self, withdrawal_id: str) -> dict:
        """
        Cancel a pending withdrawal.
        
        Parameters
        ----------
        withdrawal_id : str
            The withdrawal ID to cancel.
        
        Returns
        -------
        dict
            Cancellation confirmation.
        """
        response = await self._client._delete(
            path=f"/api/v1/wallet/withdrawals/{withdrawal_id}",
            auth=True,
        )
        
        return response
    
    async def get_withdrawal_history(
        self,
        currency: str | None = None,
        status: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BackpackWithdrawalHistory]:
        """
        Get withdrawal history.
        
        Parameters
        ----------
        currency : str, optional
            Filter by currency.
        status : str, optional
            Filter by status (PENDING, COMPLETED, FAILED, CANCELLED).
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
        list[BackpackWithdrawalHistory]
            List of withdrawal records.
        """
        params = {
            "limit": limit,
            "offset": offset,
        }
        
        if currency:
            params["currency"] = currency
        if status:
            params["status"] = status
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        response = await self._client._get(
            path="/api/v1/wallet/withdrawals",
            params=params,
            auth=True,
        )
        
        return [BackpackWithdrawalHistory.from_dict(w) for w in response]
    
    async def internal_transfer(
        self,
        from_account: str,
        to_account: str,
        currency: str,
        amount: Decimal,
    ) -> BackpackInternalTransfer:
        """
        Transfer funds between accounts (main <-> sub-accounts).
        
        Parameters
        ----------
        from_account : str
            Source account ID (or "main" for main account).
        to_account : str
            Destination account ID (or "main" for main account).
        currency : str
            The currency to transfer.
        amount : Decimal
            The amount to transfer.
        
        Returns
        -------
        BackpackInternalTransfer
            The transfer details.
        """
        data = {
            "fromAccount": from_account,
            "toAccount": to_account,
            "currency": currency,
            "amount": str(amount),
        }
        
        response = await self._client._post(
            path="/api/v1/wallet/internal_transfer",
            data=data,
            auth=True,
        )
        
        return BackpackInternalTransfer.from_dict(response)
    
    async def get_internal_transfers(
        self,
        currency: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BackpackInternalTransfer]:
        """
        Get internal transfer history.
        
        Parameters
        ----------
        currency : str, optional
            Filter by currency.
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
        list[BackpackInternalTransfer]
            List of internal transfers.
        """
        params = {
            "limit": limit,
            "offset": offset,
        }
        
        if currency:
            params["currency"] = currency
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        response = await self._client._get(
            path="/api/v1/wallet/internal_transfers",
            params=params,
            auth=True,
        )
        
        return [BackpackInternalTransfer.from_dict(t) for t in response]
    
    async def get_balance_snapshot(
        self,
        timestamp: int | None = None,
    ) -> BackpackBalanceSnapshot:
        """
        Get a balance snapshot at a specific time.
        
        Parameters
        ----------
        timestamp : int, optional
            The timestamp in milliseconds. If not provided, returns current snapshot.
        
        Returns
        -------
        BackpackBalanceSnapshot
            The balance snapshot.
        """
        params = {}
        if timestamp:
            params["timestamp"] = timestamp
        
        response = await self._client._get(
            path="/api/v1/wallet/balance_snapshot",
            params=params,
            auth=True,
        )
        
        return BackpackBalanceSnapshot.from_dict(response)
    
    async def get_balance_history(
        self,
        currency: str,
        interval: str = "1h",
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict]:
        """
        Get balance history over time.
        
        Parameters
        ----------
        currency : str
            The currency to get history for.
        interval : str, default "1h"
            Time interval (1m, 5m, 15m, 30m, 1h, 4h, 1d).
        start_time : int, optional
            Start time in milliseconds.
        end_time : int, optional
            End time in milliseconds.
        
        Returns
        -------
        list[dict]
            List of balance snapshots.
        """
        params = {
            "currency": currency,
            "interval": interval,
        }
        
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        else:
            params["endTime"] = int(time.time() * 1000)
        
        if not start_time:
            # Default to last 7 days
            params["startTime"] = params["endTime"] - (7 * 24 * 60 * 60 * 1000)
        
        response = await self._client._get(
            path="/api/v1/wallet/balance_history",
            params=params,
            auth=True,
        )
        
        return response
    
    async def dust_conversion(
        self,
        currencies: list[str] | None = None,
    ) -> dict:
        """
        Convert small balances (dust) to USDC.
        
        Parameters
        ----------
        currencies : list[str], optional
            Specific currencies to convert. If not provided, converts all dust.
        
        Returns
        -------
        dict
            Conversion result with amounts.
        """
        data = {}
        if currencies:
            data["currencies"] = currencies
        
        response = await self._client._post(
            path="/api/v1/wallet/dust_conversion",
            data=data,
            auth=True,
        )
        
        return response
    
    async def get_fee_rates(self) -> dict:
        """
        Get current fee rates for trading and withdrawals.
        
        Returns
        -------
        dict
            Fee rate information.
        """
        response = await self._client._get(
            path="/api/v1/wallet/fee_rates",
            auth=True,
        )
        
        return response