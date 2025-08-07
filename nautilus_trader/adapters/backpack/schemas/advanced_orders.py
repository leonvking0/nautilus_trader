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

"""Backpack advanced order schemas."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.enums import TriggerType


@dataclass
class BackpackAdvancedOrderParams:
    """
    Parameters for advanced order types on Backpack exchange.
    
    Supports stop orders, take profit orders, and related functionality.
    """
    
    # Basic order parameters
    symbol: str
    side: str  # "Bid" or "Ask"
    order_type: str
    quantity: str
    price: Optional[str] = None
    time_in_force: Optional[str] = None
    client_order_id: Optional[str] = None
    
    # Trigger order parameters
    trigger_price: Optional[str] = None
    trigger_by: Optional[str] = None  # "LastPrice", "MarkPrice", "IndexPrice"
    trigger_quantity: Optional[str] = None
    
    # Take profit parameters
    take_profit_trigger_price: Optional[str] = None
    take_profit_limit_price: Optional[str] = None
    take_profit_trigger_by: Optional[str] = None
    
    # Stop loss parameters
    stop_loss_trigger_price: Optional[str] = None
    stop_loss_limit_price: Optional[str] = None
    stop_loss_trigger_by: Optional[str] = None
    
    # Advanced features
    reduce_only: Optional[bool] = None
    post_only: Optional[bool] = None
    iceberg_qty: Optional[str] = None  # Display quantity for iceberg orders
    
    # Futures-specific
    position_side: Optional[str] = None  # "LONG" or "SHORT"
    
    def to_request_params(self) -> dict:
        """Convert to API request parameters, excluding None values."""
        params = {}
        
        # Add basic parameters
        params["symbol"] = self.symbol
        params["side"] = self.side
        params["orderType"] = self.order_type
        params["quantity"] = self.quantity
        
        # Add optional parameters
        if self.price is not None:
            params["price"] = self.price
        if self.time_in_force is not None:
            params["timeInForce"] = self.time_in_force
        if self.client_order_id is not None:
            params["clientId"] = self.client_order_id
            
        # Add trigger parameters
        if self.trigger_price is not None:
            params["triggerPrice"] = self.trigger_price
        if self.trigger_by is not None:
            params["triggerBy"] = self.trigger_by
        if self.trigger_quantity is not None:
            params["triggerQuantity"] = self.trigger_quantity
            
        # Add take profit parameters
        if self.take_profit_trigger_price is not None:
            params["takeProfitTriggerPrice"] = self.take_profit_trigger_price
        if self.take_profit_limit_price is not None:
            params["takeProfitLimitPrice"] = self.take_profit_limit_price
        if self.take_profit_trigger_by is not None:
            params["takeProfitTriggerBy"] = self.take_profit_trigger_by
            
        # Add stop loss parameters
        if self.stop_loss_trigger_price is not None:
            params["stopLossTriggerPrice"] = self.stop_loss_trigger_price
        if self.stop_loss_limit_price is not None:
            params["stopLossLimitPrice"] = self.stop_loss_limit_price
        if self.stop_loss_trigger_by is not None:
            params["stopLossTriggerBy"] = self.stop_loss_trigger_by
            
        # Add advanced features
        if self.reduce_only is not None:
            params["reduceOnly"] = self.reduce_only
        if self.post_only is not None:
            params["postOnly"] = self.post_only
        if self.iceberg_qty is not None:
            params["icebergQty"] = self.iceberg_qty
            
        # Add futures-specific parameters
        if self.position_side is not None:
            params["positionSide"] = self.position_side
            
        return params


@dataclass
class BackpackOrderUpdate:
    """
    Order update from WebSocket stream with advanced order fields.
    """
    
    event_type: str  # orderAccepted, orderCancelled, orderExpired, orderFill, orderModified, triggerPlaced, triggerFailed
    event_time: int  # Event time in microseconds
    symbol: str
    order_id: str
    client_order_id: Optional[str] = None
    side: Optional[str] = None
    order_type: Optional[str] = None
    time_in_force: Optional[str] = None
    quantity: Optional[str] = None
    quantity_quote: Optional[str] = None
    price: Optional[str] = None
    trigger_price: Optional[str] = None
    trigger_by: Optional[str] = None
    take_profit_trigger_price: Optional[str] = None
    stop_loss_trigger_price: Optional[str] = None
    take_profit_trigger_by: Optional[str] = None
    stop_loss_trigger_by: Optional[str] = None
    trigger_quantity: Optional[str] = None
    order_state: Optional[str] = None
    order_expiry_reason: Optional[str] = None
    trade_id: Optional[str] = None
    fill_quantity: Optional[str] = None
    executed_quantity: Optional[str] = None
    executed_quantity_quote: Optional[str] = None
    fill_price: Optional[str] = None
    is_maker: Optional[bool] = None
    fee: Optional[str] = None
    fee_symbol: Optional[str] = None
    self_trade_prevention: Optional[str] = None
    engine_timestamp: Optional[int] = None
    origin: Optional[str] = None
    related_order_id: Optional[str] = None  # For OCO orders
    
    @classmethod
    def from_websocket_message(cls, data: dict) -> "BackpackOrderUpdate":
        """Create from WebSocket message data."""
        return cls(
            event_type=data.get("e"),
            event_time=data.get("E"),
            symbol=data.get("s"),
            order_id=data.get("i"),
            client_order_id=data.get("c"),
            side=data.get("S"),
            order_type=data.get("o"),
            time_in_force=data.get("f"),
            quantity=data.get("q"),
            quantity_quote=data.get("Q"),
            price=data.get("p"),
            trigger_price=data.get("P"),
            trigger_by=data.get("B"),
            take_profit_trigger_price=data.get("a"),
            stop_loss_trigger_price=data.get("b"),
            take_profit_trigger_by=data.get("d"),
            stop_loss_trigger_by=data.get("g"),
            trigger_quantity=data.get("Y"),
            order_state=data.get("X"),
            order_expiry_reason=data.get("R"),
            trade_id=data.get("t"),
            fill_quantity=data.get("l"),
            executed_quantity=data.get("z"),
            executed_quantity_quote=data.get("Z"),
            fill_price=data.get("L"),
            is_maker=data.get("m"),
            fee=data.get("n"),
            fee_symbol=data.get("N"),
            self_trade_prevention=data.get("V"),
            engine_timestamp=data.get("T"),
            origin=data.get("O"),
            related_order_id=data.get("I"),
        )


def backpack_trigger_type_from_nautilus(trigger_type: TriggerType) -> str:
    """
    Convert NautilusTrader TriggerType to Backpack trigger reference.
    
    Parameters
    ----------
    trigger_type : TriggerType
        The NautilusTrader trigger type.
    
    Returns
    -------
    str
        The Backpack trigger reference string.
    
    """
    if trigger_type == TriggerType.DEFAULT or trigger_type == TriggerType.LAST_PRICE:
        return "LastPrice"
    elif trigger_type == TriggerType.MARK_PRICE:
        return "MarkPrice"
    elif trigger_type == TriggerType.INDEX_PRICE:
        return "IndexPrice"
    else:
        # Default to LastPrice for unsupported types
        return "LastPrice"


def backpack_order_type_for_stop(order_type: OrderType) -> str:
    """
    Convert NautilusTrader OrderType to Backpack order type string for stop orders.
    
    Parameters
    ----------
    order_type : OrderType
        The NautilusTrader order type.
    
    Returns
    -------
    str
        The Backpack order type string.
    
    """
    if order_type == OrderType.STOP_MARKET:
        return "Stop"
    elif order_type == OrderType.STOP_LIMIT:
        return "StopLimit"
    elif order_type == OrderType.TRAILING_STOP_MARKET:
        return "TrailingStop"
    elif order_type == OrderType.LIMIT_IF_TOUCHED:
        return "TakeProfit"
    elif order_type == OrderType.MARKET_IF_TOUCHED:
        return "TakeProfitMarket"
    else:
        # For regular orders
        if order_type == OrderType.MARKET:
            return "Market"
        elif order_type == OrderType.LIMIT:
            return "Limit"
        else:
            return str(order_type)