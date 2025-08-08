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
Backtesting support for Backpack Exchange data.

This module provides:
- Historical data providers for backtesting
- Data clients for fetching historical data
- Integration with NautilusTrader's BacktestEngine
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.common.component import Logger
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import BarAggregation
from nautilus_trader.model.enums import BookAction
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.http.history import BackpackHistoryHttpAPI
from nautilus_trader.adapters.backpack.loaders import (
    BackpackBarDataLoader,
    BackpackOrderBookDeltaDataLoader,
    BackpackTradeTickDataLoader,
)


if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
    from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
    from nautilus_trader.adapters.backpack.futures.providers import BackpackFuturesInstrumentProvider


class BackpackBacktestDataProvider:
    """
    Provides historical Backpack data for backtesting.
    
    This provider handles:
    - Fetching historical data from Backpack API
    - Converting to NautilusTrader data formats
    - Caching data locally for performance
    
    Parameters
    ----------
    http_client : BackpackHttpClient
        The Backpack HTTP client.
    instrument_provider : BackpackSpotInstrumentProvider | BackpackFuturesInstrumentProvider
        The instrument provider.
    cache_dir : Path, optional
        Directory for caching downloaded data.
    logger : Logger, optional
        The logger instance.
    """

    def __init__(
        self,
        http_client: BackpackHttpClient,
        instrument_provider: Any,
        cache_dir: Path | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialize the BackpackBacktestDataProvider."""
        self._http_client = http_client
        self._instrument_provider = instrument_provider
        self._history_api = BackpackHistoryHttpAPI(http_client)
        self._cache_dir = cache_dir or Path.home() / ".nautilus" / "backpack" / "cache"
        self._logger = logger or Logger(self.__class__.__name__)
        
        # Create cache directory
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def load_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        start_time: datetime,
        end_time: datetime,
        use_cache: bool = True,
    ) -> list[Bar]:
        """
        Load historical bar data for backtesting.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument to load bars for.
        bar_type : BarType
            The bar type specification.
        start_time : datetime
            Start of the historical period.
        end_time : datetime
            End of the historical period.
        use_cache : bool, default True
            Whether to use cached data if available.
            
        Returns
        -------
        list[Bar]
            The loaded bar data.
        
        """
        # Check cache first
        cache_file = self._get_cache_path(
            "bars",
            instrument_id,
            start_time,
            end_time,
            bar_type.spec.to_str(),
        )
        
        if use_cache and cache_file.exists():
            self._logger.info(f"Loading bars from cache: {cache_file}")
            return self._load_bars_from_cache(cache_file, instrument_id, bar_type)
        
        # Fetch from API
        self._logger.info(f"Fetching bars from API for {instrument_id}")
        
        # Convert bar type to Backpack interval
        interval = self._bar_type_to_interval(bar_type)
        
        # Fetch klines
        klines = await self._fetch_all_klines(
            symbol=instrument_id.symbol.value,
            interval=interval,
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000),
        )
        
        # Convert to bars
        bars = []
        instrument = await self._instrument_provider.load_async(instrument_id)
        
        for kline in klines:
            bar = self._kline_to_bar(kline, instrument_id, bar_type, instrument)
            bars.append(bar)
        
        # Cache the data
        if use_cache:
            self._save_bars_to_cache(bars, cache_file)
        
        return bars

    async def load_trades(
        self,
        instrument_id: InstrumentId,
        start_time: datetime,
        end_time: datetime,
        use_cache: bool = True,
    ) -> list[TradeTick]:
        """
        Load historical trade tick data for backtesting.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument to load trades for.
        start_time : datetime
            Start of the historical period.
        end_time : datetime
            End of the historical period.
        use_cache : bool, default True
            Whether to use cached data if available.
            
        Returns
        -------
        list[TradeTick]
            The loaded trade tick data.
        
        """
        # Check cache first
        cache_file = self._get_cache_path(
            "trades",
            instrument_id,
            start_time,
            end_time,
        )
        
        if use_cache and cache_file.exists():
            self._logger.info(f"Loading trades from cache: {cache_file}")
            return self._load_trades_from_cache(cache_file, instrument_id)
        
        # Fetch from API
        self._logger.info(f"Fetching trades from API for {instrument_id}")
        
        trades = await self._fetch_all_trades(
            symbol=instrument_id.symbol.value,
            start_time=int(start_time.timestamp() * 1000),
            end_time=int(end_time.timestamp() * 1000),
        )
        
        # Convert to trade ticks
        trade_ticks = []
        instrument = await self._instrument_provider.load_async(instrument_id)
        
        for trade in trades:
            trade_tick = self._trade_to_tick(trade, instrument_id, instrument)
            trade_ticks.append(trade_tick)
        
        # Cache the data
        if use_cache:
            self._save_trades_to_cache(trade_ticks, cache_file)
        
        return trade_ticks

    async def load_order_book_deltas(
        self,
        instrument_id: InstrumentId,
        start_time: datetime,
        end_time: datetime,
        depth: int = 20,
        use_cache: bool = True,
    ) -> list[OrderBookDelta]:
        """
        Load historical order book delta data for backtesting.
        
        Note: Backpack doesn't provide historical order book data,
        so this returns an empty list. Consider using synthetic
        order book generation from trades/bars instead.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            The instrument to load order book for.
        start_time : datetime
            Start of the historical period.
        end_time : datetime
            End of the historical period.
        depth : int, default 20
            The order book depth.
        use_cache : bool, default True
            Whether to use cached data if available.
            
        Returns
        -------
        list[OrderBookDelta]
            The loaded order book deltas (empty for Backpack).
        
        """
        self._logger.warning(
            "Backpack doesn't provide historical order book data. "
            "Consider using synthetic order book generation."
        )
        return []

    def _bar_type_to_interval(self, bar_type: BarType) -> str:
        """Convert NautilusTrader BarType to Backpack interval."""
        aggregation = bar_type.spec.aggregation
        step = bar_type.spec.step
        
        if aggregation == BarAggregation.MINUTE:
            if step == 1:
                return "1m"
            elif step == 5:
                return "5m"
            elif step == 15:
                return "15m"
            elif step == 30:
                return "30m"
        elif aggregation == BarAggregation.HOUR:
            if step == 1:
                return "1h"
            elif step == 2:
                return "2h"
            elif step == 4:
                return "4h"
        elif aggregation == BarAggregation.DAY:
            if step == 1:
                return "1d"
        elif aggregation == BarAggregation.WEEK:
            if step == 1:
                return "1w"
        elif aggregation == BarAggregation.MONTH:
            if step == 1:
                return "1M"
        
        raise ValueError(f"Unsupported bar type: {bar_type}")

    async def _fetch_all_klines(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> list[list[Any]]:
        """Fetch all klines with pagination."""
        all_klines = []
        current_start = start_time
        
        while current_start < end_time:
            klines = await self._history_api.fetch_klines_history(
                symbol=symbol,
                interval=interval,
                start_time=current_start,
                end_time=end_time,
                limit=1000,
            )
            
            if not klines:
                break
            
            all_klines.extend(klines)
            
            # Update start time for next batch
            last_kline_time = klines[-1][0]
            if last_kline_time <= current_start:
                break
            current_start = last_kline_time + 1
            
            # Rate limit protection
            await asyncio.sleep(0.1)
        
        return all_klines

    async def _fetch_all_trades(
        self,
        symbol: str,
        start_time: int,
        end_time: int,
    ) -> list[dict[str, Any]]:
        """Fetch all trades with pagination."""
        all_trades = []
        from_id = None
        
        while True:
            trades = await self._history_api.fetch_trades_history(
                symbol=symbol,
                from_id=from_id,
                start_time=start_time,
                end_time=end_time,
                limit=1000,
            )
            
            if not trades:
                break
            
            all_trades.extend(trades)
            
            # Update from_id for next batch
            from_id = trades[-1].get("id", trades[-1].get("trade_id"))
            
            # Check if we've reached the end time
            last_trade_time = trades[-1].get("timestamp", trades[-1].get("time", 0))
            if last_trade_time >= end_time:
                break
            
            # Rate limit protection
            await asyncio.sleep(0.1)
        
        return all_trades

    def _kline_to_bar(
        self,
        kline: list[Any],
        instrument_id: InstrumentId,
        bar_type: BarType,
        instrument: Any,
    ) -> Bar:
        """Convert Backpack kline to NautilusTrader Bar."""
        return Bar(
            bar_type=bar_type,
            open=Price(float(kline[1]), instrument.price_precision),
            high=Price(float(kline[2]), instrument.price_precision),
            low=Price(float(kline[3]), instrument.price_precision),
            close=Price(float(kline[4]), instrument.price_precision),
            volume=Quantity(float(kline[5]), instrument.size_precision),
            ts_event=int(kline[0]) * 1_000_000,  # Convert ms to ns
            ts_init=int(kline[0]) * 1_000_000,
        )

    def _trade_to_tick(
        self,
        trade: dict[str, Any],
        instrument_id: InstrumentId,
        instrument: Any,
    ) -> TradeTick:
        """Convert Backpack trade to NautilusTrader TradeTick."""
        # Determine aggressor side
        is_buyer_maker = trade.get("is_buyer_maker", trade.get("m", False))
        if is_buyer_maker:
            aggressor_side = AggressorSide.SELLER
        else:
            aggressor_side = AggressorSide.BUYER
        
        return TradeTick(
            instrument_id=instrument_id,
            price=Price(float(trade["price"]), instrument.price_precision),
            size=Quantity(
                float(trade.get("quantity", trade.get("size", 0))),
                instrument.size_precision,
            ),
            aggressor_side=aggressor_side,
            trade_id=TradeId(str(trade.get("id", trade.get("trade_id", "")))),
            ts_event=int(trade.get("timestamp", trade.get("time", 0))) * 1_000_000,
            ts_init=int(trade.get("timestamp", trade.get("time", 0))) * 1_000_000,
        )

    def _get_cache_path(
        self,
        data_type: str,
        instrument_id: InstrumentId,
        start_time: datetime,
        end_time: datetime,
        extra: str = "",
    ) -> Path:
        """Get cache file path for data."""
        filename = (
            f"{data_type}_{instrument_id}_{start_time.date()}_{end_time.date()}"
        )
        if extra:
            filename += f"_{extra}"
        filename += ".parquet"
        
        return self._cache_dir / filename

    def _save_bars_to_cache(self, bars: list[Bar], cache_file: Path) -> None:
        """Save bars to cache file."""
        data = []
        for bar in bars:
            data.append({
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
                "ts_event": bar.ts_event,
                "ts_init": bar.ts_init,
            })
        
        df = pd.DataFrame(data)
        df.to_parquet(cache_file)
        self._logger.info(f"Cached {len(bars)} bars to {cache_file}")

    def _load_bars_from_cache(
        self,
        cache_file: Path,
        instrument_id: InstrumentId,
        bar_type: BarType,
    ) -> list[Bar]:
        """Load bars from cache file."""
        df = pd.read_parquet(cache_file)
        
        bars = []
        for _, row in df.iterrows():
            bar = Bar(
                bar_type=bar_type,
                open=Price.from_str(str(row["open"])),
                high=Price.from_str(str(row["high"])),
                low=Price.from_str(str(row["low"])),
                close=Price.from_str(str(row["close"])),
                volume=Quantity.from_str(str(row["volume"])),
                ts_event=int(row["ts_event"]),
                ts_init=int(row["ts_init"]),
            )
            bars.append(bar)
        
        return bars

    def _save_trades_to_cache(self, trades: list[TradeTick], cache_file: Path) -> None:
        """Save trades to cache file."""
        data = []
        for trade in trades:
            data.append({
                "price": float(trade.price),
                "size": float(trade.size),
                "aggressor_side": trade.aggressor_side.value,
                "trade_id": str(trade.trade_id),
                "ts_event": trade.ts_event,
                "ts_init": trade.ts_init,
            })
        
        df = pd.DataFrame(data)
        df.to_parquet(cache_file)
        self._logger.info(f"Cached {len(trades)} trades to {cache_file}")

    def _load_trades_from_cache(
        self,
        cache_file: Path,
        instrument_id: InstrumentId,
    ) -> list[TradeTick]:
        """Load trades from cache file."""
        df = pd.read_parquet(cache_file)
        
        trades = []
        for _, row in df.iterrows():
            trade = TradeTick(
                instrument_id=instrument_id,
                price=Price.from_str(str(row["price"])),
                size=Quantity.from_str(str(row["size"])),
                aggressor_side=AggressorSide[row["aggressor_side"]],
                trade_id=TradeId(row["trade_id"]),
                ts_event=int(row["ts_event"]),
                ts_init=int(row["ts_init"]),
            )
            trades.append(trade)
        
        return trades


class BackpackHistoricalDataClient:
    """
    Client for accessing Backpack historical data.
    
    This client provides a simple interface for fetching
    historical data from Backpack for analysis or backtesting.
    
    Parameters
    ----------
    http_client : BackpackHttpClient
        The Backpack HTTP client.
    """

    def __init__(self, http_client: BackpackHttpClient) -> None:
        """Initialize the BackpackHistoricalDataClient."""
        self._http_client = http_client
        self._history_api = BackpackHistoryHttpAPI(http_client)

    async def get_historical_bars(
        self,
        symbol: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Get historical bar data as DataFrame.
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        interval : str
            The bar interval (1m, 5m, 15m, 1h, 4h, 1d).
        start_date : datetime
            Start date for historical data.
        end_date : datetime
            End date for historical data.
            
        Returns
        -------
        pd.DataFrame
            Historical bar data.
        
        """
        klines = await self._history_api.fetch_klines_history(
            symbol=symbol,
            interval=interval,
            start_time=int(start_date.timestamp() * 1000),
            end_time=int(end_date.timestamp() * 1000),
        )
        
        df = pd.DataFrame(
            klines,
            columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_volume",
                "taker_buy_quote_volume", "ignore"
            ]
        )
        
        # Convert types and set index
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col])
        
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        
        return df[["open", "high", "low", "close", "volume"]]

    async def get_historical_trades(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> pd.DataFrame:
        """
        Get historical trade data as DataFrame.
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        start_date : datetime
            Start date for historical data.
        end_date : datetime
            End date for historical data.
            
        Returns
        -------
        pd.DataFrame
            Historical trade data.
        
        """
        trades = await self._history_api.fetch_trades_history(
            symbol=symbol,
            start_time=int(start_date.timestamp() * 1000),
            end_time=int(end_date.timestamp() * 1000),
        )
        
        df = pd.DataFrame(trades)
        
        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        
        return df