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
This example demonstrates how to use the ExecTester strategy to test the
Backpack exchange adapter's execution functionality.

The strategy will:
1. Connect to Backpack exchange (testnet or mainnet)
2. Subscribe to market data for the configured instrument
3. Place limit orders on both sides of the market
4. Manage orders based on market movements
5. Test various order types and execution scenarios
"""

import asyncio
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
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.test_kit.strategies.tester_exec import ExecTester
from nautilus_trader.test_kit.strategies.tester_exec import ExecTesterConfig


# Configure the Backpack instrument to test
INSTRUMENT_ID = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)

# Test configuration
TEST_CONFIG = {
    "testnet": True,  # Use testnet for testing
    "order_qty": Decimal("0.1"),  # Small test quantity
    "subscribe_quotes": True,
    "subscribe_trades": True,
    "subscribe_book": True,
    "book_type": BookType.L2_MBP,
    "book_depth": 10,
    "book_interval_ms": 1000,
    "enable_buys": True,
    "enable_sells": True,
    "market_offset_ticks": 100,  # Place orders away from market
    "use_post_only": True,  # Use post-only orders to avoid fees
    "use_quote_quantity": False,
    "reduce_only_on_stop": False,
    "dry_run": False,  # Set to True to skip actual order submission
    "log_data": True,
}


def get_config(testnet: bool = True) -> TradingNodeConfig:
    """
    Create the trading node configuration for Backpack ExecTester.
    
    Parameters
    ----------
    testnet : bool
        Whether to use testnet (True) or mainnet (False).
    
    Returns
    -------
    TradingNodeConfig
        The configured trading node.
    """
    # Get API credentials from environment
    api_key = os.getenv("BACKPACK_TESTNET_API_KEY" if testnet else "BACKPACK_API_KEY")
    api_secret = os.getenv("BACKPACK_TESTNET_API_SECRET" if testnet else "BACKPACK_API_SECRET")
    
    if not api_key or not api_secret:
        raise ValueError(
            f"Missing Backpack {'testnet' if testnet else 'mainnet'} credentials. "
            f"Please set BACKPACK_{'TESTNET_' if testnet else ''}API_KEY and "
            f"BACKPACK_{'TESTNET_' if testnet else ''}API_SECRET environment variables."
        )
    
    # Create strategy configuration
    strategy_config = ExecTesterConfig(
        instrument_id=INSTRUMENT_ID,
        order_qty=TEST_CONFIG["order_qty"],
        subscribe_quotes=TEST_CONFIG["subscribe_quotes"],
        subscribe_trades=TEST_CONFIG["subscribe_trades"],
        subscribe_book=TEST_CONFIG["subscribe_book"],
        book_type=TEST_CONFIG["book_type"],
        book_depth=TEST_CONFIG["book_depth"],
        book_interval_ms=TEST_CONFIG["book_interval_ms"],
        enable_buys=TEST_CONFIG["enable_buys"],
        enable_sells=TEST_CONFIG["enable_sells"],
        market_offset_ticks=TEST_CONFIG["market_offset_ticks"],
        use_post_only=TEST_CONFIG["use_post_only"],
        use_quote_quantity=TEST_CONFIG["use_quote_quantity"],
        reduce_only_on_stop=TEST_CONFIG["reduce_only_on_stop"],
        dry_run=TEST_CONFIG["dry_run"],
        log_data=TEST_CONFIG["log_data"],
    )
    
    # Create data client configuration
    data_config = BackpackDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
        instrument_provider=InstrumentProviderConfig(
            load_all=False,  # Only load specific instruments
        ),
    )
    
    # Create execution client configuration
    exec_config = BackpackExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
    )
    
    # Create trading node configuration
    return TradingNodeConfig(
        trader_id="BACKPACK-TESTER-001",
        logging=LoggingConfig(
            log_level="INFO",
            log_colors=True,
        ),
        exec_engine=LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=1440,  # 24 hours
        ),
        data_clients={
            BACKPACK_VENUE.value: data_config,
        },
        exec_clients={
            BACKPACK_VENUE.value: exec_config,
        },
        strategies=[strategy_config],
    )


async def main():
    """
    Run the Backpack ExecTester.
    """
    # Determine if using testnet
    testnet = TEST_CONFIG["testnet"]
    
    print(f"Starting Backpack ExecTester on {'TESTNET' if testnet else 'MAINNET'}")
    print(f"Testing instrument: {INSTRUMENT_ID}")
    print(f"Order quantity: {TEST_CONFIG['order_qty']}")
    print(f"Post-only: {TEST_CONFIG['use_post_only']}")
    print(f"Dry run: {TEST_CONFIG['dry_run']}")
    print("-" * 50)
    
    # Create and configure the trading node
    config = get_config(testnet=testnet)
    node = TradingNode(config)
    
    # Register the Backpack client factories
    node.add_data_client_factory(BACKPACK_VENUE.value, BackpackLiveDataClientFactory)
    node.add_exec_client_factory(BACKPACK_VENUE.value, BackpackLiveExecClientFactory)
    
    try:
        # Build and start the node
        node.build()
        await node.run_async()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Ensure proper cleanup
        await node.stop()
        await asyncio.sleep(0.1)  # Allow cleanup to complete
        print("ExecTester stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
        raise