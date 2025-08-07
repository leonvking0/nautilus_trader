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
Data schemas for Backpack historical data responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import msgspec


class BackpackHistoricalOrder(msgspec.Struct):
    """
    Schema for historical order data.
    """
    order_id: int
    client_id: int | None
    symbol: str
    side: str  # 'Bid' or 'Ask'
    order_type: str  # 'Limit', 'Market', etc.
    time_in_force: str  # 'GTC', 'IOC', 'FOK', 'GTX'
    price: str | None
    trigger_price: str | None
    quantity: str
    executed_quantity: str
    executed_quote_quantity: str
    status: str  # 'Filled', 'Cancelled', 'Expired'
    created_at: int  # timestamp in milliseconds
    updated_at: int


class BackpackHistoricalFill(msgspec.Struct):
    """
    Schema for historical fill/trade data.
    """
    trade_id: int
    order_id: int
    client_id: int | None
    symbol: str
    side: str
    price: str
    quantity: str
    fee: str
    fee_symbol: str
    is_maker: bool
    timestamp: int  # milliseconds
    fill_type: str | None  # 'User', 'Liquidation', 'ADL', 'Settlement'


class BackpackPnLHistory(msgspec.Struct):
    """
    Schema for PnL history data.
    """
    symbol: str
    realized_pnl: str
    unrealized_pnl: str | None
    total_pnl: str
    position_side: str | None  # 'Long', 'Short'
    average_entry_price: str | None
    average_exit_price: str | None
    quantity: str
    timestamp: int  # milliseconds


class BackpackFundingPayment(msgspec.Struct):
    """
    Schema for funding payment history.
    """
    symbol: str
    funding_rate: str
    payment_amount: str
    position_size: str
    position_side: str  # 'Long' or 'Short'
    timestamp: int  # milliseconds


class BackpackInterestPayment(msgspec.Struct):
    """
    Schema for interest payment history.
    """
    asset: str
    interest_amount: str
    principal_amount: str
    interest_rate: str
    interest_type: str  # 'Borrow' or 'Lend'
    timestamp: int  # milliseconds


class BackpackDustConversion(msgspec.Struct):
    """
    Schema for dust conversion history.
    """
    from_assets: list[dict[str, str]]  # [{'asset': 'BTC', 'amount': '0.00001'}]
    to_asset: str
    to_amount: str
    conversion_rate: str | None
    timestamp: int  # milliseconds


@dataclass
class BackpackKline:
    """
    Schema for kline/candlestick data.
    """
    timestamp: int  # Open time in milliseconds
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: int  # Close time in milliseconds
    quote_volume: Decimal
    trades_count: int
    taker_buy_volume: Decimal
    taker_buy_quote_volume: Decimal
    
    @classmethod
    def from_list(cls, data: list[Any]) -> BackpackKline:
        """
        Create a BackpackKline from API response list format.
        
        Parameters
        ----------
        data : list[Any]
            Kline data in list format from API.
            
        Returns
        -------
        BackpackKline
            The parsed kline object.
        
        """
        return cls(
            timestamp=int(data[0]),
            open=Decimal(str(data[1])),
            high=Decimal(str(data[2])),
            low=Decimal(str(data[3])),
            close=Decimal(str(data[4])),
            volume=Decimal(str(data[5])),
            close_time=int(data[6]) if len(data) > 6 else int(data[0]),
            quote_volume=Decimal(str(data[7])) if len(data) > 7 else Decimal("0"),
            trades_count=int(data[8]) if len(data) > 8 else 0,
            taker_buy_volume=Decimal(str(data[9])) if len(data) > 9 else Decimal("0"),
            taker_buy_quote_volume=Decimal(str(data[10])) if len(data) > 10 else Decimal("0"),
        )


@dataclass
class BackpackHistoricalTrade:
    """
    Schema for historical trade data.
    """
    trade_id: int
    symbol: str
    price: Decimal
    quantity: Decimal
    is_buyer_maker: bool
    timestamp: int  # milliseconds
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackpackHistoricalTrade:
        """
        Create a BackpackHistoricalTrade from API response dict.
        
        Parameters
        ----------
        data : dict[str, Any]
            Trade data from API.
            
        Returns
        -------
        BackpackHistoricalTrade
            The parsed trade object.
        
        """
        return cls(
            trade_id=int(data.get("id", data.get("trade_id", 0))),
            symbol=data["symbol"],
            price=Decimal(str(data["price"])),
            quantity=Decimal(str(data.get("quantity", data.get("size", 0)))),
            is_buyer_maker=data.get("is_buyer_maker", data.get("m", False)),
            timestamp=int(data.get("timestamp", data.get("time", 0))),
        )


class BackpackPaginatedResponse(msgspec.Struct):
    """
    Schema for paginated API responses.
    """
    data: list[Any]
    total: int | None
    has_more: bool | None
    next_offset: int | None