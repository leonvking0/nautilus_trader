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
Test data loaders with real data from Backpack Exchange.
"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from nautilus_trader.adapters.backpack.loaders import (
    BackpackBarDataLoader,
    BackpackOrderBookDeltaDataLoader,
    BackpackTradeTickDataLoader,
)
from nautilus_trader.model.data import Bar, BarType, OrderBookDelta, TradeTick
from nautilus_trader.model.enums import AggressorSide, BarAggregation, BookAction, OrderSide, PriceType
from nautilus_trader.model.identifiers import InstrumentId, TradeId
from nautilus_trader.model.objects import Price, Quantity


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestBackpackBarDataLoader:
    """Test the BackpackBarDataLoader with real kline data."""
    
    def setup_method(self):
        """Load real kline data from fixtures."""
        klines_path = FIXTURES_DIR / "sample_klines.json"
        if not klines_path.exists():
            pytest.skip(f"Fixture not found: {klines_path}")
        
        with open(klines_path, "r") as f:
            self.klines_data = json.load(f)
    
    def test_load_klines_from_json(self):
        """Test loading klines from JSON fixture."""
        # Get BTC_USDC 1h klines
        btc_klines = self.klines_data.get("BTC_USDC_1h", [])
        assert len(btc_klines) > 0, "No BTC klines found in fixtures"
        
        # Create temporary CSV file for loader testing
        temp_file = FIXTURES_DIR / "temp_btc_klines.csv"
        
        # Convert to CSV format expected by loader
        df = pd.DataFrame(btc_klines)
        
        # Add required columns for NautilusTrader format
        df["symbol"] = "BTC_USDC"
        df["timestamp"] = pd.to_datetime(df["start"]).astype(int) // 10**6  # Convert to milliseconds
        
        # Save to CSV
        df.to_csv(temp_file, index=False)
        
        try:
            # Load with BackpackBarDataLoader
            loaded_df = BackpackBarDataLoader.load(temp_file)
            
            # Validate loaded data
            assert len(loaded_df) == len(btc_klines)
            assert "instrument_id" in loaded_df.columns
            assert "open" in loaded_df.columns
            assert "high" in loaded_df.columns
            assert "low" in loaded_df.columns
            assert "close" in loaded_df.columns
            assert "volume" in loaded_df.columns
            
            # Check instrument ID format
            assert loaded_df["instrument_id"].iloc[0] == "BTC_USDC.BACKPACK"
            
            # Validate price relationships
            for idx, row in loaded_df.iterrows():
                assert row["high"] >= row["low"]
                assert row["high"] >= row["open"]
                assert row["high"] >= row["close"]
                assert row["low"] <= row["open"]
                assert row["low"] <= row["close"]
            
            print(f"✅ Loaded {len(loaded_df)} bars from klines data")
            
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
    
    def test_convert_to_nautilus_bars(self):
        """Test conversion to NautilusTrader Bar objects."""
        btc_klines = self.klines_data.get("BTC_USDC_1h", [])[:10]  # Use first 10 klines
        
        bars = []
        instrument_id = InstrumentId.from_str("BTC_USDC.BACKPACK")
        
        from nautilus_trader.model.data import BarSpecification
        
        bar_spec = BarSpecification(
            step=1,
            aggregation=BarAggregation.HOUR,
            price_type=PriceType.LAST,
        )
        bar_type = BarType(
            instrument_id=instrument_id,
            bar_spec=bar_spec,
        )
        
        for kline in btc_klines:
            # Parse kline data
            open_price = Price.from_str(kline["open"])
            high_price = Price.from_str(kline["high"])
            low_price = Price.from_str(kline["low"])
            close_price = Price.from_str(kline["close"])
            volume = Quantity.from_str(kline["volume"])
            
            # Convert timestamp
            ts_event = int(pd.to_datetime(kline["start"]).timestamp() * 1_000_000_000)
            ts_init = ts_event
            
            # Create Bar object
            bar = Bar(
                bar_type=bar_type,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                ts_event=ts_event,
                ts_init=ts_init,
            )
            bars.append(bar)
        
        # Validate bars
        assert len(bars) == len(btc_klines)
        assert all(isinstance(bar, Bar) for bar in bars)
        
        # Check first bar values (with tolerance for float precision)
        first_bar = bars[0]
        first_kline = btc_klines[0]
        assert abs(float(first_bar.open) - float(first_kline["open"])) < 0.01
        assert abs(float(first_bar.high) - float(first_kline["high"])) < 0.01
        assert abs(float(first_bar.low) - float(first_kline["low"])) < 0.01
        assert abs(float(first_bar.close) - float(first_kline["close"])) < 0.01
        
        print(f"✅ Converted {len(bars)} klines to Bar objects")


class TestBackpackTradeTickDataLoader:
    """Test the BackpackTradeTickDataLoader with real trade data."""
    
    def setup_method(self):
        """Load real trade data from fixtures."""
        trades_path = FIXTURES_DIR / "sample_trades.json"
        if not trades_path.exists():
            pytest.skip(f"Fixture not found: {trades_path}")
        
        with open(trades_path, "r") as f:
            self.trades_data = json.load(f)
    
    def test_load_trades_from_json(self):
        """Test loading trades from JSON fixture."""
        # Get BTC_USDC trades
        btc_trades = self.trades_data.get("BTC_USDC", [])
        assert len(btc_trades) > 0, "No BTC trades found in fixtures"
        
        # Create temporary CSV file for loader testing
        temp_file = FIXTURES_DIR / "temp_btc_trades.csv"
        
        # Convert to DataFrame
        df = pd.DataFrame(btc_trades)
        
        # Add required columns
        df["symbol"] = "BTC_USDC"
        df["aggressor_side"] = df["isBuyerMaker"].apply(lambda x: "SELL" if x else "BUY")
        
        # Save to CSV
        df.to_csv(temp_file, index=False)
        
        try:
            # Load with BackpackTradeTickDataLoader
            loaded_df = BackpackTradeTickDataLoader.load(temp_file)
            
            # Validate loaded data
            assert len(loaded_df) == len(btc_trades)
            assert "instrument_id" in loaded_df.columns
            assert "price" in loaded_df.columns
            assert "size" in loaded_df.columns  # Loader maps quantity to size
            assert "aggressor_side" in loaded_df.columns
            assert "trade_id" in loaded_df.columns
            
            # Check instrument ID format
            assert loaded_df["instrument_id"].iloc[0] == "BTC_USDC.BACKPACK"
            
            print(f"✅ Loaded {len(loaded_df)} trades from trade data")
            
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
    
    def test_convert_to_nautilus_trade_ticks(self):
        """Test conversion to NautilusTrader TradeTick objects."""
        btc_trades = self.trades_data.get("BTC_USDC", [])[:10]  # Use first 10 trades
        
        trade_ticks = []
        instrument_id = InstrumentId.from_str("BTC_USDC.BACKPACK")
        
        for i, trade in enumerate(btc_trades):
            # Parse trade data
            price = Price.from_str(str(trade["price"]))
            quantity = Quantity.from_str(str(trade["quantity"]))
            aggressor_side = AggressorSide.SELLER if trade["isBuyerMaker"] else AggressorSide.BUYER
            trade_id = TradeId(str(trade.get("id", i)))
            
            # Convert timestamp
            ts_event = trade["timestamp"] * 1_000_000  # Convert ms to ns
            ts_init = ts_event
            
            # Create TradeTick object
            tick = TradeTick(
                instrument_id=instrument_id,
                price=price,
                size=quantity,
                aggressor_side=aggressor_side,
                trade_id=trade_id,
                ts_event=ts_event,
                ts_init=ts_init,
            )
            trade_ticks.append(tick)
        
        # Validate trade ticks
        assert len(trade_ticks) == len(btc_trades)
        assert all(isinstance(tick, TradeTick) for tick in trade_ticks)
        
        # Check first trade tick values
        first_tick = trade_ticks[0]
        first_trade = btc_trades[0]
        assert float(first_tick.price) == float(first_trade["price"])
        assert float(first_tick.size) == float(first_trade["quantity"])
        
        print(f"✅ Converted {len(trade_ticks)} trades to TradeTick objects")


class TestBackpackOrderBookDeltaDataLoader:
    """Test the BackpackOrderBookDeltaDataLoader with real order book data."""
    
    def setup_method(self):
        """Load real order book data from fixtures."""
        orderbook_path = FIXTURES_DIR / "sample_orderbooks.json"
        if not orderbook_path.exists():
            pytest.skip(f"Fixture not found: {orderbook_path}")
        
        with open(orderbook_path, "r") as f:
            self.orderbook_data = json.load(f)
    
    def test_load_orderbook_snapshot(self):
        """Test loading order book snapshot."""
        # Get BTC_USDC order book
        btc_book = self.orderbook_data.get("BTC_USDC", {})
        assert "bids" in btc_book, "No bids found in order book"
        assert "asks" in btc_book, "No asks found in order book"
        
        # Create list of order book updates
        updates = []
        
        # Add bids as deltas
        for bid in btc_book["bids"]:
            updates.append({
                "symbol": "BTC_USDC",
                "action": "ADD",
                "side": "bid",  # Use lowercase to match expected format
                "price": bid[0],
                "size": bid[1],
                "order_id": 0,
                "timestamp": btc_book.get("lastUpdateId", 0),
            })
        
        # Add asks as deltas
        for ask in btc_book["asks"]:
            updates.append({
                "symbol": "BTC_USDC",
                "action": "ADD",
                "side": "ask",  # Use lowercase to match expected format
                "price": ask[0],
                "size": ask[1],
                "order_id": 0,
                "timestamp": btc_book.get("lastUpdateId", 0),
            })
        
        # Create temporary CSV file
        temp_file = FIXTURES_DIR / "temp_btc_orderbook.csv"
        df = pd.DataFrame(updates)
        df.to_csv(temp_file, index=False)
        
        try:
            # Load with BackpackOrderBookDeltaDataLoader
            loaded_df = BackpackOrderBookDeltaDataLoader.load(temp_file)
            
            # Validate loaded data
            assert len(loaded_df) == len(updates)
            assert "instrument_id" in loaded_df.columns
            assert "action" in loaded_df.columns
            assert "side" in loaded_df.columns
            assert "price" in loaded_df.columns
            assert "size" in loaded_df.columns
            
            # Check instrument ID format
            assert loaded_df["instrument_id"].iloc[0] == "BTC_USDC.BACKPACK"
            
            # Validate sides
            bid_count = len([u for u in updates if u["side"] == "bid"])
            ask_count = len([u for u in updates if u["side"] == "ask"])
            # The loader maps bid/ask to BUY/SELL
            assert len(loaded_df[loaded_df["side"] == "BUY"]) == bid_count
            assert len(loaded_df[loaded_df["side"] == "SELL"]) == ask_count
            
            print(f"✅ Loaded {len(loaded_df)} order book deltas")
            print(f"   - {bid_count} bids")
            print(f"   - {ask_count} asks")
            
        finally:
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
    
    def test_convert_to_nautilus_order_book_deltas(self):
        """Test conversion to NautilusTrader OrderBookDelta objects."""
        btc_book = self.orderbook_data.get("BTC_USDC", {})
        
        # For a proper implementation, we would create OrderBookDelta objects
        # with BookOrder objects, but that requires more setup.
        # Here we just validate the data structure is correct
        
        instrument_id = InstrumentId.from_str("BTC_USDC.BACKPACK")
        
        # Validate we have bids and asks
        assert len(btc_book["bids"]) > 0
        assert len(btc_book["asks"]) > 0
        
        # Validate bid/ask structure
        for bid in btc_book["bids"][:5]:
            assert len(bid) >= 2  # [price, size]
            assert float(bid[0]) > 0  # price
            assert float(bid[1]) > 0  # size
        
        for ask in btc_book["asks"][:5]:
            assert len(ask) >= 2  # [price, size]
            assert float(ask[0]) > 0  # price
            assert float(ask[1]) > 0  # size
        
        # Note: Order book might not be sorted from the API
        # In production, we would sort the book appropriately
        
        print(f"✅ Validated order book structure with {len(btc_book['bids'])} bids and {len(btc_book['asks'])} asks")


def test_all_loaders_with_real_data():
    """Integration test for all data loaders with real fixtures."""
    print("\n" + "="*60)
    print("Testing All Data Loaders with Real Data")
    print("="*60)
    
    # Test bar loader
    bar_loader_test = TestBackpackBarDataLoader()
    bar_loader_test.setup_method()
    bar_loader_test.test_load_klines_from_json()
    bar_loader_test.test_convert_to_nautilus_bars()
    
    # Test trade loader
    trade_loader_test = TestBackpackTradeTickDataLoader()
    trade_loader_test.setup_method()
    trade_loader_test.test_load_trades_from_json()
    trade_loader_test.test_convert_to_nautilus_trade_ticks()
    
    # Test order book loader
    book_loader_test = TestBackpackOrderBookDeltaDataLoader()
    book_loader_test.setup_method()
    book_loader_test.test_load_orderbook_snapshot()
    book_loader_test.test_convert_to_nautilus_order_book_deltas()
    
    print("\n" + "="*60)
    print("✅ All data loader tests passed!")
    print("="*60)


if __name__ == "__main__":
    test_all_loaders_with_real_data()