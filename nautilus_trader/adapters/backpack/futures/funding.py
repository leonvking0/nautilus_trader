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
Backpack Exchange futures funding manager.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import msgspec
import pandas as pd

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.common.component import Component
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.core.datetime import nanos_to_millis
from nautilus_trader.model.identifiers import InstrumentId

if TYPE_CHECKING:
    from datetime import datetime

    from nautilus_trader.common.component import MessageBus
    from nautilus_trader.common.component import Clock


class FundingPayment(msgspec.Struct):
    """
    Represents a funding payment for a perpetual position.
    """
    symbol: str
    position_size: Decimal
    funding_rate: Decimal
    mark_price: Decimal
    payment: Decimal
    timestamp: int  # Unix timestamp in milliseconds
    is_payer: bool  # True if paying funding, False if receiving


class FundingRateHistory(msgspec.Struct):
    """
    Historical funding rate data.
    """
    symbol: str
    funding_rate: Decimal
    mark_price: Decimal
    timestamp: int


class BackpackFundingManager(Component):
    """
    Manages funding rates and payments for Backpack perpetual futures.
    
    This component tracks funding rates, calculates funding payments,
    and maintains historical funding data for positions.
    
    Parameters
    ----------
    client : BackpackHttpClient
        The HTTP client for API requests.
    msgbus : MessageBus
        The message bus for the trader.
    clock : Clock
        The clock for the trader.
    """
    
    def __init__(
        self,
        client: BackpackHttpClient,
        msgbus: MessageBus,
        clock: Clock,
    ) -> None:
        super().__init__(
            clock=clock,
            msgbus=msgbus,
            component_id="BackpackFundingManager",
            component_name="BackpackFundingManager",
        )
        
        self._client = client
        self._funding_rates: dict[str, Decimal] = {}
        self._next_funding_times: dict[str, int] = {}
        self._funding_history: dict[str, list[FundingPayment]] = {}
        self._position_sizes: dict[str, Decimal] = {}
        
        # Decoders
        self._decoder_funding_history = msgspec.json.Decoder(list[FundingRateHistory])
    
    def update_funding_rate(
        self,
        symbol: str,
        funding_rate: Decimal,
        next_funding_time: int,
    ) -> None:
        """
        Update the funding rate for a symbol.
        
        Parameters
        ----------
        symbol : str
            The symbol to update.
        funding_rate : Decimal
            The current funding rate.
        next_funding_time : int
            Unix timestamp (ms) of next funding.
        """
        self._funding_rates[symbol] = funding_rate
        self._next_funding_times[symbol] = next_funding_time
        self._log.info(
            f"Updated funding rate for {symbol}: {funding_rate} "
            f"(next funding at {next_funding_time})",
        )
    
    def update_position_size(
        self,
        symbol: str,
        size: Decimal,
    ) -> None:
        """
        Update the position size for funding calculations.
        
        Parameters
        ----------
        symbol : str
            The symbol to update.
        size : Decimal
            The position size (positive for long, negative for short).
        """
        if size == 0:
            self._position_sizes.pop(symbol, None)
        else:
            self._position_sizes[symbol] = size
    
    def calculate_funding_payment(
        self,
        symbol: str,
        position_size: Decimal | None = None,
        funding_rate: Decimal | None = None,
        mark_price: Decimal | None = None,
    ) -> FundingPayment | None:
        """
        Calculate the funding payment for a position.
        
        Parameters
        ----------
        symbol : str
            The symbol to calculate for.
        position_size : Decimal, optional
            The position size. If None, uses tracked size.
        funding_rate : Decimal, optional
            The funding rate. If None, uses current rate.
        mark_price : Decimal, optional
            The mark price. If None, must be provided externally.
            
        Returns
        -------
        FundingPayment | None
            The funding payment details, or None if no position.
        """
        # Get position size
        if position_size is None:
            position_size = self._position_sizes.get(symbol)
            if position_size is None or position_size == 0:
                return None
        
        # Get funding rate
        if funding_rate is None:
            funding_rate = self._funding_rates.get(symbol)
            if funding_rate is None:
                self._log.warning(f"No funding rate available for {symbol}")
                return None
        
        if mark_price is None:
            self._log.warning(f"Mark price required for funding calculation on {symbol}")
            return None
        
        # Calculate funding payment
        # Funding = Position Value * Funding Rate
        # Position Value = Position Size * Mark Price
        position_value = abs(position_size) * mark_price
        payment = position_value * funding_rate
        
        # Determine if paying or receiving
        # Long positions pay when funding is positive
        # Short positions receive when funding is positive
        is_payer = (position_size > 0 and funding_rate > 0) or \
                   (position_size < 0 and funding_rate < 0)
        
        # If paying, payment is negative (outflow)
        if is_payer:
            payment = -payment
        
        funding_payment = FundingPayment(
            symbol=symbol,
            position_size=position_size,
            funding_rate=funding_rate,
            mark_price=mark_price,
            payment=payment,
            timestamp=nanos_to_millis(self._clock.timestamp_ns()),
            is_payer=is_payer,
        )
        
        # Store in history
        if symbol not in self._funding_history:
            self._funding_history[symbol] = []
        self._funding_history[symbol].append(funding_payment)
        
        self._log.info(
            f"Funding payment for {symbol}: "
            f"{'Paying' if is_payer else 'Receiving'} {abs(payment)} "
            f"(rate={funding_rate}, size={position_size}, mark={mark_price})",
        )
        
        return funding_payment
    
    def get_next_funding_time(self, symbol: str) -> int | None:
        """
        Get the next funding time for a symbol.
        
        Parameters
        ----------
        symbol : str
            The symbol to query.
            
        Returns
        -------
        int | None
            Unix timestamp (ms) of next funding, or None.
        """
        return self._next_funding_times.get(symbol)
    
    def get_funding_rate(self, symbol: str) -> Decimal | None:
        """
        Get the current funding rate for a symbol.
        
        Parameters
        ----------
        symbol : str
            The symbol to query.
            
        Returns
        -------
        Decimal | None
            The funding rate, or None if not available.
        """
        return self._funding_rates.get(symbol)
    
    def get_payment_history(
        self,
        symbol: str | None = None,
    ) -> list[FundingPayment]:
        """
        Get funding payment history.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to get history for. If None, returns all.
            
        Returns
        -------
        list[FundingPayment]
            The funding payment history.
        """
        if symbol:
            return self._funding_history.get(symbol, [])
        
        # Return all history
        all_payments = []
        for payments in self._funding_history.values():
            all_payments.extend(payments)
        return sorted(all_payments, key=lambda p: p.timestamp)
    
    async def fetch_funding_history(
        self,
        symbol: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[FundingRateHistory]:
        """
        Fetch historical funding rates from the exchange.
        
        Parameters
        ----------
        symbol : str
            The symbol to fetch history for.
        start_time : datetime, optional
            The start time for history.
        end_time : datetime, optional
            The end time for history.
        limit : int, default 100
            Maximum number of records to fetch.
            
        Returns
        -------
        list[FundingRateHistory]
            The historical funding rate data.
        """
        params = {
            "symbol": symbol,
            "limit": limit,
        }
        
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        
        try:
            raw = await self._client._get(
                path="/api/v1/funding/history",
                params=params,
            )
            
            history = self._decoder_funding_history.decode(raw)
            
            self._log.info(
                f"Fetched {len(history)} funding rate records for {symbol}",
            )
            
            return history
            
        except Exception as e:
            self._log.error(f"Failed to fetch funding history: {e}")
            return []
    
    def calculate_cumulative_funding(
        self,
        symbol: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Decimal:
        """
        Calculate cumulative funding payments for a symbol.
        
        Parameters
        ----------
        symbol : str
            The symbol to calculate for.
        start_time : datetime, optional
            The start time for calculation.
        end_time : datetime, optional
            The end time for calculation.
            
        Returns
        -------
        Decimal
            The cumulative funding payment (positive = received, negative = paid).
        """
        payments = self._funding_history.get(symbol, [])
        
        if not payments:
            return Decimal("0")
        
        cumulative = Decimal("0")
        for payment in payments:
            # Filter by time if specified
            if start_time and payment.timestamp < int(start_time.timestamp() * 1000):
                continue
            if end_time and payment.timestamp > int(end_time.timestamp() * 1000):
                continue
            
            cumulative += payment.payment
        
        return cumulative
    
    def get_funding_summary(self) -> dict:
        """
        Get a summary of all funding payments.
        
        Returns
        -------
        dict
            Summary with total payments by symbol.
        """
        summary = {}
        
        for symbol in self._funding_history:
            payments = self._funding_history[symbol]
            if not payments:
                continue
            
            total_payment = sum(p.payment for p in payments)
            total_paid = sum(p.payment for p in payments if p.is_payer)
            total_received = sum(p.payment for p in payments if not p.is_payer)
            
            summary[symbol] = {
                "total_payment": float(total_payment),
                "total_paid": float(abs(total_paid)),
                "total_received": float(total_received),
                "payment_count": len(payments),
                "last_payment": float(payments[-1].payment) if payments else 0,
                "last_timestamp": payments[-1].timestamp if payments else 0,
            }
        
        return summary
    
    def export_to_dataframe(self, symbol: str | None = None) -> pd.DataFrame:
        """
        Export funding payment history to a pandas DataFrame.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to export. If None, exports all.
            
        Returns
        -------
        pd.DataFrame
            The funding payment history as a DataFrame.
        """
        payments = self.get_payment_history(symbol)
        
        if not payments:
            return pd.DataFrame()
        
        data = []
        for payment in payments:
            data.append({
                "symbol": payment.symbol,
                "timestamp": pd.Timestamp(payment.timestamp, unit="ms"),
                "position_size": float(payment.position_size),
                "funding_rate": float(payment.funding_rate),
                "mark_price": float(payment.mark_price),
                "payment": float(payment.payment),
                "is_payer": payment.is_payer,
            })
        
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df
    
    def clear_history(self, symbol: str | None = None) -> None:
        """
        Clear funding payment history.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to clear. If None, clears all.
        """
        if symbol:
            self._funding_history.pop(symbol, None)
            self._log.info(f"Cleared funding history for {symbol}")
        else:
            self._funding_history.clear()
            self._log.info("Cleared all funding history")