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
Report generation and export functionality for Backpack Exchange data.

This module provides:
- Daily/weekly/monthly trading reports
- Position-level analysis reports
- Fee breakdown reports
- Export to CSV/Parquet formats
- HTML report generation
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd


if TYPE_CHECKING:
    from nautilus_trader.adapters.backpack.analytics import (
        BackpackFeeAnalyzer,
        BackpackPnLAnalyzer,
        BackpackPositionPerformance,
        BackpackSlippageTracker,
        BackpackVolumeProfile,
    )
    from nautilus_trader.adapters.backpack.http.history import BackpackHistoryHttpAPI


class BackpackReportGenerator:
    """
    Generates comprehensive trading reports for Backpack Exchange.
    
    Parameters
    ----------
    history_api : BackpackHistoryHttpAPI
        The history API client.
    pnl_analyzer : BackpackPnLAnalyzer
        The PnL analyzer.
    position_analyzer : BackpackPositionPerformance
        The position performance analyzer.
    fee_analyzer : BackpackFeeAnalyzer
        The fee analyzer.
    slippage_tracker : BackpackSlippageTracker
        The slippage tracker.
    volume_profiler : BackpackVolumeProfile
        The volume profiler.
    """

    def __init__(
        self,
        history_api: BackpackHistoryHttpAPI,
        pnl_analyzer: BackpackPnLAnalyzer,
        position_analyzer: BackpackPositionPerformance,
        fee_analyzer: BackpackFeeAnalyzer,
        slippage_tracker: BackpackSlippageTracker,
        volume_profiler: BackpackVolumeProfile,
    ) -> None:
        """Initialize the BackpackReportGenerator."""
        self._history_api = history_api
        self._pnl_analyzer = pnl_analyzer
        self._position_analyzer = position_analyzer
        self._fee_analyzer = fee_analyzer
        self._slippage_tracker = slippage_tracker
        self._volume_profiler = volume_profiler

    async def generate_daily_pnl_report(
        self,
        date: datetime | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """
        Generate a daily PnL report.
        
        Parameters
        ----------
        date : datetime, optional
            The date for the report. If None, uses today.
        output_path : Path, optional
            Path to save the report. If None, returns dict only.
            
        Returns
        -------
        dict[str, Any]
            The daily PnL report data.
        
        """
        if date is None:
            date = datetime.now()
        
        # Calculate timestamps for the day
        start_of_day = datetime(date.year, date.month, date.day)
        end_of_day = datetime(date.year, date.month, date.day, 23, 59, 59)
        start_time = int(start_of_day.timestamp() * 1000)
        end_time = int(end_of_day.timestamp() * 1000)
        
        # Generate PnL report
        pnl_report = await self._pnl_analyzer.generate_pnl_report(
            period="daily",
            start_time=start_time,
            end_time=end_time,
        )
        
        # Generate fee analysis
        fee_analysis = await self._fee_analyzer.analyze_fees(
            start_time=start_time,
            end_time=end_time,
        )
        
        # Generate slippage metrics
        slippage_metrics = await self._slippage_tracker.calculate_slippage(
            start_time=start_time,
            end_time=end_time,
        )
        
        # Compile report
        report = {
            "report_date": date.isoformat(),
            "period": {
                "start": start_of_day.isoformat(),
                "end": end_of_day.isoformat(),
            },
            "pnl": {
                "total_pnl": str(pnl_report.total_pnl),
                "realized_pnl": str(pnl_report.realized_pnl),
                "unrealized_pnl": str(pnl_report.unrealized_pnl),
                "net_pnl": str(pnl_report.net_pnl),
                "fees_paid": str(pnl_report.fees_paid),
            },
            "trading_metrics": {
                "trades_count": pnl_report.trades_count,
                "winning_trades": pnl_report.winning_trades,
                "losing_trades": pnl_report.losing_trades,
                "win_rate": pnl_report.win_rate,
                "average_win": str(pnl_report.average_win),
                "average_loss": str(pnl_report.average_loss),
                "profit_factor": str(pnl_report.profit_factor),
                "sharpe_ratio": pnl_report.sharpe_ratio,
                "max_drawdown": str(pnl_report.max_drawdown),
            },
            "fees": {
                "total_fees": str(fee_analysis.total_fees),
                "maker_fees": str(fee_analysis.maker_fees),
                "taker_fees": str(fee_analysis.taker_fees),
                "funding_fees": str(fee_analysis.funding_fees),
                "interest_fees": str(fee_analysis.interest_fees),
                "average_fee_rate": fee_analysis.average_fee_rate,
                "fees_as_pct_of_volume": fee_analysis.fees_as_pct_of_volume,
                "optimization_suggestions": fee_analysis.optimization_suggestions,
            },
            "execution_quality": {
                "average_slippage": str(slippage_metrics.average_slippage),
                "positive_slippage": str(slippage_metrics.positive_slippage),
                "negative_slippage": str(slippage_metrics.negative_slippage),
            },
        }
        
        # Save report if path provided
        if output_path:
            self._save_json_report(report, output_path)
        
        return report

    async def generate_position_report(
        self,
        symbol: str,
        order_id: int | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """
        Generate a detailed position analysis report.
        
        Parameters
        ----------
        symbol : str
            The trading pair symbol.
        order_id : int, optional
            Specific order ID to analyze.
        output_path : Path, optional
            Path to save the report.
            
        Returns
        -------
        dict[str, Any]
            The position analysis report.
        
        """
        # Analyze position
        position_perf = await self._position_analyzer.analyze_position(
            symbol=symbol,
            order_id=order_id,
        )
        
        # Generate volume profile
        volume_profile = await self._volume_profiler.generate_volume_profile(
            symbol=symbol,
        )
        
        # Find POC (Point of Control)
        poc_row = volume_profile[volume_profile["is_poc"]]
        poc_price = float(poc_row["price_level"].iloc[0]) if not poc_row.empty else 0
        
        # Compile report
        report = {
            "symbol": symbol,
            "position": {
                "side": position_perf.side,
                "entry_price": str(position_perf.entry_price),
                "exit_price": str(position_perf.exit_price) if position_perf.exit_price else None,
                "quantity": str(position_perf.quantity),
                "holding_period": str(position_perf.holding_period),
            },
            "performance": {
                "realized_pnl": str(position_perf.realized_pnl),
                "unrealized_pnl": str(position_perf.unrealized_pnl),
                "return_pct": position_perf.return_pct,
                "risk_reward_ratio": position_perf.risk_reward_ratio,
                "max_profit": str(position_perf.max_profit),
                "max_loss": str(position_perf.max_loss),
                "fees_paid": str(position_perf.fees_paid),
            },
            "volume_analysis": {
                "poc_price": poc_price,
                "high_volume_nodes": volume_profile[volume_profile["is_hvn"]]["price_level"].tolist(),
                "low_volume_nodes": volume_profile[volume_profile["is_lvn"]]["price_level"].tolist(),
            },
        }
        
        # Save report if path provided
        if output_path:
            self._save_json_report(report, output_path)
        
        return report

    async def generate_fee_report(
        self,
        start_time: int | None = None,
        end_time: int | None = None,
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """
        Generate a detailed fee analysis report.
        
        Parameters
        ----------
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        output_path : Path, optional
            Path to save the report.
            
        Returns
        -------
        dict[str, Any]
            The fee analysis report.
        
        """
        # Analyze fees
        fee_analysis = await self._fee_analyzer.analyze_fees(
            start_time=start_time,
            end_time=end_time,
        )
        
        # Compile report
        report = {
            "period": {
                "start": datetime.fromtimestamp(start_time / 1000).isoformat() if start_time else None,
                "end": datetime.fromtimestamp(end_time / 1000).isoformat() if end_time else None,
            },
            "total_fees": str(fee_analysis.total_fees),
            "breakdown": {
                "maker_fees": str(fee_analysis.maker_fees),
                "taker_fees": str(fee_analysis.taker_fees),
                "funding_fees": str(fee_analysis.funding_fees),
                "interest_fees": str(fee_analysis.interest_fees),
            },
            "by_symbol": {k: str(v) for k, v in fee_analysis.fee_by_symbol.items()},
            "by_type": {k: str(v) for k, v in fee_analysis.fee_by_type.items()},
            "metrics": {
                "average_fee_rate": fee_analysis.average_fee_rate,
                "fees_as_pct_of_volume": fee_analysis.fees_as_pct_of_volume,
            },
            "optimization_suggestions": fee_analysis.optimization_suggestions,
        }
        
        # Save report if path provided
        if output_path:
            self._save_json_report(report, output_path)
        
        return report

    def _save_json_report(self, report: dict[str, Any], path: Path) -> None:
        """Save report as JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2, default=str)

    async def export_to_csv(
        self,
        data_type: str,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        output_path: Path | None = None,
    ) -> pd.DataFrame:
        """
        Export historical data to CSV format.
        
        Parameters
        ----------
        data_type : str
            Type of data to export ('orders', 'fills', 'pnl', 'funding', 'interest').
        symbol : str, optional
            Filter by symbol.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        output_path : Path, optional
            Path to save the CSV file.
            
        Returns
        -------
        pd.DataFrame
            The exported data as DataFrame.
        
        """
        # Fetch data based on type
        if data_type == "orders":
            data = await self._history_api.fetch_order_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=10000,
            )
        elif data_type == "fills":
            data = await self._history_api.fetch_fill_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=10000,
            )
        elif data_type == "pnl":
            data = await self._history_api.fetch_pnl_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=10000,
            )
        elif data_type == "funding":
            data = await self._history_api.fetch_funding_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=10000,
            )
        elif data_type == "interest":
            data = await self._history_api.fetch_interest_history(
                start_time=start_time,
                end_time=end_time,
                limit=10000,
            )
        else:
            raise ValueError(f"Unknown data type: {data_type}")
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Convert timestamps to datetime
        timestamp_cols = ["timestamp", "created_at", "updated_at"]
        for col in timestamp_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], unit="ms")
        
        # Save to CSV if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_path, index=False)
        
        return df

    async def export_to_parquet(
        self,
        data_type: str,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        output_path: Path | None = None,
    ) -> pd.DataFrame:
        """
        Export historical data to Parquet format for better performance.
        
        Parameters
        ----------
        data_type : str
            Type of data to export.
        symbol : str, optional
            Filter by symbol.
        start_time : int, optional
            Start timestamp in milliseconds.
        end_time : int, optional
            End timestamp in milliseconds.
        output_path : Path, optional
            Path to save the Parquet file.
            
        Returns
        -------
        pd.DataFrame
            The exported data as DataFrame.
        
        """
        # Get data as DataFrame
        df = await self.export_to_csv(
            data_type=data_type,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            output_path=None,  # Don't save as CSV
        )
        
        # Optimize data types for Parquet
        for col in df.columns:
            if df[col].dtype == "object":
                try:
                    # Try to convert to numeric
                    df[col] = pd.to_numeric(df[col])
                except (ValueError, TypeError):
                    # Keep as string
                    pass
        
        # Save to Parquet if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(
                output_path,
                engine="pyarrow",
                compression="snappy",
                index=False,
            )
        
        return df

    async def generate_html_report(
        self,
        report_type: str = "daily",
        date: datetime | None = None,
        output_path: Path | None = None,
    ) -> str:
        """
        Generate an HTML report with charts and visualizations.
        
        Parameters
        ----------
        report_type : str, default 'daily'
            Type of report ('daily', 'weekly', 'monthly').
        date : datetime, optional
            The date for the report.
        output_path : Path, optional
            Path to save the HTML file.
            
        Returns
        -------
        str
            The HTML report content.
        
        """
        if date is None:
            date = datetime.now()
        
        # Generate data for the report
        report_data = await self.generate_daily_pnl_report(date=date)
        
        # Create HTML template
        html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Backpack Trading Report - {date}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .header {{
            background-color: #2c3e50;
            color: white;
            padding: 20px;
            border-radius: 5px;
        }}
        .section {{
            background-color: white;
            margin: 20px 0;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metric {{
            display: inline-block;
            margin: 10px 20px;
        }}
        .metric-label {{
            color: #7f8c8d;
            font-size: 12px;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .positive {{
            color: #27ae60;
        }}
        .negative {{
            color: #e74c3c;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ecf0f1;
        }}
        th {{
            background-color: #34495e;
            color: white;
        }}
        .suggestion {{
            background-color: #f39c12;
            color: white;
            padding: 10px;
            border-radius: 3px;
            margin: 5px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Trading Report - {date}</h1>
        <p>Period: {period_start} to {period_end}</p>
    </div>
    
    <div class="section">
        <h2>PnL Summary</h2>
        <div class="metric">
            <div class="metric-label">Total PnL</div>
            <div class="metric-value {pnl_class}">{total_pnl}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Net PnL (after fees)</div>
            <div class="metric-value {net_pnl_class}">{net_pnl}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Fees Paid</div>
            <div class="metric-value negative">{fees_paid}</div>
        </div>
    </div>
    
    <div class="section">
        <h2>Trading Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Total Trades</td>
                <td>{trades_count}</td>
            </tr>
            <tr>
                <td>Win Rate</td>
                <td>{win_rate:.1%}</td>
            </tr>
            <tr>
                <td>Profit Factor</td>
                <td>{profit_factor}</td>
            </tr>
            <tr>
                <td>Sharpe Ratio</td>
                <td>{sharpe_ratio}</td>
            </tr>
            <tr>
                <td>Max Drawdown</td>
                <td>{max_drawdown}</td>
            </tr>
        </table>
    </div>
    
    <div class="section">
        <h2>Fee Analysis</h2>
        <table>
            <tr>
                <th>Fee Type</th>
                <th>Amount</th>
            </tr>
            <tr>
                <td>Maker Fees</td>
                <td>{maker_fees}</td>
            </tr>
            <tr>
                <td>Taker Fees</td>
                <td>{taker_fees}</td>
            </tr>
            <tr>
                <td>Funding Fees</td>
                <td>{funding_fees}</td>
            </tr>
            <tr>
                <td>Interest Fees</td>
                <td>{interest_fees}</td>
            </tr>
        </table>
        
        <h3>Optimization Suggestions</h3>
        {suggestions}
    </div>
    
    <div class="section">
        <h2>Execution Quality</h2>
        <div class="metric">
            <div class="metric-label">Average Slippage</div>
            <div class="metric-value">{average_slippage}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Positive Slippage</div>
            <div class="metric-value positive">{positive_slippage}</div>
        </div>
        <div class="metric">
            <div class="metric-label">Negative Slippage</div>
            <div class="metric-value negative">{negative_slippage}</div>
        </div>
    </div>
</body>
</html>
        """
        
        # Format suggestions
        suggestions_html = ""
        for suggestion in report_data["fees"]["optimization_suggestions"]:
            suggestions_html += f'<div class="suggestion">{suggestion}</div>'
        
        # Determine PnL classes
        pnl_class = "positive" if float(report_data["pnl"]["total_pnl"]) >= 0 else "negative"
        net_pnl_class = "positive" if float(report_data["pnl"]["net_pnl"]) >= 0 else "negative"
        
        # Format HTML
        html_content = html_template.format(
            date=date.strftime("%Y-%m-%d"),
            period_start=report_data["period"]["start"],
            period_end=report_data["period"]["end"],
            total_pnl=report_data["pnl"]["total_pnl"],
            pnl_class=pnl_class,
            net_pnl=report_data["pnl"]["net_pnl"],
            net_pnl_class=net_pnl_class,
            fees_paid=report_data["pnl"]["fees_paid"],
            trades_count=report_data["trading_metrics"]["trades_count"],
            win_rate=report_data["trading_metrics"]["win_rate"],
            profit_factor=report_data["trading_metrics"]["profit_factor"],
            sharpe_ratio=report_data["trading_metrics"]["sharpe_ratio"] or "N/A",
            max_drawdown=report_data["trading_metrics"]["max_drawdown"],
            maker_fees=report_data["fees"]["maker_fees"],
            taker_fees=report_data["fees"]["taker_fees"],
            funding_fees=report_data["fees"]["funding_fees"],
            interest_fees=report_data["fees"]["interest_fees"],
            suggestions=suggestions_html,
            average_slippage=report_data["execution_quality"]["average_slippage"],
            positive_slippage=report_data["execution_quality"]["positive_slippage"],
            negative_slippage=report_data["execution_quality"]["negative_slippage"],
        )
        
        # Save HTML if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(html_content)
        
        return html_content