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
from typing import TYPE_CHECKING

from nautilus_trader.common.component import Logger

if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.http.account import BackpackAccountHttpAPI


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
    account_http : BackpackAccountHttpAPI, optional
        The account HTTP API for executing operations.
    logger : Logger
        The logger for the auto-borrow manager.
    max_borrow_rate : Decimal, optional
        Maximum acceptable borrow rate (APR as decimal).
    auto_borrow_threshold : Decimal, optional
        Minimum USDC shortage to trigger auto-borrow.
    auto_repay_enabled : bool, optional
        Whether auto-repay is enabled.
    """
    
    def __init__(
        self,
        account_http: "BackpackAccountHttpAPI | None" = None,
        logger: Logger | None = None,
        max_borrow_rate: Decimal = Decimal("0.50"),  # 50% APR max
        auto_borrow_threshold: Decimal = Decimal("1.0"),  # Min $1 shortage
        auto_repay_enabled: bool = True,
    ) -> None:
        self._account_http = account_http
        self._log = logger or Logger(name=self.__class__.__name__)
        self._max_borrow_rate = max_borrow_rate
        self._auto_borrow_threshold = auto_borrow_threshold
        self._auto_repay_enabled = auto_repay_enabled
        self._active_borrows: dict[str, Decimal] = {}  # asset -> amount
        
        # Market condition tracking
        self._market_rates: dict[str, Decimal] = {}  # asset -> current market rate
        self._rate_history: dict[str, list[Decimal]] = {}  # asset -> rate history
        self._volatility_score: Decimal = Decimal(0)  # Market volatility indicator
        
        # Auto-repay configuration
        self._repay_priority: list[str] = []  # Assets to repay first
        self._min_balance_after_repay = Decimal("100")  # Keep $100 minimum
        self._repay_threshold_rate = Decimal("0.10")  # Repay if rate > 10% APR
        self._scheduled_repayments: dict[str, int] = {}  # asset -> timestamp
    
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
    
    # Enhanced Auto-Repay Methods with Market Conditions
    
    def update_market_rate(self, asset: str, rate: Decimal) -> None:
        """
        Update market borrow rate for an asset.
        
        Parameters
        ----------
        asset : str
            The asset symbol.
        rate : Decimal
            The current borrow rate (APR).
        """
        self._market_rates[asset] = rate
        
        # Track rate history
        if asset not in self._rate_history:
            self._rate_history[asset] = []
        self._rate_history[asset].append(rate)
        
        # Keep only last 24 data points
        if len(self._rate_history[asset]) > 24:
            self._rate_history[asset].pop(0)
        
        # Calculate volatility
        if len(self._rate_history[asset]) >= 3:
            rates = self._rate_history[asset]
            avg_rate = sum(rates) / len(rates)
            variance = sum((r - avg_rate) ** 2 for r in rates) / len(rates)
            self._volatility_score = variance.sqrt()
    
    def should_auto_repay_advanced(
        self,
        asset: str,
        available_balance: Decimal,
        borrowed_amount: Decimal,
        current_rate: Decimal | None = None,
    ) -> tuple[bool, Decimal, str]:
        """
        Advanced auto-repay decision with market conditions.
        
        Parameters
        ----------
        asset : str
            The asset to repay.
        available_balance : Decimal
            The available balance.
        borrowed_amount : Decimal
            The borrowed amount.
        current_rate : Decimal, optional
            The current borrow rate.
            
        Returns
        -------
        tuple[bool, Decimal, str]
            (should_repay, repay_amount, reason)
        """
        if not self._auto_repay_enabled or borrowed_amount <= 0:
            return False, Decimal(0), "Auto-repay disabled or no borrow"
        
        # Use provided rate or fetch from market rates
        rate = current_rate or self._market_rates.get(asset, Decimal(0))
        
        reasons = []
        score = Decimal(0)
        
        # Factor 1: High interest rate
        if rate > self._repay_threshold_rate:
            score += Decimal("0.4")
            reasons.append(f"High rate: {rate:.2%}")
        
        # Factor 2: Rising rate trend
        if asset in self._rate_history and len(self._rate_history[asset]) >= 3:
            recent_rates = self._rate_history[asset][-3:]
            if all(recent_rates[i] <= recent_rates[i+1] for i in range(len(recent_rates)-1)):
                score += Decimal("0.2")
                reasons.append("Rising rate trend")
        
        # Factor 3: Excess balance available
        excess = available_balance - self._min_balance_after_repay
        if excess > borrowed_amount:
            score += Decimal("0.3")
            reasons.append(f"Excess balance: ${excess}")
        
        # Factor 4: High volatility (repay to reduce risk)
        if self._volatility_score > Decimal("0.05"):
            score += Decimal("0.1")
            reasons.append("High rate volatility")
        
        # Decision threshold
        if score >= Decimal("0.5"):
            # Calculate optimal repay amount
            max_repay = min(
                excess if excess > 0 else Decimal(0),
                borrowed_amount
            )
            
            # Partial repay if rate is moderate
            if rate < Decimal("0.20"):  # < 20% APR
                repay_amount = max_repay * Decimal("0.5")  # Repay 50%
            else:
                repay_amount = max_repay  # Full repay
            
            reason = f"Auto-repay triggered: {', '.join(reasons)} (score: {score})"
            return True, repay_amount, reason
        
        return False, Decimal(0), f"Score {score} below threshold"
    
    async def execute_auto_repay(
        self,
        asset: str,
        amount: Decimal,
        reason: str,
    ) -> bool:
        """
        Execute auto-repay operation.
        
        Parameters
        ----------
        asset : str
            The asset to repay.
        amount : Decimal
            The amount to repay.
        reason : str
            The reason for repayment.
            
        Returns
        -------
        bool
            True if repayment successful.
        """
        if not self._account_http:
            self._log.warning("No account HTTP client available for auto-repay")
            return False
        
        try:
            self._log.info(f"Executing auto-repay: {amount} {asset} - {reason}")
            
            # Execute repay via API
            result = await self._account_http.execute_repay(
                asset=asset,
                amount=str(amount),
            )
            
            # Update tracking
            if result:
                current = self._active_borrows.get(asset, Decimal(0))
                new_amount = max(Decimal(0), current - amount)
                if new_amount > 0:
                    self._active_borrows[asset] = new_amount
                else:
                    self._active_borrows.pop(asset, None)
                
                self._log.info(
                    f"Auto-repay successful: {amount} {asset} "
                    f"(remaining: {new_amount})"
                )
                return True
            
        except Exception as e:
            self._log.error(f"Auto-repay failed: {e}")
        
        return False
    
    def set_repay_priority(self, assets: list[str]) -> None:
        """
        Set priority order for auto-repayment.
        
        Parameters
        ----------
        assets : list[str]
            Ordered list of assets (highest priority first).
        """
        self._repay_priority = assets
        self._log.info(f"Repay priority set: {assets}")
    
    def get_repayment_plan(
        self,
        available_balances: dict[str, Decimal],
    ) -> list[tuple[str, Decimal, str]]:
        """
        Get optimized repayment plan based on current conditions.
        
        Parameters
        ----------
        available_balances : dict[str, Decimal]
            Available balances by asset.
            
        Returns
        -------
        list[tuple[str, Decimal, str]]
            List of (asset, amount, reason) to repay.
        """
        plan = []
        
        # Sort borrows by priority and rate
        sorted_borrows = sorted(
            self._active_borrows.items(),
            key=lambda x: (
                self._repay_priority.index(x[0]) if x[0] in self._repay_priority else 999,
                -self._market_rates.get(x[0], Decimal(0)),  # Higher rate first
            ),
        )
        
        for asset, borrowed in sorted_borrows:
            available = available_balances.get(asset, Decimal(0))
            
            should_repay, amount, reason = self.should_auto_repay_advanced(
                asset=asset,
                available_balance=available,
                borrowed_amount=borrowed,
            )
            
            if should_repay and amount > 0:
                plan.append((asset, amount, reason))
        
        return plan
    
    def estimate_interest_savings(
        self,
        asset: str,
        repay_amount: Decimal,
        days: int = 30,
    ) -> Decimal:
        """
        Estimate interest savings from repayment.
        
        Parameters
        ----------
        asset : str
            The asset to repay.
        repay_amount : Decimal
            The repayment amount.
        days : int, default 30
            Number of days to calculate savings.
            
        Returns
        -------
        Decimal
            Estimated interest savings.
        """
        rate = self._market_rates.get(asset, Decimal(0))
        if rate == 0:
            return Decimal(0)
        
        # Calculate interest that would accrue
        hours = days * 24
        interest = self.calculate_interest(repay_amount, rate, hours)
        
        return interest