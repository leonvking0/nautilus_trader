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
Data loaders for Backpack Exchange historical data.

This module provides loaders for:
- Order book delta data
- Trade tick data  
- Bar/OHLCV data
"""

from __future__ import annotations

import json
from os import PathLike
from typing import TYPE_CHECKING, Any

import pandas as pd

from nautilus_trader.model.enums import RecordFlag


if TYPE_CHECKING:
    from os import PathLike


class BackpackOrderBookDeltaDataLoader:
    """
    Provides a means of loading Backpack order book data.
    
    This loader handles:
    - Order book snapshots
    - Order book deltas/updates
    - Conversion to NautilusTrader format
    """

    @classmethod
    def load(
        cls,
        file_path: PathLike[str] | str,
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """
        Return the deltas `pandas.DataFrame` loaded from the given `file_path`.

        Parameters
        ----------
        file_path : str, path object or file-like object
            The path to the CSV or JSON file.
        nrows : int, optional
            The maximum number of rows to load.

        Returns
        -------
        pd.DataFrame
            Order book delta data with columns:
            - instrument_id
            - action (ADD, UPDATE, DELETE, CLEAR)
            - side (BUY, SELL)
            - price
            - size
            - order_id
            - flags
            - sequence

        """
        # Detect file format
        file_str = str(file_path)
        if file_str.endswith('.json'):
            df = cls._load_json(file_path, nrows)
        else:
            df = cls._load_csv(file_path, nrows)
        
        # Convert timestamp to datetime index
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            df = df.set_index('timestamp')
        
        # Ensure required columns
        df['instrument_id'] = df.get('symbol', '') + '.BACKPACK'
        df['action'] = df.apply(cls._map_actions, axis=1)
        df['side'] = df['side'].apply(cls._map_sides) if 'side' in df else 'BUY'
        df['order_id'] = df.get('order_id', 0)
        df['flags'] = df.apply(cls._map_flags, axis=1)
        df['sequence'] = df.get('sequence', df.get('update_id', 0))
        
        # Select and reorder columns
        columns = [
            'instrument_id',
            'action',
            'side',
            'price',
            'size',
            'order_id',
            'flags',
            'sequence',
        ]
        df = df[columns]
        
        return df

    @classmethod
    def _load_json(
        cls,
        file_path: PathLike[str] | str, 
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """Load order book data from JSON file."""
        rows = []
        
        with open(file_path, 'r') as f:
            for i, line in enumerate(f):
                if nrows is not None and i >= nrows:
                    break
                    
                data = json.loads(line.strip())
                
                # Handle both snapshot and update formats
                if 'bids' in data or 'asks' in data:
                    # Order book snapshot/update
                    timestamp = data.get('timestamp', data.get('E', 0))
                    symbol = data.get('symbol', data.get('s', ''))
                    update_type = data.get('type', 'update')
                    
                    # Process bids
                    if 'bids' in data:
                        for price, size in data['bids']:
                            rows.append({
                                'timestamp': timestamp,
                                'symbol': symbol,
                                'update_type': update_type,
                                'side': 'bid',
                                'price': float(price),
                                'size': float(size),
                            })
                    
                    # Process asks
                    if 'asks' in data:
                        for price, size in data['asks']:
                            rows.append({
                                'timestamp': timestamp,
                                'symbol': symbol,
                                'update_type': update_type,
                                'side': 'ask',
                                'price': float(price),
                                'size': float(size),
                            })
                else:
                    # Single level update
                    rows.append(data)
        
        return pd.DataFrame(rows)

    @classmethod
    def _load_csv(
        cls,
        file_path: PathLike[str] | str,
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """Load order book data from CSV file."""
        return pd.read_csv(file_path, nrows=nrows)

    @classmethod
    def _map_actions(cls, row: pd.Series) -> str:
        """Map update type and size to action."""
        update_type = row.get('update_type', 'update')
        size = row.get('size', 0)
        
        if update_type == 'snapshot':
            return 'ADD'
        elif size == 0:
            return 'DELETE'
        else:
            return 'UPDATE'

    @classmethod
    def _map_sides(cls, side: str) -> str:
        """Map side to standard format."""
        side = str(side).lower()
        if side in ['bid', 'b']:
            return 'BUY'
        elif side in ['ask', 'a']:
            return 'SELL'
        else:
            raise ValueError(f"Unrecognized side '{side}'")

    @classmethod
    def _map_flags(cls, row: pd.Series) -> int:
        """Map update type to flags."""
        update_type = row.get('update_type', 'update')
        if update_type == 'snapshot':
            return RecordFlag.F_SNAPSHOT
        else:
            return 0


class BackpackTradeTickDataLoader:
    """
    Provides a means of loading Backpack trade tick data.
    
    This loader handles:
    - Historical trade data
    - Real-time trade snapshots
    - Conversion to NautilusTrader TradeTick format
    """

    @classmethod
    def load(
        cls,
        file_path: PathLike[str] | str,
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """
        Return the trade ticks `pandas.DataFrame` loaded from the given `file_path`.

        Parameters
        ----------
        file_path : str, path object or file-like object
            The path to the CSV or JSON file.
        nrows : int, optional
            The maximum number of rows to load.

        Returns
        -------
        pd.DataFrame
            Trade tick data with columns:
            - instrument_id
            - price
            - size
            - aggressor_side (BUY, SELL, NO_AGGRESSOR)
            - trade_id
            - ts_event
            - ts_init

        """
        # Detect file format
        file_str = str(file_path)
        if file_str.endswith('.json'):
            df = cls._load_json(file_path, nrows)
        else:
            df = cls._load_csv(file_path, nrows)
        
        # Convert timestamp to nanoseconds
        if 'timestamp' in df.columns:
            df['ts_event'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).astype('int64')
            df['ts_init'] = df['ts_event']
        
        # Map fields
        df['instrument_id'] = df.get('symbol', '') + '.BACKPACK'
        df['price'] = df['price'].astype(float)
        df['size'] = df.get('quantity', df.get('size', 0)).astype(float)
        df['aggressor_side'] = df.apply(cls._map_aggressor_side, axis=1)
        df['trade_id'] = df.get('trade_id', df.get('id', '')).astype(str)
        
        # Select and reorder columns
        columns = [
            'instrument_id',
            'price',
            'size',
            'aggressor_side',
            'trade_id',
            'ts_event',
            'ts_init',
        ]
        
        # Set timestamp as index
        df = df[columns].set_index('ts_event')
        
        return df

    @classmethod
    def _load_json(
        cls,
        file_path: PathLike[str] | str,
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """Load trade data from JSON file."""
        rows = []
        
        with open(file_path, 'r') as f:
            for i, line in enumerate(f):
                if nrows is not None and i >= nrows:
                    break
                
                data = json.loads(line.strip())
                
                # Handle both single trade and trade array formats
                if isinstance(data, list):
                    rows.extend(data)
                else:
                    rows.append(data)
        
        return pd.DataFrame(rows)

    @classmethod
    def _load_csv(
        cls,
        file_path: PathLike[str] | str,
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """Load trade data from CSV file."""
        return pd.read_csv(file_path, nrows=nrows)

    @classmethod
    def _map_aggressor_side(cls, row: pd.Series) -> str:
        """Map trade side to aggressor side."""
        is_buyer_maker = row.get('is_buyer_maker', row.get('m', None))
        side = row.get('side', '')
        
        if is_buyer_maker is not None:
            # If buyer is maker, then seller is aggressor
            return 'SELL' if is_buyer_maker else 'BUY'
        elif side:
            # Direct side mapping
            side = str(side).upper()
            if side in ['BUY', 'BID']:
                return 'BUY'
            elif side in ['SELL', 'ASK']:
                return 'SELL'
        
        return 'NO_AGGRESSOR'


class BackpackBarDataLoader:
    """
    Provides a means of loading Backpack bar/kline data.
    
    This loader handles:
    - OHLCV candlestick data
    - Multiple timeframes (1m, 5m, 15m, 1h, 4h, 1d, etc.)
    - Conversion to NautilusTrader Bar format
    """

    @classmethod
    def load(
        cls,
        file_path: PathLike[str] | str,
        bar_type: str = '1m',
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """
        Return the bars `pandas.DataFrame` loaded from the given `file_path`.

        Parameters
        ----------
        file_path : str, path object or file-like object
            The path to the CSV or JSON file.
        bar_type : str, default '1m'
            The bar type/timeframe (1m, 5m, 15m, 1h, 4h, 1d).
        nrows : int, optional
            The maximum number of rows to load.

        Returns
        -------
        pd.DataFrame
            Bar data with columns:
            - instrument_id
            - open
            - high
            - low
            - close
            - volume
            - ts_event
            - ts_init

        """
        # Detect file format
        file_str = str(file_path)
        if file_str.endswith('.json'):
            df = cls._load_json(file_path, nrows)
        else:
            df = cls._load_csv(file_path, nrows)
        
        # Handle kline array format [timestamp, open, high, low, close, volume, ...]
        if 'kline' in df.columns or isinstance(df.iloc[0, 0] if len(df) > 0 else None, list):
            df = cls._parse_kline_array(df)
        
        # Convert timestamp to nanoseconds
        if 'timestamp' in df.columns:
            df['ts_event'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).astype('int64')
        elif 'open_time' in df.columns:
            df['ts_event'] = pd.to_datetime(df['open_time'], unit='ms', utc=True).astype('int64')
        elif 'close_time' in df.columns:
            df['ts_event'] = pd.to_datetime(df['close_time'], unit='ms', utc=True).astype('int64')
        
        df['ts_init'] = df.get('ts_event', 0)
        
        # Map fields
        df['instrument_id'] = df.get('symbol', '') + '.BACKPACK'
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # Select and reorder columns
        columns = [
            'instrument_id',
            'open',
            'high',
            'low',
            'close',
            'volume',
            'ts_event',
            'ts_init',
        ]
        
        # Set timestamp as index
        df = df[columns].set_index('ts_event')
        
        return df

    @classmethod
    def _load_json(
        cls,
        file_path: PathLike[str] | str,
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """Load bar data from JSON file."""
        rows = []
        
        with open(file_path, 'r') as f:
            for i, line in enumerate(f):
                if nrows is not None and i >= nrows:
                    break
                
                data = json.loads(line.strip())
                
                # Handle both single bar and bar array formats
                if isinstance(data, list) and isinstance(data[0], list):
                    # Array of klines
                    for kline in data:
                        rows.append({'kline': kline})
                elif isinstance(data, list):
                    # Single kline array
                    rows.append({'kline': data})
                else:
                    rows.append(data)
        
        return pd.DataFrame(rows)

    @classmethod
    def _load_csv(
        cls,
        file_path: PathLike[str] | str,
        nrows: int | None = None,
    ) -> pd.DataFrame:
        """Load bar data from CSV file."""
        return pd.read_csv(file_path, nrows=nrows)

    @classmethod
    def _parse_kline_array(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Parse kline array format [timestamp, open, high, low, close, volume, ...]."""
        parsed_rows = []
        
        for _, row in df.iterrows():
            kline = row.get('kline', row.iloc[0] if isinstance(row.iloc[0], list) else None)
            
            if kline and isinstance(kline, list) and len(kline) >= 6:
                parsed_rows.append({
                    'timestamp': kline[0],
                    'open': kline[1],
                    'high': kline[2],
                    'low': kline[3],
                    'close': kline[4],
                    'volume': kline[5],
                    'symbol': row.get('symbol', ''),
                })
        
        return pd.DataFrame(parsed_rows)