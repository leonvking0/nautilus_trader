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

"""Backpack WebSocket message schemas."""

import msgspec


class BackpackWsOrderUpdate(msgspec.Struct, frozen=True):
    """WebSocket order update message."""

    e: str  # Event type
    E: int  # Event time in microseconds
    s: str  # Symbol
    c: str | None = None  # Client order ID
    S: str | None = None  # Side
    o: str | None = None  # Order type
    f: str | None = None  # Time in force
    q: str | None = None  # Quantity
    Q: str | None = None  # Quantity in quote
    p: str | None = None  # Price
    P: str | None = None  # Trigger price
    B: str | None = None  # Trigger by
    a: str | None = None  # Take profit trigger price
    b: str | None = None  # Stop loss trigger price
    d: str | None = None  # Take profit trigger by
    g: str | None = None  # Stop loss trigger by
    Y: str | None = None  # Trigger quantity
    X: str | None = None  # Order state
    R: str | None = None  # Order expiry reason
    i: str | None = None  # Order ID
    t: int | None = None  # Trade ID
    l: str | None = None  # Fill quantity
    z: str | None = None  # Executed quantity
    Z: str | None = None  # Executed quantity in quote
    L: str | None = None  # Fill price
    m: bool | None = None  # Whether the order was maker
    n: str | None = None  # Fee
    N: str | None = None  # Fee symbol
    V: str | None = None  # Self trade prevention
    T: int | None = None  # Engine timestamp in microseconds
    O: str | None = None  # Origin of the update
    I: str | None = None  # Related order ID
    r: bool | None = None  # Reduce only


class BackpackWsPositionUpdate(msgspec.Struct, frozen=True):
    """WebSocket position update message."""

    e: str | None = None  # Event type
    E: int  # Event time in microseconds
    s: str  # Symbol
    b: float  # Break even price
    B: float  # Entry price
    l: float | None  # Estimated liquidation price
    f: float  # Initial margin fraction
    M: float  # Mark price
    m: float  # Maintenance margin fraction
    q: float  # Net quantity
    Q: float  # Net exposure quantity
    n: float  # Net exposure notional
    i: str  # Position ID
    p: str  # PnL realized
    P: str  # PnL unrealized
    T: int  # Engine timestamp in microseconds


class BackpackWsSubscribeRequest(msgspec.Struct, frozen=True):
    """WebSocket subscribe request."""

    method: str
    params: list[str]
    signature: list[str] | None = None


class BackpackWsUnsubscribeRequest(msgspec.Struct, frozen=True):
    """WebSocket unsubscribe request."""

    method: str
    params: list[str]