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
Backpack Exchange futures historical data API.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

import msgspec
import pandas as pd

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.core.datetime import millis_to_nanos

if TYPE_CHECKING:
    from datetime import datetime


class PositionHistory(msgspec.Struct):
    """Historical position data."""
    symbol: str
    position_id: str
    side: str  # LONG or SHORT
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    max_quantity: Decimal
    entry_time: int  # Unix timestamp in milliseconds
    exit_time: int | None
    leverage: int
    margin_type: str  # CROSS or ISOLATED
    liquidation_price: Decimal | None
    status: str  # OPEN, CLOSED, LIQUIDATED


class FundingHistory(msgspec.Struct):
    """Historical funding payment data."""
    symbol: str
    funding_rate: Decimal
    mark_price: Decimal
    position_size: Decimal
    payment: Decimal
    timestamp: int  # Unix timestamp in milliseconds
    is_payer: bool


class LiquidationHistory(msgspec.Struct):
    """Historical liquidation data."""
    symbol: str
    side: str  # BUY or SELL
    price: Decimal
    quantity: Decimal
    loss: Decimal
    timestamp: int  # Unix timestamp in milliseconds
    liquidation_type: str  # LIQUIDATION or ADL
    margin_ratio: Decimal


class TradeHistory(msgspec.Struct):
    """Historical trade data."""
    symbol: str
    trade_id: str
    order_id: str
    side: str  # BUY or SELL
    price: Decimal
    quantity: Decimal
    fee: Decimal
    fee_asset: str
    timestamp: int  # Unix timestamp in milliseconds
    is_maker: bool
    realized_pnl: Decimal | None


class BackpackFuturesHistoryAPI:
    """
    Provides access to Backpack futures historical data.
    
    Parameters
    ----------
    client : BackpackHttpClient
        The HTTP client for API requests.
    """
    
    def __init__(self, client: BackpackHttpClient) -> None:
        self._client = client
        
        # Response decoders
        self._decoder_positions = msgspec.json.Decoder(list[PositionHistory])
        self._decoder_funding = msgspec.json.Decoder(list[FundingHistory])
        self._decoder_liquidations = msgspec.json.Decoder(list[LiquidationHistory])
        self._decoder_trades = msgspec.json.Decoder(list[TradeHistory])
    
    async def get_position_history(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[PositionHistory]:
        """
        Fetch historical position data.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch history for.
        start_time : datetime, optional
            The start time for history.
        end_time : datetime, optional
            The end time for history.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[PositionHistory]
            The historical position data.
        """
        params: dict[str, Any] = {"limit": limit}
        
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        
        raw = await self._client._get(
            path="/api/v1/history/positions",
            params=params,
            auth=True,
        )
        
        return self._decoder_positions.decode(raw)
    
    async def get_funding_history(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[FundingHistory]:
        """
        Fetch historical funding payment data.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch history for.
        start_time : datetime, optional
            The start time for history.
        end_time : datetime, optional
            The end time for history.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[FundingHistory]
            The historical funding payment data.
        """
        params: dict[str, Any] = {"limit": limit}
        
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        
        raw = await self._client._get(
            path="/api/v1/history/funding",
            params=params,
            auth=True,
        )
        
        return self._decoder_funding.decode(raw)
    
    async def get_liquidation_history(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[LiquidationHistory]:
        """
        Fetch historical liquidation data.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch history for.
        start_time : datetime, optional
            The start time for history.
        end_time : datetime, optional
            The end time for history.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[LiquidationHistory]
            The historical liquidation data.
        """
        params: dict[str, Any] = {"limit": limit}
        
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        
        raw = await self._client._get(
            path="/api/v1/history/liquidations",
            params=params,
            auth=True,
        )
        
        return self._decoder_liquidations.decode(raw)
    
    async def get_trade_history(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[TradeHistory]:
        """
        Fetch historical trade data.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to fetch history for.
        start_time : datetime, optional
            The start time for history.
        end_time : datetime, optional
            The end time for history.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[TradeHistory]
            The historical trade data.
        """
        params: dict[str, Any] = {"limit": limit}
        
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        
        raw = await self._client._get(
            path="/api/v1/history/trades",
            params=params,
            auth=True,
        )
        
        return self._decoder_trades.decode(raw)
    
    async def get_income_history(
        self,
        income_type: str | None = None,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Fetch income history (funding fees, trading fees, etc.).
        
        Parameters
        ----------
        income_type : str, optional
            Type of income (FUNDING_FEE, TRADING_FEE, etc.).
        symbol : str, optional
            The symbol to fetch history for.
        start_time : datetime, optional
            The start time for history.
        end_time : datetime, optional
            The end time for history.
        limit : int, default 100
            Maximum number of records.
            
        Returns
        -------
        list[dict]
            The income history data.
        """
        params: dict[str, Any] = {"limit": limit}
        
        if income_type:
            params["incomeType"] = income_type
        if symbol:
            params["symbol"] = symbol
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)
        
        raw = await self._client._get(
            path="/api/v1/history/income",
            params=params,
            auth=True,
        )
        
        return msgspec.json.decode(raw)
    
    def positions_to_dataframe(self, positions: list[PositionHistory]) -> pd.DataFrame:
        """
        Convert position history to DataFrame.
        
        Parameters
        ----------
        positions : list[PositionHistory]
            The position history data.
            
        Returns
        -------
        pd.DataFrame
            The position history as a DataFrame.
        """
        if not positions:
            return pd.DataFrame()
        
        data = []
        for pos in positions:
            data.append({
                "symbol": pos.symbol,
                "position_id": pos.position_id,
                "side": pos.side,
                "entry_price": float(pos.entry_price),
                "exit_price": float(pos.exit_price) if pos.exit_price else None,
                "quantity": float(pos.quantity),
                "realized_pnl": float(pos.realized_pnl),
                "unrealized_pnl": float(pos.unrealized_pnl),
                "max_quantity": float(pos.max_quantity),
                "entry_time": pd.Timestamp(pos.entry_time, unit="ms"),
                "exit_time": pd.Timestamp(pos.exit_time, unit="ms") if pos.exit_time else None,
                "leverage": pos.leverage,
                "margin_type": pos.margin_type,
                "liquidation_price": float(pos.liquidation_price) if pos.liquidation_price else None,
                "status": pos.status,
            })
        
        df = pd.DataFrame(data)
        df.set_index("entry_time", inplace=True)
        return df
    
    def funding_to_dataframe(self, funding: list[FundingHistory]) -> pd.DataFrame:
        """
        Convert funding history to DataFrame.
        
        Parameters
        ----------
        funding : list[FundingHistory]
            The funding history data.
            
        Returns
        -------
        pd.DataFrame
            The funding history as a DataFrame.
        """
        if not funding:
            return pd.DataFrame()
        
        data = []
        for f in funding:
            data.append({
                "symbol": f.symbol,
                "funding_rate": float(f.funding_rate),
                "mark_price": float(f.mark_price),
                "position_size": float(f.position_size),
                "payment": float(f.payment),
                "timestamp": pd.Timestamp(f.timestamp, unit="ms"),
                "is_payer": f.is_payer,
            })
        
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df
    
    def liquidations_to_dataframe(self, liquidations: list[LiquidationHistory]) -> pd.DataFrame:
        """
        Convert liquidation history to DataFrame.
        
        Parameters
        ----------
        liquidations : list[LiquidationHistory]
            The liquidation history data.
            
        Returns
        -------
        pd.DataFrame
            The liquidation history as a DataFrame.
        """
        if not liquidations:
            return pd.DataFrame()
        
        data = []
        for liq in liquidations:
            data.append({
                "symbol": liq.symbol,
                "side": liq.side,
                "price": float(liq.price),
                "quantity": float(liq.quantity),
                "loss": float(liq.loss),
                "timestamp": pd.Timestamp(liq.timestamp, unit="ms"),
                "liquidation_type": liq.liquidation_type,
                "margin_ratio": float(liq.margin_ratio),
            })
        
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df
    
    def trades_to_dataframe(self, trades: list[TradeHistory]) -> pd.DataFrame:
        """
        Convert trade history to DataFrame.
        
        Parameters
        ----------
        trades : list[TradeHistory]
            The trade history data.
            
        Returns
        -------
        pd.DataFrame
            The trade history as a DataFrame.
        """
        if not trades:
            return pd.DataFrame()
        
        data = []
        for trade in trades:
            data.append({
                "symbol": trade.symbol,
                "trade_id": trade.trade_id,
                "order_id": trade.order_id,
                "side": trade.side,
                "price": float(trade.price),
                "quantity": float(trade.quantity),
                "fee": float(trade.fee),
                "fee_asset": trade.fee_asset,
                "timestamp": pd.Timestamp(trade.timestamp, unit="ms"),
                "is_maker": trade.is_maker,
                "realized_pnl": float(trade.realized_pnl) if trade.realized_pnl else None,
            })
        
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df
    
    async def get_performance_summary(
        self,
        symbol: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        """
        Get a performance summary from historical data.
        
        Parameters
        ----------
        symbol : str, optional
            The symbol to analyze.
        start_time : datetime, optional
            The start time for analysis.
        end_time : datetime, optional
            The end time for analysis.
            
        Returns
        -------
        dict
            Performance metrics summary.
        """
        # Fetch all relevant history
        positions = await self.get_position_history(symbol, start_time, end_time)
        funding = await self.get_funding_history(symbol, start_time, end_time)
        trades = await self.get_trade_history(symbol, start_time, end_time)
        liquidations = await self.get_liquidation_history(symbol, start_time, end_time)
        
        # Calculate metrics
        total_pnl = sum(p.realized_pnl for p in positions)
        total_funding = sum(f.payment for f in funding)
        total_fees = sum(t.fee for t in trades)
        total_liquidation_loss = sum(l.loss for l in liquidations)
        
        winning_positions = [p for p in positions if p.realized_pnl > 0]
        losing_positions = [p for p in positions if p.realized_pnl < 0]
        
        win_rate = len(winning_positions) / len(positions) if positions else 0
        avg_win = sum(p.realized_pnl for p in winning_positions) / len(winning_positions) if winning_positions else 0
        avg_loss = sum(p.realized_pnl for p in losing_positions) / len(losing_positions) if losing_positions else 0
        
        return {
            "total_positions": len(positions),
            "winning_positions": len(winning_positions),
            "losing_positions": len(losing_positions),
            "win_rate": float(win_rate),
            "total_pnl": float(total_pnl),
            "average_win": float(avg_win),
            "average_loss": float(avg_loss),
            "total_funding_payments": float(total_funding),
            "total_fees": float(total_fees),
            "total_liquidation_loss": float(total_liquidation_loss),
            "liquidation_count": len(liquidations),
            "total_trades": len(trades),
            "net_pnl": float(total_pnl + total_funding - total_fees - total_liquidation_loss),
        }