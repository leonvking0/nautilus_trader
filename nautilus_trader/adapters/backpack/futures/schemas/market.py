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
Backpack Exchange futures market schemas.
"""

from decimal import Decimal

import msgspec

from nautilus_trader.adapters.backpack.futures.types import BackpackFuturesMarkPriceUpdate
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price


class BackpackMarkPrice(msgspec.Struct, frozen=True):
    """
    Schema for Backpack mark price data.
    
    Fields
    ------
    symbol : str
        The symbol identifier.
    markPrice : str
        The mark price.
    indexPrice : str
        The index price.
    fundingRate : str
        The current funding rate.
    nextFundingTime : int
        The next funding time in milliseconds.
    openInterest : str, optional
        The open interest.
    timestamp : int
        The timestamp in milliseconds.
    """
    
    symbol: str
    markPrice: str
    indexPrice: str
    fundingRate: str
    nextFundingTime: int
    openInterest: str | None = None
    timestamp: int
    
    def parse_to_mark_price_update(
        self,
        instrument_id: InstrumentId,
        ts_init: int,
    ) -> BackpackFuturesMarkPriceUpdate:
        """Parse to a BackpackFuturesMarkPriceUpdate."""
        return BackpackFuturesMarkPriceUpdate(
            instrument_id=instrument_id,
            mark_price=Price.from_str(self.markPrice),
            index_price=Price.from_str(self.indexPrice),
            funding_rate=Decimal(self.fundingRate),
            next_funding_time=self.nextFundingTime,
            open_interest=Decimal(self.openInterest) if self.openInterest else Decimal(0),
            ts_event=millis_to_nanos(self.timestamp),
            ts_init=ts_init,
        )


class BackpackFundingRate(msgspec.Struct, frozen=True):
    """
    Schema for Backpack funding rate data.
    
    Fields
    ------
    symbol : str
        The symbol identifier.
    fundingRate : str
        The funding rate.
    fundingTime : int
        The funding time in milliseconds.
    """
    
    symbol: str
    fundingRate: str
    fundingTime: int


class BackpackOpenInterest(msgspec.Struct, frozen=True):
    """
    Schema for Backpack open interest data.
    
    Fields
    ------
    symbol : str
        The symbol identifier.
    openInterest : str
        The open interest value.
    timestamp : int
        The timestamp in milliseconds.
    """
    
    symbol: str
    openInterest: str
    timestamp: int


class BackpackMarkPriceMsg(msgspec.Struct, frozen=True):
    """
    WebSocket message for mark price updates.
    
    Fields
    ------
    stream : str
        The stream name (markPrice.<symbol>).
    data : BackpackMarkPrice
        The mark price data.
    """
    
    stream: str
    data: BackpackMarkPrice


class BackpackFundingRateMsg(msgspec.Struct, frozen=True):
    """
    WebSocket message for funding rate updates.
    
    Fields
    ------
    stream : str
        The stream name (fundingRate.<symbol>).
    data : BackpackFundingRate
        The funding rate data.
    """
    
    stream: str
    data: BackpackFundingRate


class BackpackOpenInterestMsg(msgspec.Struct, frozen=True):
    """
    WebSocket message for open interest updates.
    
    Fields
    ------
    stream : str
        The stream name (openInterest.<symbol>).
    data : BackpackOpenInterest
        The open interest data.
    """
    
    stream: str
    data: BackpackOpenInterest