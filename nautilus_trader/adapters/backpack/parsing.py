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

"""Parsing utilities for Backpack exchange data."""

from decimal import Decimal
from typing import Any

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_SYMBOL_SEP
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.common.constants import NAUTILUS_SYMBOL_SEP
from nautilus_trader.adapters.backpack.common.enums import BackpackMarketType
from nautilus_trader.adapters.backpack.common.enums import BackpackOrderSide
from nautilus_trader.adapters.backpack.common.enums import BackpackOrderStatus
from nautilus_trader.adapters.backpack.common.enums import BackpackOrderType
from nautilus_trader.adapters.backpack.common.enums import BackpackTimeInForce
from nautilus_trader.adapters.backpack.common.enums import backpack_order_side_to_nautilus
from nautilus_trader.adapters.backpack.common.enums import backpack_order_status_to_nautilus
from nautilus_trader.adapters.backpack.common.enums import backpack_order_type_to_nautilus
from nautilus_trader.adapters.backpack.common.enums import backpack_time_in_force_to_nautilus
from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.enums import BookAction
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.instruments import CryptoFuture
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


def parse_symbol_to_backpack(symbol: str) -> str:
    """
    Convert Nautilus symbol format to Backpack format.
    
    Parameters
    ----------
    symbol : str
        Symbol in Nautilus format (e.g., "BTC-USDC").
    
    Returns
    -------
    str
        Symbol in Backpack format (e.g., "BTC_USDC").
    
    """
    return symbol.replace(NAUTILUS_SYMBOL_SEP, BACKPACK_SYMBOL_SEP)


def parse_symbol_from_backpack(symbol: str) -> str:
    """
    Convert Backpack symbol format to Nautilus format.
    
    Parameters
    ----------
    symbol : str
        Symbol in Backpack format (e.g., "BTC_USDC").
    
    Returns
    -------
    str
        Symbol in Nautilus format (e.g., "BTC-USDC").
    
    """
    return symbol.replace(BACKPACK_SYMBOL_SEP, NAUTILUS_SYMBOL_SEP)


def parse_instrument_id(symbol: str, market_type: str | None = None) -> InstrumentId:
    """
    Parse a Backpack symbol to a Nautilus InstrumentId.
    
    Parameters
    ----------
    symbol : str
        The Backpack symbol (e.g., "BTC_USDC" or "SOL_USDC_PERP").
    market_type : str, optional
        The market type ("Spot" or "Perpetual").
    
    Returns
    -------
    InstrumentId
        The parsed instrument ID.
    
    """
    # Convert symbol format
    nautilus_symbol = parse_symbol_from_backpack(symbol)
    
    # Determine suffix based on market type or symbol format
    if market_type == "Perpetual" or symbol.endswith("_PERP"):
        nautilus_symbol = nautilus_symbol.replace("-PERP", "")
        symbol_str = f"{nautilus_symbol}-PERP"
    else:
        symbol_str = nautilus_symbol
    
    return InstrumentId(Symbol(symbol_str), BACKPACK_VENUE)


def parse_market(data: dict[str, Any]) -> CurrencyPair | CryptoPerpetual:
    """
    Parse a Backpack market response to a Nautilus instrument.
    
    Parameters
    ----------
    data : dict[str, Any]
        The market data from Backpack API.
    
    Returns
    -------
    CurrencyPair or CryptoPerpetual
        The parsed instrument.
    
    """
    symbol = data["symbol"]
    market_type = data.get("marketType", "Spot")
    
    # Parse currencies
    parts = symbol.split(BACKPACK_SYMBOL_SEP)
    if len(parts) >= 2:
        base_currency = Currency.from_str(parts[0])
        quote_currency = Currency.from_str(parts[1])
    else:
        raise ValueError(f"Invalid symbol format: {symbol}")
    
    # Parse common fields
    instrument_id = parse_instrument_id(symbol, market_type)
    price_precision = int(data.get("pricePrecision", 8))
    size_precision = int(data.get("quantityPrecision", 8))
    price_increment = Price.from_str(str(10 ** -price_precision))
    size_increment = Quantity.from_str(str(10 ** -size_precision))
    
    # Parse filters
    filters = data.get("filters", {})
    
    # Price filter
    price_filter = filters.get("price", {})
    min_price = Price.from_str(price_filter.get("minPrice", "0.00000001"))
    max_price = Price.from_str(price_filter.get("maxPrice", "1000000"))
    
    # Quantity filter
    quantity_filter = filters.get("quantity", {})
    min_quantity = Quantity.from_str(quantity_filter.get("minQuantity", "0.00000001"))
    max_quantity = Quantity.from_str(quantity_filter.get("maxQuantity", "1000000"))
    
    # Notional filter
    notional_filter = filters.get("notional", {})
    min_notional = Money(
        Decimal(notional_filter.get("minNotional", "10")),
        quote_currency,
    )
    
    # Leverage filter (for futures)
    leverage_filter = filters.get("leverage", {})
    max_leverage = Decimal(leverage_filter.get("maxLeverage", "1"))
    
    # Create instrument based on market type
    if market_type == "Perpetual" or symbol.endswith("_PERP"):
        return CryptoPerpetual(
            instrument_id=instrument_id,
            raw_symbol=Symbol(symbol),
            base_currency=base_currency,
            quote_currency=quote_currency,
            settlement_currency=quote_currency,
            is_inverse=False,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            max_quantity=max_quantity,
            min_quantity=min_quantity,
            max_price=max_price,
            min_price=min_price,
            min_notional=min_notional,
            max_leverage=max_leverage,
            margin_init=Decimal("0.01"),  # Default 1%
            margin_maint=Decimal("0.005"),  # Default 0.5%
            ts_event=0,
            ts_init=0,
        )
    else:
        return CurrencyPair(
            instrument_id=instrument_id,
            raw_symbol=Symbol(symbol),
            base_currency=base_currency,
            quote_currency=quote_currency,
            price_precision=price_precision,
            size_precision=size_precision,
            price_increment=price_increment,
            size_increment=size_increment,
            lot_size=size_increment,
            max_quantity=max_quantity,
            min_quantity=min_quantity,
            max_price=max_price,
            min_price=min_price,
            min_notional=min_notional,
            ts_event=0,
            ts_init=0,
        )


def parse_ticker(data: dict[str, Any], ts_init: int) -> QuoteTick:
    """
    Parse a Backpack ticker response to a QuoteTick.
    
    Parameters
    ----------
    data : dict[str, Any]
        The ticker data from Backpack API.
    ts_init : int
        The initialization timestamp in nanoseconds.
    
    Returns
    -------
    QuoteTick
        The parsed quote tick.
    
    """
    symbol = data["symbol"]
    instrument_id = parse_instrument_id(symbol)
    
    return QuoteTick(
        instrument_id=instrument_id,
        bid_price=Price.from_str(data["bidPrice"]),
        ask_price=Price.from_str(data["askPrice"]),
        bid_size=Quantity.from_str(data["bidQuantity"]),
        ask_size=Quantity.from_str(data["askQuantity"]),
        ts_event=ts_init,
        ts_init=ts_init,
    )


def parse_trade(data: dict[str, Any], ts_init: int) -> TradeTick:
    """
    Parse a Backpack trade response to a TradeTick.
    
    Parameters
    ----------
    data : dict[str, Any]
        The trade data from Backpack API.
    ts_init : int
        The initialization timestamp in nanoseconds.
    
    Returns
    -------
    TradeTick
        The parsed trade tick.
    
    """
    symbol = data.get("symbol", data.get("s", ""))
    instrument_id = parse_instrument_id(symbol)
    
    # Determine aggressor side
    is_buyer_maker = data.get("isBuyerMaker", data.get("m", False))
    aggressor_side = AggressorSide.SELLER if is_buyer_maker else AggressorSide.BUYER
    
    # Parse timestamp
    timestamp_ms = data.get("timestamp", data.get("t", 0))
    ts_event = timestamp_ms * 1_000_000  # Convert to nanoseconds
    
    return TradeTick(
        instrument_id=instrument_id,
        price=Price.from_str(str(data.get("price", data.get("p", 0)))),
        size=Quantity.from_str(str(data.get("quantity", data.get("q", 0)))),
        aggressor_side=aggressor_side,
        trade_id=TradeId(str(data.get("id", data.get("i", 0)))),
        ts_event=ts_event,
        ts_init=ts_init,
    )


def parse_order_book(data: dict[str, Any], symbol: str, ts_init: int) -> OrderBookDeltas:
    """
    Parse a Backpack order book response to OrderBookDeltas.
    
    Parameters
    ----------
    data : dict[str, Any]
        The order book data from Backpack API.
    symbol : str
        The Backpack symbol.
    ts_init : int
        The initialization timestamp in nanoseconds.
    
    Returns
    -------
    OrderBookDeltas
        The parsed order book deltas.
    
    """
    instrument_id = parse_instrument_id(symbol)
    
    # Parse timestamp from data if available
    timestamp = data.get("timestamp", 0)
    if timestamp:
        ts_event = timestamp  # Already in microseconds
    else:
        ts_event = ts_init
    
    deltas = []
    
    # Clear the book first
    deltas.append(
        OrderBookDelta(
            instrument_id=instrument_id,
            action=BookAction.CLEAR,
            order=None,
            ts_event=ts_event,
            ts_init=ts_init,
        )
    )
    
    # Add bids
    for bid in data.get("bids", []):
        price = Price.from_str(str(bid[0]))
        size = Quantity.from_str(str(bid[1]))
        
        deltas.append(
            OrderBookDelta(
                instrument_id=instrument_id,
                action=BookAction.ADD,
                order=(OrderSide.BUY, price, size, 0),
                ts_event=ts_event,
                ts_init=ts_init,
            )
        )
    
    # Add asks
    for ask in data.get("asks", []):
        price = Price.from_str(str(ask[0]))
        size = Quantity.from_str(str(ask[1]))
        
        deltas.append(
            OrderBookDelta(
                instrument_id=instrument_id,
                action=BookAction.ADD,
                order=(OrderSide.SELL, price, size, 0),
                ts_event=ts_event,
                ts_init=ts_init,
            )
        )
    
    return OrderBookDeltas(
        instrument_id=instrument_id,
        deltas=deltas,
    )


def parse_order(data: dict[str, Any]) -> dict[str, Any]:
    """
    Parse a Backpack order response.
    
    Parameters
    ----------
    data : dict[str, Any]
        The order data from Backpack API.
    
    Returns
    -------
    dict[str, Any]
        The parsed order data.
    """
    return {
        "id": data.get("id"),
        "client_id": data.get("client_id"),
        "symbol": data.get("symbol"),
        "side": backpack_order_side_to_nautilus(data.get("side", "")),
        "order_type": backpack_order_type_to_nautilus(data.get("order_type", "")),
        "time_in_force": backpack_time_in_force_to_nautilus(data.get("time_in_force", "")),
        "price": data.get("price"),
        "quantity": data.get("quantity"),
        "executed_quantity": data.get("executed_quantity", "0"),
        "executed_quote_quantity": data.get("executed_quote_quantity", "0"),
        "status": backpack_order_status_to_nautilus(data.get("status", "")),
        "created_at": data.get("created_at"),
        "post_only": data.get("post_only", False),
        "reduce_only": data.get("reduce_only", False),
        "trigger_price": data.get("trigger_price"),
    }


def parse_order_report(data: dict[str, Any], account_id: AccountId, ts_init: int) -> dict[str, Any]:
    """
    Parse a Backpack order report for execution updates.
    
    Parameters
    ----------
    data : dict[str, Any]
        The order data from Backpack API.
    account_id : AccountId
        The account identifier.
    ts_init : int
        The initialization timestamp in nanoseconds.
    
    Returns
    -------
    dict[str, Any]
        The parsed order report data.
    """
    return {
        "account_id": account_id,
        "instrument_id": parse_instrument_id(data.get("symbol", "")),
        "venue_order_id": data.get("id"),
        "client_order_id": data.get("client_id"),
        "order_side": backpack_order_side_to_nautilus(data.get("side", "")),
        "order_type": backpack_order_type_to_nautilus(data.get("order_type", "")),
        "time_in_force": backpack_time_in_force_to_nautilus(data.get("time_in_force", "")),
        "order_status": backpack_order_status_to_nautilus(data.get("status", "")),
        "price": data.get("price"),
        "quantity": data.get("quantity"),
        "filled_qty": data.get("executed_quantity", "0"),
        "avg_px": None,  # Calculate from executed_quote_quantity / executed_quantity if needed
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at", data.get("created_at")),
        "ts_init": ts_init,
        "post_only": data.get("post_only", False),
        "reduce_only": data.get("reduce_only", False),
    }


def parse_balance(data: dict[str, Any], account_id: AccountId) -> list[AccountBalance]:
    """
    Parse a Backpack balance response to AccountBalance list.
    
    Parameters
    ----------
    data : dict[str, Any]
        The balance data from Backpack API.
    account_id : AccountId
        The account ID.
    
    Returns
    -------
    list[AccountBalance]
        The parsed account balances.
    
    """
    balances = []
    
    for asset, values in data.items():
        currency = Currency.from_str(asset)
        
        available = Decimal(values.get("available", "0"))
        locked = Decimal(values.get("locked", "0"))
        total = available + locked
        
        balance = AccountBalance(
            total=Money(total, currency),
            locked=Money(locked, currency),
            free=Money(available, currency),
        )
        
        balances.append(balance)
    
    return balances