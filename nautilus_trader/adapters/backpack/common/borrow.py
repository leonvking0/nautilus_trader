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
Backpack Exchange auto-borrow functionality for unified account.
"""

from decimal import Decimal
from enum import Enum

from nautilus_trader.common.component import Logger


class BorrowType(Enum):
    """Type of borrow operation."""
    
    AUTO = "AUTO"  # Automatic borrow when insufficient
    MANUAL = "MANUAL"  # Manual borrow request
    SETTLEMENT = "SETTLEMENT"  # For settlement needs


class BackpackAutoBorrow:
    """
    Manages auto-borrow functionality for Backpack's unified account.
    
    Backpack automatically creates USDC borrows when insufficient funds
    exist for settlement, avoiding unnecessary liquidation of collateral.
    
    Parameters
    ----------
    logger : Logger
        The logger for the auto-borrow manager.
    max_borrow_rate : Decimal, optional
        Maximum acceptable borrow rate (APR as decimal).
    auto_borrow_threshold : Decimal, optional
        Minimum USDC shortage to trigger auto-borrow.
    """
    
    def __init__(
        self,
        logger: Logger,
        max_borrow_rate: Decimal = Decimal("0.50"),  # 50% APR max
        auto_borrow_threshold: Decimal = Decimal("1.0"),  # Min $1 shortage
    ) -> None:
        self._log = logger
        self._max_borrow_rate = max_borrow_rate
        self._auto_borrow_threshold = auto_borrow_threshold
        self._active_borrows: dict[str, Decimal] = {}  # asset -> amount
    
    def check_borrow_needed(
        self,
        required_usdc: Decimal,
        available_usdc: Decimal,
        include_pending: bool = True,
    ) -> tuple[bool, Decimal]:
        """
        Check if auto-borrow is needed for USDC.
        
        Parameters
        ----------
        required_usdc : Decimal
            The USDC amount required.
        available_usdc : Decimal
            The available USDC balance.
        include_pending : bool, default True
            Whether to include pending settlements.
            
        Returns
        -------
        tuple[bool, Decimal]
            (needs_borrow, shortage_amount)
        """
        shortage = required_usdc - available_usdc
        
        if shortage <= 0:
            return False, Decimal(0)
        
        if shortage < self._auto_borrow_threshold:
            self._log.debug(
                f"USDC shortage ${shortage} below threshold ${self._auto_borrow_threshold}",
            )
            return False, Decimal(0)
        
        self._log.info(f"Auto-borrow needed: ${shortage} USDC required")
        return True, shortage
    
    def calculate_borrow_amount(
        self,
        shortage: Decimal,
        buffer_multiplier: Decimal = Decimal("1.1"),  # 10% buffer
    ) -> Decimal:
        """
        Calculate optimal borrow amount with buffer.
        
        Parameters
        ----------
        shortage : Decimal
            The shortage amount.
        buffer_multiplier : Decimal, default 1.1
            Multiplier for buffer (1.1 = 10% extra).
            
        Returns
        -------
        Decimal
            The amount to borrow.
        """
        # Round up to nearest dollar with buffer
        borrow_amount = shortage * buffer_multiplier
        borrow_amount = borrow_amount.quantize(Decimal("1"))  # Round to dollar
        
        self._log.debug(f"Calculated borrow amount: ${borrow_amount} (shortage: ${shortage})")
        return borrow_amount
    
    def can_borrow(
        self,
        amount: Decimal,
        current_rate: Decimal,
        collateral_available: Decimal,
        max_ltv: Decimal = Decimal("0.80"),  # 80% max loan-to-value
    ) -> tuple[bool, str]:
        """
        Check if borrow is allowed based on risk parameters.
        
        Parameters
        ----------
        amount : Decimal
            The amount to borrow.
        current_rate : Decimal
            The current borrow rate (APR).
        collateral_available : Decimal
            The available collateral value.
        max_ltv : Decimal, default 0.80
            Maximum loan-to-value ratio.
            
        Returns
        -------
        tuple[bool, str]
            (can_borrow, reason_if_not)
        """
        # Check rate limit
        if current_rate > self._max_borrow_rate:
            return False, f"Rate {current_rate} exceeds max {self._max_borrow_rate}"
        
        # Check collateral coverage
        max_borrow = collateral_available * max_ltv
        if amount > max_borrow:
            return False, f"Amount ${amount} exceeds max borrow ${max_borrow} (LTV {max_ltv})"
        
        return True, ""
    
    def calculate_interest(
        self,
        principal: Decimal,
        rate: Decimal,
        hours: int = 1,
    ) -> Decimal:
        """
        Calculate hourly interest for a borrow.
        
        Backpack typically charges interest hourly.
        
        Parameters
        ----------
        principal : Decimal
            The borrowed amount.
        rate : Decimal
            The annual interest rate (as decimal).
        hours : int, default 1
            Number of hours.
            
        Returns
        -------
        Decimal
            The interest amount.
        """
        # Convert annual rate to hourly
        hours_per_year = Decimal("8760")  # 365 * 24
        hourly_rate = rate / hours_per_year
        
        interest = principal * hourly_rate * Decimal(hours)
        
        return interest.quantize(Decimal("0.000001"))  # 6 decimal places
    
    def track_borrow(
        self,
        asset: str,
        amount: Decimal,
        rate: Decimal,
    ) -> None:
        """
        Track an active borrow.
        
        Parameters
        ----------
        asset : str
            The borrowed asset.
        amount : Decimal
            The borrowed amount.
        rate : Decimal
            The borrow rate.
        """
        current = self._active_borrows.get(asset, Decimal(0))
        self._active_borrows[asset] = current + amount
        
        self._log.info(
            f"Tracked borrow: {amount} {asset} at {rate:.2%} APR "
            f"(total: {self._active_borrows[asset]})",
        )
    
    def get_total_borrow_liability(
        self,
        prices: dict[str, Decimal] | None = None,
    ) -> Decimal:
        """
        Get total borrow liability in USD.
        
        Parameters
        ----------
        prices : dict[str, Decimal], optional
            Asset prices in USD. If None, assumes all are USD-denominated.
            
        Returns
        -------
        Decimal
            The total borrow liability.
        """
        total = Decimal(0)
        
        for asset, amount in self._active_borrows.items():
            if prices and asset in prices:
                total += amount * prices[asset]
            elif asset in ["USDC", "USDT", "USD"]:
                total += amount
            else:
                self._log.warning(f"No price for borrowed asset {asset}")
        
        return total
    
    def should_repay(
        self,
        asset: str,
        available_balance: Decimal,
        borrowed_amount: Decimal,
        keep_buffer: Decimal = Decimal("100"),  # Keep $100 buffer
    ) -> tuple[bool, Decimal]:
        """
        Check if we should repay a borrow.
        
        Parameters
        ----------
        asset : str
            The asset to repay.
        available_balance : Decimal
            The available balance.
        borrowed_amount : Decimal
            The borrowed amount.
        keep_buffer : Decimal, default 100
            Buffer to keep after repayment.
            
        Returns
        -------
        tuple[bool, Decimal]
            (should_repay, repay_amount)
        """
        if borrowed_amount <= 0:
            return False, Decimal(0)
        
        # Can we repay and keep buffer?
        max_repay = max(Decimal(0), available_balance - keep_buffer)
        
        if max_repay <= 0:
            return False, Decimal(0)
        
        # Repay as much as possible
        repay_amount = min(max_repay, borrowed_amount)
        
        if repay_amount > 0:
            self._log.info(f"Should repay {repay_amount} {asset} of {borrowed_amount} borrowed")
            return True, repay_amount
        
        return False, Decimal(0)
    
    def clear_borrow(self, asset: str) -> None:
        """
        Clear a tracked borrow after repayment.
        
        Parameters
        ----------
        asset : str
            The asset that was repaid.
        """
        if asset in self._active_borrows:
            amount = self._active_borrows.pop(asset)
            self._log.info(f"Cleared {asset} borrow of {amount}")