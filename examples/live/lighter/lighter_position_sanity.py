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
Mainnet sanity script: fetch account and position data from Lighter.

Tests the PR4 implementation of account/position models and endpoint methods.

Requirements:
- .env populated with LIGHTER_ACCOUNT_INDEX, LIGHTER_API_KEY_INDEX,
  LIGHTER_API_KEY_PRIVATE_KEY (or LIGHTER_API_SECRET).
- Signer binaries present under /tmp/lighter-python/lighter/signers (as per README).
- requests library available (installed with dev deps).

Usage:
    python examples/live/lighter/lighter_position_sanity.py
    python examples/live/lighter/lighter_position_sanity.py --testnet
    python examples/live/lighter/lighter_position_sanity.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from decimal import Decimal

import requests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from nautilus_trader.adapters.lighter.constants import LIGHTER_MAINNET_HTTP_BASE  # noqa: E402
from nautilus_trader.adapters.lighter.constants import LIGHTER_TESTNET_HTTP_BASE  # noqa: E402
from nautilus_trader.adapters.lighter.signer import LighterSigner  # noqa: E402


# Market symbols by market_id
MARKET_SYMBOLS = {
    0: "ETH",
    1: "BTC",
}


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging with appropriate format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def env(name: str, default: str | None = None) -> str:
    """Get environment variable or raise if required."""
    value = os.getenv(name, default)
    if value is None:
        raise SystemExit(f"Missing required env var {name}")
    return value


def format_usd(value: str | Decimal | None) -> str:
    """Format a value as USD."""
    if value is None:
        return "$0.00"
    try:
        return f"${Decimal(str(value)):,.6f}"
    except Exception:
        return f"${value}"


def get_position_side(sign: int, position_value: str | None) -> str:
    """Determine position side from sign and value."""
    if position_value is None:
        return "FLAT"
    try:
        pos = Decimal(str(position_value))
        if pos == 0:
            return "FLAT"
        elif sign >= 0:
            return "LONG"
        else:
            return "SHORT"
    except Exception:
        return "UNKNOWN"


def fetch_account(base_url: str, account_index: int, auth_token: str) -> dict:
    """Fetch account data by index."""
    resp = requests.get(
        f"{base_url}/api/v1/account",
        params={"by": "index", "value": account_index},
        headers={"Authorization": f"Bearer {auth_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_order_books(base_url: str) -> list[dict]:
    """Fetch all order book details to get market info."""
    resp = requests.get(
        f"{base_url}/api/v1/orderBooks",
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    # Handle both wrapped and flat response formats
    if isinstance(data, list):
        return data
    return data.get("order_books", data.get("orderBooks", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Lighter account/position sanity check.")
    parser.add_argument("--testnet", action="store_true", help="Use testnet endpoints")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    logger = setup_logging(args.verbose)

    # Determine base URL
    base_http = os.getenv(
        "LIGHTER_HTTP_BASE",
        LIGHTER_TESTNET_HTTP_BASE if args.testnet else LIGHTER_MAINNET_HTTP_BASE,
    ).rstrip("/")

    network = "testnet" if args.testnet else "mainnet"
    chain_id = 300 if args.testnet else 304

    # Get credentials
    account_index = int(env("LIGHTER_ACCOUNT_INDEX"))
    api_key_index = int(env("LIGHTER_API_KEY_INDEX", "2"))
    api_key = env("LIGHTER_API_KEY_PRIVATE_KEY", os.getenv("LIGHTER_API_SECRET", "")).removeprefix("0x")
    if not api_key:
        raise SystemExit("LIGHTER_API_KEY_PRIVATE_KEY (or LIGHTER_API_SECRET) must be set")

    print("\n" + "=" * 60)
    print("  Lighter Position Sanity Check (PR4)")
    print("=" * 60)
    print(f"  Network:       {network}")
    print(f"  Base URL:      {base_http}")
    print(f"  Account Index: {account_index}")
    print(f"  API Key Index: {api_key_index}")
    print("=" * 60 + "\n")

    # Initialize signer for auth token
    logger.info("Initializing signer...")
    signer_base = base_http.removesuffix("/api/v1")
    signer = LighterSigner(
        base_url=signer_base,
        account_index=account_index,
        api_key_index=api_key_index,
        api_key_private=api_key,
        chain_id=chain_id,
    )

    # Get auth token
    logger.info("Generating auth token...")
    auth_token = signer.auth_token()
    logger.debug(f"Auth token: {auth_token[:20]}...")

    # Fetch order books for market info
    logger.info("Fetching order book details...")
    try:
        order_books = fetch_order_books(base_http)
        market_info = {
            ob.get("market_index", ob.get("marketIndex", ob.get("market_id", i))): {
                "symbol": ob.get("symbol", ob.get("base_token", f"MARKET_{i}")),
                "last_price": ob.get("last_trade_price"),
            }
            for i, ob in enumerate(order_books)
        }
        logger.debug(f"Found {len(order_books)} markets")
    except Exception as e:
        logger.warning(f"Could not fetch order books: {e}")
        market_info = {}

    # Fetch account data
    logger.info("Fetching account data...")
    try:
        account_data = fetch_account(base_http, account_index, auth_token)
    except requests.exceptions.HTTPError as e:
        logger.error(f"Failed to fetch account: {e}")
        logger.error(f"Response: {e.response.text if e.response else 'N/A'}")
        return
    except Exception as e:
        logger.error(f"Failed to fetch account: {e}")
        return

    logger.debug(f"Account response: {account_data}")

    # Parse account info
    accounts = account_data.get("accounts", [])
    if not accounts:
        logger.warning("No accounts found in response")
        return

    account = accounts[0]

    # Display account details
    print("\n" + "-" * 40)
    print("  Account Details")
    print("-" * 40)
    print(f"  L1 Address:        {account.get('l1_address', 'N/A')}")
    print(f"  Status:            {'Active' if account.get('status') == 1 else 'Inactive'}")
    print(f"  Available Balance: {format_usd(account.get('available_balance'))}")
    print(f"  Collateral:        {format_usd(account.get('collateral'))}")
    print(f"  Total Asset Value: {format_usd(account.get('total_asset_value'))}")
    print(f"  Cross Asset Value: {format_usd(account.get('cross_asset_value'))}")
    print(f"  Total Order Count: {account.get('total_order_count', 0)}")
    print(f"  Pending Orders:    {account.get('pending_order_count', 0)}")

    # Display positions
    positions = account.get("positions", [])
    print("\n" + "-" * 40)
    print(f"  Positions ({len(positions)} markets)")
    print("-" * 40)

    if not positions:
        print("  No positions found")
    else:
        for pos in positions:
            market_id = pos.get("market_id")
            symbol = pos.get("symbol", market_info.get(market_id, {}).get("symbol", f"MARKET_{market_id}"))
            sign = pos.get("sign", 0)
            position_size = pos.get("position", "0")
            side = get_position_side(sign, position_size)

            print(f"\n  {symbol} (market_id={market_id}):")
            print(f"    Position:         {position_size} ({side})")
            print(f"    Entry Price:      {format_usd(pos.get('avg_entry_price'))}")
            print(f"    Position Value:   {format_usd(pos.get('position_value'))}")
            print(f"    Unrealized P&L:   {format_usd(pos.get('unrealized_pnl'))}")
            print(f"    Realized P&L:     {format_usd(pos.get('realized_pnl'))}")
            print(f"    Liquidation:      {format_usd(pos.get('liquidation_price'))}")
            print(f"    Open Orders:      {pos.get('open_order_count', 0)}")
            margin_mode = "Isolated" if pos.get("margin_mode") == 1 else "Cross"
            print(f"    Margin Mode:      {margin_mode}")

    print("\n" + "=" * 60)
    print("  Done - PR4 Account/Position fetch successful!")
    print("=" * 60 + "\n")

    logger.info("Sanity check completed successfully")


if __name__ == "__main__":
    main()
