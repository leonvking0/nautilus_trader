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
Backpack futures position manager for real-time position tracking.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from nautilus_trader.adapters.backpack.futures.margin import BackpackFuturesMarginCalculator
from nautilus_trader.adapters.backpack.futures.schemas.position import BackpackFuturesPosition
from nautilus_trader.adapters.backpack.futures.schemas.position import BackpackFuturesPositionUpdate
from nautilus_trader.common.component import Logger
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.core.datetime import nanos_to_millis
from nautilus_trader.execution.reports import PositionStatusReport
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity

if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.futures.http.position import BackpackFuturesPositionHttpAPI
    from nautilus_trader.cache.cache import Cache
    from nautilus_trader.common.component import LiveClock


class BackpackFuturesPositionManager:
    """
    Manages futures positions for Backpack Exchange.
    
    Handles:
    - Position tracking and updates
    - P&L calculations
    - Risk metrics monitoring
    - Position reconciliation
    - Position status reports
    
    Parameters
    ----------
    position_http : BackpackFuturesPositionHttpAPI
        The position HTTP API client.
    margin_calculator : BackpackFuturesMarginCalculator
        The margin calculator.
    cache : Cache
        The cache for storing positions.
    clock : LiveClock
        The clock for timestamps.
    account_id : AccountId
        The account ID.
    on_position_event : Callable[[dict], None], optional
        Callback for position events.
    logger : Logger, optional
        The logger for the manager.
    """
    
    def __init__(
        self,
        position_http: "BackpackFuturesPositionHttpAPI",
        margin_calculator: BackpackFuturesMarginCalculator,
        cache: "Cache",
        clock: "LiveClock",
        account_id: AccountId,
        on_position_event: Callable[[dict], None] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._position_http = position_http
        self._margin_calculator = margin_calculator
        self._cache = cache
        self._clock = clock
        self._account_id = account_id
        self._on_position_event = on_position_event
        self._log = logger or Logger(name=self.__class__.__name__)
        
        # Position tracking
        self._positions: dict[str, BackpackFuturesPosition] = {}
        self._position_ids: dict[str, PositionId] = {}  # symbol -> PositionId mapping
        self._mark_prices: dict[str, Decimal] = {}  # symbol -> mark price
        self._funding_rates: dict[str, Decimal] = {}  # symbol -> funding rate
        
        # Risk metrics
        self._total_unrealized_pnl = Decimal(0)
        self._total_margin_used = Decimal(0)
        self._position_count = 0
    
    async def initialize(self) -> None:
        """Initialize the position manager by fetching current positions."""
        try:
            positions = await self._position_http.fetch_positions()
            
            for position in positions:
                self._positions[position.symbol] = position
                self._position_count = len(self._positions)
                
                # Generate position ID if not exists
                if position.symbol not in self._position_ids:
                    position_id = PositionId(f"{position.symbol}-{self._clock.timestamp_ns()}")
                    self._position_ids[position.symbol] = position_id
                
                self._log.info(
                    f"Initialized position: {position.symbol} "
                    f"side={position.side} qty={position.quantity}"
                )
            
            await self._calculate_aggregate_metrics()
            
            self._log.info(f"Position manager initialized with {self._position_count} positions")
            
        except Exception as e:
            self._log.error(f"Failed to initialize position manager: {e}")
    
    def update_position(self, update: BackpackFuturesPositionUpdate) -> None:
        """
        Update a position from WebSocket data.
        
        Parameters
        ----------
        update : BackpackFuturesPositionUpdate
            The position update data.
        """
        symbol = update.symbol
        
        # Check if position exists
        if symbol not in self._positions:
            # New position opened
            self._handle_position_opened(update)
        elif update.quantity == 0:
            # Position closed
            self._handle_position_closed(update)
        else:
            # Position adjusted
            self._handle_position_adjusted(update)
        
        # Update aggregate metrics
        self._calculate_aggregate_metrics_sync()
    
    def _handle_position_opened(self, update: BackpackFuturesPositionUpdate) -> None:
        """Handle a new position being opened."""
        position = BackpackFuturesPosition(
            symbol=update.symbol,
            side=update.side,
            quantity=update.quantity,
            entry_price=update.entry_price,
            mark_price=update.mark_price,
            liquidation_price=update.liquidation_price,
            unrealized_pnl=update.unrealized_pnl,
            realized_pnl=update.realized_pnl,
            margin_ratio=update.margin_ratio,
            initial_margin=update.initial_margin,
            maintenance_margin=update.maintenance_margin,
            leverage=update.leverage,
            position_id=update.position_id,
            timestamp=update.timestamp,
        )
        
        self._positions[update.symbol] = position
        self._position_count = len(self._positions)
        
        # Generate position ID
        if update.symbol not in self._position_ids:
            position_id = PositionId(f"{update.symbol}-{self._clock.timestamp_ns()}")
            self._position_ids[update.symbol] = position_id
        
        self._log.info(
            f"Position opened: {update.symbol} {update.side} "
            f"qty={update.quantity} @ {update.entry_price}"
        )
        
        # Send event
        if self._on_position_event:
            self._on_position_event({
                "type": "POSITION_OPENED",
                "symbol": update.symbol,
                "side": update.side,
                "quantity": float(update.quantity),
                "entry_price": float(update.entry_price),
                "timestamp": update.timestamp,
            })
    
    def _handle_position_closed(self, update: BackpackFuturesPositionUpdate) -> None:
        """Handle a position being closed."""
        if update.symbol in self._positions:
            old_position = self._positions[update.symbol]
            del self._positions[update.symbol]
            self._position_count = len(self._positions)
            
            self._log.info(
                f"Position closed: {update.symbol} "
                f"realized_pnl={update.realized_pnl}"
            )
            
            # Send event
            if self._on_position_event:
                self._on_position_event({
                    "type": "POSITION_CLOSED",
                    "symbol": update.symbol,
                    "realized_pnl": float(update.realized_pnl),
                    "timestamp": update.timestamp,
                })
    
    def _handle_position_adjusted(self, update: BackpackFuturesPositionUpdate) -> None:
        """Handle a position being adjusted."""
        if update.symbol in self._positions:
            old_position = self._positions[update.symbol]
            
            # Update position
            self._positions[update.symbol] = BackpackFuturesPosition(
                symbol=update.symbol,
                side=update.side,
                quantity=update.quantity,
                entry_price=update.entry_price,
                mark_price=update.mark_price,
                liquidation_price=update.liquidation_price,
                unrealized_pnl=update.unrealized_pnl,
                realized_pnl=update.realized_pnl,
                margin_ratio=update.margin_ratio,
                initial_margin=update.initial_margin,
                maintenance_margin=update.maintenance_margin,
                leverage=update.leverage,
                position_id=update.position_id,
                timestamp=update.timestamp,
            )
            
            self._log.info(
                f"Position adjusted: {update.symbol} "
                f"qty={old_position.quantity} -> {update.quantity}"
            )
            
            # Send event
            if self._on_position_event:
                self._on_position_event({
                    "type": "POSITION_ADJUSTED",
                    "symbol": update.symbol,
                    "old_quantity": float(old_position.quantity),
                    "new_quantity": float(update.quantity),
                    "unrealized_pnl": float(update.unrealized_pnl),
                    "timestamp": update.timestamp,
                })
    
    def update_mark_price(self, symbol: str, mark_price: Decimal) -> None:
        """
        Update mark price for a symbol.
        
        Parameters
        ----------
        symbol : str
            The symbol.
        mark_price : Decimal
            The new mark price.
        """
        self._mark_prices[symbol] = mark_price
        
        # Update position if exists
        if symbol in self._positions:
            position = self._positions[symbol]
            
            # Recalculate unrealized P&L
            unrealized_pnl = self._margin_calculator.calculate_unrealized_pnl(
                position.quantity,
                position.entry_price,
                mark_price,
                position.side == "LONG",
            )
            
            position.mark_price = mark_price
            position.unrealized_pnl = unrealized_pnl
            
            self._log.debug(
                f"Mark price updated: {symbol}={mark_price}, "
                f"unrealized_pnl={unrealized_pnl}"
            )
    
    def update_funding_rate(self, symbol: str, funding_rate: Decimal) -> None:
        """
        Update funding rate for a symbol.
        
        Parameters
        ----------
        symbol : str
            The symbol.
        funding_rate : Decimal
            The new funding rate.
        """
        self._funding_rates[symbol] = funding_rate
        
        self._log.debug(f"Funding rate updated: {symbol}={funding_rate}")
    
    async def reconcile_positions(self) -> None:
        """Reconcile positions with exchange via REST API."""
        try:
            # Fetch current positions from exchange
            exchange_positions = await self._position_http.fetch_positions()
            
            exchange_symbols = {p.symbol for p in exchange_positions}
            local_symbols = set(self._positions.keys())
            
            # Find discrepancies
            missing_locally = exchange_symbols - local_symbols
            missing_on_exchange = local_symbols - exchange_symbols
            
            # Add missing positions
            for position in exchange_positions:
                if position.symbol in missing_locally:
                    self._positions[position.symbol] = position
                    self._log.warning(
                        f"Added missing position from exchange: {position.symbol}"
                    )
            
            # Remove positions not on exchange
            for symbol in missing_on_exchange:
                del self._positions[symbol]
                self._log.warning(
                    f"Removed position not found on exchange: {symbol}"
                )
            
            # Update quantities for existing positions
            for position in exchange_positions:
                if position.symbol in self._positions:
                    local_pos = self._positions[position.symbol]
                    if abs(local_pos.quantity - position.quantity) > Decimal("0.00001"):
                        self._log.warning(
                            f"Position quantity mismatch for {position.symbol}: "
                            f"local={local_pos.quantity}, exchange={position.quantity}"
                        )
                        self._positions[position.symbol] = position
            
            self._position_count = len(self._positions)
            await self._calculate_aggregate_metrics()
            
            self._log.info(
                f"Position reconciliation complete: {self._position_count} positions"
            )
            
        except Exception as e:
            self._log.error(f"Position reconciliation failed: {e}")
    
    def _calculate_aggregate_metrics_sync(self) -> None:
        """Calculate aggregate position metrics synchronously."""
        self._total_unrealized_pnl = Decimal(0)
        self._total_margin_used = Decimal(0)
        
        for position in self._positions.values():
            self._total_unrealized_pnl += position.unrealized_pnl
            self._total_margin_used += position.initial_margin
    
    async def _calculate_aggregate_metrics(self) -> None:
        """Calculate aggregate position metrics."""
        self._calculate_aggregate_metrics_sync()
        
        self._log.debug(
            f"Aggregate metrics: unrealized_pnl={self._total_unrealized_pnl}, "
            f"margin_used={self._total_margin_used}"
        )
    
    def get_position(self, symbol: str) -> BackpackFuturesPosition | None:
        """
        Get a position by symbol.
        
        Parameters
        ----------
        symbol : str
            The symbol.
            
        Returns
        -------
        BackpackFuturesPosition | None
            The position if exists, else None.
        """
        return self._positions.get(symbol)
    
    def get_all_positions(self) -> list[BackpackFuturesPosition]:
        """
        Get all positions.
        
        Returns
        -------
        list[BackpackFuturesPosition]
            All current positions.
        """
        return list(self._positions.values())
    
    def generate_position_status_report(
        self,
        position: BackpackFuturesPosition,
        venue: Venue,
    ) -> PositionStatusReport:
        """
        Generate a position status report for NautilusTrader.
        
        Parameters
        ----------
        position : BackpackFuturesPosition
            The position data.
        venue : Venue
            The venue.
            
        Returns
        -------
        PositionStatusReport
            The position status report.
        """
        # Get or create position ID
        position_id = self._position_ids.get(
            position.symbol,
            PositionId(f"{position.symbol}-{self._clock.timestamp_ns()}"),
        )
        
        # Create instrument ID
        instrument_id = InstrumentId(Symbol(position.symbol), venue)
        
        # Determine position side
        position_side = PositionSide.LONG if position.side == "LONG" else PositionSide.SHORT
        
        # Create report
        report = PositionStatusReport(
            account_id=self._account_id,
            instrument_id=instrument_id,
            position_side=position_side,
            quantity=Quantity.from_str(str(abs(position.quantity))),
            signed_qty=position.quantity,
            ts_last=millis_to_nanos(position.timestamp),
            ts_init=self._clock.timestamp_ns(),
            report_id=position.position_id,
        )
        
        return report
    
    def get_risk_summary(self) -> dict[str, Any]:
        """
        Get a summary of position risk metrics.
        
        Returns
        -------
        dict[str, Any]
            Risk summary including all positions.
        """
        positions_data = []
        
        for position in self._positions.values():
            mark_price = self._mark_prices.get(position.symbol, position.mark_price)
            
            # Get margin info
            margin_info = self._margin_calculator.get_margin_info(
                position,
                mark_price,
                position.initial_margin,  # Use initial margin as collateral proxy
            )
            
            positions_data.append(margin_info)
        
        return {
            "position_count": self._position_count,
            "total_unrealized_pnl": float(self._total_unrealized_pnl),
            "total_margin_used": float(self._total_margin_used),
            "positions": positions_data,
            "timestamp": nanos_to_millis(self._clock.timestamp_ns()),
        }
    
    def check_liquidation_risk(self) -> list[dict]:
        """
        Check all positions for liquidation risk.
        
        Returns
        -------
        list[dict]
            Positions at risk of liquidation.
        """
        at_risk = []
        
        for position in self._positions.values():
            if position.margin_ratio > Decimal("0.8"):
                mark_price = self._mark_prices.get(position.symbol, position.mark_price)
                
                at_risk.append({
                    "symbol": position.symbol,
                    "side": position.side,
                    "quantity": float(position.quantity),
                    "margin_ratio": float(position.margin_ratio),
                    "mark_price": float(mark_price),
                    "liquidation_price": float(position.liquidation_price),
                    "risk_level": "CRITICAL" if position.margin_ratio > Decimal("0.95") else "WARNING",
                })
        
        return at_risk
    
    def should_reduce_positions(self) -> bool:
        """
        Check if positions should be reduced based on risk.
        
        Returns
        -------
        bool
            True if risk is too high and positions should be reduced.
        """
        # Check if any position has high margin ratio
        for position in self._positions.values():
            if position.margin_ratio > Decimal("0.9"):
                return True
        
        return False