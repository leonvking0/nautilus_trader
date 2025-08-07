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

"""Constants for the Backpack adapter."""

from typing import Final

from nautilus_trader.model.identifiers import ClientId
from nautilus_trader.model.identifiers import Venue


# Exchange identifiers
BACKPACK: Final[str] = "BACKPACK"
BACKPACK_VENUE: Final[Venue] = Venue(BACKPACK)
BACKPACK_CLIENT_ID: Final[ClientId] = ClientId(BACKPACK)

# API endpoints
BACKPACK_BASE_URL_PROD: Final[str] = "https://api.backpack.exchange"
BACKPACK_BASE_URL_TESTNET: Final[str] = "https://api.backpack.exchange"  # Backpack uses same URL
BACKPACK_WS_URL_PROD: Final[str] = "wss://ws.backpack.exchange"
BACKPACK_WS_URL_TESTNET: Final[str] = "wss://ws.backpack.exchange"  # Backpack uses same URL

# Rate limits
BACKPACK_SPOT_RATE_LIMIT: Final[int] = 6000  # requests per minute
BACKPACK_FUTURES_RATE_LIMIT: Final[int] = 2400  # requests per minute

# Authentication
BACKPACK_DEFAULT_WINDOW: Final[int] = 5000  # milliseconds
BACKPACK_MAX_WINDOW: Final[int] = 60000  # milliseconds

# Instruction types for signing
BACKPACK_INSTRUCTIONS: Final[dict[str, str]] = {
    # Query instructions
    "account_query": "accountQuery",
    "balance_query": "balanceQuery",
    "borrow_history_query_all": "borrowHistoryQueryAll",
    "borrow_position_history_query_all": "borrowPositionHistoryQueryAll",
    "collateral_query": "collateralQuery",
    "deposit_address_query": "depositAddressQuery",
    "deposit_query_all": "depositQueryAll",
    "fill_history_query_all": "fillHistoryQueryAll",
    "funding_history_query_all": "fundingHistoryQueryAll",
    "interest_history_query_all": "interestHistoryQueryAll",
    "order_history_query_all": "orderHistoryQueryAll",
    "order_query": "orderQuery",
    "order_query_all": "orderQueryAll",
    "pnl_history_query_all": "pnlHistoryQueryAll",
    "position_query": "positionQuery",
    "strategy_history_query_all": "strategyHistoryQueryAll",
    "strategy_query": "strategyQuery",
    "strategy_query_all": "strategyQueryAll",
    "withdrawal_query_all": "withdrawalQueryAll",
    # Execute instructions
    "borrow_lend_execute": "borrowLendExecute",
    "order_cancel": "orderCancel",
    "order_cancel_all": "orderCancelAll",
    "order_execute": "orderExecute",
    "quote_submit": "quoteSubmit",
    "strategy_cancel": "strategyCancel",
    "strategy_cancel_all": "strategyCancelAll",
    "strategy_create": "strategyCreate",
    "withdraw": "withdraw",
    # WebSocket subscription
    "subscribe": "subscribe",
}

# API paths
BACKPACK_API_PATHS: Final[dict[str, str]] = {
    # Public endpoints
    "markets": "/api/v1/markets",
    "ticker": "/api/v1/ticker",
    "tickers": "/api/v1/tickers",
    "depth": "/api/v1/depth",
    "trades": "/api/v1/trades",
    "klines": "/api/v1/klines",
    "server_time": "/api/v1/time",
    "status": "/api/v1/status",
    # Private endpoints
    "capital": "/api/v1/capital",
    "order": "/api/v1/order",
    "orders": "/api/v1/orders",
    "order_history": "/api/v1/orderHistory",
    "fills": "/api/v1/fills",
    "deposits": "/api/v1/deposits",
    "withdrawals": "/api/v1/withdrawals",
    "positions": "/api/v1/positions",
    "funding": "/api/v1/funding",
    "deposit_address": "/api/v1/depositAddress",
    "withdraw_request": "/api/v1/requestWithdrawal",
    # Historical data endpoints
    "trades_history": "/api/v1/trades/history",
    "order_history": "/wapi/v1/history/orders",
    "fill_history": "/wapi/v1/history/fills",
    "pnl_history": "/wapi/v1/history/pnl",
    "funding_history": "/wapi/v1/history/funding",
    "interest_history": "/wapi/v1/history/interest",
    "dust_history": "/wapi/v1/history/dust",
}

# WebSocket streams
BACKPACK_WS_STREAMS: Final[dict[str, str]] = {
    "trade": "trade",
    "kline": "kline",
    "ticker": "ticker",
    "depth": "depth",
    "book_ticker": "bookTicker",
    # Private streams
    "account": "account",
    "order_update": "account.orderUpdate",
}

# Symbol format conversion
BACKPACK_SYMBOL_SEP: Final[str] = "_"  # Backpack uses underscore separator (e.g., BTC_USDC)
NAUTILUS_SYMBOL_SEP: Final[str] = "-"  # Nautilus uses hyphen separator (e.g., BTC-USDC)

# Error codes that warrant retries
BACKPACK_RETRY_ERRORS: Final[set[int]] = {
    -1000,  # Unknown error
    -1001,  # Disconnected
    -1002,  # Unauthorized
    -1003,  # Too many requests
    -1006,  # Unexpected response
    -1007,  # Timeout
    -1021,  # Invalid timestamp
}