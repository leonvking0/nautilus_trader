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
Backpack system order handling for liquidations, ADL, and settlements.

This module manages system-generated orders and events including:
- Liquidation orders and events
- Auto-deleveraging (ADL) events  
- Settlement processing
- Collateral conversion events
- System order identification and tracking
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from nautilus_trader.common.component import Component
from nautilus_trader.core.message import Event
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.identifiers import VenueOrderId
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orders import Order
from nautilus_trader.msgbus.bus import MessageBus


class SystemOrderType(Enum):
    """Type of system-generated order."""
    
    LIQUIDATION = "LIQUIDATION"  # Forced liquidation due to margin call
    ADL = "ADL"  # Auto-deleveraging to reduce system risk
    SETTLEMENT = "SETTLEMENT"  # Settlement of expired contracts
    COLLATERAL_CONVERSION = "COLLATERAL_CONVERSION"  # Automatic collateral conversion
    FUNDING_PAYMENT = "FUNDING_PAYMENT"  # Funding rate payments
    INTEREST_PAYMENT = "INTEREST_PAYMENT"  # Interest on borrowed funds
    DUST_CONVERSION = "DUST_CONVERSION"  # Small balance cleanup


class SystemOrderReason(Enum):
    """Reason for system order generation."""
    
    MARGIN_CALL = "MARGIN_CALL"  # Below maintenance margin
    ISOLATED_MARGIN_BREACH = "ISOLATED_MARGIN_BREACH"  # Isolated position breach
    CROSS_MARGIN_BREACH = "CROSS_MARGIN_BREACH"  # Cross margin breach
    ADL_TRIGGER = "ADL_TRIGGER"  # ADL system activated
    CONTRACT_EXPIRY = "CONTRACT_EXPIRY"  # Contract settlement
    AUTO_CONVERT = "AUTO_CONVERT"  # Automatic conversion
    RISK_LIMIT = "RISK_LIMIT"  # Risk limit exceeded
    SYSTEM_MAINTENANCE = "SYSTEM_MAINTENANCE"  # System-initiated action


@dataclass
class BackpackSystemOrder:
    """Represents a system-generated order."""
    
    order_id: str
    instrument_id: InstrumentId
    order_type: SystemOrderType
    reason: SystemOrderReason
    side: str  # BUY/SELL
    quantity: Quantity
    price: Price | None  # None for market orders
    timestamp: int
    affected_position_id: str | None  # Position being liquidated/adjusted
    metadata: dict[str, Any] | None = None
    
    def is_liquidation(self) -> bool:
        """Check if this is a liquidation order."""
        return self.order_type == SystemOrderType.LIQUIDATION
    
    def is_adl(self) -> bool:
        """Check if this is an ADL order."""
        return self.order_type == SystemOrderType.ADL
    
    def to_venue_order_id(self) -> VenueOrderId:
        """Convert to VenueOrderId with system prefix."""
        return VenueOrderId(f"SYSTEM_{self.order_id}")


@dataclass
class LiquidationEvent(Event):
    """Event representing a liquidation."""
    
    account_id: AccountId
    instrument_id: InstrumentId
    position_id: PositionId
    side: PositionSide
    liquidation_price: Price
    liquidation_quantity: Quantity
    remaining_quantity: Quantity | None
    bankruptcy_price: Price | None
    margin_ratio: Decimal
    reason: SystemOrderReason
    ts_event: int
    ts_init: int
    
    def __repr__(self) -> str:
        return (
            f"LiquidationEvent("
            f"instrument={self.instrument_id}, "
            f"side={self.side}, "
            f"qty={self.liquidation_quantity}, "
            f"price={self.liquidation_price})"
        )


@dataclass
class ADLEvent(Event):
    """Event representing auto-deleveraging."""
    
    account_id: AccountId
    instrument_id: InstrumentId
    position_id: PositionId
    side: PositionSide
    adl_quantity: Quantity
    adl_price: Price
    adl_rank: int  # Position in ADL queue
    counterparty_count: int  # Number of counterparties affected
    ts_event: int
    ts_init: int
    
    def __repr__(self) -> str:
        return (
            f"ADLEvent("
            f"instrument={self.instrument_id}, "
            f"qty={self.adl_quantity}, "
            f"rank={self.adl_rank})"
        )


@dataclass
class SettlementEvent(Event):
    """Event representing contract settlement."""
    
    account_id: AccountId
    instrument_id: InstrumentId
    settlement_price: Price
    position_quantity: Quantity | None
    pnl: Money
    settlement_type: str  # CASH/PHYSICAL
    ts_event: int
    ts_init: int
    
    def __repr__(self) -> str:
        return (
            f"SettlementEvent("
            f"instrument={self.instrument_id}, "
            f"price={self.settlement_price}, "
            f"pnl={self.pnl})"
        )


@dataclass
class CollateralConversionEvent(Event):
    """Event representing collateral conversion."""
    
    account_id: AccountId
    from_currency: str
    to_currency: str
    from_amount: Decimal
    to_amount: Decimal
    conversion_rate: Decimal
    reason: SystemOrderReason
    ts_event: int
    ts_init: int
    
    def __repr__(self) -> str:
        return (
            f"CollateralConversionEvent("
            f"{self.from_currency}->{self.to_currency}, "
            f"amount={self.from_amount}, "
            f"rate={self.conversion_rate})"
        )


class BackpackSystemOrderHandler(Component):
    """
    Handles system-generated orders and events.
    
    Responsibilities:
    - Identify and track system orders
    - Process liquidation events
    - Handle ADL events
    - Process settlements
    - Track collateral conversions
    - Emit appropriate events to message bus
    """
    
    def __init__(
        self,
        msgbus: MessageBus,
        account_id: AccountId,
        logger: Any,
    ):
        super().__init__(logger=logger)
        self._msgbus = msgbus
        self._account_id = account_id
        self._system_orders: dict[str, BackpackSystemOrder] = {}
        self._liquidation_history: list[LiquidationEvent] = []
        self._adl_history: list[ADLEvent] = []
        self._settlement_history: list[SettlementEvent] = []
        
        # Subscribe to relevant topics
        self._msgbus.subscribe(topic="backpack.websocket.order", handler=self._handle_order_update)
        self._msgbus.subscribe(topic="backpack.websocket.position", handler=self._handle_position_update)
        
    def identify_system_order(self, order_data: dict) -> BackpackSystemOrder | None:
        """
        Identify if an order is system-generated.
        
        System orders typically have:
        - Special order source field
        - System-specific order IDs
        - Liquidation/ADL flags
        - No client order ID
        """
        # Check for system order indicators
        order_source = order_data.get("orderSource", "")
        order_type = order_data.get("orderType", "")
        client_order_id = order_data.get("clientOrderId")
        
        # System orders don't have client order IDs
        if client_order_id:
            return None
            
        # Check for liquidation indicators
        if any(indicator in order_source.upper() for indicator in ["LIQUIDATION", "SYSTEM", "ADL"]):
            return self._create_system_order(order_data, SystemOrderType.LIQUIDATION)
            
        # Check order type
        if order_type == "LIQUIDATION":
            return self._create_system_order(order_data, SystemOrderType.LIQUIDATION)
            
        # Check for ADL
        if "ADL" in order_source.upper():
            return self._create_system_order(order_data, SystemOrderType.ADL)
            
        # Check for settlement
        if "SETTLEMENT" in order_source.upper():
            return self._create_system_order(order_data, SystemOrderType.SETTLEMENT)
            
        return None
    
    def _create_system_order(
        self,
        order_data: dict,
        order_type: SystemOrderType,
    ) -> BackpackSystemOrder:
        """Create a system order from raw data."""
        reason = self._determine_reason(order_data, order_type)
        
        return BackpackSystemOrder(
            order_id=order_data["id"],
            instrument_id=InstrumentId.from_str(order_data["symbol"] + ".BACKPACK"),
            order_type=order_type,
            reason=reason,
            side=order_data["side"],
            quantity=Quantity.from_str(str(order_data["quantity"])),
            price=Price.from_str(str(order_data["price"])) if order_data.get("price") else None,
            timestamp=order_data["timestamp"],
            affected_position_id=order_data.get("positionId"),
            metadata=order_data,
        )
    
    def _determine_reason(
        self,
        order_data: dict,
        order_type: SystemOrderType,
    ) -> SystemOrderReason:
        """Determine the reason for system order."""
        if order_type == SystemOrderType.LIQUIDATION:
            margin_type = order_data.get("marginType", "")
            if margin_type == "ISOLATED":
                return SystemOrderReason.ISOLATED_MARGIN_BREACH
            return SystemOrderReason.CROSS_MARGIN_BREACH
            
        if order_type == SystemOrderType.ADL:
            return SystemOrderReason.ADL_TRIGGER
            
        if order_type == SystemOrderType.SETTLEMENT:
            return SystemOrderReason.CONTRACT_EXPIRY
            
        return SystemOrderReason.SYSTEM_MAINTENANCE
    
    async def process_liquidation(
        self,
        position_data: dict,
        liquidation_data: dict,
    ) -> LiquidationEvent:
        """Process a liquidation event."""
        event = LiquidationEvent(
            account_id=self._account_id,
            instrument_id=InstrumentId.from_str(position_data["symbol"] + ".BACKPACK"),
            position_id=PositionId(position_data["id"]),
            side=PositionSide[position_data["side"]],
            liquidation_price=Price.from_str(str(liquidation_data["liquidationPrice"])),
            liquidation_quantity=Quantity.from_str(str(liquidation_data["quantity"])),
            remaining_quantity=Quantity.from_str(str(liquidation_data.get("remainingQuantity", 0))),
            bankruptcy_price=Price.from_str(str(liquidation_data["bankruptcyPrice"])) if liquidation_data.get("bankruptcyPrice") else None,
            margin_ratio=Decimal(str(position_data.get("marginRatio", 0))),
            reason=SystemOrderReason.MARGIN_CALL,
            ts_event=liquidation_data["timestamp"],
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._liquidation_history.append(event)
        self._msgbus.publish(topic="backpack.liquidation", msg=event)
        
        self._log.warning(
            f"LIQUIDATION: {event.instrument_id} {event.side} "
            f"qty={event.liquidation_quantity} price={event.liquidation_price} "
            f"margin_ratio={event.margin_ratio}",
        )
        
        return event
    
    async def process_adl(
        self,
        position_data: dict,
        adl_data: dict,
    ) -> ADLEvent:
        """Process an auto-deleveraging event."""
        event = ADLEvent(
            account_id=self._account_id,
            instrument_id=InstrumentId.from_str(position_data["symbol"] + ".BACKPACK"),
            position_id=PositionId(position_data["id"]),
            side=PositionSide[position_data["side"]],
            adl_quantity=Quantity.from_str(str(adl_data["quantity"])),
            adl_price=Price.from_str(str(adl_data["price"])),
            adl_rank=adl_data.get("adlRank", 0),
            counterparty_count=adl_data.get("counterpartyCount", 0),
            ts_event=adl_data["timestamp"],
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._adl_history.append(event)
        self._msgbus.publish(topic="backpack.adl", msg=event)
        
        self._log.warning(
            f"ADL: {event.instrument_id} {event.side} "
            f"qty={event.adl_quantity} price={event.adl_price} "
            f"rank={event.adl_rank}",
        )
        
        return event
    
    async def process_settlement(
        self,
        instrument_data: dict,
        settlement_data: dict,
    ) -> SettlementEvent:
        """Process a contract settlement event."""
        pnl_value = Decimal(str(settlement_data.get("pnl", 0)))
        
        event = SettlementEvent(
            account_id=self._account_id,
            instrument_id=InstrumentId.from_str(instrument_data["symbol"] + ".BACKPACK"),
            settlement_price=Price.from_str(str(settlement_data["settlementPrice"])),
            position_quantity=Quantity.from_str(str(settlement_data.get("positionQuantity", 0))) if settlement_data.get("positionQuantity") else None,
            pnl=Money(pnl_value, USDC),
            settlement_type=settlement_data.get("settlementType", "CASH"),
            ts_event=settlement_data["timestamp"],
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._settlement_history.append(event)
        self._msgbus.publish(topic="backpack.settlement", msg=event)
        
        self._log.info(
            f"SETTLEMENT: {event.instrument_id} "
            f"price={event.settlement_price} pnl={event.pnl}",
        )
        
        return event
    
    async def process_collateral_conversion(
        self,
        conversion_data: dict,
    ) -> CollateralConversionEvent:
        """Process a collateral conversion event."""
        event = CollateralConversionEvent(
            account_id=self._account_id,
            from_currency=conversion_data["fromCurrency"],
            to_currency=conversion_data["toCurrency"],
            from_amount=Decimal(str(conversion_data["fromAmount"])),
            to_amount=Decimal(str(conversion_data["toAmount"])),
            conversion_rate=Decimal(str(conversion_data["rate"])),
            reason=SystemOrderReason.AUTO_CONVERT if conversion_data.get("auto") else SystemOrderReason.SYSTEM_MAINTENANCE,
            ts_event=conversion_data["timestamp"],
            ts_init=self._clock.timestamp_ns(),
        )
        
        self._msgbus.publish(topic="backpack.collateral_conversion", msg=event)
        
        self._log.info(
            f"COLLATERAL_CONVERSION: {event.from_currency}->{event.to_currency} "
            f"amount={event.from_amount} rate={event.conversion_rate}",
        )
        
        return event
    
    def _handle_order_update(self, msg: Any) -> None:
        """Handle order updates to detect system orders."""
        order_data = msg.data
        
        # Check if this is a system order
        system_order = self.identify_system_order(order_data)
        if system_order:
            self._system_orders[system_order.order_id] = system_order
            
            # Log system order detection
            self._log.warning(
                f"SYSTEM_ORDER detected: type={system_order.order_type} "
                f"reason={system_order.reason} id={system_order.order_id}",
            )
            
            # Process based on type
            if system_order.is_liquidation():
                asyncio.create_task(
                    self.process_liquidation(
                        order_data.get("position", {}),
                        order_data,
                    ),
                )
    
    def _handle_position_update(self, msg: Any) -> None:
        """Handle position updates to detect liquidations."""
        position_data = msg.data
        
        # Check for liquidation flag
        if position_data.get("liquidated") or position_data.get("status") == "LIQUIDATED":
            asyncio.create_task(
                self.process_liquidation(
                    position_data,
                    position_data.get("liquidation", {}),
                ),
            )
        
        # Check for ADL flag
        if position_data.get("adl") or position_data.get("adlFlag"):
            asyncio.create_task(
                self.process_adl(
                    position_data,
                    position_data.get("adlData", {}),
                ),
            )
    
    def get_system_orders(self) -> list[BackpackSystemOrder]:
        """Get all system orders."""
        return list(self._system_orders.values())
    
    def get_liquidation_history(self) -> list[LiquidationEvent]:
        """Get liquidation history."""
        return self._liquidation_history.copy()
    
    def get_adl_history(self) -> list[ADLEvent]:
        """Get ADL history."""
        return self._adl_history.copy()
    
    def get_settlement_history(self) -> list[SettlementEvent]:
        """Get settlement history."""
        return self._settlement_history.copy()
    
    def is_system_order(self, order_id: str) -> bool:
        """Check if an order ID represents a system order."""
        return order_id in self._system_orders or order_id.startswith("SYSTEM_")