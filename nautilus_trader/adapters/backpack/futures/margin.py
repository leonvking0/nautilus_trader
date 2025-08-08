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
Backpack futures margin calculator for perpetuals-specific margin calculations.
"""

from decimal import Decimal
from typing import TYPE_CHECKING

from nautilus_trader.common.component import Logger

if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.futures.schemas.position import BackpackFuturesPosition


class BackpackFuturesMarginCalculator:
    """
    Calculates margin requirements for Backpack perpetual futures.
    
    Handles:
    - Initial margin calculations
    - Maintenance margin calculations
    - Liquidation price calculations
    - Margin ratio calculations
    - Position value calculations
    
    Parameters
    ----------
    logger : Logger, optional
        The logger for the calculator.
    """
    
    # Maintenance margin tiers (Backpack uses tiered system)
    # These are example values - should be fetched from exchange
    MARGIN_TIERS = [
        {"notional_cap": Decimal("10000"), "maint_margin_rate": Decimal("0.004"), "maint_amount": Decimal("0")},
        {"notional_cap": Decimal("50000"), "maint_margin_rate": Decimal("0.005"), "maint_amount": Decimal("10")},
        {"notional_cap": Decimal("250000"), "maint_margin_rate": Decimal("0.01"), "maint_amount": Decimal("260")},
        {"notional_cap": Decimal("1000000"), "maint_margin_rate": Decimal("0.025"), "maint_amount": Decimal("4010")},
        {"notional_cap": Decimal("5000000"), "maint_margin_rate": Decimal("0.05"), "maint_amount": Decimal("29010")},
        {"notional_cap": Decimal("10000000"), "maint_margin_rate": Decimal("0.1"), "maint_amount": Decimal("279010")},
        {"notional_cap": Decimal("20000000"), "maint_margin_rate": Decimal("0.125"), "maint_amount": Decimal("529010")},
        {"notional_cap": Decimal("50000000"), "maint_margin_rate": Decimal("0.15"), "maint_amount": Decimal("1029010")},
    ]
    
    def __init__(self, logger: Logger | None = None) -> None:
        self._log = logger or Logger(name=self.__class__.__name__)
    
    def calculate_initial_margin(
        self,
        quantity: Decimal,
        price: Decimal,
        leverage: int,
    ) -> Decimal:
        """
        Calculate initial margin required for a position.
        
        Parameters
        ----------
        quantity : Decimal
            The position size (contracts).
        price : Decimal
            The entry price.
        leverage : int
            The leverage (1-125).
            
        Returns
        -------
        Decimal
            The initial margin required.
        """
        if leverage <= 0:
            raise ValueError(f"Invalid leverage: {leverage}")
        
        notional = abs(quantity * price)
        initial_margin = notional / Decimal(leverage)
        
        self._log.debug(
            f"Initial margin calculated: notional={notional}, "
            f"leverage={leverage}x, IM={initial_margin}"
        )
        
        return initial_margin
    
    def calculate_maintenance_margin(
        self,
        quantity: Decimal,
        price: Decimal,
    ) -> Decimal:
        """
        Calculate maintenance margin for a position.
        
        Uses tiered maintenance margin rates based on notional value.
        
        Parameters
        ----------
        quantity : Decimal
            The position size (contracts).
        price : Decimal
            The mark price.
            
        Returns
        -------
        Decimal
            The maintenance margin required.
        """
        notional = abs(quantity * price)
        
        # Find applicable tier
        for tier in self.MARGIN_TIERS:
            if notional <= tier["notional_cap"]:
                maint_margin = notional * tier["maint_margin_rate"] + tier["maint_amount"]
                
                self._log.debug(
                    f"Maintenance margin: notional={notional}, "
                    f"rate={tier['maint_margin_rate']}, MM={maint_margin}"
                )
                
                return maint_margin
        
        # Use highest tier if above all caps
        highest_tier = self.MARGIN_TIERS[-1]
        maint_margin = notional * highest_tier["maint_margin_rate"] + highest_tier["maint_amount"]
        
        return maint_margin
    
    def calculate_margin_ratio(
        self,
        position_value: Decimal,
        unrealized_pnl: Decimal,
        collateral: Decimal,
        maintenance_margin: Decimal,
    ) -> Decimal:
        """
        Calculate margin ratio (maintenance margin ratio).
        
        Parameters
        ----------
        position_value : Decimal
            The current position value.
        unrealized_pnl : Decimal
            The unrealized P&L.
        collateral : Decimal
            The available collateral.
        maintenance_margin : Decimal
            The maintenance margin required.
            
        Returns
        -------
        Decimal
            The margin ratio (0-1, where 1 = 100% = liquidation).
        """
        if collateral <= 0:
            return Decimal("1.0")  # Max risk
        
        # Account equity = collateral + unrealized PnL
        equity = collateral + unrealized_pnl
        
        if equity <= 0:
            return Decimal("1.0")  # Liquidation
        
        # Margin ratio = Maintenance Margin / Account Equity
        margin_ratio = maintenance_margin / equity
        
        self._log.debug(
            f"Margin ratio: MM={maintenance_margin}, equity={equity}, "
            f"ratio={margin_ratio:.4f}"
        )
        
        return margin_ratio
    
    def calculate_liquidation_price(
        self,
        quantity: Decimal,
        entry_price: Decimal,
        is_long: bool,
        collateral: Decimal,
        leverage: int,
    ) -> Decimal:
        """
        Calculate the liquidation price for a position.
        
        Parameters
        ----------
        quantity : Decimal
            The position size (contracts).
        entry_price : Decimal
            The entry price.
        is_long : bool
            Whether the position is long.
        collateral : Decimal
            The collateral allocated to position.
        leverage : int
            The leverage used.
            
        Returns
        -------
        Decimal
            The liquidation price.
        """
        if quantity == 0:
            return Decimal("0")
        
        abs_quantity = abs(quantity)
        
        # Get maintenance margin rate for the position
        notional = abs_quantity * entry_price
        mm_rate = self._get_maintenance_margin_rate(notional)
        
        # Initial margin
        initial_margin = self.calculate_initial_margin(abs_quantity, entry_price, leverage)
        
        if is_long:
            # Long position liquidates when:
            # Price = Entry * (1 - 1/leverage + mm_rate)
            liquidation_price = entry_price * (Decimal("1") - Decimal("1")/Decimal(leverage) + mm_rate)
        else:
            # Short position liquidates when:
            # Price = Entry * (1 + 1/leverage - mm_rate)
            liquidation_price = entry_price * (Decimal("1") + Decimal("1")/Decimal(leverage) - mm_rate)
        
        # Ensure non-negative
        liquidation_price = max(Decimal("0"), liquidation_price)
        
        self._log.debug(
            f"Liquidation price: entry={entry_price}, "
            f"is_long={is_long}, leverage={leverage}x, "
            f"liq_price={liquidation_price}"
        )
        
        return liquidation_price
    
    def _get_maintenance_margin_rate(self, notional: Decimal) -> Decimal:
        """
        Get the maintenance margin rate for a notional value.
        
        Parameters
        ----------
        notional : Decimal
            The notional position value.
            
        Returns
        -------
        Decimal
            The maintenance margin rate.
        """
        for tier in self.MARGIN_TIERS:
            if notional <= tier["notional_cap"]:
                return tier["maint_margin_rate"]
        
        # Use highest tier rate if above all caps
        return self.MARGIN_TIERS[-1]["maint_margin_rate"]
    
    def calculate_max_position_size(
        self,
        available_balance: Decimal,
        price: Decimal,
        leverage: int,
    ) -> Decimal:
        """
        Calculate maximum position size given available balance.
        
        Parameters
        ----------
        available_balance : Decimal
            The available balance for trading.
        price : Decimal
            The current price.
        leverage : int
            The leverage to use.
            
        Returns
        -------
        Decimal
            The maximum position size (contracts).
        """
        if price <= 0 or leverage <= 0:
            return Decimal("0")
        
        # Max notional = available_balance * leverage
        max_notional = available_balance * Decimal(leverage)
        
        # Max position size = max_notional / price
        max_size = max_notional / price
        
        self._log.debug(
            f"Max position size: balance={available_balance}, "
            f"price={price}, leverage={leverage}x, max_size={max_size}"
        )
        
        return max_size
    
    def calculate_unrealized_pnl(
        self,
        quantity: Decimal,
        entry_price: Decimal,
        mark_price: Decimal,
        is_long: bool,
    ) -> Decimal:
        """
        Calculate unrealized P&L for a position.
        
        Parameters
        ----------
        quantity : Decimal
            The position size (contracts).
        entry_price : Decimal
            The entry price.
        mark_price : Decimal
            The current mark price.
        is_long : bool
            Whether the position is long.
            
        Returns
        -------
        Decimal
            The unrealized P&L.
        """
        abs_quantity = abs(quantity)
        
        if is_long:
            # Long P&L = quantity * (mark_price - entry_price)
            pnl = abs_quantity * (mark_price - entry_price)
        else:
            # Short P&L = quantity * (entry_price - mark_price)
            pnl = abs_quantity * (entry_price - mark_price)
        
        self._log.debug(
            f"Unrealized P&L: qty={quantity}, entry={entry_price}, "
            f"mark={mark_price}, is_long={is_long}, pnl={pnl}"
        )
        
        return pnl
    
    def calculate_funding_payment(
        self,
        position_value: Decimal,
        funding_rate: Decimal,
    ) -> Decimal:
        """
        Calculate funding payment for a position.
        
        Parameters
        ----------
        position_value : Decimal
            The position value (quantity * mark_price).
        funding_rate : Decimal
            The funding rate (e.g., 0.0001 for 0.01%).
            
        Returns
        -------
        Decimal
            The funding payment (positive = receive, negative = pay).
        """
        # Funding payment = position_value * funding_rate
        # Long positions pay when rate is positive
        # Short positions receive when rate is positive
        payment = position_value * funding_rate
        
        self._log.debug(
            f"Funding payment: value={position_value}, "
            f"rate={funding_rate}, payment={payment}"
        )
        
        return payment
    
    def validate_leverage(self, leverage: int, max_leverage: int = 125) -> bool:
        """
        Validate that leverage is within acceptable range.
        
        Parameters
        ----------
        leverage : int
            The leverage to validate.
        max_leverage : int, default 125
            The maximum allowed leverage.
            
        Returns
        -------
        bool
            True if leverage is valid.
        """
        return 1 <= leverage <= max_leverage
    
    def get_margin_info(
        self,
        position: "BackpackFuturesPosition",
        mark_price: Decimal,
        collateral: Decimal,
    ) -> dict:
        """
        Get comprehensive margin information for a position.
        
        Parameters
        ----------
        position : BackpackFuturesPosition
            The futures position.
        mark_price : Decimal
            The current mark price.
        collateral : Decimal
            The available collateral.
            
        Returns
        -------
        dict
            Margin information including all calculations.
        """
        # Calculate all margin metrics
        initial_margin = self.calculate_initial_margin(
            position.quantity,
            position.entry_price,
            position.leverage,
        )
        
        maintenance_margin = self.calculate_maintenance_margin(
            position.quantity,
            mark_price,
        )
        
        unrealized_pnl = self.calculate_unrealized_pnl(
            position.quantity,
            position.entry_price,
            mark_price,
            position.side == "LONG",
        )
        
        position_value = abs(position.quantity * mark_price)
        
        margin_ratio = self.calculate_margin_ratio(
            position_value,
            unrealized_pnl,
            collateral,
            maintenance_margin,
        )
        
        liquidation_price = self.calculate_liquidation_price(
            position.quantity,
            position.entry_price,
            position.side == "LONG",
            collateral,
            position.leverage,
        )
        
        return {
            "symbol": position.symbol,
            "side": position.side,
            "quantity": float(position.quantity),
            "entry_price": float(position.entry_price),
            "mark_price": float(mark_price),
            "leverage": position.leverage,
            "initial_margin": float(initial_margin),
            "maintenance_margin": float(maintenance_margin),
            "position_value": float(position_value),
            "unrealized_pnl": float(unrealized_pnl),
            "margin_ratio": float(margin_ratio),
            "liquidation_price": float(liquidation_price),
            "margin_health": "SAFE" if margin_ratio < Decimal("0.8") else "WARNING" if margin_ratio < Decimal("0.95") else "DANGER",
        }