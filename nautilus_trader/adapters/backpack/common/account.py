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
Backpack Exchange unified account management.
"""

from decimal import Decimal

from nautilus_trader.accounting.accounts.margin import MarginAccount
from nautilus_trader.adapters.backpack.common.borrow import BackpackAutoBorrow
from nautilus_trader.adapters.backpack.common.collateral import BackpackCollateralCalculator
from nautilus_trader.adapters.backpack.http.account import BackpackAccountHttpAPI
from nautilus_trader.adapters.backpack.schemas.account import BackpackCapital
from nautilus_trader.adapters.backpack.schemas.account import BackpackUnifiedAccount
from nautilus_trader.common.component import Logger
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.currency import Currency
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.objects import MarginBalance
from nautilus_trader.model.objects import Money


class BackpackUnifiedAccountManager:
    """
    Manages Backpack's unified multi-currency cross-margin account.
    
    This manager handles the unified account where spot, margin, and futures
    all share the same collateral pool with cross-margining.
    
    Parameters
    ----------
    account_http : BackpackAccountHttpAPI
        The account HTTP API client.
    logger : Logger
        The logger for the manager.
    """
    
    def __init__(
        self,
        account_http: BackpackAccountHttpAPI,
        logger: Logger,
    ) -> None:
        self._account_http = account_http
        self._log = logger
        
        # Components
        self._collateral_calc = BackpackCollateralCalculator(logger)
        self._auto_borrow = BackpackAutoBorrow(logger)
        
        # State
        self._unified_account: BackpackUnifiedAccount | None = None
        self._nautilus_account: MarginAccount | None = None
        self._collateral_weights: dict[str, Decimal] = {}
        self._mark_prices: dict[str, Decimal] = {}
        self._subaccount_id: str | None = None
    
    async def initialize(
        self,
        account_id: AccountId,
        base_currency: Currency | None = None,
    ) -> MarginAccount:
        """
        Initialize the unified account.
        
        Parameters
        ----------
        account_id : AccountId
            The account identifier.
        base_currency : Currency, optional
            The base currency for the account.
            
        Returns
        -------
        MarginAccount
            The initialized Nautilus account.
        """
        # Fetch initial account state
        await self.refresh_account_state()
        
        # Create Nautilus account
        self._nautilus_account = MarginAccount(
            account_id=account_id,
            type=AccountType.MARGIN,  # Unified is margin type
            base_currency=base_currency,
            calculate_account_state=True,
        )
        
        # Update with current state
        if self._unified_account:
            self._update_nautilus_account()
        
        self._log.info(f"Initialized unified account {account_id}")
        return self._nautilus_account
    
    async def refresh_account_state(self) -> BackpackUnifiedAccount | None:
        """
        Refresh the complete unified account state.
        
        Returns
        -------
        BackpackUnifiedAccount | None
            The refreshed account state.
        """
        try:
            # Fetch all account data
            capital = await self._account_http.fetch_capital()
            collateral = await self._account_http.fetch_collateral()
            collateral_details = await self._account_http.fetch_collateral_details()
            borrow_positions = await self._account_http.fetch_borrow_positions()
            limits = await self._account_http.fetch_account_limits()
            
            # Update collateral weights
            self._collateral_weights = {
                asset.asset: Decimal(asset.weight)
                for asset in collateral.assets
            }
            
            # Update mark prices from collateral details
            for detail in collateral_details:
                self._mark_prices[detail.asset] = Decimal(detail.markPrice)
            
            # Create unified account
            self._unified_account = BackpackUnifiedAccount(
                accountId="unified",
                subaccountId=self._subaccount_id,
                balances=capital.balances,
                totalCollateral=capital.totalCollateral,
                availableCollateral=capital.availableCollateral,
                collateralWeights=collateral.assets,
                initialMarginRate=capital.initialMarginRate,
                maintenanceMarginRate=capital.maintenanceMarginRate,
                marginRatio=str(
                    Decimal(capital.maintenanceMarginRate) / Decimal(capital.totalCollateral)
                    if Decimal(capital.totalCollateral) > 0 else Decimal(0)
                ),
                spotBalances=capital.balances,
                futuresPositions=[],  # Will be populated by futures client
                borrowPositions=borrow_positions,
                totalBorrowLiability=capital.totalBorrowLiability,
                unsettledBalances=capital.unsettledBalances,
                unrealizedPnl=capital.unrealizedPnl,
                realizedPnl="0",  # Not provided in capital response
                liquidationPrice=None,  # Calculate based on positions
                timeTillLiquidation=None,  # Calculate based on margin ratio
                limits=limits,
                timestamp=millis_to_nanos(int(Decimal("1000") * Decimal(capital.totalCollateral))),  # Approximate
            )
            
            # Update Nautilus account if exists
            if self._nautilus_account:
                self._update_nautilus_account()
            
            return self._unified_account
            
        except Exception as e:
            self._log.error(f"Failed to refresh account state: {e}")
            return None
    
    def _update_nautilus_account(self) -> None:
        """Update the Nautilus account from unified account state."""
        if not self._unified_account or not self._nautilus_account:
            return
        
        # Convert balances
        balances = []
        margins = []
        
        for balance in self._unified_account.balances:
            currency = Currency.from_str(balance.symbol)
            
            # Create account balance
            total = Decimal(balance.available) + Decimal(balance.locked)
            free = Decimal(balance.available)
            locked = Decimal(balance.locked)
            
            account_balance = AccountBalance(
                currency=currency,
                total=Money(total, currency),
                free=Money(free, currency),
                locked=Money(locked, currency),
            )
            balances.append(account_balance)
            
            # Create margin balance if has collateral weight
            weight = self._collateral_weights.get(balance.symbol, Decimal(0))
            if weight > 0:
                margin_balance = MarginBalance(
                    currency=currency,
                    initial=Money(total * weight * Decimal("0.9"), currency),  # 90% of collateral
                    maintenance=Money(total * weight * Decimal("0.95"), currency),  # 95% of collateral
                )
                margins.append(margin_balance)
        
        # Update account
        self._nautilus_account.update_balances(
            balances=balances,
            margins=margins,
            ts_event=self._unified_account.timestamp,
        )
    
    def get_unified_positions(self) -> list[dict]:
        """
        Get unified position information across spot and futures.
        
        Returns
        -------
        list[dict]
            List of unified position information.
        """
        if not self._unified_account:
            return []
        
        positions = []
        
        # Add spot positions (from balances)
        for balance in self._unified_account.balances:
            if Decimal(balance.available) + Decimal(balance.locked) > 0:
                positions.append({
                    "type": "spot",
                    "symbol": balance.symbol,
                    "quantity": str(Decimal(balance.available) + Decimal(balance.locked)),
                    "value_usdc": str(
                        (Decimal(balance.available) + Decimal(balance.locked)) *
                        Decimal(self._mark_prices.get(balance.symbol, "1"))
                    ),
                    "collateral_value": str(
                        (Decimal(balance.available) + Decimal(balance.locked)) *
                        Decimal(self._mark_prices.get(balance.symbol, "1")) *
                        Decimal(self._collateral_weights.get(balance.symbol, "0"))
                    ),
                })
        
        # Add futures positions
        for position in self._unified_account.futuresPositions:
            positions.append({
                "type": "futures",
                "symbol": position.symbol,
                "side": position.side,
                "quantity": str(position.size),
                "entry_price": str(position.entryPrice),
                "mark_price": str(position.markPrice),
                "unrealized_pnl": str(position.unrealizedPnl),
                "margin_used": str(
                    Decimal(position.size) * Decimal(position.markPrice) *
                    Decimal(self._unified_account.initialMarginRate)
                ),
            })
        
        return positions
    
    def calculate_total_margin_used(self) -> Decimal:
        """
        Calculate total margin used across all positions.
        
        Returns
        -------
        Decimal
            Total margin used.
        """
        if not self._unified_account:
            return Decimal(0)
        
        total_margin = Decimal(0)
        
        # Add margin from futures positions
        for position in self._unified_account.futuresPositions:
            position_value = Decimal(position.size) * Decimal(position.markPrice)
            margin_required = position_value * Decimal(self._unified_account.initialMarginRate)
            total_margin += margin_required
        
        # Add margin from borrow positions
        total_margin += Decimal(self._unified_account.totalBorrowLiability)
        
        return total_margin
    
    async def check_and_execute_auto_borrow(
        self,
        required_usdc: Decimal,
    ) -> bool:
        """
        Check and execute auto-borrow if needed.
        
        Parameters
        ----------
        required_usdc : Decimal
            The required USDC amount.
            
        Returns
        -------
        bool
            True if borrow was executed or not needed.
        """
        if not self._unified_account:
            await self.refresh_account_state()
        
        # Get available USDC
        usdc_balance = next(
            (b for b in self._unified_account.balances if b.symbol == "USDC"),
            None,
        )
        available_usdc = Decimal(usdc_balance.available) if usdc_balance else Decimal(0)
        
        # Check if borrow needed
        needs_borrow, shortage = self._auto_borrow.check_borrow_needed(
            required_usdc=required_usdc,
            available_usdc=available_usdc,
        )
        
        if not needs_borrow:
            return True
        
        # Calculate borrow amount
        borrow_amount = self._auto_borrow.calculate_borrow_amount(shortage)
        
        # Check if we can borrow
        can_borrow, reason = self._auto_borrow.can_borrow(
            amount=borrow_amount,
            current_rate=Decimal("0.10"),  # 10% APR example
            collateral_available=Decimal(self._unified_account.availableCollateral),
        )
        
        if not can_borrow:
            self._log.warning(f"Cannot auto-borrow: {reason}")
            return False
        
        # Execute borrow
        try:
            result = await self._account_http.execute_borrow(
                asset="USDC",
                amount=str(borrow_amount),
            )
            
            self._auto_borrow.track_borrow(
                asset="USDC",
                amount=borrow_amount,
                rate=Decimal("0.10"),
            )
            
            self._log.info(f"Auto-borrowed {borrow_amount} USDC: {result}")
            
            # Refresh account state
            await self.refresh_account_state()
            
            return True
            
        except Exception as e:
            self._log.error(f"Failed to execute auto-borrow: {e}")
            return False
    
    def get_available_equity(self) -> Decimal:
        """
        Get available equity for opening new positions.
        
        Returns
        -------
        Decimal
            The available equity.
        """
        if not self._unified_account:
            return Decimal(0)
        
        return self._collateral_calc.calculate_available_equity(
            total_collateral=Decimal(self._unified_account.totalCollateral),
            unrealized_pnl=Decimal(self._unified_account.unrealizedPnl),
            borrow_liability=Decimal(self._unified_account.totalBorrowLiability),
            unsettled_balances=Decimal(self._unified_account.unsettledBalances),
            initial_margin_used=Decimal(self._unified_account.initialMarginRate) 
                * Decimal(self._unified_account.totalCollateral),
        )
    
    def get_margin_ratio(self) -> Decimal:
        """
        Get current margin ratio (MMR).
        
        Returns
        -------
        Decimal
            The margin ratio (0.0 to 1.0+).
        """
        if not self._unified_account:
            return Decimal(0)
        
        return Decimal(self._unified_account.marginRatio)
    
    def is_liquidatable(self) -> bool:
        """
        Check if account is liquidatable.
        
        Returns
        -------
        bool
            True if margin ratio >= 1.0 (100%).
        """
        return self.get_margin_ratio() >= Decimal("1.0")
    
    async def switch_subaccount(self, subaccount_id: str) -> bool:
        """
        Switch to a different subaccount.
        
        Parameters
        ----------
        subaccount_id : str
            The subaccount ID to switch to.
            
        Returns
        -------
        bool
            True if switch was successful.
        """
        try:
            result = await self._account_http.switch_subaccount(subaccount_id)
            self._subaccount_id = subaccount_id
            
            # Refresh account state for new subaccount
            await self.refresh_account_state()
            
            self._log.info(f"Switched to subaccount {subaccount_id}: {result}")
            return True
            
        except Exception as e:
            self._log.error(f"Failed to switch subaccount: {e}")
            return False