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
Backpack Exchange futures-specific enums.
"""

from enum import Enum
from enum import unique

from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PositionSide


@unique
class BackpackFuturesPositionSide(Enum):
    """Represents a Backpack futures position side."""
    
    BOTH = "BOTH"
    LONG = "LONG"
    SHORT = "SHORT"


@unique
class BackpackFuturesMarginType(Enum):
    """Represents a Backpack futures margin type."""
    
    CROSS = "CROSS"
    ISOLATED = "ISOLATED"


@unique
class BackpackFuturesPositionMode(Enum):
    """Represents a Backpack futures position mode."""
    
    ONE_WAY = "ONE_WAY"  # Net position mode
    HEDGE = "HEDGE"      # Long/Short separate positions


@unique
class BackpackFuturesContractType(Enum):
    """Represents a Backpack futures contract type."""
    
    PERPETUAL = "PERPETUAL"
    DATED = "DATED"
    INVERSE = "INVERSE"


@unique
class BackpackFuturesOrderOrigin(Enum):
    """Represents the origin of a futures order update."""
    
    USER = "USER"
    LIQUIDATION_AUTOCLOSE = "LIQUIDATION_AUTOCLOSE"
    ADL_AUTOCLOSE = "ADL_AUTOCLOSE"
    COLLATERAL_CONVERSION = "COLLATERAL_CONVERSION"
    SETTLEMENT_AUTOCLOSE = "SETTLEMENT_AUTOCLOSE"
    BACKSTOP_LIQUIDITY_PROVIDER = "BACKSTOP_LIQUIDITY_PROVIDER"


def backpack_futures_position_side_to_nautilus(side: str) -> PositionSide | None:
    """
    Convert Backpack futures position side to Nautilus position side.
    
    Parameters
    ----------
    side : str
        The Backpack position side string.
        
    Returns
    -------
    PositionSide | None
        The Nautilus position side, or None if BOTH.
    """
    if side == "LONG":
        return PositionSide.LONG
    elif side == "SHORT":
        return PositionSide.SHORT
    else:  # BOTH
        return PositionSide.NO_POSITION_SIDE


def nautilus_position_side_to_backpack_futures(side: PositionSide) -> str:
    """
    Convert Nautilus position side to Backpack futures position side.
    
    Parameters
    ----------
    side : PositionSide
        The Nautilus position side.
        
    Returns
    -------
    str
        The Backpack futures position side string.
    """
    if side == PositionSide.LONG:
        return "LONG"
    elif side == PositionSide.SHORT:
        return "SHORT"
    else:
        return "BOTH"


def order_side_to_position_side(order_side: OrderSide, reduce_only: bool = False) -> PositionSide:
    """
    Determine position side from order side.
    
    Parameters
    ----------
    order_side : OrderSide
        The order side.
    reduce_only : bool, default False
        Whether the order is reduce-only.
        
    Returns
    -------
    PositionSide
        The corresponding position side.
    """
    if reduce_only:
        # Reduce-only orders affect opposite position
        return PositionSide.SHORT if order_side == OrderSide.BUY else PositionSide.LONG
    else:
        # Regular orders
        return PositionSide.LONG if order_side == OrderSide.BUY else PositionSide.SHORT