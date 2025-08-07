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
Backpack margin manager for handling margin operations and events.
"""

from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from nautilus_trader.common.component import Logger
from nautilus_trader.core.datetime import nanos_to_millis

if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.http.account import BackpackAccountHttpAPI


class MarginState(Enum):
    """Margin account state."""
    
    HEALTHY = "HEALTHY"  # Margin ratio < 50%
    NORMAL = "NORMAL"  # Margin ratio 50-80%
    WARNING = "WARNING"  # Margin ratio 80-95%
    CRITICAL = "CRITICAL"  # Margin ratio > 95%
    LIQUIDATION = "LIQUIDATION"  # Being liquidated


class MarginEventType(Enum):
    """Types of margin events."""
    
    MARGIN_CALL = "MARGIN_CALL"
    LIQUIDATION_WARNING = "LIQUIDATION_WARNING"
    LIQUIDATION_START = "LIQUIDATION_START"
    LIQUIDATION_COMPLETE = "LIQUIDATION_COMPLETE"
    COLLATERAL_CONVERSION = "COLLATERAL_CONVERSION"
    AUTO_BORROW = "AUTO_BORROW"
    AUTO_REPAY = "AUTO_REPAY"
    MARGIN_STATE_CHANGE = "MARGIN_STATE_CHANGE"


class BackpackMarginManager:
    """
    Manages margin operations and events for Backpack's unified account.
    
    Handles:
    - Margin state tracking
    - Margin call detection
    - Liquidation monitoring
    - Cross-margin calculations
    - Margin event notifications
    
    Parameters
    ----------
    account_http : BackpackAccountHttpAPI
        The account HTTP API client.
    on_margin_event : Callable[[dict], None], optional
        Callback for margin events.
    logger : Logger
        The logger for the manager.
    """
    
    # Margin ratio thresholds
    HEALTHY_THRESHOLD = Decimal("0.50")  # 50%
    NORMAL_THRESHOLD = Decimal("0.80")  # 80%
    WARNING_THRESHOLD = Decimal("0.95")  # 95%
    LIQUIDATION_THRESHOLD = Decimal("1.00")  # 100%
    
    def __init__(
        self,
        account_http: "BackpackAccountHttpAPI",
        on_margin_event: Callable[[dict], None] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._account_http = account_http
        self._on_margin_event = on_margin_event
        self._log = logger or Logger(name=self.__class__.__name__)
        
        # Margin state
        self._current_state = MarginState.HEALTHY
        self._margin_ratio = Decimal(0)
        self._total_collateral = Decimal(0)
        self._borrow_liability = Decimal(0)
        self._available_equity = Decimal(0)
        self._unrealized_pnl = Decimal(0)
        self._initial_margin_used = Decimal(0)
        self._maintenance_margin_required = Decimal(0)
        
        # Interest tracking
        self._cumulative_interest: dict[str, Decimal] = {}  # Asset -> cumulative interest
        self._interest_rates: dict[str, Decimal] = {}  # Asset -> current rate
        
        # Event history
        self._event_history: list[dict] = []
        self._max_history = 100
    
    async def update_margin_state(
        self,
        total_collateral: Decimal,
        borrow_liability: Decimal,
        margin_ratio: Decimal,
        available_equity: Decimal,
        unrealized_pnl: Decimal,
        initial_margin_used: Decimal,
        maintenance_margin_required: Decimal,
    ) -> None:
        """
        Update the margin state from WebSocket data.
        
        Parameters
        ----------
        total_collateral : Decimal
            The total collateral value.
        borrow_liability : Decimal
            The total borrow liability.
        margin_ratio : Decimal
            The current margin ratio (MMR).
        available_equity : Decimal
            The available equity.
        unrealized_pnl : Decimal
            The unrealized P&L.
        initial_margin_used : Decimal
            The initial margin used.
        maintenance_margin_required : Decimal
            The maintenance margin required.
        """
        # Store previous state for comparison
        previous_state = self._current_state
        previous_ratio = self._margin_ratio
        
        # Update values
        self._total_collateral = total_collateral
        self._borrow_liability = borrow_liability
        self._margin_ratio = margin_ratio
        self._available_equity = available_equity
        self._unrealized_pnl = unrealized_pnl
        self._initial_margin_used = initial_margin_used
        self._maintenance_margin_required = maintenance_margin_required
        
        # Determine new state
        new_state = self._determine_margin_state(margin_ratio)
        
        # Check for state transition
        if new_state != previous_state:
            self._current_state = new_state
            await self._handle_state_transition(
                previous_state,
                new_state,
                previous_ratio,
                margin_ratio,
            )
    
    def _determine_margin_state(self, margin_ratio: Decimal) -> MarginState:
        """
        Determine the margin state based on ratio.
        
        Parameters
        ----------
        margin_ratio : Decimal
            The margin ratio (MMR).
            
        Returns
        -------
        MarginState
            The determined margin state.
        """
        if margin_ratio >= self.LIQUIDATION_THRESHOLD:
            return MarginState.LIQUIDATION
        elif margin_ratio >= self.WARNING_THRESHOLD:
            return MarginState.CRITICAL
        elif margin_ratio >= self.NORMAL_THRESHOLD:
            return MarginState.WARNING
        elif margin_ratio >= self.HEALTHY_THRESHOLD:
            return MarginState.NORMAL
        else:
            return MarginState.HEALTHY
    
    async def _handle_state_transition(
        self,
        previous_state: MarginState,
        new_state: MarginState,
        previous_ratio: Decimal,
        new_ratio: Decimal,
    ) -> None:
        """
        Handle margin state transitions.
        
        Parameters
        ----------
        previous_state : MarginState
            The previous margin state.
        new_state : MarginState
            The new margin state.
        previous_ratio : Decimal
            The previous margin ratio.
        new_ratio : Decimal
            The new margin ratio.
        """
        self._log.info(
            f"Margin state transition: {previous_state.value} -> {new_state.value} "
            f"(ratio: {previous_ratio:.2%} -> {new_ratio:.2%})"
        )
        
        # Create state change event
        event = {
            "type": MarginEventType.MARGIN_STATE_CHANGE,
            "previous_state": previous_state.value,
            "new_state": new_state.value,
            "previous_ratio": float(previous_ratio),
            "new_ratio": float(new_ratio),
            "total_collateral": float(self._total_collateral),
            "borrow_liability": float(self._borrow_liability),
            "available_equity": float(self._available_equity),
            "timestamp": nanos_to_millis(self._log.get_clock().timestamp_ns()),
        }
        
        # Handle specific transitions
        if new_state == MarginState.WARNING and previous_state in [MarginState.HEALTHY, MarginState.NORMAL]:
            await self._handle_margin_warning()
        elif new_state == MarginState.CRITICAL and previous_state != MarginState.CRITICAL:
            await self._handle_margin_critical()
        elif new_state == MarginState.LIQUIDATION:
            await self._handle_liquidation_start()
        
        # Send event
        self._send_margin_event(event)
    
    async def _handle_margin_warning(self) -> None:
        """Handle entering margin warning state."""
        event = {
            "type": MarginEventType.LIQUIDATION_WARNING,
            "level": "WARNING",
            "margin_ratio": float(self._margin_ratio),
            "available_equity": float(self._available_equity),
            "message": f"Margin warning: {self._margin_ratio:.2%} margin used. Consider reducing positions.",
            "timestamp": nanos_to_millis(self._log.get_clock().timestamp_ns()),
        }
        
        self._log.warning(event["message"])
        self._send_margin_event(event)
    
    async def _handle_margin_critical(self) -> None:
        """Handle entering critical margin state."""
        event = {
            "type": MarginEventType.MARGIN_CALL,
            "level": "CRITICAL",
            "margin_ratio": float(self._margin_ratio),
            "available_equity": float(self._available_equity),
            "message": f"MARGIN CALL: {self._margin_ratio:.2%} margin used. Liquidation imminent!",
            "timestamp": nanos_to_millis(self._log.get_clock().timestamp_ns()),
        }
        
        self._log.error(event["message"])
        self._send_margin_event(event)
    
    async def _handle_liquidation_start(self) -> None:
        """Handle liquidation start."""
        event = {
            "type": MarginEventType.LIQUIDATION_START,
            "margin_ratio": float(self._margin_ratio),
            "total_collateral": float(self._total_collateral),
            "borrow_liability": float(self._borrow_liability),
            "message": "LIQUIDATION STARTED: Positions being liquidated",
            "timestamp": nanos_to_millis(self._log.get_clock().timestamp_ns()),
        }
        
        self._log.error(event["message"])
        self._send_margin_event(event)
    
    async def update_borrow_position(
        self,
        asset: str,
        borrowed: Decimal,
        interest: Decimal,
        interest_rate: Decimal,
        cumulative_interest: Decimal,
    ) -> None:
        """
        Update a borrow position.
        
        Parameters
        ----------
        asset : str
            The borrowed asset.
        borrowed : Decimal
            The borrowed amount.
        interest : Decimal
            The current interest.
        interest_rate : Decimal
            The interest rate (APR).
        cumulative_interest : Decimal
            The cumulative interest paid.
        """
        # Update tracking
        self._cumulative_interest[asset] = cumulative_interest
        self._interest_rates[asset] = interest_rate
        
        # Log significant interest changes
        if interest > Decimal("10"):  # More than $10 interest
            self._log.info(
                f"Significant interest on {asset}: ${interest} "
                f"(cumulative: ${cumulative_interest})"
            )
    
    async def update_collateral_weight(
        self,
        asset: str,
        weight: Decimal,
    ) -> None:
        """
        Update collateral weight for an asset.
        
        Parameters
        ----------
        asset : str
            The asset symbol.
        weight : Decimal
            The collateral weight.
        """
        self._log.debug(f"Collateral weight updated: {asset} = {weight}")
    
    def _send_margin_event(self, event: dict[str, Any]) -> None:
        """
        Send a margin event and store in history.
        
        Parameters
        ----------
        event : dict[str, Any]
            The event to send.
        """
        # Store in history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
        
        # Send to callback
        if self._on_margin_event:
            self._on_margin_event(event)
    
    def get_margin_health(self) -> dict[str, Any]:
        """
        Get the current margin health status.
        
        Returns
        -------
        dict[str, Any]
            The margin health information.
        """
        return {
            "state": self._current_state.value,
            "margin_ratio": float(self._margin_ratio),
            "health_percentage": float((Decimal(1) - self._margin_ratio) * 100),  # Inverse for health
            "total_collateral": float(self._total_collateral),
            "borrow_liability": float(self._borrow_liability),
            "available_equity": float(self._available_equity),
            "unrealized_pnl": float(self._unrealized_pnl),
            "can_open_positions": self._current_state in [MarginState.HEALTHY, MarginState.NORMAL],
            "requires_action": self._current_state in [MarginState.WARNING, MarginState.CRITICAL],
        }
    
    def get_interest_summary(self) -> dict[str, dict[str, float]]:
        """
        Get summary of interest across all borrowed assets.
        
        Returns
        -------
        dict[str, dict[str, float]]
            Interest summary by asset.
        """
        summary = {}
        for asset in self._cumulative_interest:
            summary[asset] = {
                "cumulative_interest": float(self._cumulative_interest.get(asset, 0)),
                "interest_rate": float(self._interest_rates.get(asset, 0)),
            }
        return summary
    
    def get_event_history(self, limit: int = 10) -> list[dict]:
        """
        Get recent margin events.
        
        Parameters
        ----------
        limit : int, default 10
            Maximum number of events to return.
            
        Returns
        -------
        list[dict]
            Recent margin events.
        """
        return self._event_history[-limit:] if self._event_history else []
    
    def should_reduce_positions(self) -> bool:
        """
        Check if positions should be reduced.
        
        Returns
        -------
        bool
            True if margin state requires position reduction.
        """
        return self._current_state in [MarginState.WARNING, MarginState.CRITICAL]
    
    def can_open_position(self, required_margin: Decimal) -> bool:
        """
        Check if a new position can be opened.
        
        Parameters
        ----------
        required_margin : Decimal
            The margin required for the new position.
            
        Returns
        -------
        bool
            True if position can be opened.
        """
        if self._current_state in [MarginState.CRITICAL, MarginState.LIQUIDATION]:
            return False
        
        # Check if we have enough available equity
        return self._available_equity >= required_margin
    
    def estimate_liquidation_price(
        self,
        position_size: Decimal,
        entry_price: Decimal,
        is_long: bool,
    ) -> Decimal:
        """
        Estimate liquidation price for a position.
        
        Parameters
        ----------
        position_size : Decimal
            The position size.
        entry_price : Decimal
            The entry price.
        is_long : bool
            Whether the position is long.
            
        Returns
        -------
        Decimal
            The estimated liquidation price.
        """
        # Simplified calculation - would need full position details for accuracy
        if self._total_collateral == 0:
            return Decimal(0)
        
        # Liquidation happens at 100% margin usage
        margin_buffer = self._total_collateral - self._maintenance_margin_required
        
        if is_long:
            # Long liquidates when price drops
            price_move = margin_buffer / position_size
            return max(Decimal(0), entry_price - price_move)
        else:
            # Short liquidates when price rises
            price_move = margin_buffer / position_size
            return entry_price + price_move