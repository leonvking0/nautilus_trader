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

"""Backpack account data response schemas."""

import msgspec


class BackpackBalance(msgspec.Struct, frozen=True):
    """Account balance for a single asset."""

    symbol: str
    available: str
    locked: str
    staked: str


class BackpackAccount(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/account."""

    account_id: str
    balances: list[BackpackBalance]


class BackpackFill(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/fills."""

    trade_id: int
    order_id: str
    symbol: str
    side: str
    price: str
    quantity: str
    fee: str
    fee_symbol: str
    is_maker: bool
    timestamp: int
    client_id: str | None = None


class BackpackOrder(msgspec.Struct, frozen=True):
    """HTTP response from Backpack GET /api/orders."""

    id: str
    client_id: str | None
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    price: str | None
    trigger_price: str | None
    quantity: str | None
    quote_quantity: str | None
    executed_quantity: str
    executed_quote_quantity: str
    status: str
    created_at: int
    self_trade_prevention: str | None = None
    post_only: bool | None = None
    reduce_only: bool | None = None


class BackpackOrderResponse(msgspec.Struct, frozen=True):
    """HTTP response from Backpack POST /api/order/execute."""

    id: str
    client_id: str | None
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    price: str | None
    trigger_price: str | None
    quantity: str | None
    quote_quantity: str | None
    status: str
    created_at: int


class BackpackCancelResponse(msgspec.Struct, frozen=True):
    """HTTP response from Backpack DELETE /api/order."""

    order: BackpackOrder