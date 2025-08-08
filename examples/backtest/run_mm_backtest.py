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
Run market making strategy backtest with orderbook data.

This script:
1. Loads orderbook and trade data from catalog
2. Configures backtest engine with realistic fill models
3. Runs the market making strategy
4. Generates performance reports
"""

import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.engine import BacktestEngineConfig
from nautilus_trader.backtest.models import FillModel
from nautilus_trader.backtest.models import LatencyModel
from nautilus_trader.backtest.node import BacktestDataConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.backtest.node import BacktestRunConfig
from nautilus_trader.backtest.node import BacktestVenueConfig
from nautilus_trader.config import ImportableStrategyConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.enums import OmsType
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.catalog import ParquetDataCatalog


def run_backtest(
    catalog_path: str = "backpack_mm_catalog",
    symbol: str = "SOL_USDC",
    starting_balance_quote: str = "10000",
    starting_balance_base: str = "100",
) -> dict:
    """
    Run market making strategy backtest.
    
    Parameters
    ----------
    catalog_path : str
        Path to the data catalog
    symbol : str
        Trading symbol (e.g., "SOL_USDC")
    starting_balance_quote : str
        Starting balance in quote currency
    starting_balance_base : str
        Starting balance in base currency
    
    Returns
    -------
    dict
        Backtest results and statistics
    """
    
    print("=" * 80)
    print("Market Making Strategy Backtest")
    print("=" * 80)
    
    # Check catalog exists
    if not os.path.exists(catalog_path):
        print(f"Error: Catalog not found at {catalog_path}")
        print("Please run collect_backpack_mm_data.py first to collect data")
        return {}
    
    # Load catalog
    catalog = ParquetDataCatalog(catalog_path)
    
    # Get instrument
    instruments = catalog.instruments()
    if not instruments:
        print("Error: No instruments found in catalog")
        return {}
    
    instrument = instruments[0]
    print(f"Instrument: {instrument.id}")
    
    # Check available data
    start = catalog.min_timestamp()
    end = catalog.max_timestamp()
    
    if start and end:
        start_dt = pd.Timestamp(start, unit='ns', tz='UTC')
        end_dt = pd.Timestamp(end, unit='ns', tz='UTC')
        duration = (end_dt - start_dt).total_seconds() / 60
        print(f"Data range: {start_dt} to {end_dt} ({duration:.1f} minutes)")
    
    # Count data points
    ob_deltas = catalog.order_book_deltas(instrument_ids=[instrument.id])
    trade_ticks = catalog.trade_ticks(instrument_ids=[instrument.id])
    
    print(f"Orderbook deltas: {len(ob_deltas)}")
    print(f"Trade ticks: {len(trade_ticks)}")
    
    if len(ob_deltas) == 0 and len(trade_ticks) == 0:
        print("Error: No data available in catalog")
        return {}
    
    print("\nConfiguring backtest...")
    
    # Configure data feeds
    data_configs = []
    
    # Add orderbook data if available
    if ob_deltas:
        data_configs.append(
            BacktestDataConfig(
                catalog_path=catalog_path,
                data_cls=OrderBookDelta,
                instrument_id=instrument.id,
            )
        )
    
    # Add trade data if available
    if trade_ticks:
        data_configs.append(
            BacktestDataConfig(
                catalog_path=catalog_path,
                data_cls=TradeTick,
                instrument_id=instrument.id,
            )
        )
    
    # Configure venue with realistic fill model
    venues_configs = [
        BacktestVenueConfig(
            name=BACKPACK_VENUE.value,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=None,
            starting_balances=[
                f"{starting_balance_quote} {symbol.split('_')[1]}",
                f"{starting_balance_base} {symbol.split('_')[0]}",
            ],
            book_type=BookType.L2_MBP,
            # Realistic fill model for market making
            fill_model=FillModel(
                prob_fill_on_limit=0.8,  # 80% chance of fill when price touches
                prob_fill_on_stop=0.95,  # 95% for stops
                prob_slippage=0.1,       # 10% chance of slippage
                random_seed=42,
            ),
            # Latency model for realistic execution
            latency_model=LatencyModel(
                base_latency_nanos=10_000_000,     # 10ms base latency
                insert_latency_nanos=5_000_000,     # 5ms for order insertion
                update_latency_nanos=5_000_000,     # 5ms for order updates
                cancel_latency_nanos=5_000_000,     # 5ms for cancellations
            ),
        ),
    ]
    
    # Configure strategy
    strategies = [
        ImportableStrategyConfig(
            strategy_path="nautilus_trader.examples.strategies.simple_mm_backtest:SimpleMMBacktest",
            config_path="nautilus_trader.examples.strategies.simple_mm_backtest:SimpleMMBacktestConfig",
            config={
                "instrument_id": str(instrument.id),
                "trade_size": Decimal("0.1"),  # 0.1 SOL per order
                "base_spread_bps": 20,         # 0.20% base spread
                "min_spread_bps": 10,          # 0.10% minimum
                "max_spread_bps": 100,         # 1.00% maximum
                "max_position": Decimal("5.0"), # Max 5 SOL position
                "inventory_skew_factor": Decimal("0.1"),
                "stop_loss_pct": Decimal("0.02"),  # 2% stop loss
                "book_type": BookType.L2_MBP,
                "orderbook_imbalance_threshold": Decimal("0.6"),
                "atr_period": 20,
                "volatility_adjustment": True,
                "update_interval_seconds": 5,
                "order_levels": 1,  # Single level for simplicity
            },
        ),
    ]
    
    # Create run configuration
    config = BacktestRunConfig(
        engine=BacktestEngineConfig(
            strategies=strategies,
            logging=LoggingConfig(
                log_level="INFO",
                # Use file handler to avoid Jupyter rate limits
                log_to_file=True,
                log_file_name="mm_backtest.log",
            ),
        ),
        data=data_configs,
        venues=venues_configs,
    )
    
    print("Running backtest...")
    print("-" * 80)
    
    # Run backtest
    node = BacktestNode(configs=[config])
    results = node.run()
    
    print("-" * 80)
    print("Backtest complete!")
    
    # Get engine for detailed analysis
    engine: BacktestEngine = node.get_engine(config.id)
    
    # Generate reports
    print("\n" + "=" * 80)
    print("Performance Reports")
    print("=" * 80)
    
    # Order fills report
    print("\n--- Order Fills ---")
    fills_report = engine.trader.generate_order_fills_report()
    if not fills_report.empty:
        print(f"Total fills: {len(fills_report)}")
        print(f"Buy fills: {len(fills_report[fills_report['side'] == 'BUY'])}")
        print(f"Sell fills: {len(fills_report[fills_report['side'] == 'SELL'])}")
        
        # Calculate some statistics
        if 'avg_px' in fills_report.columns:
            avg_fill_price = fills_report['avg_px'].mean()
            print(f"Average fill price: {avg_fill_price:.4f}")
    else:
        print("No fills executed")
    
    # Positions report
    print("\n--- Positions ---")
    positions_report = engine.trader.generate_positions_report()
    if not positions_report.empty:
        print(f"Total positions: {len(positions_report)}")
        print(f"Winning positions: {len(positions_report[positions_report['realized_pnl'] > 0])}")
        print(f"Losing positions: {len(positions_report[positions_report['realized_pnl'] < 0])}")
        
        if 'realized_pnl' in positions_report.columns:
            total_pnl = positions_report['realized_pnl'].sum()
            print(f"Total realized PnL: {total_pnl:.2f}")
    else:
        print("No positions opened")
    
    # Account report
    print("\n--- Account Summary ---")
    account_report = engine.trader.generate_account_report(Venue(BACKPACK_VENUE.value))
    print(account_report)
    
    # Calculate additional metrics
    print("\n--- Market Making Metrics ---")
    
    if not fills_report.empty:
        # Calculate spread capture
        if 'avg_px' in fills_report.columns:
            buy_fills = fills_report[fills_report['side'] == 'BUY']['avg_px']
            sell_fills = fills_report[fills_report['side'] == 'SELL']['avg_px']
            
            if not buy_fills.empty and not sell_fills.empty:
                avg_buy_price = buy_fills.mean()
                avg_sell_price = sell_fills.mean()
                avg_spread = avg_sell_price - avg_buy_price
                spread_bps = (avg_spread / avg_buy_price) * 10000
                print(f"Average spread captured: {spread_bps:.1f} bps")
        
        # Calculate fill rate
        total_orders = len(engine.trader.generate_orders_report())
        fill_rate = (len(fills_report) / total_orders * 100) if total_orders > 0 else 0
        print(f"Fill rate: {fill_rate:.1f}%")
        
        # Volume analysis
        if 'qty' in fills_report.columns:
            total_volume = fills_report['qty'].sum()
            print(f"Total volume traded: {total_volume:.4f}")
    
    # Save detailed reports
    output_dir = Path("backtest_results")
    output_dir.mkdir(exist_ok=True)
    
    # Save fills report
    if not fills_report.empty:
        fills_report.to_csv(output_dir / "fills_report.csv", index=False)
        print(f"\nFills report saved to: {output_dir / 'fills_report.csv'}")
    
    # Save positions report
    if not positions_report.empty:
        positions_report.to_csv(output_dir / "positions_report.csv", index=False)
        print(f"Positions report saved to: {output_dir / 'positions_report.csv'}")
    
    print("\n" + "=" * 80)
    print("Backtest analysis complete!")
    print("=" * 80)
    
    # Return results
    return {
        "results": results,
        "fills_report": fills_report,
        "positions_report": positions_report,
        "account_report": account_report,
    }


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run market making strategy backtest")
    parser.add_argument(
        "--catalog",
        default="backpack_mm_catalog",
        help="Path to data catalog (default: backpack_mm_catalog)",
    )
    parser.add_argument(
        "--symbol",
        default="SOL_USDC",
        help="Trading symbol (default: SOL_USDC)",
    )
    parser.add_argument(
        "--quote-balance",
        default="10000",
        help="Starting balance in quote currency (default: 10000)",
    )
    parser.add_argument(
        "--base-balance",
        default="100",
        help="Starting balance in base currency (default: 100)",
    )
    
    args = parser.parse_args()
    
    # Run backtest
    results = run_backtest(
        catalog_path=args.catalog,
        symbol=args.symbol,
        starting_balance_quote=args.quote_balance,
        starting_balance_base=args.base_balance,
    )
    
    return results


if __name__ == "__main__":
    main()