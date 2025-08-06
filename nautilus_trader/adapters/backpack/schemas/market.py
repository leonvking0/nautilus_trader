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

"""Backpack market data response schemas."""

import msgspec


################################################################################
# HTTP responses
################################################################################


class BackpackMarket(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/markets."""

    symbol: str
    base_currency: str
    quote_currency: str
    price_decimals: int
    quantity_decimals: int
    taker_fee: str
    maker_fee: str
    min_quantity: str
    max_quantity: str
    min_price: str
    max_price: str
    tick_size: str
    lot_size: str
    status: str
    market_type: str | None = None
    open_interest_limit: str | None = None
    funding_rate_lower_bound: str | None = None
    funding_rate_upper_bound: str | None = None


class BackpackTicker(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/ticker."""

    symbol: str
    first_price: str
    last_price: str
    price_change: str
    price_change_percent: str
    high: str
    low: str
    volume: str
    quote_volume: str
    trades: int


class BackpackOrderBook(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/depth."""

    last_update_id: int
    bids: list[list[str]]
    asks: list[list[str]]
    timestamp: int | None = None


class BackpackTrade(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/trades."""

    id: int
    price: str
    quantity: str
    quote_quantity: str
    timestamp: int
    is_buyer_maker: bool


class BackpackKline(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/klines."""

    start_time: int
    open: str
    high: str
    low: str
    close: str
    volume: str
    close_time: int
    quote_volume: str
    trades: int
    taker_buy_volume: str
    taker_buy_quote_volume: str


################################################################################
# WebSocket messages
################################################################################


class BackpackWsBookTicker(msgspec.Struct, frozen=True):
    """WebSocket book ticker message."""

    e: str  # Event type
    E: int  # Event time in microseconds
    s: str  # Symbol
    a: str  # Inside ask price
    A: str  # Inside ask quantity
    b: str  # Inside bid price
    B: str  # Inside bid quantity
    u: str  # Update ID
    T: int  # Engine timestamp in microseconds


class BackpackWsDepth(msgspec.Struct, frozen=True):
    """WebSocket depth update message."""

    e: str  # Event type
    E: int  # Event time in microseconds
    s: str  # Symbol
    a: list[list[str]]  # Asks
    b: list[list[str]]  # Bids
    U: int  # First update ID in event
    u: int  # Last update ID in event
    T: int  # Engine timestamp in microseconds


class BackpackWsTrade(msgspec.Struct, frozen=True):
    """WebSocket trade message."""

    e: str  # Event type
    E: int  # Event time in microseconds
    s: str  # Symbol
    p: str  # Price
    q: str  # Quantity
    b: str  # Buyer order ID
    a: str  # Seller order ID
    t: int  # Trade ID
    T: int  # Engine timestamp in microseconds
    m: bool  # Is buyer the maker


class BackpackWsKline(msgspec.Struct, frozen=True):
    """WebSocket kline message."""

    e: str  # Event type
    E: int  # Event time in microseconds
    s: str  # Symbol
    t: int  # Kline start time in seconds
    T: int  # Kline close time in seconds
    o: str  # Open price
    c: str  # Close price
    h: str  # High price
    l: str  # Low price
    v: str  # Base asset volume
    n: int  # Number of trades
    X: bool  # Is kline closed


class BackpackWsTicker(msgspec.Struct, frozen=True):
    """WebSocket ticker message."""

    e: str  # Event type
    E: int  # Event time in microseconds
    s: str  # Symbol
    o: str  # First price
    c: str  # Last price
    h: str  # High price
    l: str  # Low price
    v: str  # Base asset volume
    V: str  # Quote asset volume
    n: int  # Number of trades


class BackpackWsMessage(msgspec.Struct, frozen=True):
    """WebSocket message wrapper."""

    stream: str
    data: dict