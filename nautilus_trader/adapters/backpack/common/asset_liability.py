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
Backpack asset liability management system.
"""

from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from nautilus_trader.common.component import Logger

if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.common.account import BackpackUnifiedAccountManager


class AssetCategory(Enum):
    """Asset categorization for risk management."""
    
    STABLE = "STABLE"  # Stablecoins (USDC, USDT)
    MAJOR = "MAJOR"  # Major cryptos (BTC, ETH)
    ALTCOIN = "ALTCOIN"  # Alternative coins (SOL, BNB, etc.)
    VOLATILE = "VOLATILE"  # High volatility assets


class LiabilityType(Enum):
    """Types of liabilities."""
    
    BORROW = "BORROW"  # Direct borrowing
    INTEREST = "INTEREST"  # Accrued interest
    FUNDING = "FUNDING"  # Futures funding payments
    FEE = "FEE"  # Trading fees owed
    SETTLEMENT = "SETTLEMENT"  # Pending settlements


class BackpackAssetLiabilityManager:
    """
    Manages assets and liabilities for Backpack's unified account.
    
    Provides comprehensive tracking and optimization of:
    - Asset allocation
    - Liability management
    - Net exposure calculation
    - Risk-adjusted valuations
    - Optimization recommendations
    
    Parameters
    ----------
    account_manager : BackpackUnifiedAccountManager
        The unified account manager.
    logger : Logger
        The logger for the manager.
    """
    
    def __init__(
        self,
        account_manager: "BackpackUnifiedAccountManager",
        logger: Logger | None = None,
    ) -> None:
        self._account_manager = account_manager
        self._log = logger or Logger(name=self.__class__.__name__)
        
        # Asset tracking
        self._assets: dict[str, dict[str, Any]] = {}  # asset -> details
        self._asset_categories: dict[str, AssetCategory] = self._init_asset_categories()
        
        # Liability tracking
        self._liabilities: dict[str, dict[LiabilityType, Decimal]] = {}  # asset -> type -> amount
        self._total_liability_usd = Decimal(0)
        
        # Net exposure tracking
        self._net_exposures: dict[str, Decimal] = {}  # asset -> net exposure
        self._exposure_limits: dict[str, Decimal] = {}  # asset -> max exposure
        
        # Risk metrics
        self._concentration_risk = Decimal(0)
        self._diversification_score = Decimal(0)
        self._liability_ratio = Decimal(0)
    
    def _init_asset_categories(self) -> dict[str, AssetCategory]:
        """Initialize default asset categorizations."""
        return {
            "USDC": AssetCategory.STABLE,
            "USDT": AssetCategory.STABLE,
            "BTC": AssetCategory.MAJOR,
            "ETH": AssetCategory.MAJOR,
            "SOL": AssetCategory.ALTCOIN,
            "BNB": AssetCategory.ALTCOIN,
            # Others default to VOLATILE
        }
    
    def update_asset(
        self,
        asset: str,
        balance: Decimal,
        locked: Decimal,
        price: Decimal,
        weight: Decimal,
    ) -> None:
        """
        Update asset information.
        
        Parameters
        ----------
        asset : str
            The asset symbol.
        balance : Decimal
            Total balance.
        locked : Decimal
            Locked/unavailable balance.
        price : Decimal
            Current price in USD.
        weight : Decimal
            Collateral weight.
        """
        available = balance - locked
        value_usd = balance * price
        collateral_value = value_usd * weight
        
        self._assets[asset] = {
            "balance": balance,
            "available": available,
            "locked": locked,
            "price": price,
            "weight": weight,
            "value_usd": value_usd,
            "collateral_value": collateral_value,
            "category": self._asset_categories.get(asset, AssetCategory.VOLATILE),
        }
        
        self._log.debug(
            f"Asset updated: {asset} balance={balance}, "
            f"value=${value_usd}, collateral=${collateral_value}"
        )
    
    def update_liability(
        self,
        asset: str,
        liability_type: LiabilityType,
        amount: Decimal,
        price: Decimal | None = None,
    ) -> None:
        """
        Update liability information.
        
        Parameters
        ----------
        asset : str
            The asset symbol.
        liability_type : LiabilityType
            The type of liability.
        amount : Decimal
            The liability amount.
        price : Decimal, optional
            Asset price for USD calculation.
        """
        if asset not in self._liabilities:
            self._liabilities[asset] = {}
        
        self._liabilities[asset][liability_type] = amount
        
        # Calculate USD value if price provided
        if price:
            usd_value = amount * price
            self._log.debug(
                f"Liability updated: {asset} {liability_type.value}={amount} (${usd_value})"
            )
    
    def calculate_net_exposure(
        self,
        include_futures: bool = True,
    ) -> dict[str, Decimal]:
        """
        Calculate net exposure by asset.
        
        Net exposure = Assets - Liabilities + Futures Positions
        
        Parameters
        ----------
        include_futures : bool, default True
            Whether to include futures positions.
            
        Returns
        -------
        dict[str, Decimal]
            Net exposure by asset.
        """
        net_exposures = {}
        
        # Add assets
        for asset, details in self._assets.items():
            net_exposures[asset] = details["balance"]
        
        # Subtract liabilities
        for asset, liabilities in self._liabilities.items():
            total_liability = sum(liabilities.values())
            if asset in net_exposures:
                net_exposures[asset] -= total_liability
            else:
                net_exposures[asset] = -total_liability
        
        # Add futures positions if requested
        if include_futures:
            # This would integrate with futures position tracking
            pass
        
        self._net_exposures = net_exposures
        return net_exposures
    
    def calculate_risk_metrics(self) -> dict[str, Decimal]:
        """
        Calculate comprehensive risk metrics.
        
        Returns
        -------
        dict[str, Decimal]
            Risk metrics including concentration, diversification, etc.
        """
        if not self._assets:
            return {}
        
        # Total portfolio value
        total_value = sum(a["value_usd"] for a in self._assets.values())
        
        if total_value == 0:
            return {}
        
        # Concentration risk (Herfindahl index)
        concentration = Decimal(0)
        for asset_details in self._assets.values():
            weight = asset_details["value_usd"] / total_value
            concentration += weight ** 2
        self._concentration_risk = concentration
        
        # Diversification score (inverse of concentration)
        self._diversification_score = Decimal(1) / concentration if concentration > 0 else Decimal(0)
        
        # Liability ratio
        total_liability = Decimal(0)
        for liabilities in self._liabilities.values():
            # Assume USD denomination for simplicity
            total_liability += sum(liabilities.values())
        
        self._liability_ratio = total_liability / total_value if total_value > 0 else Decimal(0)
        
        # Category distribution
        category_distribution = {}
        for asset, details in self._assets.items():
            category = details["category"]
            if category not in category_distribution:
                category_distribution[category] = Decimal(0)
            category_distribution[category] += details["value_usd"] / total_value
        
        return {
            "concentration_risk": self._concentration_risk,
            "diversification_score": self._diversification_score,
            "liability_ratio": self._liability_ratio,
            "total_value": total_value,
            "total_liability": total_liability,
            **{f"category_{k.value}": v for k, v in category_distribution.items()},
        }
    
    def get_optimization_recommendations(self) -> list[dict[str, Any]]:
        """
        Get recommendations for optimizing asset/liability structure.
        
        Returns
        -------
        list[dict[str, Any]]
            List of optimization recommendations.
        """
        recommendations = []
        risk_metrics = self.calculate_risk_metrics()
        
        # Check concentration risk
        if self._concentration_risk > Decimal("0.5"):  # > 50% in one asset
            recommendations.append({
                "type": "REDUCE_CONCENTRATION",
                "severity": "HIGH",
                "message": f"High concentration risk ({self._concentration_risk:.2%}). Consider diversifying.",
                "action": "Rebalance portfolio to reduce largest positions",
            })
        
        # Check liability ratio
        if self._liability_ratio > Decimal("0.3"):  # > 30% liabilities
            recommendations.append({
                "type": "REDUCE_LIABILITY",
                "severity": "MEDIUM",
                "message": f"High liability ratio ({self._liability_ratio:.2%}). Consider repaying borrows.",
                "action": "Prioritize repayment of high-interest liabilities",
            })
        
        # Check stable allocation
        stable_allocation = risk_metrics.get(f"category_{AssetCategory.STABLE.value}", Decimal(0))
        if stable_allocation < Decimal("0.2"):  # < 20% in stables
            recommendations.append({
                "type": "INCREASE_STABLE",
                "severity": "LOW",
                "message": f"Low stable allocation ({stable_allocation:.2%}). Consider increasing for stability.",
                "action": "Convert some volatile assets to stablecoins",
            })
        
        # Check for unproductive assets
        for asset, details in self._assets.items():
            if details["weight"] < Decimal("0.5") and details["value_usd"] > Decimal("1000"):
                recommendations.append({
                    "type": "OPTIMIZE_COLLATERAL",
                    "severity": "LOW",
                    "message": f"{asset} has low collateral weight ({details['weight']})",
                    "action": f"Consider converting {asset} to higher-weight assets",
                })
        
        return recommendations
    
    def calculate_liquidation_cascade_risk(
        self,
        price_shocks: dict[str, Decimal],
    ) -> dict[str, Any]:
        """
        Calculate risk of liquidation cascade under price shocks.
        
        Parameters
        ----------
        price_shocks : dict[str, Decimal]
            Price shock scenarios (asset -> percentage change).
            
        Returns
        -------
        dict[str, Any]
            Cascade risk analysis.
        """
        # Calculate collateral after shocks
        shocked_collateral = Decimal(0)
        for asset, details in self._assets.items():
            shock = price_shocks.get(asset, Decimal(0))
            shocked_price = details["price"] * (Decimal(1) + shock)
            shocked_value = details["balance"] * shocked_price
            shocked_collateral += shocked_value * details["weight"]
        
        # Calculate if liquidation would occur
        total_liability = sum(
            sum(liabilities.values())
            for liabilities in self._liabilities.values()
        )
        
        # Simple liquidation check (would need margin requirements)
        margin_after_shock = (shocked_collateral - total_liability) / shocked_collateral
        
        return {
            "shocked_collateral": shocked_collateral,
            "margin_after_shock": margin_after_shock,
            "would_liquidate": margin_after_shock < Decimal("0.05"),  # < 5% margin
            "buffer_remaining": max(Decimal(0), margin_after_shock - Decimal("0.05")),
        }
    
    def get_liability_optimization_plan(self) -> list[tuple[str, LiabilityType, Decimal, str]]:
        """
        Get optimized plan for liability reduction.
        
        Returns
        -------
        list[tuple[str, LiabilityType, Decimal, str]]
            List of (asset, type, amount, reason) to optimize.
        """
        plan = []
        
        # Prioritize by interest cost
        for asset, liabilities in self._liabilities.items():
            for liability_type, amount in liabilities.items():
                if liability_type == LiabilityType.BORROW and amount > Decimal("100"):
                    # High priority for large borrows
                    plan.append((
                        asset,
                        liability_type,
                        amount,
                        "High-cost borrow liability",
                    ))
                elif liability_type == LiabilityType.INTEREST and amount > Decimal("10"):
                    # Medium priority for accumulated interest
                    plan.append((
                        asset,
                        liability_type,
                        amount,
                        "Accumulated interest payment",
                    ))
        
        # Sort by amount (largest first)
        plan.sort(key=lambda x: x[2], reverse=True)
        
        return plan
    
    def get_summary(self) -> dict[str, Any]:
        """
        Get comprehensive asset/liability summary.
        
        Returns
        -------
        dict[str, Any]
            Summary of assets, liabilities, and risk metrics.
        """
        total_assets = sum(a["value_usd"] for a in self._assets.values())
        total_collateral = sum(a["collateral_value"] for a in self._assets.values())
        
        total_liabilities = Decimal(0)
        liability_breakdown = {}
        for asset, liabilities in self._liabilities.items():
            for liability_type, amount in liabilities.items():
                if liability_type not in liability_breakdown:
                    liability_breakdown[liability_type] = Decimal(0)
                liability_breakdown[liability_type] += amount
                total_liabilities += amount
        
        net_worth = total_assets - total_liabilities
        
        return {
            "total_assets_usd": float(total_assets),
            "total_collateral_usd": float(total_collateral),
            "total_liabilities_usd": float(total_liabilities),
            "net_worth_usd": float(net_worth),
            "liability_breakdown": {k.value: float(v) for k, v in liability_breakdown.items()},
            "concentration_risk": float(self._concentration_risk),
            "diversification_score": float(self._diversification_score),
            "liability_ratio": float(self._liability_ratio),
            "num_assets": len(self._assets),
            "num_liabilities": len(self._liabilities),
        }