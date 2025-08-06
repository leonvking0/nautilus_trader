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
Backpack exchange enumerations.

References
----------
https://docs.backpack.exchange/

"""

from enum import Enum
from enum import unique

from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce


@unique
class BackpackOrderSide(Enum):
    """Represents a Backpack order side."""

    BID = "Bid"
    ASK = "Ask"


@unique
class BackpackOrderType(Enum):
    """Represents a Backpack order type."""

    LIMIT = "Limit"
    MARKET = "Market"


@unique
class BackpackTimeInForce(Enum):
    """Represents a Backpack time-in-force."""

    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill
    POST_ONLY = "PostOnly"


@unique
class BackpackOrderStatus(Enum):
    """Represents a Backpack order status."""

    NEW = "New"
    OPEN = "Open"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"
    REJECTED = "Rejected"


@unique
class BackpackKlineInterval(Enum):
    """Represents a Backpack kline (candlestick) interval."""

    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_8 = "8h"
    HOUR_12 = "12h"
    DAY_1 = "1d"
    DAY_3 = "3d"
    WEEK_1 = "1w"
    MONTH_1 = "1M"


@unique
class BackpackMarketType(Enum):
    """Represents a Backpack market type."""

    SPOT = "Spot"
    PERP = "Perpetual"


# Conversion functions
def backpack_order_side_from_nautilus(side: OrderSide) -> str:
    """Convert Nautilus order side to Backpack format."""
    if side == OrderSide.BUY:
        return BackpackOrderSide.BID.value
    elif side == OrderSide.SELL:
        return BackpackOrderSide.ASK.value
    else:
        raise ValueError(f"Invalid order side: {side}")


def backpack_order_side_to_nautilus(side: str) -> OrderSide:
    """Convert Backpack order side to Nautilus format."""
    if side in ("Bid", "Buy"):
        return OrderSide.BUY
    elif side in ("Ask", "Sell"):
        return OrderSide.SELL
    else:
        raise ValueError(f"Invalid Backpack order side: {side}")


def backpack_order_type_from_nautilus(order_type: OrderType) -> str:
    """Convert Nautilus order type to Backpack format."""
    if order_type == OrderType.LIMIT:
        return BackpackOrderType.LIMIT.value
    elif order_type == OrderType.MARKET:
        return BackpackOrderType.MARKET.value
    else:
        raise ValueError(f"Unsupported order type: {order_type}")


def backpack_order_type_to_nautilus(order_type: str) -> OrderType:
    """Convert Backpack order type to Nautilus format."""
    if order_type == "Limit":
        return OrderType.LIMIT
    elif order_type == "Market":
        return OrderType.MARKET
    elif order_type in ("Stop", "Stop_Limit", "StopLimit"):
        return OrderType.STOP_LIMIT
    else:
        raise ValueError(f"Invalid Backpack order type: {order_type}")


def backpack_time_in_force_from_nautilus(tif: TimeInForce) -> str:
    """Convert Nautilus time-in-force to Backpack format."""
    if tif == TimeInForce.GTC:
        return BackpackTimeInForce.GTC.value
    elif tif == TimeInForce.IOC:
        return BackpackTimeInForce.IOC.value
    elif tif == TimeInForce.FOK:
        return BackpackTimeInForce.FOK.value
    elif tif == TimeInForce.GTD:
        # Backpack doesn't support GTD, use GTC as fallback
        return BackpackTimeInForce.GTC.value
    else:
        raise ValueError(f"Unsupported time-in-force: {tif}")


def backpack_time_in_force_to_nautilus(tif: str) -> TimeInForce:
    """Convert Backpack time-in-force to Nautilus format."""
    if tif == "GTC":
        return TimeInForce.GTC
    elif tif == "IOC":
        return TimeInForce.IOC
    elif tif == "FOK":
        return TimeInForce.FOK
    elif tif == "PostOnly":
        # PostOnly is handled separately via post_only flag
        return TimeInForce.GTC
    else:
        raise ValueError(f"Invalid Backpack time-in-force: {tif}")


def backpack_order_status_to_nautilus(status: str) -> OrderStatus:
    """Convert Backpack order status to Nautilus format."""
    status_lower = status.lower()
    if status_lower in ("new", "open"):
        return OrderStatus.ACCEPTED
    elif status_lower == "partiallyfilled":
        return OrderStatus.PARTIALLY_FILLED
    elif status_lower == "filled":
        return OrderStatus.FILLED
    elif status_lower in ("cancelled", "canceled"):
        return OrderStatus.CANCELED
    elif status_lower == "expired":
        return OrderStatus.EXPIRED
    elif status_lower == "rejected":
        return OrderStatus.REJECTED
    else:
        raise ValueError(f"Invalid Backpack order status: {status}")


@unique
class BackpackFillType(Enum):
    """Represents a Backpack fill type."""

    USER = "User"
    LIQUIDATION = "Liquidation"
    ADL = "ADL"
    SETTLEMENT = "Settlement"


@unique
class BackpackErrorCode(Enum):
    """Represents a Backpack API error code."""

    UNKNOWN = -1000
    DISCONNECTED = -1001
    UNAUTHORIZED = -1002
    TOO_MANY_REQUESTS = -1003
    DUPLICATE_ORDER = -1004
    ORDER_NOT_FOUND = -1005
    UNEXPECTED_RESPONSE = -1006
    TIMEOUT = -1007
    INVALID_MESSAGE = -1013
    UNKNOWN_ORDER_COMPOSITION = -1014
    TOO_MANY_ORDERS = -1015
    SERVICE_UNAVAILABLE = -1016
    UNSUPPORTED_OPERATION = -1020
    INVALID_TIMESTAMP = -1021
    INVALID_SIGNATURE = -1022
    INVALID_API_KEY = -1023
    INVALID_PARAMETER = -2010
    INSUFFICIENT_BALANCE = -2011
    ORDER_WOULD_TRIGGER_IMMEDIATELY = -2021
    REDUCE_ONLY_MARGIN_CHECK_FAILED = -2022
    MARKET_ORDER_REJECT = -2023


# Conversion mappings
def backpack_order_side_to_nautilus(side: BackpackOrderSide) -> OrderSide:
    """Convert Backpack order side to Nautilus OrderSide."""
    if side == BackpackOrderSide.BID:
        return OrderSide.BUY
    elif side == BackpackOrderSide.ASK:
        return OrderSide.SELL
    else:
        raise ValueError(f"Invalid Backpack order side: {side}")


def nautilus_order_side_to_backpack(side: OrderSide) -> BackpackOrderSide:
    """Convert Nautilus OrderSide to Backpack order side."""
    if side == OrderSide.BUY:
        return BackpackOrderSide.BID
    elif side == OrderSide.SELL:
        return BackpackOrderSide.ASK
    else:
        raise ValueError(f"Invalid Nautilus order side: {side}")


def backpack_order_type_to_nautilus(order_type: BackpackOrderType) -> OrderType:
    """Convert Backpack order type to Nautilus OrderType."""
    if order_type == BackpackOrderType.LIMIT:
        return OrderType.LIMIT
    elif order_type == BackpackOrderType.MARKET:
        return OrderType.MARKET
    else:
        raise ValueError(f"Invalid Backpack order type: {order_type}")


def nautilus_order_type_to_backpack(order_type: OrderType) -> BackpackOrderType:
    """Convert Nautilus OrderType to Backpack order type."""
    if order_type == OrderType.LIMIT:
        return BackpackOrderType.LIMIT
    elif order_type == OrderType.MARKET:
        return BackpackOrderType.MARKET
    else:
        raise ValueError(f"Unsupported Nautilus order type for Backpack: {order_type}")


def backpack_order_status_to_nautilus(status: BackpackOrderStatus) -> OrderStatus:
    """Convert Backpack order status to Nautilus OrderStatus."""
    if status in (BackpackOrderStatus.NEW, BackpackOrderStatus.OPEN):
        return OrderStatus.ACCEPTED
    elif status == BackpackOrderStatus.PARTIALLY_FILLED:
        return OrderStatus.PARTIALLY_FILLED
    elif status == BackpackOrderStatus.FILLED:
        return OrderStatus.FILLED
    elif status == BackpackOrderStatus.CANCELLED:
        return OrderStatus.CANCELED
    elif status == BackpackOrderStatus.EXPIRED:
        return OrderStatus.EXPIRED
    elif status == BackpackOrderStatus.REJECTED:
        return OrderStatus.REJECTED
    else:
        raise ValueError(f"Invalid Backpack order status: {status}")


def backpack_time_in_force_to_nautilus(tif: BackpackTimeInForce) -> TimeInForce:
    """Convert Backpack time-in-force to Nautilus TimeInForce."""
    if tif == BackpackTimeInForce.GTC:
        return TimeInForce.GTC
    elif tif == BackpackTimeInForce.IOC:
        return TimeInForce.IOC
    elif tif == BackpackTimeInForce.FOK:
        return TimeInForce.FOK
    elif tif == BackpackTimeInForce.POST_ONLY:
        return TimeInForce.GTD  # Map PostOnly to GTD as placeholder
    else:
        raise ValueError(f"Invalid Backpack time-in-force: {tif}")


def nautilus_time_in_force_to_backpack(tif: TimeInForce) -> BackpackTimeInForce:
    """Convert Nautilus TimeInForce to Backpack time-in-force."""
    if tif == TimeInForce.GTC:
        return BackpackTimeInForce.GTC
    elif tif == TimeInForce.IOC:
        return BackpackTimeInForce.IOC
    elif tif == TimeInForce.FOK:
        return BackpackTimeInForce.FOK
    else:
        # Default to GTC for unsupported TIF
        return BackpackTimeInForce.GTC