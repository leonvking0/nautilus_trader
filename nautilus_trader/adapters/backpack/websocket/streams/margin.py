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
Backpack margin WebSocket stream handler.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from nautilus_trader.common.component import Logger
from nautilus_trader.core.datetime import micros_to_nanos

if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.common.account import BackpackUnifiedAccountManager


class BackpackMarginStream:
    """
    Handles margin-related WebSocket streams from Backpack.
    
    Processes real-time margin updates including:
    - Total collateral changes
    - Borrow liability updates
    - Margin ratio changes
    - Available equity updates
    - Liquidation warnings
    
    Parameters
    ----------
    account_manager : BackpackUnifiedAccountManager
        The unified account manager for processing updates.
    on_margin_update : Callable[[dict], None], optional
        Callback for margin update events.
    on_liquidation_warning : Callable[[dict], None], optional
        Callback for liquidation warning events.
    logger : Logger
        The logger for the stream handler.
    """
    
    # Liquidation warning thresholds
    WARNING_MARGIN_RATIO = Decimal("0.80")  # Warn at 80% margin usage
    CRITICAL_MARGIN_RATIO = Decimal("0.95")  # Critical at 95% margin usage
    
    def __init__(
        self,
        account_manager: "BackpackUnifiedAccountManager",
        on_margin_update: Callable[[dict], None] | None = None,
        on_liquidation_warning: Callable[[dict], None] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._account_manager = account_manager
        self._on_margin_update = on_margin_update
        self._on_liquidation_warning = on_liquidation_warning
        self._log = logger or Logger(name=self.__class__.__name__)
        
        # State tracking
        self._last_margin_ratio = Decimal(0)
        self._last_total_collateral = Decimal(0)
        self._last_borrow_liability = Decimal(0)
        self._last_available_equity = Decimal(0)
        self._warning_sent = False
        self._critical_warning_sent = False
        
    def get_stream_names(self) -> list[str]:
        """
        Get the WebSocket stream names to subscribe to.
        
        Returns
        -------
        list[str]
            The stream names for margin updates.
        """
        return [
            "account.margin",  # Main margin update stream
            "account.borrowPosition",  # Borrow position updates
            "account.collateral",  # Collateral weight changes
        ]
    
    async def handle_message(self, message: dict[str, Any]) -> None:
        """
        Handle a margin-related WebSocket message.
        
        Parameters
        ----------
        message : dict[str, Any]
            The WebSocket message to process.
        """
        stream = message.get("stream", "")
        data = message.get("data", {})
        
        if stream == "account.margin":
            await self._handle_margin_update(data)
        elif stream == "account.borrowPosition":
            await self._handle_borrow_position_update(data)
        elif stream == "account.collateral":
            await self._handle_collateral_update(data)
        else:
            self._log.warning(f"Unknown margin stream: {stream}")
    
    async def _handle_margin_update(self, data: dict[str, Any]) -> None:
        """
        Handle margin update message.
        
        Expected format:
        {
            "e": "marginUpdate",
            "E": 1694687692980000,  # Event time in microseconds
            "totalCollateral": "10000.00",
            "borrowLiability": "5000.00",
            "marginRatio": "0.25",  # MMR ratio (0.25 = 25% margin used)
            "availableEquity": "3000.00",
            "unrealizedPnl": "100.00",
            "initialMarginUsed": "2000.00",
            "maintenanceMarginRequired": "1500.00",
            "T": 1694687692989999  # Engine timestamp
        }
        """
        event_type = data.get("e", "")
        if event_type != "marginUpdate":
            return
        
        # Parse margin data
        total_collateral = Decimal(data.get("totalCollateral", "0"))
        borrow_liability = Decimal(data.get("borrowLiability", "0"))
        margin_ratio = Decimal(data.get("marginRatio", "0"))
        available_equity = Decimal(data.get("availableEquity", "0"))
        unrealized_pnl = Decimal(data.get("unrealizedPnl", "0"))
        initial_margin_used = Decimal(data.get("initialMarginUsed", "0"))
        maintenance_margin_required = Decimal(data.get("maintenanceMarginRequired", "0"))
        
        # Update account manager state
        await self._account_manager.update_margin_state(
            total_collateral=total_collateral,
            borrow_liability=borrow_liability,
            margin_ratio=margin_ratio,
            available_equity=available_equity,
            unrealized_pnl=unrealized_pnl,
            initial_margin_used=initial_margin_used,
            maintenance_margin_required=maintenance_margin_required,
        )
        
        # Check for liquidation warnings
        self._check_liquidation_risk(margin_ratio, available_equity)
        
        # Store state
        self._last_margin_ratio = margin_ratio
        self._last_total_collateral = total_collateral
        self._last_borrow_liability = borrow_liability
        self._last_available_equity = available_equity
        
        # Trigger callback
        if self._on_margin_update:
            self._on_margin_update({
                "margin_ratio": margin_ratio,
                "total_collateral": total_collateral,
                "borrow_liability": borrow_liability,
                "available_equity": available_equity,
                "unrealized_pnl": unrealized_pnl,
                "timestamp_ns": micros_to_nanos(data.get("T", 0)),
            })
        
        self._log.debug(
            f"Margin update: ratio={margin_ratio:.2%}, "
            f"collateral=${total_collateral}, "
            f"borrows=${borrow_liability}, "
            f"available=${available_equity}"
        )
    
    async def _handle_borrow_position_update(self, data: dict[str, Any]) -> None:
        """
        Handle borrow position update.
        
        Expected format:
        {
            "e": "borrowPositionUpdate",
            "E": 1694687692980000,
            "asset": "USDC",
            "borrowed": "5000.00",
            "interest": "10.50",
            "interestRate": "0.05",  # 5% APR
            "cumulativeInterest": "100.50",
            "T": 1694687692989999
        }
        """
        event_type = data.get("e", "")
        if event_type != "borrowPositionUpdate":
            return
        
        asset = data.get("asset", "")
        borrowed = Decimal(data.get("borrowed", "0"))
        interest = Decimal(data.get("interest", "0"))
        interest_rate = Decimal(data.get("interestRate", "0"))
        cumulative_interest = Decimal(data.get("cumulativeInterest", "0"))
        
        # Update borrow position in account manager
        await self._account_manager.update_borrow_position(
            asset=asset,
            borrowed=borrowed,
            interest=interest,
            interest_rate=interest_rate,
            cumulative_interest=cumulative_interest,
        )
        
        # Track borrow in auto-borrow system
        if borrowed > 0:
            self._account_manager._auto_borrow.track_borrow(
                asset=asset,
                amount=borrowed,
                rate=interest_rate,
            )
        
        self._log.info(
            f"Borrow position update: {asset} "
            f"borrowed={borrowed}, "
            f"interest={interest}, "
            f"rate={interest_rate:.2%} APR"
        )
    
    async def _handle_collateral_update(self, data: dict[str, Any]) -> None:
        """
        Handle collateral weight update.
        
        Expected format:
        {
            "e": "collateralUpdate",
            "E": 1694687692980000,
            "weights": {
                "USDC": "1.00",
                "BTC": "0.95",
                "ETH": "0.95",
                "SOL": "0.90"
            },
            "T": 1694687692989999
        }
        """
        event_type = data.get("e", "")
        if event_type != "collateralUpdate":
            return
        
        weights = data.get("weights", {})
        
        # Update collateral weights in account manager
        for asset, weight_str in weights.items():
            weight = Decimal(weight_str)
            await self._account_manager.update_collateral_weight(asset, weight)
        
        self._log.debug(f"Collateral weights updated: {weights}")
    
    def _check_liquidation_risk(
        self,
        margin_ratio: Decimal,
        available_equity: Decimal,
    ) -> None:
        """
        Check for liquidation risk and send warnings.
        
        Parameters
        ----------
        margin_ratio : Decimal
            The current margin ratio (MMR).
        available_equity : Decimal
            The available equity.
        """
        # Critical warning at 95% margin usage
        if margin_ratio >= self.CRITICAL_MARGIN_RATIO:
            if not self._critical_warning_sent:
                self._send_liquidation_warning(
                    level="CRITICAL",
                    margin_ratio=margin_ratio,
                    available_equity=available_equity,
                    message="CRITICAL: Liquidation imminent! Reduce positions or add collateral immediately.",
                )
                self._critical_warning_sent = True
        # Warning at 80% margin usage
        elif margin_ratio >= self.WARNING_MARGIN_RATIO:
            if not self._warning_sent:
                self._send_liquidation_warning(
                    level="WARNING",
                    margin_ratio=margin_ratio,
                    available_equity=available_equity,
                    message="WARNING: High margin usage detected. Consider reducing positions.",
                )
                self._warning_sent = True
        else:
            # Reset warnings if margin ratio drops
            if margin_ratio < self.WARNING_MARGIN_RATIO:
                self._warning_sent = False
                self._critical_warning_sent = False
    
    def _send_liquidation_warning(
        self,
        level: str,
        margin_ratio: Decimal,
        available_equity: Decimal,
        message: str,
    ) -> None:
        """
        Send a liquidation warning.
        
        Parameters
        ----------
        level : str
            The warning level (WARNING/CRITICAL).
        margin_ratio : Decimal
            The current margin ratio.
        available_equity : Decimal
            The available equity.
        message : str
            The warning message.
        """
        warning_data = {
            "level": level,
            "margin_ratio": margin_ratio,
            "available_equity": available_equity,
            "message": message,
            "timestamp": time.time(),
        }
        
        # Log the warning
        if level == "CRITICAL":
            self._log.error(message)
        else:
            self._log.warning(message)
        
        # Trigger callback
        if self._on_liquidation_warning:
            self._on_liquidation_warning(warning_data)
    
    def get_margin_state(self) -> dict[str, Decimal]:
        """
        Get the current margin state.
        
        Returns
        -------
        dict[str, Decimal]
            The current margin state.
        """
        return {
            "margin_ratio": self._last_margin_ratio,
            "total_collateral": self._last_total_collateral,
            "borrow_liability": self._last_borrow_liability,
            "available_equity": self._last_available_equity,
        }
    
    def is_margin_healthy(self) -> bool:
        """
        Check if margin is in a healthy state.
        
        Returns
        -------
        bool
            True if margin ratio is below warning threshold.
        """
        return self._last_margin_ratio < self.WARNING_MARGIN_RATIO