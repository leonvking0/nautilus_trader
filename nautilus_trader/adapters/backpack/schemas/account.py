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

"""Backpack account data response schemas."""

import msgspec


class BackpackBalance(msgspec.Struct, frozen=True):
    """Account balance for a single asset."""

    symbol: str
    available: str
    locked: str
    staked: str


class BackpackAccount(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/account."""

    account_id: str
    balances: list[BackpackBalance]


class BackpackFill(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/fills."""

    trade_id: int
    order_id: str
    symbol: str
    side: str
    price: str
    quantity: str
    fee: str
    fee_symbol: str
    is_maker: bool
    timestamp: int
    client_id: str | None = None


class BackpackOrder(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/orders."""

    id: str
    client_id: str | None
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    price: str | None
    trigger_price: str | None
    quantity: str | None
    quote_quantity: str | None
    executed_quantity: str
    executed_quote_quantity: str
    status: str
    created_at: int
    self_trade_prevention: str | None = None
    post_only: bool | None = None
    reduce_only: bool | None = None


class BackpackOrderResponse(msgspec.Struct, frozen=True):
    """HTTP response from Backpack POST /api/order/execute."""

    id: str
    client_id: str | None
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    price: str | None
    trigger_price: str | None
    quantity: str | None
    quote_quantity: str | None
    status: str
    created_at: int


class BackpackCancelResponse(msgspec.Struct, frozen=True):
    """HTTP response from Backpack DELETE /api/order."""

    order: BackpackOrder


# Unified Account Model Schemas (Multi-currency Cross-margin)

class BackpackCollateralWeight(msgspec.Struct, frozen=True):
    """Collateral weight (haircut) for an asset."""
    
    asset: str
    weight: str  # 0.0 to 1.0, where 1.0 = 100% collateral value
    tier: int | None = None  # Size tier affecting weight


class BackpackCapital(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/v1/capital."""
    
    balances: list[BackpackBalance]
    totalCollateral: str  # Total USD value of all collateral
    availableCollateral: str  # Available for trading
    initialMarginRate: str  # IMR - for opening positions
    maintenanceMarginRate: str  # MMR - liquidation threshold
    totalBorrowLiability: str  # Total borrowed amount in USD
    unsettledBalances: str  # Pending settlements
    unrealizedPnl: str  # Unrealized P&L across all positions
    
    
class BackpackCollateral(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/v1/collateral."""
    
    assets: list[BackpackCollateralWeight]
    totalWeightedCollateral: str
    
    
class BackpackCollateralDetail(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/v1/capital/collateral."""
    
    asset: str
    quantity: str
    markPrice: str
    collateralValue: str  # quantity * markPrice * weight
    weight: str
    usdValue: str
    
    
class BackpackBorrowPosition(msgspec.Struct, frozen=True):
    """Borrow position for an asset."""
    
    asset: str
    borrowed: str
    interest: str
    interestRate: str
    cumulativeInterest: str
    timestamp: int
    
    
class BackpackAccountLimits(msgspec.Struct, frozen=True):
    """Account trading limits."""
    
    maxLeverage: int
    maxPositions: int
    maxOrders: int
    maxBorrowUSD: str
    maxSubaccounts: int
    currentSubaccounts: int
    
    
class BackpackUnifiedAccount(msgspec.Struct, frozen=True):
    """
    Unified account state for Backpack's cross-margin model.
    
    This represents the complete account state where spot, margin,
    and futures all share the same collateral pool.
    """
    
    # Account identification
    accountId: str
    subaccountId: str | None
    
    # Balances (multi-currency)
    balances: list[BackpackBalance]
    
    # Collateral information
    totalCollateral: str  # Total USD value
    availableCollateral: str  # Available for new positions
    collateralWeights: list[BackpackCollateralWeight]
    
    # Margin rates
    initialMarginRate: str  # IMR - required to open positions
    maintenanceMarginRate: str  # MMR - liquidation threshold
    marginRatio: str  # Current margin usage ratio
    
    # Positions across all markets
    spotBalances: list[BackpackBalance]  # Spot holdings
    futuresPositions: list  # Futures positions (from position endpoint)
    borrowPositions: list[BackpackBorrowPosition]  # Active borrows
    
    # Risk metrics
    totalBorrowLiability: str  # Total borrowed in USD
    unsettledBalances: str  # Pending settlements
    unrealizedPnl: str  # Total unrealized P&L
    realizedPnl: str  # Total realized P&L
    
    # Liquidation info
    liquidationPrice: str | None  # Estimated liquidation price
    timeTillLiquidation: int | None  # Milliseconds till liquidation
    
    # Account limits
    limits: BackpackAccountLimits | None
    
    # Timestamps
    timestamp: int  # Last update timestamp
    
    
class BackpackSubaccount(msgspec.Struct, frozen=True):
    """Subaccount information."""
    
    subaccountId: str
    name: str
    isActive: bool
    createdAt: int
    totalCollateral: str
    marginRatio: str