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
Backpack RFQ (Request for Quote) data schemas.

Defines the structure for RFQ-related data including quotes,
executions, and RFQ requests.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass
class BackpackRFQRequest:
    """Represents an RFQ request."""
    
    quote_id: str
    symbol: str
    side: str  # BUY/SELL
    quantity: Decimal
    status: str  # PENDING, QUOTED, EXPIRED
    created_at: int
    expires_at: int
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackRFQRequest":
        """Create from API response."""
        return cls(
            quote_id=data["quoteId"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=Decimal(str(data["quantity"])),
            status=data["status"],
            created_at=data["createdAt"],
            expires_at=data["expiresAt"],
        )


@dataclass
class BackpackRFQQuote:
    """Represents an RFQ quote with pricing."""
    
    quote_id: str
    symbol: str
    side: str  # BUY/SELL
    quantity: Decimal
    price: Decimal
    total_value: Decimal
    bid_price: Decimal | None  # For reference
    ask_price: Decimal | None  # For reference
    spread: Decimal | None  # Price improvement
    status: str  # PENDING, ACCEPTED, REJECTED, EXPIRED, CANCELLED
    created_at: int
    expires_at: int
    accepted_at: int | None = None
    rejected_at: int | None = None
    rejection_reason: str | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackRFQQuote":
        """Create from API response."""
        return cls(
            quote_id=data["quoteId"],
            symbol=data["symbol"],
            side=data["side"],
            quantity=Decimal(str(data["quantity"])),
            price=Decimal(str(data["price"])),
            total_value=Decimal(str(data["totalValue"])),
            bid_price=Decimal(str(data["bidPrice"])) if data.get("bidPrice") else None,
            ask_price=Decimal(str(data["askPrice"])) if data.get("askPrice") else None,
            spread=Decimal(str(data["spread"])) if data.get("spread") else None,
            status=data["status"],
            created_at=data["createdAt"],
            expires_at=data["expiresAt"],
            accepted_at=data.get("acceptedAt"),
            rejected_at=data.get("rejectedAt"),
            rejection_reason=data.get("rejectionReason"),
        )
    
    def is_valid(self, current_time: int) -> bool:
        """Check if quote is still valid."""
        return (
            self.status == "PENDING" and
            current_time < self.expires_at
        )
    
    def is_expired(self, current_time: int) -> bool:
        """Check if quote has expired."""
        return current_time >= self.expires_at
    
    def get_price_improvement(self) -> Decimal | None:
        """Get price improvement vs market."""
        if self.spread:
            return self.spread
        
        if self.side == "BUY" and self.ask_price:
            return self.ask_price - self.price
        elif self.side == "SELL" and self.bid_price:
            return self.price - self.bid_price
        
        return None


@dataclass
class BackpackRFQExecution:
    """Represents an executed RFQ trade."""
    
    execution_id: str
    quote_id: str
    order_id: str
    client_order_id: str | None
    symbol: str
    side: str  # BUY/SELL
    quantity: Decimal
    price: Decimal
    total_value: Decimal
    fee: Decimal
    fee_currency: str
    status: str  # FILLED, PARTIALLY_FILLED
    executed_at: int
    
    @classmethod
    def from_dict(cls, data: dict) -> "BackpackRFQExecution":
        """Create from API response."""
        return cls(
            execution_id=data["executionId"],
            quote_id=data["quoteId"],
            order_id=data["orderId"],
            client_order_id=data.get("clientOrderId"),
            symbol=data["symbol"],
            side=data["side"],
            quantity=Decimal(str(data["quantity"])),
            price=Decimal(str(data["price"])),
            total_value=Decimal(str(data["totalValue"])),
            fee=Decimal(str(data["fee"])),
            fee_currency=data["feeCurrency"],
            status=data["status"],
            executed_at=data["executedAt"],
        )
    
    def get_net_value(self) -> Decimal:
        """Get net value after fees."""
        if self.side == "BUY":
            return self.total_value + self.fee
        else:
            return self.total_value - self.fee