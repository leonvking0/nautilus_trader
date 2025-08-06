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
Update mock test data with real API responses captured from Backpack Exchange.

This script updates the test fixtures to match the current API response format,
ensuring tests validate against accurate data structures.
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def update_mock_data():
    """Update mock test data with real API responses."""
    print("="*60)
    print("UPDATING MOCK DATA WITH REAL API RESPONSES")
    print("="*60)
    
    # Directories
    real_dir = Path("tests/integration_tests/adapters/backpack/resources/real_responses")
    mock_dir = Path("tests/integration_tests/adapters/backpack/resources/http_responses")
    
    # Backup existing mock data
    backup_dir = mock_dir.parent / f"http_responses_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n📦 Backing up existing mock data to: {backup_dir}")
    shutil.copytree(mock_dir, backup_dir)
    
    # Files to update
    files_to_update = [
        "markets.json",
        "ticker.json",
        "tickers.json",
        "orderbook.json",
        "trades.json",
        "balance.json",
        "orders.json",
    ]
    
    print("\n🔄 Updating mock data files...")
    
    for filename in files_to_update:
        real_file = real_dir / filename
        mock_file = mock_dir / filename
        
        if not real_file.exists():
            print(f"  ⚠️ {filename}: No real data captured, skipping")
            continue
        
        # Load real data
        with open(real_file) as f:
            real_data = json.load(f)
        
        # Extract the actual data (remove metadata wrapper)
        if "data" in real_data:
            actual_data = real_data["data"]
        else:
            actual_data = real_data
        
        # Handle special cases for test data
        if filename == "markets.json":
            # Keep only first 3 markets for test size
            if isinstance(actual_data, list):
                actual_data = actual_data[:3]
        
        elif filename == "tickers.json":
            # Convert dict to list format if needed
            if isinstance(actual_data, dict):
                # Take first 5 tickers
                actual_data = [
                    {"symbol": symbol, **data}
                    for symbol, data in list(actual_data.items())[:5]
                ]
        
        elif filename == "trades.json":
            # Limit to 10 trades
            if isinstance(actual_data, list):
                actual_data = actual_data[:10]
        
        elif filename == "orders.json":
            # Sanitize order IDs
            if isinstance(actual_data, list):
                for i, order in enumerate(actual_data):
                    order["id"] = f"TEST_ORDER_{i+1}"
                    if "clientId" in order:
                        order["clientId"] = f"CLIENT_{i+1}"
        
        # Save updated mock data
        with open(mock_file, "w") as f:
            json.dump(actual_data, f, indent=2)
        
        print(f"  ✅ {filename}: Updated with real API structure")
    
    # Also need to handle special cases that weren't captured
    print("\n📝 Creating missing mock files...")
    
    # Order response (single order)
    order_file = mock_dir / "order.json"
    if not (real_dir / "order.json").exists():
        # Use first order from orders.json as template
        orders_file = mock_dir / "orders.json"
        if orders_file.exists():
            with open(orders_file) as f:
                orders = json.load(f)
            if orders and isinstance(orders, list):
                single_order = orders[0] if orders else {
                    "id": "TEST_ORDER_1",
                    "clientId": "CLIENT_1",
                    "symbol": "SOL_USDC",
                    "side": "Bid",
                    "orderType": "Limit",
                    "timeInForce": "GTC",
                    "quantity": "1.0",
                    "price": "150.00",
                    "status": "New",
                    "createdAt": 1234567890000,
                    "updatedAt": 1234567890000,
                }
                with open(order_file, "w") as f:
                    json.dump(single_order, f, indent=2)
                print(f"  ✅ order.json: Created from orders template")
    
    # Order history
    history_file = mock_dir / "order_history.json"
    if not (real_dir / "order_history.json").exists():
        # Create sample history
        history = []
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)
        print(f"  ✅ order_history.json: Created empty template")
    
    # Klines
    klines_file = mock_dir / "klines.json"
    if not (real_dir / "klines.json").exists():
        # Create sample klines data
        klines = [
            [1234567890000, "150.00", "155.00", "145.00", "152.00", "1000.0"],
            [1234567950000, "152.00", "157.00", "150.00", "156.00", "1200.0"],
            [1234568010000, "156.00", "158.00", "153.00", "154.00", "900.0"],
        ]
        with open(klines_file, "w") as f:
            json.dump(klines, f, indent=2)
        print(f"  ✅ klines.json: Created sample template")
    
    print("\n📊 Summary:")
    print(f"  - Backed up original mock data to: {backup_dir}")
    print(f"  - Updated {len(files_to_update)} mock files with real API structure")
    print(f"  - Created missing template files")
    
    print("\n✅ Mock data update complete!")
    print("\n⚠️ IMPORTANT: Review the updated files and run tests to ensure compatibility")


if __name__ == "__main__":
    update_mock_data()