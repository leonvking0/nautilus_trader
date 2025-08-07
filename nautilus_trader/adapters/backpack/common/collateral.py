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
Backpack Exchange collateral calculator for unified cross-margin account.
"""

from decimal import Decimal

from nautilus_trader.adapters.backpack.schemas.account import BackpackBalance
from nautilus_trader.adapters.backpack.schemas.account import BackpackCollateralWeight
from nautilus_trader.common.component import Logger
from nautilus_trader.model.objects import Price


class BackpackCollateralCalculator:
    """
    Calculates collateral values for Backpack's multi-currency cross-margin model.
    
    In Backpack's unified account:
    - All assets contribute to collateral with weights (haircuts)
    - Collateral Value = Token Quantity * Mark Price * Weight
    - Weights adjust dynamically based on position size and risk
    
    Parameters
    ----------
    logger : Logger
        The logger for the calculator.
    """
    
    def __init__(self, logger: Logger) -> None:
        self._log = logger
    
    def calculate_asset_collateral(
        self,
        asset: str,
        quantity: Decimal,
        mark_price: Decimal,
        weight: Decimal,
    ) -> Decimal:
        """
        Calculate collateral value for a single asset.
        
        Parameters
        ----------
        asset : str
            The asset symbol.
        quantity : Decimal
            The asset quantity.
        mark_price : Decimal
            The mark price in USD.
        weight : Decimal
            The collateral weight (0.0 to 1.0).
            
        Returns
        -------
        Decimal
            The collateral value in USD.
        """
        if quantity <= 0:
            return Decimal(0)
        
        if weight < 0 or weight > 1:
            self._log.warning(f"Invalid weight {weight} for {asset}, clamping to [0, 1]")
            weight = max(Decimal(0), min(Decimal(1), weight))
        
        collateral_value = quantity * mark_price * weight
        
        self._log.debug(
            f"Collateral for {asset}: {quantity} * ${mark_price} * {weight} = ${collateral_value}",
        )
        
        return collateral_value
    
    def calculate_total_collateral(
        self,
        balances: list[BackpackBalance],
        prices: dict[str, Decimal],
        weights: dict[str, Decimal],
    ) -> Decimal:
        """
        Calculate total collateral value across all assets.
        
        Parameters
        ----------
        balances : list[BackpackBalance]
            The account balances.
        prices : dict[str, Decimal]
            The mark prices for each asset.
        weights : dict[str, Decimal]
            The collateral weights for each asset.
            
        Returns
        -------
        Decimal
            The total collateral value in USD.
        """
        total_collateral = Decimal(0)
        
        for balance in balances:
            asset = balance.symbol
            
            # Get available balance (not locked)
            quantity = Decimal(balance.available)
            
            # Skip if no balance
            if quantity <= 0:
                continue
            
            # Get price and weight
            price = prices.get(asset, Decimal(0))
            weight = weights.get(asset, Decimal(0))
            
            if price == 0:
                self._log.warning(f"No price for {asset}, skipping collateral calculation")
                continue
            
            # Calculate and add to total
            asset_collateral = self.calculate_asset_collateral(
                asset=asset,
                quantity=quantity,
                mark_price=price,
                weight=weight,
            )
            
            total_collateral += asset_collateral
        
        self._log.info(f"Total collateral value: ${total_collateral}")
        return total_collateral
    
    def calculate_available_equity(
        self,
        total_collateral: Decimal,
        unrealized_pnl: Decimal,
        borrow_liability: Decimal,
        unsettled_balances: Decimal,
        initial_margin_used: Decimal,
    ) -> Decimal:
        """
        Calculate available equity for opening new positions.
        
        Parameters
        ----------
        total_collateral : Decimal
            The total collateral value.
        unrealized_pnl : Decimal
            The unrealized P&L (can be negative).
        borrow_liability : Decimal
            The total borrow liability.
        unsettled_balances : Decimal
            The unsettled balance amount.
        initial_margin_used : Decimal
            The initial margin already used.
            
        Returns
        -------
        Decimal
            The available equity for new positions.
        """
        # Available = Collateral + Unrealized P&L - Borrows - Unsettled - Used Margin
        available = (
            total_collateral 
            + unrealized_pnl 
            - borrow_liability 
            - unsettled_balances 
            - initial_margin_used
        )
        
        self._log.debug(
            f"Available equity: ${total_collateral} + ${unrealized_pnl} "
            f"- ${borrow_liability} - ${unsettled_balances} - ${initial_margin_used} = ${available}",
        )
        
        return max(Decimal(0), available)  # Can't be negative
    
    def calculate_margin_ratio(
        self,
        maintenance_margin_required: Decimal,
        total_equity: Decimal,
    ) -> Decimal:
        """
        Calculate margin ratio (MMR).
        
        Parameters
        ----------
        maintenance_margin_required : Decimal
            The maintenance margin required.
        total_equity : Decimal
            The total account equity.
            
        Returns
        -------
        Decimal
            The margin ratio (0.0 to 1.0+, where 1.0 = 100% = liquidation).
        """
        if total_equity <= 0:
            return Decimal("999")  # Infinite ratio, immediate liquidation
        
        ratio = maintenance_margin_required / total_equity
        
        self._log.debug(f"Margin ratio: {maintenance_margin_required} / {total_equity} = {ratio}")
        
        return ratio
    
    def get_default_weights(self) -> dict[str, Decimal]:
        """
        Get default collateral weights for common assets.
        
        These are typical values; actual weights come from the API.
        
        Returns
        -------
        dict[str, Decimal]
            The default collateral weights.
        """
        return {
            "USDC": Decimal("1.00"),  # Stablecoins typically 100%
            "USDT": Decimal("1.00"),
            "BTC": Decimal("0.95"),   # Major cryptos with small haircut
            "ETH": Decimal("0.95"),
            "SOL": Decimal("0.90"),   # Slightly higher haircut
            "BNB": Decimal("0.90"),
            # Other altcoins would have lower weights
        }
    
    def adjust_weight_for_size(
        self,
        base_weight: Decimal,
        position_size_usd: Decimal,
        tier_thresholds: list[tuple[Decimal, Decimal]] | None = None,
    ) -> Decimal:
        """
        Adjust collateral weight based on position size (tiered system).
        
        Larger positions get lower weights (higher haircuts) for risk management.
        
        Parameters
        ----------
        base_weight : Decimal
            The base collateral weight.
        position_size_usd : Decimal
            The position size in USD.
        tier_thresholds : list[tuple[Decimal, Decimal]], optional
            List of (threshold, weight_multiplier) tuples.
            
        Returns
        -------
        Decimal
            The adjusted weight.
        """
        if tier_thresholds is None:
            # Default tiers (example)
            tier_thresholds = [
                (Decimal("10000"), Decimal("1.0")),    # <$10k: full weight
                (Decimal("100000"), Decimal("0.95")),   # <$100k: 95% of base
                (Decimal("1000000"), Decimal("0.90")),  # <$1M: 90% of base
                (Decimal("10000000"), Decimal("0.80")), # <$10M: 80% of base
            ]
        
        multiplier = Decimal("1.0")
        for threshold, mult in tier_thresholds:
            if position_size_usd < threshold:
                multiplier = mult
                break
        
        adjusted_weight = base_weight * multiplier
        
        if adjusted_weight != base_weight:
            self._log.debug(
                f"Weight adjusted for size ${position_size_usd}: "
                f"{base_weight} -> {adjusted_weight}",
            )
        
        return adjusted_weight