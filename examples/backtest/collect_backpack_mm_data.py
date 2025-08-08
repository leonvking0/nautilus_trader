#!/usr/bin/env python3
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
Collect live orderbook and trade data from Backpack Exchange for market making backtest.

This script:
1. Connects to Backpack WebSocket streams
2. Collects orderbook snapshots and updates
3. Collects trade ticks
4. Runs for specified duration (default 20 minutes)
5. Saves data to a ParquetDataCatalog for backtesting
"""

import asyncio
import os
import shutil
import signal
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import aiohttp
import msgspec
import pandas as pd

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.parsing import parse_order_book
from nautilus_trader.adapters.backpack.schemas.market import BackpackOrderBook
from nautilus_trader.adapters.backpack.schemas.market import BackpackTrade
from nautilus_trader.common.component import Clock
from nautilus_trader.common.component import LiveClock
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import BookAction
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog


class BackpackDataCollector:
    """Collect live data from Backpack Exchange."""
    
    def __init__(
        self,
        symbol: str = "SOL_USDC",
        duration_mins: int = 20,
        catalog_path: str = "backpack_mm_catalog",
    ):
        self.symbol = symbol
        self.duration_mins = duration_mins
        self.catalog_path = catalog_path
        
        # Initialize clock
        self.clock = LiveClock()
        
        # Data storage
        self.orderbook_deltas: list[OrderBookDeltas] = []
        self.trade_ticks: list[TradeTick] = []
        
        # WebSocket state
        self.ws_session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.running = False
        
        # Statistics
        self.stats = {
            "orderbook_updates": 0,
            "trades": 0,
            "start_time": None,
            "end_time": None,
        }
        
        # Create instrument
        self.instrument = self._create_instrument()
        self.instrument_id = self.instrument.id
        
    def _create_instrument(self) -> CurrencyPair:
        """Create the instrument for data collection."""
        base, quote = self.symbol.split("_")
        
        return CurrencyPair(
            instrument_id=InstrumentId(
                symbol=Symbol(self.symbol),
                venue=BACKPACK_VENUE,
            ),
            raw_symbol=Symbol(self.symbol),
            base_currency=Currency.from_str(base),
            quote_currency=Currency.from_str(quote),
            price_precision=2,  # Will be updated from actual data
            size_precision=4,    # Will be updated from actual data
            price_increment=Price.from_str("0.01"),
            size_increment=Quantity.from_str("0.0001"),
            lot_size=None,
            max_quantity=Quantity.from_str("10000"),
            min_quantity=Quantity.from_str("0.0001"),
            max_notional=None,
            min_notional=None,
            max_price=Price.from_str("1000000"),
            min_price=Price.from_str("0.01"),
            margin_init=Decimal("0"),
            margin_maint=Decimal("0"),
            maker_fee=Decimal("0.0002"),  # 0.02%
            taker_fee=Decimal("0.0005"),  # 0.05%
            ts_event=0,
            ts_init=0,
        )
    
    async def fetch_initial_orderbook(self) -> OrderBookDeltas | None:
        """Fetch initial orderbook snapshot via REST API."""
        url = "https://api.backpack.exchange/api/v1/depth"
        params = {"symbol": self.symbol}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    ts_init = self.clock.timestamp_ns()
                    
                    # Parse orderbook data
                    deltas = parse_order_book(data, self.symbol, ts_init)
                    
                    print(f"Fetched initial orderbook: {len(deltas.deltas)} levels")
                    return deltas
                else:
                    print(f"Failed to fetch orderbook: {response.status}")
                    return None
    
    async def connect_websocket(self) -> None:
        """Connect to Backpack WebSocket stream."""
        # Backpack WebSocket endpoint
        ws_url = "wss://ws.backpack.exchange"
        
        self.ws_session = aiohttp.ClientSession()
        self.ws = await self.ws_session.ws_connect(ws_url)
        
        # Subscribe to orderbook and trades
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [
                f"depth.{self.symbol}",
                f"trades.{self.symbol}",
            ],
        }
        
        await self.ws.send_json(subscribe_msg)
        print(f"Connected to WebSocket and subscribed to {self.symbol} streams")
    
    async def process_ws_message(self, msg: dict) -> None:
        """Process WebSocket message."""
        if "stream" not in msg:
            return
            
        stream = msg["stream"]
        data = msg.get("data", {})
        
        if stream == f"depth.{self.symbol}":
            # Process orderbook update
            self.process_orderbook_update(data)
        elif stream == f"trades.{self.symbol}":
            # Process trade
            self.process_trade(data)
    
    def process_orderbook_update(self, data: dict) -> None:
        """Process orderbook update message."""
        ts_init = self.clock.timestamp_ns()
        
        # Create OrderBookDeltas from update
        deltas = []
        
        # Process bids
        for bid in data.get("bids", []):
            price = Price.from_str(str(bid[0]))
            size = Quantity.from_str(str(bid[1]))
            
            action = BookAction.UPDATE if size > 0 else BookAction.DELETE
            
            delta = OrderBookDelta(
                instrument_id=self.instrument_id,
                action=action,
                order=BookOrder(
                    side=OrderSide.BUY,
                    price=price,
                    size=size,
                    order_id=0,  # Not provided by Backpack
                ),
                flags=0,
                sequence=0,  # Not provided
                ts_event=ts_init,
                ts_init=ts_init,
            )
            deltas.append(delta)
        
        # Process asks
        for ask in data.get("asks", []):
            price = Price.from_str(str(ask[0]))
            size = Quantity.from_str(str(ask[1]))
            
            action = BookAction.UPDATE if size > 0 else BookAction.DELETE
            
            delta = OrderBookDelta(
                instrument_id=self.instrument_id,
                action=action,
                order=BookOrder(
                    side=OrderSide.SELL,
                    price=price,
                    size=size,
                    order_id=0,  # Not provided by Backpack
                ),
                flags=0,
                sequence=0,  # Not provided
                ts_event=ts_init,
                ts_init=ts_init,
            )
            deltas.append(delta)
        
        if deltas:
            orderbook_deltas = OrderBookDeltas(
                instrument_id=self.instrument_id,
                deltas=deltas,
            )
            self.orderbook_deltas.append(orderbook_deltas)
            self.stats["orderbook_updates"] += 1
    
    def process_trade(self, data: dict) -> None:
        """Process trade message."""
        ts_init = self.clock.timestamp_ns()
        
        # Parse trade data
        price = Price.from_str(str(data.get("price", 0)))
        size = Quantity.from_str(str(data.get("quantity", 0)))
        side = data.get("side", "buy")
        trade_id = str(data.get("id", ts_init))
        
        # Determine aggressor side
        aggressor_side = AggressorSide.BUYER if side == "buy" else AggressorSide.SELLER
        
        trade = TradeTick(
            instrument_id=self.instrument_id,
            price=price,
            size=size,
            aggressor_side=aggressor_side,
            trade_id=TradeId(trade_id),
            ts_event=ts_init,
            ts_init=ts_init,
        )
        
        self.trade_ticks.append(trade)
        self.stats["trades"] += 1
    
    async def collect_data(self) -> None:
        """Main data collection loop."""
        self.running = True
        self.stats["start_time"] = datetime.now(timezone.utc)
        
        print(f"Starting data collection for {self.duration_mins} minutes...")
        print(f"Symbol: {self.symbol}")
        print(f"Start time: {self.stats['start_time']}")
        
        # Fetch initial orderbook
        initial_ob = await self.fetch_initial_orderbook()
        if initial_ob:
            self.orderbook_deltas.append(initial_ob)
        
        # Connect to WebSocket
        await self.connect_websocket()
        
        # Calculate end time
        end_time = datetime.now(timezone.utc) + timedelta(minutes=self.duration_mins)
        
        # Collect data until duration expires
        try:
            while self.running and datetime.now(timezone.utc) < end_time:
                try:
                    msg = await asyncio.wait_for(
                        self.ws.receive(),
                        timeout=1.0,
                    )
                    
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = msgspec.json.decode(msg.data)
                        await self.process_ws_message(data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"WebSocket error: {msg.data}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        print("WebSocket closed")
                        break
                        
                except asyncio.TimeoutError:
                    # Print progress every timeout
                    remaining = (end_time - datetime.now(timezone.utc)).total_seconds()
                    print(f"Progress: {self.stats['orderbook_updates']} orderbook updates, "
                          f"{self.stats['trades']} trades | "
                          f"Remaining: {remaining:.0f}s")
                    
        except KeyboardInterrupt:
            print("\nData collection interrupted by user")
        finally:
            self.running = False
            self.stats["end_time"] = datetime.now(timezone.utc)
            
            # Clean up WebSocket
            if self.ws:
                await self.ws.close()
            if self.ws_session:
                await self.ws_session.close()
    
    def save_to_catalog(self) -> None:
        """Save collected data to ParquetDataCatalog."""
        print("\n" + "=" * 80)
        print("Saving data to catalog...")
        
        # Clear catalog if exists
        if os.path.exists(self.catalog_path):
            shutil.rmtree(self.catalog_path)
        os.mkdir(self.catalog_path)
        
        # Create catalog
        catalog = ParquetDataCatalog(self.catalog_path)
        
        # Write instrument
        catalog.write_data([self.instrument])
        
        # Write orderbook deltas
        if self.orderbook_deltas:
            # Flatten all deltas
            all_deltas = []
            for ob_deltas in self.orderbook_deltas:
                all_deltas.extend(ob_deltas.deltas)
            
            # Sort by timestamp
            all_deltas.sort(key=lambda x: x.ts_init)
            
            # Write to catalog
            catalog.write_data(all_deltas)
            print(f"Saved {len(all_deltas)} orderbook deltas")
        
        # Write trade ticks
        if self.trade_ticks:
            catalog.write_data(self.trade_ticks)
            print(f"Saved {len(self.trade_ticks)} trade ticks")
        
        print(f"Catalog saved to: {self.catalog_path}")
    
    def print_summary(self) -> None:
        """Print collection summary."""
        print("\n" + "=" * 80)
        print("Data Collection Summary")
        print("=" * 80)
        print(f"Symbol: {self.symbol}")
        print(f"Duration: {self.duration_mins} minutes")
        print(f"Start time: {self.stats['start_time']}")
        print(f"End time: {self.stats['end_time']}")
        
        if self.stats['start_time'] and self.stats['end_time']:
            actual_duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            print(f"Actual duration: {actual_duration:.1f} seconds")
        
        print(f"\nData collected:")
        print(f"  Orderbook updates: {self.stats['orderbook_updates']}")
        print(f"  Trades: {self.stats['trades']}")
        
        if self.trade_ticks:
            # Calculate some basic statistics
            prices = [float(t.price) for t in self.trade_ticks]
            volumes = [float(t.size) for t in self.trade_ticks]
            
            print(f"\nTrade statistics:")
            print(f"  Price range: ${min(prices):.2f} - ${max(prices):.2f}")
            print(f"  Avg price: ${sum(prices)/len(prices):.2f}")
            print(f"  Total volume: {sum(volumes):.4f} {self.symbol.split('_')[0]}")
        
        print("\n" + "=" * 80)


async def main():
    """Run the data collector."""
    # Configuration
    symbol = os.getenv("BACKPACK_SYMBOL", "SOL_USDC")
    duration_mins = int(os.getenv("COLLECTION_DURATION_MINS", "20"))
    catalog_path = os.getenv("CATALOG_PATH", "backpack_mm_catalog")
    
    # Create collector
    collector = BackpackDataCollector(
        symbol=symbol,
        duration_mins=duration_mins,
        catalog_path=catalog_path,
    )
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down gracefully...")
        collector.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Collect data
    await collector.collect_data()
    
    # Save to catalog
    collector.save_to_catalog()
    
    # Print summary
    collector.print_summary()


if __name__ == "__main__":
    print("Backpack Market Making Data Collector")
    print("=" * 80)
    print("This script will collect live orderbook and trade data from Backpack Exchange")
    print("for use in market making strategy backtesting.")
    print("\nConfiguration (via environment variables):")
    print(f"  BACKPACK_SYMBOL: {os.getenv('BACKPACK_SYMBOL', 'SOL_USDC')} (default: SOL_USDC)")
    print(f"  COLLECTION_DURATION_MINS: {os.getenv('COLLECTION_DURATION_MINS', '20')} (default: 20)")
    print(f"  CATALOG_PATH: {os.getenv('CATALOG_PATH', 'backpack_mm_catalog')} (default: backpack_mm_catalog)")
    print("=" * 80)
    print()
    
    asyncio.run(main())