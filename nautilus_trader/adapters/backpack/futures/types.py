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
Backpack Exchange futures-specific types.
"""

from decimal import Decimal

from nautilus_trader.core.data import Data
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price


class BackpackFuturesMarkPriceUpdate(Data):
    """
    Represents a Backpack futures mark price update.
    
    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument identifier.
    mark_price : Price
        The mark price.
    index_price : Price
        The index price.
    funding_rate : Decimal
        The current funding rate.
    next_funding_time : int
        The next funding time in milliseconds.
    open_interest : Decimal
        The open interest.
    ts_event : int
        The event timestamp in nanoseconds.
    ts_init : int
        The initialization timestamp in nanoseconds.
    """
    
    def __init__(
        self,
        instrument_id: InstrumentId,
        mark_price: Price,
        index_price: Price,
        funding_rate: Decimal,
        next_funding_time: int,
        open_interest: Decimal,
        ts_event: int,
        ts_init: int,
    ) -> None:
        super().__init__(ts_event=ts_event, ts_init=ts_init)
        self.instrument_id = instrument_id
        self.mark_price = mark_price
        self.index_price = index_price
        self.funding_rate = funding_rate
        self.next_funding_time = next_funding_time
        self.open_interest = open_interest
    
    def __repr__(self) -> str:
        return (
            f"BackpackFuturesMarkPriceUpdate("
            f"instrument_id={self.instrument_id}, "
            f"mark_price={self.mark_price}, "
            f"index_price={self.index_price}, "
            f"funding_rate={self.funding_rate}, "
            f"next_funding_time={self.next_funding_time}, "
            f"open_interest={self.open_interest})"
        )


class BackpackFuturesFundingPayment(Data):
    """
    Represents a Backpack futures funding payment.
    
    Parameters
    ----------
    instrument_id : InstrumentId
        The instrument identifier.
    funding_rate : Decimal
        The funding rate applied.
    payment : Decimal
        The funding payment amount (positive = receive, negative = pay).
    position_size : Decimal
        The position size at funding time.
    ts_event : int
        The event timestamp in nanoseconds.
    ts_init : int
        The initialization timestamp in nanoseconds.
    """
    
    def __init__(
        self,
        instrument_id: InstrumentId,
        funding_rate: Decimal,
        payment: Decimal,
        position_size: Decimal,
        ts_event: int,
        ts_init: int,
    ) -> None:
        super().__init__(ts_event=ts_event, ts_init=ts_init)
        self.instrument_id = instrument_id
        self.funding_rate = funding_rate
        self.payment = payment
        self.position_size = position_size
    
    def __repr__(self) -> str:
        return (
            f"BackpackFuturesFundingPayment("
            f"instrument_id={self.instrument_id}, "
            f"funding_rate={self.funding_rate}, "
            f"payment={self.payment}, "
            f"position_size={self.position_size})"
        )