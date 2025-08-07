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
Backpack borrow/lend market schemas.
"""

import msgspec


class BackpackBorrowMarket(msgspec.Struct, frozen=True):
    """Borrow/lend market information for an asset."""
    
    asset: str
    availableToBorrow: str  # Total available to borrow
    borrowRate: str  # Current borrow APR
    borrowRateMin24h: str  # 24h minimum rate
    borrowRateMax24h: str  # 24h maximum rate
    borrowRateAvg24h: str  # 24h average rate
    lendRate: str  # Current lend APR
    lendRateMin24h: str  # 24h minimum lend rate
    lendRateMax24h: str  # 24h maximum lend rate
    lendRateAvg24h: str  # 24h average lend rate
    totalBorrowed: str  # Total borrowed across all users
    totalSupply: str  # Total supplied for lending
    utilizationRate: str  # Utilization percentage
    maxBorrowLimitPerAccount: str  # Max borrow per account
    minBorrowAmount: str  # Minimum borrow amount
    borrowEnabled: bool  # Whether borrowing is enabled
    lendEnabled: bool  # Whether lending is enabled
    lastUpdated: int  # Timestamp


class BackpackBorrowRates(msgspec.Struct, frozen=True):
    """Current borrow rates for all assets."""
    
    rates: dict[str, str]  # Asset -> current borrow rate (APR)
    timestamp: int


class BackpackBorrowMarketHistory(msgspec.Struct, frozen=True):
    """Historical borrow market data point."""
    
    asset: str
    timestamp: int
    borrowRate: str
    lendRate: str
    totalBorrowed: str
    totalSupply: str
    utilizationRate: str
    volume24h: str  # Borrow/lend volume in 24h


class BackpackLendingPosition(msgspec.Struct, frozen=True):
    """Lending position (supplying assets to earn interest)."""
    
    asset: str
    supplied: str  # Amount supplied
    interestEarned: str  # Interest earned
    interestRate: str  # Current earning rate
    cumulativeInterest: str  # Total interest earned
    autoCompound: bool  # Whether interest auto-compounds
    lockedUntil: int | None  # Lock period end timestamp (if applicable)
    timestamp: int


class BackpackBorrowCapacity(msgspec.Struct, frozen=True):
    """User's borrowing capacity."""
    
    totalCollateral: str  # Total collateral value in USD
    totalBorrowed: str  # Total borrowed value in USD
    availableToBorrow: str  # Available to borrow in USD
    borrowLimitUsed: str  # Percentage of limit used
    maxBorrowByAsset: dict[str, str]  # Max borrowable per asset
    marginLevel: str  # Current margin level
    liquidationThreshold: str  # Liquidation threshold


class BackpackInterestRate(msgspec.Struct, frozen=True):
    """Interest rate information."""
    
    asset: str
    borrowRate: str  # Borrow APR
    lendRate: str  # Lend APR
    utilizationRate: str  # Pool utilization
    optimalUtilization: str  # Optimal utilization target
    baseRate: str  # Base interest rate
    slope1: str  # Rate slope below optimal
    slope2: str  # Rate slope above optimal
    timestamp: int


class BackpackBorrowEvent(msgspec.Struct, frozen=True):
    """Borrow/repay event from WebSocket."""
    
    e: str  # Event type "borrowEvent"
    E: int  # Event timestamp
    type: str  # "BORROW" or "REPAY"
    asset: str
    amount: str
    principal: str  # New principal amount
    interest: str  # Interest component
    borrowRate: str  # Rate at time of event
    T: int  # Engine timestamp


class BackpackLendEvent(msgspec.Struct, frozen=True):
    """Lend/withdraw event from WebSocket."""
    
    e: str  # Event type "lendEvent"
    E: int  # Event timestamp
    type: str  # "SUPPLY" or "WITHDRAW"
    asset: str
    amount: str
    supplied: str  # New supplied amount
    interestEarned: str  # Interest earned
    lendRate: str  # Rate at time of event
    T: int  # Engine timestamp


class BackpackUtilizationUpdate(msgspec.Struct, frozen=True):
    """Pool utilization update from WebSocket."""
    
    e: str  # Event type "utilizationUpdate"
    E: int  # Event timestamp
    asset: str
    utilizationRate: str
    totalBorrowed: str
    totalSupply: str
    borrowRate: str  # New borrow rate
    lendRate: str  # New lend rate
    T: int  # Engine timestamp