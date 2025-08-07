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
Backpack wallet data schemas.

Defines the structure for wallet-related data including deposits,
withdrawals, transfers, and balance snapshots.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class BackpackDepositAddress:
    """Represents a deposit address for a currency."""
    
    currency: str
    address: str
    blockchain: str
    memo: str | None = None
    qr_code: str | None = None
    created_at: int | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackDepositAddress":
        """Create from API response."""
        return cls(
            currency=data["currency"],
            address=data["address"],
            blockchain=data["blockchain"],
            memo=data.get("memo"),
            qr_code=data.get("qrCode"),
            created_at=data.get("createdAt"),
        )


@dataclass
class BackpackDepositHistory:
    """Represents a deposit transaction."""
    
    id: str
    currency: str
    amount: Decimal
    address: str
    blockchain: str
    tx_hash: str
    confirmations: int
    required_confirmations: int
    status: str  # PENDING, COMPLETED, FAILED
    created_at: int
    completed_at: int | None = None
    memo: str | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackDepositHistory":
        """Create from API response."""
        return cls(
            id=data["id"],
            currency=data["currency"],
            amount=Decimal(str(data["amount"])),
            address=data["address"],
            blockchain=data["blockchain"],
            tx_hash=data["txHash"],
            confirmations=data["confirmations"],
            required_confirmations=data["requiredConfirmations"],
            status=data["status"],
            created_at=data["createdAt"],
            completed_at=data.get("completedAt"),
            memo=data.get("memo"),
        )
    
    def is_completed(self) -> bool:
        """Check if deposit is completed."""
        return self.status == "COMPLETED"
    
    def is_pending(self) -> bool:
        """Check if deposit is pending."""
        return self.status == "PENDING"


@dataclass
class BackpackWithdrawal:
    """Represents a withdrawal request."""
    
    id: str
    currency: str
    amount: Decimal
    fee: Decimal
    net_amount: Decimal
    address: str
    blockchain: str
    status: str  # PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED
    created_at: int
    memo: str | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackWithdrawal":
        """Create from API response."""
        return cls(
            id=data["id"],
            currency=data["currency"],
            amount=Decimal(str(data["amount"])),
            fee=Decimal(str(data["fee"])),
            net_amount=Decimal(str(data["netAmount"])),
            address=data["address"],
            blockchain=data["blockchain"],
            status=data["status"],
            created_at=data["createdAt"],
            memo=data.get("memo"),
        )


@dataclass
class BackpackWithdrawalHistory:
    """Represents a historical withdrawal."""
    
    id: str
    currency: str
    amount: Decimal
    fee: Decimal
    net_amount: Decimal
    address: str
    blockchain: str
    tx_hash: str | None
    status: str  # PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED
    created_at: int
    processed_at: int | None = None
    completed_at: int | None = None
    memo: str | None = None
    failure_reason: str | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackWithdrawalHistory":
        """Create from API response."""
        return cls(
            id=data["id"],
            currency=data["currency"],
            amount=Decimal(str(data["amount"])),
            fee=Decimal(str(data["fee"])),
            net_amount=Decimal(str(data["netAmount"])),
            address=data["address"],
            blockchain=data["blockchain"],
            tx_hash=data.get("txHash"),
            status=data["status"],
            created_at=data["createdAt"],
            processed_at=data.get("processedAt"),
            completed_at=data.get("completedAt"),
            memo=data.get("memo"),
            failure_reason=data.get("failureReason"),
        )
    
    def is_completed(self) -> bool:
        """Check if withdrawal is completed."""
        return self.status == "COMPLETED"
    
    def is_pending(self) -> bool:
        """Check if withdrawal is pending or processing."""
        return self.status in ["PENDING", "PROCESSING"]
    
    def is_failed(self) -> bool:
        """Check if withdrawal failed."""
        return self.status == "FAILED"


@dataclass
class BackpackInternalTransfer:
    """Represents an internal transfer between accounts."""
    
    id: str
    from_account: str
    to_account: str
    currency: str
    amount: Decimal
    status: str  # COMPLETED, FAILED
    created_at: int
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackInternalTransfer":
        """Create from API response."""
        return cls(
            id=data["id"],
            from_account=data["fromAccount"],
            to_account=data["toAccount"],
            currency=data["currency"],
            amount=Decimal(str(data["amount"])),
            status=data["status"],
            created_at=data["createdAt"],
        )


@dataclass
class BackpackBalanceSnapshot:
    """Represents a balance snapshot at a point in time."""
    
    timestamp: int
    total_usdc_value: Decimal
    balances: dict[str, dict[str, Decimal]]  # currency -> {free, locked, total}
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackBalanceSnapshot":
        """Create from API response."""
        balances = {}
        for currency, balance_data in data["balances"].items():
            balances[currency] = {
                "free": Decimal(str(balance_data["free"])),
                "locked": Decimal(str(balance_data["locked"])),
                "total": Decimal(str(balance_data["total"])),
            }
        
        return cls(
            timestamp=data["timestamp"],
            total_usdc_value=Decimal(str(data["totalUsdcValue"])),
            balances=balances,
        )
    
    def get_balance(self, currency: str) -> dict[str, Decimal] | None:
        """Get balance for a specific currency."""
        return self.balances.get(currency)
    
    def get_free_balance(self, currency: str) -> Decimal:
        """Get free balance for a currency."""
        balance = self.get_balance(currency)
        return balance["free"] if balance else Decimal(0)
    
    def get_locked_balance(self, currency: str) -> Decimal:
        """Get locked balance for a currency."""
        balance = self.get_balance(currency)
        return balance["locked"] if balance else Decimal(0)
    
    def get_total_balance(self, currency: str) -> Decimal:
        """Get total balance for a currency."""
        balance = self.get_balance(currency)
        return balance["total"] if balance else Decimal(0)