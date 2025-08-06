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
Backpack Exchange Market Maker Example

This example demonstrates a simple market-making strategy on Backpack Exchange.
The strategy places limit orders on both sides of the order book and adjusts
them based on market volatility.

*** THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
*** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***
"""

import os
from decimal import Decimal

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.factories import BackpackLiveDataClientFactory
from nautilus_trader.adapters.backpack.factories import BackpackLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.config import LiveExecEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.examples.strategies.volatility_market_maker import VolatilityMarketMaker
from nautilus_trader.examples.strategies.volatility_market_maker import VolatilityMarketMakerConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TraderId


# *** THIS IS A TEST STRATEGY WITH NO ALPHA ADVANTAGE WHATSOEVER. ***
# *** IT IS NOT INTENDED TO BE USED TO TRADE LIVE WITH REAL MONEY. ***


def main():
    """Run the Backpack market maker example."""
    
    # Configuration for the trading node
    config_node = TradingNodeConfig(
        trader_id=TraderId("MM-001"),
        logging=LoggingConfig(
            log_level="INFO",
            use_pyo3=True,
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=5,
            snapshot_orders=True,
            snapshot_positions=True,
            snapshot_positions_interval_secs=10.0,
        ),
        data_clients={
            BACKPACK_VENUE.value: BackpackDataClientConfig(
                api_key=os.getenv("BACKPACK_API_KEY"),
                api_secret=os.getenv("BACKPACK_API_SECRET"),
                testnet=os.getenv("BACKPACK_TESTNET", "false").lower() == "true",
                instrument_provider=InstrumentProviderConfig(
                    load_all=True,
                    log_warnings=True,
                ),
            ),
        },
        exec_clients={
            BACKPACK_VENUE.value: BackpackExecClientConfig(
                api_key=os.getenv("BACKPACK_API_KEY"),
                api_secret=os.getenv("BACKPACK_API_SECRET"),
                testnet=os.getenv("BACKPACK_TESTNET", "false").lower() == "true",
                instrument_provider=InstrumentProviderConfig(
                    load_all=True,
                    log_warnings=True,
                ),
                max_retries=3,
                retry_delay=1.0,
            ),
        },
        timeout_connection=30.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )
    
    # Instantiate the trading node
    node = TradingNode(config=config_node)
    
    # Configure the market maker strategy
    # Using SOL/USDC as an example trading pair
    instrument_id = InstrumentId.from_str(f"SOL_USDC.{BACKPACK_VENUE}")
    
    strategy_config = VolatilityMarketMakerConfig(
        instrument_id=instrument_id,
        external_order_claims=[instrument_id],
        bar_type=BarType.from_str(f"SOL_USDC.{BACKPACK_VENUE}-1-MINUTE-LAST-INTERNAL"),
        atr_period=20,  # ATR period for volatility calculation
        atr_multiple=3.0,  # Multiplier for spread calculation
        trade_size=Decimal("0.1"),  # Size per order in base currency (0.1 SOL)
        order_id_tag="MM",  # Tag for order IDs
        oms_type="HEDGING",  # Order management system type
    )
    
    # Instantiate the strategy
    strategy = VolatilityMarketMaker(config=strategy_config)
    
    # Add the strategy to the trader
    node.trader.add_strategy(strategy)
    
    # Register the Backpack client factories
    node.add_data_client_factory(BACKPACK_VENUE.value, BackpackLiveDataClientFactory)
    node.add_exec_client_factory(BACKPACK_VENUE.value, BackpackLiveExecClientFactory)
    
    # Build the node
    node.build()
    
    return node


# Stop and dispose of the node with SIGINT/CTRL+C
if __name__ == "__main__":
    node = main()
    
    try:
        node.run()
    finally:
        node.dispose()