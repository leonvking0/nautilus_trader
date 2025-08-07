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
Backpack Exchange futures position schemas.
"""

from decimal import Decimal

import msgspec

from nautilus_trader.accounting.accounts.base import Account
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.execution.reports import PositionStatusReport
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


class BackpackFuturesPosition(msgspec.Struct, frozen=True, kw_only=True):
    """
    Schema for Backpack futures position data.
    
    Fields
    ------
    symbol : str
        The symbol identifier.
    side : str
        The position side (LONG/SHORT/BOTH).
    size : str
        The position size.
    entryPrice : str
        The average entry price.
    markPrice : str
        The current mark price.
    liquidationPrice : str, optional
        The liquidation price.
    unrealizedPnl : str
        The unrealized PnL.
    realizedPnl : str
        The realized PnL.
    marginRatio : str
        The margin ratio.
    leverage : int
        The leverage.
    marginType : str
        The margin type (CROSS/ISOLATED).
    positionMargin : str
        The position margin.
    maintenanceMargin : str
        The maintenance margin required.
    timestamp : int
        The timestamp in milliseconds.
    """
    
    symbol: str
    side: str
    size: str
    entryPrice: str
    markPrice: str
    liquidationPrice: str | None
    unrealizedPnl: str
    realizedPnl: str
    marginRatio: str
    leverage: int
    marginType: str
    positionMargin: str
    maintenanceMargin: str
    timestamp: int
    
    def parse_to_position_status_report(
        self,
        account: Account,
        instrument_id: InstrumentId,
        position_id: PositionId | None,
        ts_init: int,
    ) -> PositionStatusReport:
        """Parse to a PositionStatusReport."""
        size = Decimal(self.size)
        
        # Determine position side from side field and size
        if self.side == "LONG":
            position_side = PositionSide.LONG
        elif self.side == "SHORT":
            position_side = PositionSide.SHORT
        else:  # BOTH - determine from size sign
            if size > 0:
                position_side = PositionSide.LONG
            elif size < 0:
                position_side = PositionSide.SHORT
            else:
                position_side = PositionSide.FLAT
        
        return PositionStatusReport(
            account_id=account.id,
            instrument_id=instrument_id,
            position_side=position_side,
            quantity=Quantity.from_str(str(abs(size))),
            signed_qty=size,
            avg_px_open=Decimal(self.entryPrice) if self.entryPrice else None,
            avg_px_close=None,
            unrealized_pnl=Money.from_str(f"{self.unrealizedPnl} USDT"),
            realized_pnl=Money.from_str(f"{self.realizedPnl} USDT"),
            report_id=VenuePositionId(f"{self.symbol}_{self.side}"),
            ts_last=millis_to_nanos(self.timestamp),
            ts_init=ts_init,
        )


class BackpackFuturesPositionUpdate(msgspec.Struct, frozen=True):
    """
    WebSocket message for position updates.
    
    Fields
    ------
    e : str
        Event type (POSITION_UPDATE).
    E : int
        Event time in milliseconds.
    s : str
        Symbol.
    ps : str
        Position side.
    pa : str
        Position amount.
    ep : str
        Entry price.
    cr : str
        Cumulative realized PnL.
    up : str
        Unrealized PnL.
    mt : str
        Margin type.
    iw : str
        Position margin.
    mp : str
        Mark price.
    """
    
    e: str
    E: int
    s: str
    ps: str
    pa: str
    ep: str
    cr: str
    up: str
    mt: str
    iw: str
    mp: str