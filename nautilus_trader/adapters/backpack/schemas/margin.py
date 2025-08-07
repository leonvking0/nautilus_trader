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
Backpack margin-related schemas.
"""

import msgspec


class BackpackMarginUpdate(msgspec.Struct, frozen=True):
    """Real-time margin update from WebSocket."""
    
    e: str  # Event type "marginUpdate"
    E: int  # Event timestamp (microseconds)
    totalCollateral: str
    borrowLiability: str
    marginRatio: str  # MMR ratio
    availableEquity: str
    unrealizedPnl: str
    initialMarginUsed: str
    maintenanceMarginRequired: str
    T: int  # Engine timestamp (microseconds)


class BackpackBorrowUpdate(msgspec.Struct, frozen=True):
    """Borrow position update from WebSocket."""
    
    e: str  # Event type "borrowPositionUpdate"
    E: int  # Event timestamp
    asset: str
    borrowed: str
    interest: str
    interestRate: str  # APR as decimal
    cumulativeInterest: str
    T: int  # Engine timestamp


class BackpackCollateralUpdate(msgspec.Struct, frozen=True):
    """Collateral weight update from WebSocket."""
    
    e: str  # Event type "collateralUpdate"
    E: int  # Event timestamp
    weights: dict[str, str]  # Asset -> weight mapping
    T: int  # Engine timestamp


class BackpackBorrowHistory(msgspec.Struct, frozen=True):
    """Historical borrow/repay record."""
    
    id: str
    asset: str
    type: str  # "BORROW" or "REPAY"
    amount: str
    interest: str
    principal: str
    timestamp: int


class BackpackInterestHistory(msgspec.Struct, frozen=True):
    """Historical interest payment record."""
    
    id: str
    asset: str
    interest: str
    rate: str
    principal: str
    timestamp: int


class BackpackBorrowMarket(msgspec.Struct, frozen=True):
    """Borrow market information."""
    
    asset: str
    availableToBorrow: str
    borrowRate: str  # Current APR
    borrowRateMin: str  # 24h min
    borrowRateMax: str  # 24h max
    totalBorrowed: str
    totalSupply: str
    utilizationRate: str
    maxBorrowLimit: str  # Per account


class BackpackCollateralConversion(msgspec.Struct, frozen=True):
    """Collateral conversion request/result."""
    
    id: str
    fromAsset: str
    toAsset: str
    fromAmount: str
    toAmount: str
    conversionRate: str
    status: str  # "PENDING", "COMPLETED", "FAILED"
    timestamp: int


class BackpackMarginCall(msgspec.Struct, frozen=True):
    """Margin call notification."""
    
    level: str  # "WARNING", "CRITICAL"
    marginRatio: str
    totalCollateral: str
    borrowLiability: str
    availableEquity: str
    requiredAction: str  # "REDUCE_POSITION", "ADD_COLLATERAL", "REPAY_BORROW"
    timeToLiquidation: int | None  # Milliseconds, if estimatable
    timestamp: int


class BackpackLiquidation(msgspec.Struct, frozen=True):
    """Liquidation event details."""
    
    id: str
    type: str  # "PARTIAL", "FULL"
    positions: list[dict]  # Liquidated positions
    totalLiquidated: str  # USD value
    collateralLost: str
    debtRepaid: str
    liquidationFee: str
    timestamp: int


class BackpackAutoRepay(msgspec.Struct, frozen=True):
    """Auto-repay execution record."""
    
    id: str
    asset: str
    amount: str
    interestSaved: str
    previousBorrowed: str
    remainingBorrowed: str
    trigger: str  # "EXCESS_BALANCE", "SCHEDULED", "MANUAL"
    timestamp: int