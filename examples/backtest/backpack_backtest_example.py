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
Example script demonstrating how to backtest with Backpack Exchange data.

This script:
1. Fetches historical bar data from Backpack API
2. Stores it in a data catalog
3. Runs a backtest with an EMA crossover strategy
4. Displays performance results
"""

import asyncio
import os
import shutil
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pandas as pd

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.backtest.node import BacktestDataConfig
from nautilus_trader.backtest.node import BacktestEngineConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.node import BacktestRunConfig
from nautilus_trader.backtest.node import BacktestVenueConfig
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import AggregationSource
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler


async def fetch_backpack_bars(
    symbol: str = "BTC_USDC",
    interval: str = "1h",
    days_back: int = 30,
) -> list[list]:
    """
    Fetch historical klines/bars from Backpack Exchange.
    
    Parameters
    ----------
    symbol : str
        The trading pair symbol (e.g., 'BTC_USDC')
    interval : str
        The bar interval (1m, 5m, 15m, 1h, 4h, 1d)
    days_back : int
        Number of days of historical data to fetch
    
    Returns
    -------
    list[list]
        Raw klines data from Backpack API
    
    """
    # For public endpoints, we can use a direct HTTP request
    # The klines endpoint doesn't require authentication
    import aiohttp
    
    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days_back)
    
    # Convert to seconds (Backpack API uses seconds, not milliseconds)
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())
    
    print(f"Fetching {symbol} {interval} bars from {start_time} to {end_time}")
    
    # Fetch klines directly from the public API
    url = "https://api.backpack.exchange/api/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_timestamp,
        "endTime": end_timestamp,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                klines = await response.json()
                print(f"Fetched {len(klines)} bars from Backpack")
                return klines
            else:
                error_text = await response.text()
                raise Exception(f"Failed to fetch klines: {response.status} - {error_text}")


def create_backpack_instrument(
    symbol: str = "BTC_USDC", 
    price_precision: int = 1,
    size_precision: int = 8,
) -> CurrencyPair:
    """
    Create a Backpack instrument for backtesting.
    
    Parameters
    ----------
    symbol : str
        The trading pair symbol
    price_precision : int
        The price precision (will be auto-detected from data)
    size_precision : int
        The size/volume precision (will be auto-detected from data)
    
    Returns
    -------
    CurrencyPair
        The configured instrument
    
    """
    base, quote = symbol.split("_")
    
    # Set price increment based on precision
    price_increment_str = "0." + "0" * (price_precision - 1) + "1" if price_precision > 0 else "1"
    size_increment_str = "0." + "0" * (size_precision - 1) + "1" if size_precision > 0 else "1"
    
    return CurrencyPair(
        instrument_id=InstrumentId(
            symbol=Symbol(symbol),
            venue=BACKPACK_VENUE,
        ),
        raw_symbol=Symbol(symbol),
        base_currency=Currency.from_str(base),
        quote_currency=Currency.from_str(quote),
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=Price.from_str(price_increment_str),
        size_increment=Quantity.from_str(size_increment_str),
        lot_size=None,
        max_quantity=Quantity.from_str("10000"),
        min_quantity=Quantity.from_str("0.0001"),
        max_notional=None,
        min_notional=Money(10, Currency.from_str(quote)),  # $10 minimum
        max_price=Price.from_str("10000000"),
        min_price=Price.from_str("0.01"),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0.0002"),  # 0.02%
        taker_fee=Decimal("0.0005"),  # 0.05%
        ts_event=0,
        ts_init=0,
    )


def process_klines_to_bars(
    klines: list,
    instrument: CurrencyPair,
    bar_type: BarType,
) -> list[Bar]:
    """
    Process raw klines data into NautilusTrader Bar objects.
    
    Parameters
    ----------
    klines : list
        Raw klines data from Backpack (can be list of lists or list of dicts)
    instrument : CurrencyPair
        The instrument for the bars
    bar_type : BarType
        The bar type specification
    
    Returns
    -------
    list[Bar]
        Processed bar objects
    
    """
    bars = []
    
    for kline in klines:
        # Check if kline is a dict or list
        if isinstance(kline, dict):
            # Dictionary format from API
            timestamp_ms = kline.get('start', kline.get('timestamp', 0))
            open_price = kline.get('open', 0)
            high_price = kline.get('high', 0)
            low_price = kline.get('low', 0)
            close_price = kline.get('close', 0)
            volume = kline.get('volume', 0)
        else:
            # List format: [timestamp, open, high, low, close, volume, ...]
            timestamp_ms = kline[0]
            open_price = kline[1]
            high_price = kline[2]
            low_price = kline[3]
            close_price = kline[4]
            volume = kline[5]
        
        # Convert timestamp to nanoseconds
        # Handle both string and numeric timestamps
        if isinstance(timestamp_ms, str):
            # Parse string timestamp
            from dateutil import parser
            dt = parser.parse(timestamp_ms)
            timestamp_ms = int(dt.timestamp() * 1000)
        
        ts_event = int(timestamp_ms) * 1_000_000
        ts_init = ts_event
        
        bar = Bar(
            bar_type=bar_type,
            open=Price.from_str(str(open_price)),
            high=Price.from_str(str(high_price)),
            low=Price.from_str(str(low_price)),
            close=Price.from_str(str(close_price)),
            volume=Quantity.from_str(str(volume)),
            ts_event=ts_event,
            ts_init=ts_init,
        )
        bars.append(bar)
    
    return bars


async def main():
    """Run the Backpack backtest example."""
    
    # Configuration
    symbol = "BTC_USDC"
    interval = "1h"
    days_back = 30
    
    # 1. Fetch historical data from Backpack
    print("=" * 80)
    print("Step 1: Fetching historical data from Backpack Exchange")
    print("=" * 80)
    
    klines = await fetch_backpack_bars(
        symbol=symbol,
        interval=interval,
        days_back=days_back,
    )
    
    if not klines:
        print("No data fetched. Please check your connection and try again.")
        return
    
    # 2. Create instrument and process data
    print("\n" + "=" * 80)
    print("Step 2: Processing data for NautilusTrader")
    print("=" * 80)
    
    # Detect price and volume precision from the first kline
    if klines and len(klines) > 0:
        first_kline = klines[0]
        if isinstance(first_kline, dict):
            sample_price = str(first_kline.get('open', 0))
            sample_volume = str(first_kline.get('volume', 0))
        else:
            sample_price = str(first_kline[1])
            sample_volume = str(first_kline[5])
        
        # Determine price precision from decimal places
        if '.' in sample_price:
            decimal_places = len(sample_price.split('.')[1].rstrip('0'))
            price_precision = max(1, decimal_places)  # At least 1 decimal place
        else:
            price_precision = 0
            
        # Determine volume precision from decimal places
        if '.' in sample_volume:
            decimal_places = len(sample_volume.split('.')[1].rstrip('0'))
            size_precision = max(1, decimal_places)  # At least 1 decimal place
        else:
            size_precision = 0
    else:
        price_precision = 1  # Default
        size_precision = 3  # Default
    
    print(f"Detected price precision: {price_precision}, size precision: {size_precision}")
    instrument = create_backpack_instrument(symbol, price_precision, size_precision)
    
    # Create bar type
    bar_type = BarType(
        instrument_id=instrument.id,
        bar_spec=BarSpecification(
            step=1,
            aggregation=BarAggregation.HOUR,
            price_type=PriceType.LAST,
        ),
        aggregation_source=AggregationSource.EXTERNAL,
    )
    
    # Process klines to bars
    bars = process_klines_to_bars(klines, instrument, bar_type)
    print(f"Processed {len(bars)} bars")
    
    # 3. Set up data catalog
    print("\n" + "=" * 80)
    print("Step 3: Setting up data catalog")
    print("=" * 80)
    
    CATALOG_PATH = os.getcwd() + "/backpack_catalog"
    
    # Clear if it already exists, then create fresh
    if os.path.exists(CATALOG_PATH):
        shutil.rmtree(CATALOG_PATH)
    os.mkdir(CATALOG_PATH)
    
    # Create a catalog instance
    catalog = ParquetDataCatalog(CATALOG_PATH)
    
    # Write instrument and bars to catalog
    catalog.write_data([instrument])
    catalog.write_data(bars)
    
    print(f"Data catalog created at: {CATALOG_PATH}")
    print(f"Instruments in catalog: {catalog.instruments()}")
    
    # 4. Configure and run backtest
    print("\n" + "=" * 80)
    print("Step 4: Configuring and running backtest")
    print("=" * 80)
    
    # Configure data
    data_configs = [
        BacktestDataConfig(
            catalog_path=CATALOG_PATH,
            data_cls=Bar,
            instrument_id=instrument.id,
            bar_spec=bar_type.spec,  # Add bar_spec
        )
    ]
    
    # Configure venue
    venues_configs = [
        BacktestVenueConfig(
            name="BACKPACK",
            oms_type="NETTING",  # Use string instead of enum
            account_type="CASH",  # Use string instead of enum
            base_currency=None,
            starting_balances=["10000 USDC", "1 BTC"],
        )
    ]
    
    # Configure strategy
    strategies = [
        ImportableStrategyConfig(
            strategy_path="nautilus_trader.examples.strategies.ema_cross:EMACross",
            config_path="nautilus_trader.examples.strategies.ema_cross:EMACrossConfig",
            config={
                "instrument_id": str(instrument.id),
                "bar_type": str(bar_type),
                "fast_ema_period": 10,
                "slow_ema_period": 20,
                "trade_size": Decimal("0.01"),  # 0.01 BTC per trade
            },
        ),
    ]
    
    # Create run configuration
    config = BacktestRunConfig(
        engine=BacktestEngineConfig(
            strategies=strategies,
            logging=LoggingConfig(log_level="INFO"),
        ),
        data=data_configs,
        venues=venues_configs,
    )
    
    # Run backtest
    node = BacktestNode(configs=[config])
    result = node.run()
    
    # 5. Display results
    print("\n" + "=" * 80)
    print("Step 5: Backtest Results")
    print("=" * 80)
    
    print(f"\nBacktest completed!")
    print(f"Run ID: {result[0].run_id}")
    print(f"Duration: {result[0].stats['run_stats']['duration']}")
    
    # Get engine for detailed reports
    from nautilus_trader.backtest.engine import BacktestEngine
    engine: BacktestEngine = node.get_engine(config.id)
    
    # Generate reports
    print("\n--- Order Fills Report ---")
    fills_report = engine.trader.generate_order_fills_report()
    if not fills_report.empty:
        print(fills_report.head(10))
    else:
        print("No trades executed")
    
    print("\n--- Positions Report ---")
    positions_report = engine.trader.generate_positions_report()
    if not positions_report.empty:
        print(positions_report.head(10))
    else:
        print("No positions opened")
    
    print("\n--- Account Report ---")
    account_report = engine.trader.generate_account_report(BACKPACK_VENUE)
    print(account_report)
    
    # Clean up catalog
    print("\n" + "=" * 80)
    print("Backtest example completed successfully!")
    print("=" * 80)


# Missing import - let me add it
from nautilus_trader.model.data import BarSpecification


if __name__ == "__main__":
    asyncio.run(main())