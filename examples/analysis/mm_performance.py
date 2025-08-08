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
Market Making Performance Analysis Module.

Provides comprehensive analysis tools for market making strategy performance including:
- Spread capture analysis
- Inventory risk metrics
- Fill rate analysis
- PnL attribution
- Visualization tools
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.gridspec import GridSpec

from nautilus_trader.analysis.analyzer import PortfolioAnalyzer
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.identifiers import Venue


class MarketMakingAnalyzer:
    """
    Analyzer for market making strategy performance.
    
    Provides specialized metrics and visualizations for market making strategies.
    """
    
    def __init__(self, engine: BacktestEngine, venue: Venue):
        """
        Initialize the analyzer.
        
        Parameters
        ----------
        engine : BacktestEngine
            The backtest engine with results
        venue : Venue
            The trading venue
        """
        self.engine = engine
        self.venue = venue
        
        # Load reports
        self.fills_report = engine.trader.generate_order_fills_report()
        self.positions_report = engine.trader.generate_positions_report()
        self.orders_report = engine.trader.generate_orders_report()
        self.account_report = engine.trader.generate_account_report(venue)
        
        # Portfolio analyzer for standard metrics
        self.portfolio_analyzer = PortfolioAnalyzer()
    
    def calculate_spread_metrics(self) -> dict:
        """
        Calculate spread capture metrics.
        
        Returns
        -------
        dict
            Spread metrics including realized vs quoted spread
        """
        metrics = {}
        
        if self.fills_report.empty:
            return metrics
        
        # Separate buy and sell fills
        buy_fills = self.fills_report[self.fills_report['side'] == 'BUY'].copy()
        sell_fills = self.fills_report[self.fills_report['side'] == 'SELL'].copy()
        
        if not buy_fills.empty and not sell_fills.empty:
            # Calculate average prices
            avg_buy_price = buy_fills['avg_px'].mean()
            avg_sell_price = sell_fills['avg_px'].mean()
            
            # Realized spread
            realized_spread = avg_sell_price - avg_buy_price
            realized_spread_bps = (realized_spread / avg_buy_price) * 10000
            
            metrics['avg_buy_price'] = avg_buy_price
            metrics['avg_sell_price'] = avg_sell_price
            metrics['realized_spread'] = realized_spread
            metrics['realized_spread_bps'] = realized_spread_bps
            
            # Calculate per-trade spreads if timestamps align
            buy_fills['timestamp'] = pd.to_datetime(buy_fills['timestamp'])
            sell_fills['timestamp'] = pd.to_datetime(sell_fills['timestamp'])
            
            # Match trades within time windows (e.g., 1 minute)
            spreads = []
            for _, buy in buy_fills.iterrows():
                time_window = pd.Timedelta(minutes=1)
                matched_sells = sell_fills[
                    (sell_fills['timestamp'] >= buy['timestamp']) &
                    (sell_fills['timestamp'] <= buy['timestamp'] + time_window)
                ]
                
                if not matched_sells.empty:
                    for _, sell in matched_sells.iterrows():
                        spread = sell['avg_px'] - buy['avg_px']
                        spread_bps = (spread / buy['avg_px']) * 10000
                        spreads.append(spread_bps)
            
            if spreads:
                metrics['median_spread_bps'] = np.median(spreads)
                metrics['std_spread_bps'] = np.std(spreads)
                metrics['min_spread_bps'] = np.min(spreads)
                metrics['max_spread_bps'] = np.max(spreads)
        
        return metrics
    
    def calculate_inventory_metrics(self) -> dict:
        """
        Calculate inventory risk metrics.
        
        Returns
        -------
        dict
            Inventory metrics including turnover and risk measures
        """
        metrics = {}
        
        if self.positions_report.empty:
            return metrics
        
        # Calculate position statistics
        positions = self.positions_report.copy()
        
        if 'peak_qty' in positions.columns:
            metrics['max_position'] = positions['peak_qty'].abs().max()
            metrics['avg_position'] = positions['peak_qty'].abs().mean()
            metrics['position_std'] = positions['peak_qty'].std()
        
        if 'duration' in positions.columns:
            # Convert duration to seconds if needed
            metrics['avg_holding_time'] = positions['duration'].mean()
            metrics['max_holding_time'] = positions['duration'].max()
        
        # Calculate inventory turnover
        if not self.fills_report.empty and 'qty' in self.fills_report.columns:
            total_volume = self.fills_report['qty'].sum()
            
            if 'peak_qty' in positions.columns:
                avg_inventory = positions['peak_qty'].abs().mean()
                if avg_inventory > 0:
                    metrics['inventory_turnover'] = total_volume / avg_inventory
        
        # Calculate inventory-adjusted returns
        if 'realized_pnl' in positions.columns and 'peak_qty' in positions.columns:
            positions['return_per_unit'] = positions['realized_pnl'] / positions['peak_qty'].abs()
            metrics['avg_return_per_unit'] = positions['return_per_unit'].mean()
            metrics['sharpe_per_unit'] = (
                positions['return_per_unit'].mean() / positions['return_per_unit'].std()
                if positions['return_per_unit'].std() > 0 else 0
            )
        
        return metrics
    
    def calculate_fill_metrics(self) -> dict:
        """
        Calculate order fill metrics.
        
        Returns
        -------
        dict
            Fill rate and execution quality metrics
        """
        metrics = {}
        
        if self.orders_report.empty:
            return metrics
        
        # Overall fill rate
        total_orders = len(self.orders_report)
        filled_orders = len(self.orders_report[self.orders_report['status'] == 'FILLED'])
        metrics['fill_rate'] = (filled_orders / total_orders * 100) if total_orders > 0 else 0
        
        # Fill rate by side
        buy_orders = self.orders_report[self.orders_report['side'] == 'BUY']
        sell_orders = self.orders_report[self.orders_report['side'] == 'SELL']
        
        if not buy_orders.empty:
            buy_filled = len(buy_orders[buy_orders['status'] == 'FILLED'])
            metrics['buy_fill_rate'] = (buy_filled / len(buy_orders) * 100)
        
        if not sell_orders.empty:
            sell_filled = len(sell_orders[sell_orders['status'] == 'FILLED'])
            metrics['sell_fill_rate'] = (sell_filled / len(sell_orders) * 100)
        
        # Time to fill analysis
        if not self.fills_report.empty and 'timestamp' in self.fills_report.columns:
            # This would require order submission times which may not be available
            # in the standard reports
            pass
        
        # Partial fill analysis
        partially_filled = self.orders_report[self.orders_report['status'] == 'PARTIALLY_FILLED']
        metrics['partial_fill_rate'] = (
            len(partially_filled) / total_orders * 100 if total_orders > 0 else 0
        )
        
        # Cancellation rate
        canceled_orders = len(self.orders_report[self.orders_report['status'] == 'CANCELED'])
        metrics['cancel_rate'] = (canceled_orders / total_orders * 100) if total_orders > 0 else 0
        
        return metrics
    
    def calculate_pnl_attribution(self) -> dict:
        """
        Attribute PnL to spread capture vs directional moves.
        
        Returns
        -------
        dict
            PnL attribution metrics
        """
        attribution = {}
        
        if self.positions_report.empty:
            return attribution
        
        # Total PnL
        if 'realized_pnl' in self.positions_report.columns:
            total_pnl = self.positions_report['realized_pnl'].sum()
            attribution['total_pnl'] = total_pnl
            
            # Estimate spread component
            spread_metrics = self.calculate_spread_metrics()
            if 'realized_spread_bps' in spread_metrics and not self.fills_report.empty:
                # Rough estimation: spread * volume
                if 'qty' in self.fills_report.columns and 'avg_px' in self.fills_report.columns:
                    total_volume = self.fills_report['qty'].sum() / 2  # Divide by 2 for round trips
                    avg_price = self.fills_report['avg_px'].mean()
                    spread_pnl = (spread_metrics['realized_spread_bps'] / 10000) * avg_price * total_volume
                    attribution['spread_pnl'] = spread_pnl
                    attribution['directional_pnl'] = total_pnl - spread_pnl
                    
                    # Calculate percentages
                    if total_pnl != 0:
                        attribution['spread_pnl_pct'] = (spread_pnl / total_pnl) * 100
                        attribution['directional_pnl_pct'] = ((total_pnl - spread_pnl) / total_pnl) * 100
        
        return attribution
    
    def generate_performance_report(self) -> pd.DataFrame:
        """
        Generate comprehensive performance report.
        
        Returns
        -------
        pd.DataFrame
            Performance metrics summary
        """
        # Collect all metrics
        report_data = []
        
        # Spread metrics
        spread_metrics = self.calculate_spread_metrics()
        for key, value in spread_metrics.items():
            report_data.append({
                'Category': 'Spread',
                'Metric': key.replace('_', ' ').title(),
                'Value': f"{value:.4f}" if isinstance(value, (int, float)) else value
            })
        
        # Inventory metrics
        inventory_metrics = self.calculate_inventory_metrics()
        for key, value in inventory_metrics.items():
            report_data.append({
                'Category': 'Inventory',
                'Metric': key.replace('_', ' ').title(),
                'Value': f"{value:.4f}" if isinstance(value, (int, float)) else value
            })
        
        # Fill metrics
        fill_metrics = self.calculate_fill_metrics()
        for key, value in fill_metrics.items():
            report_data.append({
                'Category': 'Execution',
                'Metric': key.replace('_', ' ').title(),
                'Value': f"{value:.2f}%" if 'rate' in key else f"{value:.4f}"
            })
        
        # PnL attribution
        pnl_attribution = self.calculate_pnl_attribution()
        for key, value in pnl_attribution.items():
            report_data.append({
                'Category': 'PnL Attribution',
                'Metric': key.replace('_', ' ').title(),
                'Value': f"{value:.2f}%" if 'pct' in key else f"${value:.2f}"
            })
        
        return pd.DataFrame(report_data)
    
    def plot_performance(self, save_path: Optional[Path] = None) -> None:
        """
        Create comprehensive performance visualization.
        
        Parameters
        ----------
        save_path : Optional[Path]
            Path to save the plot
        """
        # Set style
        plt.style.use('seaborn-v0_8-darkgrid')
        
        # Create figure with subplots
        fig = plt.figure(figsize=(16, 12))
        gs = GridSpec(3, 3, figure=fig, hspace=0.3, wspace=0.3)
        
        # 1. Cumulative PnL
        ax1 = fig.add_subplot(gs[0, :])
        self._plot_cumulative_pnl(ax1)
        
        # 2. Inventory evolution
        ax2 = fig.add_subplot(gs[1, 0])
        self._plot_inventory_evolution(ax2)
        
        # 3. Spread distribution
        ax3 = fig.add_subplot(gs[1, 1])
        self._plot_spread_distribution(ax3)
        
        # 4. Fill rates
        ax4 = fig.add_subplot(gs[1, 2])
        self._plot_fill_rates(ax4)
        
        # 5. PnL attribution
        ax5 = fig.add_subplot(gs[2, 0])
        self._plot_pnl_attribution(ax5)
        
        # 6. Trade size distribution
        ax6 = fig.add_subplot(gs[2, 1])
        self._plot_trade_sizes(ax6)
        
        # 7. Hourly performance
        ax7 = fig.add_subplot(gs[2, 2])
        self._plot_hourly_performance(ax7)
        
        # Add title
        fig.suptitle('Market Making Strategy Performance Analysis', fontsize=16, y=0.98)
        
        # Save or show
        if save_path:
            plt.savefig(save_path, dpi=100, bbox_inches='tight')
            print(f"Performance plot saved to: {save_path}")
        else:
            plt.show()
    
    def _plot_cumulative_pnl(self, ax) -> None:
        """Plot cumulative PnL over time."""
        if self.positions_report.empty or 'realized_pnl' not in self.positions_report.columns:
            ax.text(0.5, 0.5, 'No PnL data available', ha='center', va='center')
            ax.set_title('Cumulative PnL')
            return
        
        positions = self.positions_report.copy()
        if 'closed_time' in positions.columns:
            positions['timestamp'] = pd.to_datetime(positions['closed_time'])
            positions = positions.sort_values('timestamp')
            positions['cumulative_pnl'] = positions['realized_pnl'].cumsum()
            
            ax.plot(positions['timestamp'], positions['cumulative_pnl'], 
                   linewidth=2, color='green' if positions['cumulative_pnl'].iloc[-1] > 0 else 'red')
            ax.fill_between(positions['timestamp'], 0, positions['cumulative_pnl'], 
                           alpha=0.3, color='green' if positions['cumulative_pnl'].iloc[-1] > 0 else 'red')
            ax.axhline(y=0, color='black', linestyle='--', alpha=0.5)
            ax.set_xlabel('Time')
            ax.set_ylabel('Cumulative PnL ($)')
            ax.set_title('Cumulative Profit/Loss')
            ax.grid(True, alpha=0.3)
    
    def _plot_inventory_evolution(self, ax) -> None:
        """Plot inventory over time."""
        if self.positions_report.empty:
            ax.text(0.5, 0.5, 'No position data available', ha='center', va='center')
            ax.set_title('Inventory Evolution')
            return
        
        positions = self.positions_report.copy()
        if 'peak_qty' in positions.columns and 'opened_time' in positions.columns:
            positions['timestamp'] = pd.to_datetime(positions['opened_time'])
            positions = positions.sort_values('timestamp')
            
            ax.plot(positions['timestamp'], positions['peak_qty'], 
                   linewidth=1.5, color='blue', alpha=0.7)
            ax.fill_between(positions['timestamp'], 0, positions['peak_qty'], 
                           alpha=0.3, color='blue')
            ax.axhline(y=0, color='black', linestyle='--', alpha=0.5)
            ax.set_xlabel('Time')
            ax.set_ylabel('Position Size')
            ax.set_title('Inventory Evolution')
            ax.grid(True, alpha=0.3)
    
    def _plot_spread_distribution(self, ax) -> None:
        """Plot distribution of captured spreads."""
        spread_metrics = self.calculate_spread_metrics()
        
        if not self.fills_report.empty:
            # Calculate spreads between consecutive buy/sell orders
            fills = self.fills_report.copy()
            fills['timestamp'] = pd.to_datetime(fills['timestamp'])
            fills = fills.sort_values('timestamp')
            
            spreads = []
            for i in range(1, len(fills)):
                if fills.iloc[i-1]['side'] != fills.iloc[i]['side']:
                    spread_bps = abs(fills.iloc[i]['avg_px'] - fills.iloc[i-1]['avg_px']) / fills.iloc[i-1]['avg_px'] * 10000
                    spreads.append(spread_bps)
            
            if spreads:
                ax.hist(spreads, bins=30, edgecolor='black', alpha=0.7, color='purple')
                ax.axvline(x=np.mean(spreads), color='red', linestyle='--', 
                          label=f'Mean: {np.mean(spreads):.1f} bps')
                ax.set_xlabel('Spread (bps)')
                ax.set_ylabel('Frequency')
                ax.set_title('Spread Distribution')
                ax.legend()
                ax.grid(True, alpha=0.3)
            else:
                ax.text(0.5, 0.5, 'No spread data available', ha='center', va='center')
                ax.set_title('Spread Distribution')
        else:
            ax.text(0.5, 0.5, 'No fill data available', ha='center', va='center')
            ax.set_title('Spread Distribution')
    
    def _plot_fill_rates(self, ax) -> None:
        """Plot fill rates by order side."""
        fill_metrics = self.calculate_fill_metrics()
        
        if fill_metrics:
            categories = []
            rates = []
            colors = []
            
            if 'buy_fill_rate' in fill_metrics:
                categories.append('Buy')
                rates.append(fill_metrics['buy_fill_rate'])
                colors.append('green')
            
            if 'sell_fill_rate' in fill_metrics:
                categories.append('Sell')
                rates.append(fill_metrics['sell_fill_rate'])
                colors.append('red')
            
            if 'fill_rate' in fill_metrics:
                categories.append('Overall')
                rates.append(fill_metrics['fill_rate'])
                colors.append('blue')
            
            if categories:
                bars = ax.bar(categories, rates, color=colors, alpha=0.7, edgecolor='black')
                ax.set_ylabel('Fill Rate (%)')
                ax.set_title('Order Fill Rates')
                ax.set_ylim(0, 100)
                
                # Add value labels on bars
                for bar, rate in zip(bars, rates):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height,
                           f'{rate:.1f}%', ha='center', va='bottom')
                
                ax.grid(True, alpha=0.3, axis='y')
            else:
                ax.text(0.5, 0.5, 'No fill rate data available', ha='center', va='center')
                ax.set_title('Order Fill Rates')
        else:
            ax.text(0.5, 0.5, 'No order data available', ha='center', va='center')
            ax.set_title('Order Fill Rates')
    
    def _plot_pnl_attribution(self, ax) -> None:
        """Plot PnL attribution pie chart."""
        attribution = self.calculate_pnl_attribution()
        
        if attribution and 'spread_pnl' in attribution and 'directional_pnl' in attribution:
            sizes = [abs(attribution['spread_pnl']), abs(attribution['directional_pnl'])]
            labels = ['Spread Capture', 'Directional']
            colors = ['#90EE90', '#FFB6C1']
            
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors,
                                               autopct='%1.1f%%', startangle=90)
            ax.set_title('PnL Attribution')
            
            # Add total PnL as text
            if 'total_pnl' in attribution:
                ax.text(0, -1.3, f"Total PnL: ${attribution['total_pnl']:.2f}",
                       ha='center', fontsize=10, weight='bold')
        else:
            ax.text(0.5, 0.5, 'No PnL attribution data available', ha='center', va='center')
            ax.set_title('PnL Attribution')
    
    def _plot_trade_sizes(self, ax) -> None:
        """Plot distribution of trade sizes."""
        if not self.fills_report.empty and 'qty' in self.fills_report.columns:
            ax.hist(self.fills_report['qty'], bins=20, edgecolor='black', 
                   alpha=0.7, color='orange')
            ax.set_xlabel('Trade Size')
            ax.set_ylabel('Frequency')
            ax.set_title('Trade Size Distribution')
            ax.grid(True, alpha=0.3)
            
            # Add statistics
            mean_size = self.fills_report['qty'].mean()
            ax.axvline(x=mean_size, color='red', linestyle='--',
                      label=f'Mean: {mean_size:.4f}')
            ax.legend()
        else:
            ax.text(0.5, 0.5, 'No trade size data available', ha='center', va='center')
            ax.set_title('Trade Size Distribution')
    
    def _plot_hourly_performance(self, ax) -> None:
        """Plot performance by hour of day."""
        if not self.fills_report.empty and 'timestamp' in self.fills_report.columns:
            fills = self.fills_report.copy()
            fills['timestamp'] = pd.to_datetime(fills['timestamp'])
            fills['hour'] = fills['timestamp'].dt.hour
            
            # Calculate hourly statistics
            hourly_counts = fills.groupby('hour').size()
            
            if not hourly_counts.empty:
                ax.bar(hourly_counts.index, hourly_counts.values, 
                      color='teal', alpha=0.7, edgecolor='black')
                ax.set_xlabel('Hour of Day')
                ax.set_ylabel('Number of Fills')
                ax.set_title('Trading Activity by Hour')
                ax.set_xticks(range(0, 24))
                ax.grid(True, alpha=0.3, axis='y')
            else:
                ax.text(0.5, 0.5, 'No hourly data available', ha='center', va='center')
                ax.set_title('Trading Activity by Hour')
        else:
            ax.text(0.5, 0.5, 'No timestamp data available', ha='center', va='center')
            ax.set_title('Trading Activity by Hour')
    
    def save_metrics_to_csv(self, filepath: Path) -> None:
        """
        Save performance metrics to CSV file.
        
        Parameters
        ----------
        filepath : Path
            Path to save the CSV file
        """
        report = self.generate_performance_report()
        report.to_csv(filepath, index=False)
        print(f"Performance metrics saved to: {filepath}")


def analyze_backtest_results(
    engine: BacktestEngine,
    venue: Venue,
    output_dir: Optional[Path] = None,
) -> MarketMakingAnalyzer:
    """
    Analyze backtest results for market making strategy.
    
    Parameters
    ----------
    engine : BacktestEngine
        The backtest engine with results
    venue : Venue
        The trading venue
    output_dir : Optional[Path]
        Directory to save analysis outputs
    
    Returns
    -------
    MarketMakingAnalyzer
        The analyzer instance
    """
    # Create analyzer
    analyzer = MarketMakingAnalyzer(engine, venue)
    
    # Generate performance report
    print("\n" + "=" * 80)
    print("Market Making Performance Analysis")
    print("=" * 80)
    
    report = analyzer.generate_performance_report()
    print("\n" + report.to_string(index=False))
    
    # Save outputs if directory provided
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)
        
        # Save metrics
        analyzer.save_metrics_to_csv(output_dir / "mm_performance_metrics.csv")
        
        # Save plot
        analyzer.plot_performance(save_path=output_dir / "mm_performance_plot.png")
    else:
        # Show plot
        analyzer.plot_performance()
    
    return analyzer