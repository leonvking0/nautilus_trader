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
Analytics and performance analysis for Backpack Exchange trading data.

This module provides:
- PnL analysis and reporting
- Position performance metrics
- Fee analysis and optimization
- Slippage tracking
- Volume profiling
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pandas as pd


if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.http.history import BackpackHistoryHttpAPI


@dataclass
class PnLReport:
    """Daily/weekly/monthly PnL report."""
    period: str  # 'daily', 'weekly', 'monthly'
    start_date: datetime
    end_date: datetime
    total_pnl: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    winning_trades: int
    losing_trades: int
    win_rate: float
    average_win: Decimal
    average_loss: Decimal
    profit_factor: Decimal
    sharpe_ratio: float | None
    max_drawdown: Decimal
    trades_count: int
    fees_paid: Decimal
    net_pnl: Decimal  # PnL after fees


@dataclass
class PositionPerformance:
    """Individual position performance metrics."""
    symbol: str
    side: str  # 'Long' or 'Short'
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    holding_period: timedelta
    max_profit: Decimal
    max_loss: Decimal
    fees_paid: Decimal
    return_pct: float
    risk_reward_ratio: float | None


@dataclass
class FeeAnalysis:
    """Fee breakdown and analysis."""
    total_fees: Decimal
    maker_fees: Decimal
    taker_fees: Decimal
    funding_fees: Decimal
    interest_fees: Decimal
    fee_by_symbol: dict[str, Decimal]
    fee_by_type: dict[str, Decimal]
    average_fee_rate: float
    fees_as_pct_of_volume: float
    optimization_suggestions: list[str]


@dataclass
class SlippageMetrics:
    """Execution quality and slippage metrics."""
    average_slippage: Decimal
    positive_slippage: Decimal
    negative_slippage: Decimal
    slippage_by_order_type: dict[str, Decimal]
    slippage_by_size: dict[str, Decimal]
    market_impact: Decimal
    execution_delay: timedelta | None


class BackpackPnLAnalyzer:
    """
    Analyzes PnL data and generates performance reports.
    
    Parameters
    ----------
    history_api : BackpackHistoryHttpAPI
        The history API client.
    """

    def __init__(self, history_api: BackpackHistoryHttpAPI) -> None:
        """Initialize the BackpackPnLAnalyzer."""
        self._history_api = history_api

    async def generate_pnl_report(
        self,
        symbol: str | None = None,
        period: str = "daily",
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> PnLReport:
        """
        Generate a PnL report for the specified period.
        
        Parameters
        ----------
        symbol : str, optional
            Filter by symbol.
        period : str, default 'daily'
            Report period ('daily', 'weekly', 'monthly').
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
            
        Returns
        -------
        PnLReport
            The generated PnL report.
        
        """
        # Fetch PnL history
        pnl_data = await self._history_api.fetch_pnl_history(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )
        
        # Fetch fill history for win/loss analysis
        fills = await self._history_api.fetch_fill_history(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )
        
        # Calculate metrics
        total_pnl = sum(Decimal(p["total_pnl"]) for p in pnl_data)
        realized_pnl = sum(Decimal(p["realized_pnl"]) for p in pnl_data)
        unrealized_pnl = sum(Decimal(p.get("unrealized_pnl", "0")) for p in pnl_data if p.get("unrealized_pnl"))
        
        # Analyze trades
        winning_trades = sum(1 for p in pnl_data if Decimal(p["realized_pnl"]) > 0)
        losing_trades = sum(1 for p in pnl_data if Decimal(p["realized_pnl"]) < 0)
        trades_count = len(pnl_data)
        
        win_rate = winning_trades / trades_count if trades_count > 0 else 0.0
        
        # Calculate averages
        wins = [Decimal(p["realized_pnl"]) for p in pnl_data if Decimal(p["realized_pnl"]) > 0]
        losses = [abs(Decimal(p["realized_pnl"])) for p in pnl_data if Decimal(p["realized_pnl"]) < 0]
        
        average_win = sum(wins) / len(wins) if wins else Decimal("0")
        average_loss = sum(losses) / len(losses) if losses else Decimal("0")
        
        # Profit factor
        total_wins = sum(wins)
        total_losses = sum(losses)
        profit_factor = total_wins / total_losses if total_losses > 0 else Decimal("0")
        
        # Calculate fees
        fees_paid = sum(Decimal(f["fee"]) for f in fills)
        net_pnl = total_pnl - fees_paid
        
        # Max drawdown calculation
        cumulative_pnl = []
        running_total = Decimal("0")
        for p in sorted(pnl_data, key=lambda x: x["timestamp"]):
            running_total += Decimal(p["realized_pnl"])
            cumulative_pnl.append(running_total)
        
        max_drawdown = self._calculate_max_drawdown(cumulative_pnl)
        
        # Sharpe ratio (simplified - would need risk-free rate)
        sharpe_ratio = self._calculate_sharpe_ratio(pnl_data) if pnl_data else None
        
        return PnLReport(
            period=period,
            start_date=datetime.fromtimestamp(start_time / 1000) if start_time else datetime.now(),
            end_date=datetime.fromtimestamp(end_time / 1000) if end_time else datetime.now(),
            total_pnl=total_pnl,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            average_win=average_win,
            average_loss=average_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            trades_count=trades_count,
            fees_paid=fees_paid,
            net_pnl=net_pnl,
        )

    def _calculate_max_drawdown(self, cumulative_pnl: list[Decimal]) -> Decimal:
        """Calculate maximum drawdown from cumulative PnL."""
        if not cumulative_pnl:
            return Decimal("0")
        
        peak = cumulative_pnl[0]
        max_dd = Decimal("0")
        
        for value in cumulative_pnl:
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_dd:
                max_dd = drawdown
        
        return max_dd

    def _calculate_sharpe_ratio(self, pnl_data: list[dict]) -> float | None:
        """Calculate simplified Sharpe ratio."""
        if len(pnl_data) < 2:
            return None
        
        returns = [float(p["realized_pnl"]) for p in pnl_data]
        
        if not returns:
            return None
        
        import numpy as np
        
        mean_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return None
        
        # Annualized Sharpe (assuming daily returns and 252 trading days)
        return (mean_return / std_return) * np.sqrt(252)


class BackpackPositionPerformance:
    """
    Analyzes individual position performance.
    
    Parameters
    ----------
    history_api : BackpackHistoryHttpAPI
        The history API client.
    """

    def __init__(self, history_api: BackpackHistoryHttpAPI) -> None:
        """Initialize the BackpackPositionPerformance."""
        self._history_api = history_api

    async def analyze_position(
        self,
        symbol: str,
        order_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> PositionPerformance:
        """
        Analyze performance of a specific position.
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        order_id : int, optional
            Specific order ID to analyze.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
            
        Returns
        -------
        PositionPerformance
            The position performance metrics.
        
        """
        # Fetch fills for the position
        fills = await self._history_api.fetch_fill_history(
            symbol=symbol,
            order_id=order_id,
            start_time=start_time,
            end_time=end_time,
        )
        
        if not fills:
            raise ValueError(f"No fills found for {symbol}")
        
        # Group fills by position
        entry_fills = []
        exit_fills = []
        
        position_size = Decimal("0")
        for fill in fills:
            quantity = Decimal(fill["quantity"])
            if position_size == 0:
                # Opening position
                entry_fills.append(fill)
                position_size = quantity
            elif (position_size > 0 and fill["side"] == "Ask") or \
                 (position_size < 0 and fill["side"] == "Bid"):
                # Closing position
                exit_fills.append(fill)
                position_size -= quantity
            else:
                # Adding to position
                entry_fills.append(fill)
                position_size += quantity if fill["side"] == "Bid" else -quantity
        
        # Calculate metrics
        total_entry_value = sum(Decimal(f["price"]) * Decimal(f["quantity"]) for f in entry_fills)
        total_entry_quantity = sum(Decimal(f["quantity"]) for f in entry_fills)
        entry_price = total_entry_value / total_entry_quantity if total_entry_quantity else Decimal("0")
        
        exit_price = None
        realized_pnl = Decimal("0")
        if exit_fills:
            total_exit_value = sum(Decimal(f["price"]) * Decimal(f["quantity"]) for f in exit_fills)
            total_exit_quantity = sum(Decimal(f["quantity"]) for f in exit_fills)
            exit_price = total_exit_value / total_exit_quantity if total_exit_quantity else Decimal("0")
            
            # Calculate realized PnL
            side = "Long" if entry_fills[0]["side"] == "Bid" else "Short"
            if side == "Long":
                realized_pnl = (exit_price - entry_price) * total_exit_quantity
            else:
                realized_pnl = (entry_price - exit_price) * total_exit_quantity
        
        # Calculate holding period
        first_fill_time = min(f["timestamp"] for f in fills)
        last_fill_time = max(f["timestamp"] for f in fills)
        holding_period = timedelta(milliseconds=last_fill_time - first_fill_time)
        
        # Calculate fees
        fees_paid = sum(Decimal(f["fee"]) for f in fills)
        
        # Calculate return percentage
        return_pct = float((realized_pnl / total_entry_value) * 100) if total_entry_value else 0.0
        
        # Risk reward ratio (simplified)
        risk_reward_ratio = None
        if exit_price and entry_price:
            if entry_fills[0]["side"] == "Bid":  # Long
                risk = entry_price * Decimal("0.02")  # Assume 2% stop loss
                reward = exit_price - entry_price
            else:  # Short
                risk = entry_price * Decimal("0.02")
                reward = entry_price - exit_price
            
            risk_reward_ratio = float(reward / risk) if risk else None
        
        return PositionPerformance(
            symbol=symbol,
            side="Long" if entry_fills[0]["side"] == "Bid" else "Short",
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=total_entry_quantity,
            realized_pnl=realized_pnl,
            unrealized_pnl=Decimal("0"),  # Would need current price
            holding_period=holding_period,
            max_profit=realized_pnl,  # Simplified
            max_loss=Decimal("0"),  # Would need tick data
            fees_paid=fees_paid,
            return_pct=return_pct,
            risk_reward_ratio=risk_reward_ratio,
        )


class BackpackFeeAnalyzer:
    """
    Analyzes trading fees and provides optimization suggestions.
    
    Parameters
    ----------
    history_api : BackpackHistoryHttpAPI
        The history API client.
    """

    def __init__(self, history_api: BackpackHistoryHttpAPI) -> None:
        """Initialize the BackpackFeeAnalyzer."""
        self._history_api = history_api

    async def analyze_fees(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> FeeAnalysis:
        """
        Analyze trading fees and provide optimization suggestions.
        
        Parameters
        ----------
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
            
        Returns
        -------
        FeeAnalysis
            The fee analysis report.
        
        """
        # Fetch fill history
        fills = await self._history_api.fetch_fill_history(
            start_time=start_time,
            end_time=end_time,
        )
        
        # Fetch funding history
        funding = await self._history_api.fetch_funding_history(
            start_time=start_time,
            end_time=end_time,
        )
        
        # Fetch interest history
        interest = await self._history_api.fetch_interest_history(
            start_time=start_time,
            end_time=end_time,
        )
        
        # Calculate fee metrics
        total_fees = Decimal("0")
        maker_fees = Decimal("0")
        taker_fees = Decimal("0")
        fee_by_symbol = defaultdict(Decimal)
        fee_by_type = defaultdict(Decimal)
        total_volume = Decimal("0")
        
        for fill in fills:
            fee = Decimal(fill["fee"])
            symbol = fill["symbol"]
            is_maker = fill.get("is_maker", False)
            
            total_fees += fee
            fee_by_symbol[symbol] += fee
            
            if is_maker:
                maker_fees += fee
                fee_by_type["maker"] += fee
            else:
                taker_fees += fee
                fee_by_type["taker"] += fee
            
            # Calculate volume
            total_volume += Decimal(fill["price"]) * Decimal(fill["quantity"])
        
        # Add funding fees
        funding_fees = sum(Decimal(f["payment_amount"]) for f in funding)
        total_fees += funding_fees
        fee_by_type["funding"] += funding_fees
        
        # Add interest fees
        interest_fees = sum(Decimal(i["interest_amount"]) for i in interest)
        total_fees += interest_fees
        fee_by_type["interest"] += interest_fees
        
        # Calculate metrics
        average_fee_rate = float(total_fees / total_volume) if total_volume else 0.0
        fees_as_pct_of_volume = float((total_fees / total_volume) * 100) if total_volume else 0.0
        
        # Generate optimization suggestions
        suggestions = []
        
        if taker_fees > maker_fees * 2:
            suggestions.append("Consider using more limit orders to reduce taker fees")
        
        if funding_fees > total_fees * Decimal("0.3"):
            suggestions.append("High funding fees detected - consider position timing")
        
        if interest_fees > total_fees * Decimal("0.2"):
            suggestions.append("High interest fees - consider reducing leverage or borrowing")
        
        if average_fee_rate > 0.001:  # 0.1%
            suggestions.append("Fee rate above 0.1% - consider VIP tier or fee discounts")
        
        return FeeAnalysis(
            total_fees=total_fees,
            maker_fees=maker_fees,
            taker_fees=taker_fees,
            funding_fees=funding_fees,
            interest_fees=interest_fees,
            fee_by_symbol=dict(fee_by_symbol),
            fee_by_type=dict(fee_by_type),
            average_fee_rate=average_fee_rate,
            fees_as_pct_of_volume=fees_as_pct_of_volume,
            optimization_suggestions=suggestions,
        )


class BackpackSlippageTracker:
    """
    Tracks execution quality and slippage metrics.
    
    Parameters
    ----------
    history_api : BackpackHistoryHttpAPI
        The history API client.
    """

    def __init__(self, history_api: BackpackHistoryHttpAPI) -> None:
        """Initialize the BackpackSlippageTracker."""
        self._history_api = history_api

    async def calculate_slippage(
        self,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> SlippageMetrics:
        """
        Calculate slippage metrics for executed orders.
        
        Parameters
        ----------
        symbol : str, optional
            Filter by symbol.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
            
        Returns
        -------
        SlippageMetrics
            The slippage analysis.
        
        """
        # Fetch order history
        orders = await self._history_api.fetch_order_history(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )
        
        # Fetch fills
        fills = await self._history_api.fetch_fill_history(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
        )
        
        # Group fills by order
        fills_by_order = defaultdict(list)
        for fill in fills:
            fills_by_order[fill["order_id"]].append(fill)
        
        # Calculate slippage
        total_slippage = Decimal("0")
        positive_slippage = Decimal("0")
        negative_slippage = Decimal("0")
        slippage_by_order_type = defaultdict(list)
        slippage_count = 0
        
        for order in orders:
            if order["order_type"] != "Market":
                continue
            
            order_fills = fills_by_order.get(order["order_id"], [])
            if not order_fills:
                continue
            
            # Calculate average fill price
            total_value = sum(Decimal(f["price"]) * Decimal(f["quantity"]) for f in order_fills)
            total_quantity = sum(Decimal(f["quantity"]) for f in order_fills)
            avg_fill_price = total_value / total_quantity if total_quantity else Decimal("0")
            
            # Expected price (for market orders, use first fill as reference)
            expected_price = Decimal(order_fills[0]["price"])
            
            # Calculate slippage
            if order["side"] == "Bid":  # Buy order
                slippage = avg_fill_price - expected_price
            else:  # Sell order
                slippage = expected_price - avg_fill_price
            
            total_slippage += slippage
            slippage_count += 1
            
            if slippage > 0:
                positive_slippage += slippage
            else:
                negative_slippage += abs(slippage)
            
            slippage_by_order_type[order["order_type"]].append(slippage)
        
        # Calculate averages
        average_slippage = total_slippage / slippage_count if slippage_count else Decimal("0")
        
        # Calculate average by order type
        avg_slippage_by_type = {}
        for order_type, slippages in slippage_by_order_type.items():
            if slippages:
                avg_slippage_by_type[order_type] = sum(slippages) / len(slippages)
        
        return SlippageMetrics(
            average_slippage=average_slippage,
            positive_slippage=positive_slippage,
            negative_slippage=negative_slippage,
            slippage_by_order_type=avg_slippage_by_type,
            slippage_by_size={},  # Would need size buckets
            market_impact=Decimal("0"),  # Would need order book data
            execution_delay=None,  # Would need timestamp analysis
        )


class BackpackVolumeProfile:
    """
    Analyzes trading volume patterns and profiles.
    
    Parameters
    ----------
    history_api : BackpackHistoryHttpAPI
        The history API client.
    """

    def __init__(self, history_api: BackpackHistoryHttpAPI) -> None:
        """Initialize the BackpackVolumeProfile."""
        self._history_api = history_api

    async def generate_volume_profile(
        self,
        symbol: str,
        interval: str = "1h",
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> pd.DataFrame:
        """
        Generate volume profile for a symbol.
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        interval : str, default '1h'
            Time interval for volume aggregation.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
            
        Returns
        -------
        pd.DataFrame
            Volume profile with price levels and volume distribution.
        
        """
        # Fetch klines for volume data
        klines = await self._history_api.fetch_klines_history(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )
        
        # Convert to DataFrame
        df = pd.DataFrame(
            klines,
            columns=[
                "timestamp", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_volume",
                "taker_buy_quote_volume", "ignore"
            ]
        )
        
        # Convert types
        for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
            df[col] = pd.to_numeric(df[col])
        
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        
        # Calculate volume profile
        # Group by price levels
        price_min = df["low"].min()
        price_max = df["high"].max()
        price_range = price_max - price_min
        
        # Create 50 price levels
        n_levels = 50
        price_levels = [price_min + (price_range * i / n_levels) for i in range(n_levels + 1)]
        
        # Calculate volume at each price level
        volume_profile = []
        
        for i in range(len(price_levels) - 1):
            level_low = price_levels[i]
            level_high = price_levels[i + 1]
            level_mid = (level_low + level_high) / 2
            
            # Find bars that traded in this range
            mask = (df["low"] <= level_high) & (df["high"] >= level_low)
            level_volume = df.loc[mask, "volume"].sum()
            
            volume_profile.append({
                "price_level": level_mid,
                "price_low": level_low,
                "price_high": level_high,
                "volume": level_volume,
                "volume_pct": 0,  # Will calculate after
            })
        
        # Convert to DataFrame
        vp_df = pd.DataFrame(volume_profile)
        
        # Calculate volume percentage
        total_volume = vp_df["volume"].sum()
        if total_volume > 0:
            vp_df["volume_pct"] = (vp_df["volume"] / total_volume) * 100
        
        # Identify high volume nodes (HVN) and low volume nodes (LVN)
        vp_df["is_hvn"] = vp_df["volume"] > vp_df["volume"].quantile(0.7)
        vp_df["is_lvn"] = vp_df["volume"] < vp_df["volume"].quantile(0.3)
        
        # Calculate Point of Control (POC) - price level with highest volume
        poc_idx = vp_df["volume"].idxmax()
        vp_df["is_poc"] = False
        vp_df.loc[poc_idx, "is_poc"] = True
        
        return vp_df