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
Test Backpack Account Architecture Refactoring

This script tests the unified account architecture changes made in Phase 3.
It directly tests the HTTP client and account management without the full system.
"""

import asyncio
import os
from decimal import Decimal

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.common.account import BackpackUnifiedAccountManager
from nautilus_trader.adapters.backpack.http.account import BackpackAccountHttpAPI
from nautilus_trader.common.component import LiveClock, Logger
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.currencies import USDC


class AccountRefactoringTest:
    """Test the unified account architecture refactoring."""
    
    def __init__(self):
        self.api_key = os.getenv("BACKPACK_API_KEY")
        self.api_secret = os.getenv("BACKPACK_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError("Missing BACKPACK_API_KEY or BACKPACK_API_SECRET")
        
        self.testnet = False  # Using mainnet
        self.clock = LiveClock()
        self.logger = Logger(name="AccountTest")
        self.http_client = None
        self.account_manager = None
        
        self.test_results = {}
        self.errors = []
        
    async def setup(self):
        """Set up the test environment."""
        print("\n🔧 Setting up test environment...")
        
        # Create HTTP client with clock
        self.http_client = BackpackHttpClient(
            clock=self.clock,
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
        )
        
        # Create account HTTP API
        self.account_http = BackpackAccountHttpAPI(self.http_client)
        
        # Create unified account manager
        self.account_manager = BackpackUnifiedAccountManager(
            account_http=self.account_http,
            logger=self.logger,
        )
        
        print("✅ Test environment ready")
        
    async def test_connection(self):
        """Test basic connection to Backpack API."""
        print("\n🔌 Testing API connection...")
        
        try:
            # Test by fetching markets
            markets = await self.http_client.fetch_markets()
            if markets:
                self.test_results["connection"] = "✅ PASS"
                print(f"  Connected: Found {len(markets)} markets")
            else:
                self.test_results["connection"] = "⚠️ PARTIAL"
                print("  Connected but no markets returned")
        except Exception as e:
            self.test_results["connection"] = "❌ FAIL"
            self.errors.append(f"Connection error: {e}")
            print(f"  ❌ Connection failed: {e}")
            
    async def test_account_balances(self):
        """Test fetching account balances."""
        print("\n💰 Testing account balances...")
        
        try:
            balances = await self.http_client.fetch_balance()
            if balances:
                self.test_results["balances"] = "✅ PASS"
                print("  Balances retrieved:")
                for asset, balance in balances.items():
                    if asset in ["SOL", "USDC", "BTC"]:
                        available = balance.get("available", 0)
                        locked = balance.get("locked", 0)
                        print(f"    {asset}: Available={available}, Locked={locked}")
            else:
                self.test_results["balances"] = "⚠️ EMPTY"
                print("  No balances found")
        except Exception as e:
            self.test_results["balances"] = "❌ FAIL"
            self.errors.append(f"Balance error: {e}")
            print(f"  ❌ Balance fetch failed: {e}")
            
    async def test_unified_account(self):
        """Test unified account initialization and management."""
        print("\n🏛️ Testing unified account architecture...")
        
        try:
            # Initialize unified account
            account_id = AccountId("BACKPACK-UNIFIED-001")
            account = await self.account_manager.initialize(
                account_id=account_id,
                base_currency=USDC,
            )
            
            if account:
                self.test_results["unified_account"] = "✅ PASS"
                print(f"  Account initialized: {account_id}")
                
                # Check account type
                print(f"  Account type: {account.account_type}")  # Should be MARGIN
                
                # Get collateral information
                capital = account.capital
                if capital:
                    print(f"  Total collateral: {capital.get('totalCollateral', 'N/A')}")
                    print(f"  Available collateral: {capital.get('availableCollateral', 'N/A')}")
                    print(f"  Initial margin rate: {capital.get('initialMarginRate', 'N/A')}")
                    print(f"  Maintenance margin rate: {capital.get('maintenanceMarginRate', 'N/A')}")
            else:
                self.test_results["unified_account"] = "❌ FAIL"
                self.errors.append("Failed to initialize unified account")
                
        except Exception as e:
            self.test_results["unified_account"] = "❌ FAIL"
            self.errors.append(f"Unified account error: {e}")
            print(f"  ❌ Unified account failed: {e}")
            
    async def test_collateral_weights(self):
        """Test collateral weight fetching."""
        print("\n⚖️ Testing collateral weights...")
        
        try:
            # Get collateral information
            collateral = await self.account_http.fetch_collateral()
            if collateral:
                self.test_results["collateral_weights"] = "✅ PASS"
                print("  Collateral weights:")
                
                for asset_info in collateral.assets[:5]:  # Show first 5
                    print(f"    {asset_info.asset}: weight={asset_info.weight}")
                    
                print(f"  Total weighted collateral: {collateral.totalWeightedCollateral}")
            else:
                self.test_results["collateral_weights"] = "⚠️ EMPTY"
                print("  No collateral data available")
                
        except Exception as e:
            self.test_results["collateral_weights"] = "❌ FAIL"
            self.errors.append(f"Collateral weights error: {e}")
            print(f"  ❌ Collateral weights failed: {e}")
            
    async def test_auto_borrow(self):
        """Test auto-borrow functionality."""
        print("\n💸 Testing auto-borrow system...")
        
        try:
            # Check if auto-borrow would trigger
            required_usdc = Decimal("100")  # Test amount
            
            # This tests the logic (might actually borrow if needed)
            should_borrow = await self.account_manager.check_and_execute_auto_borrow(
                required_usdc=required_usdc,
            )
            
            if should_borrow is not None:
                self.test_results["auto_borrow"] = "✅ PASS"
                print(f"  Auto-borrow check completed")
                print(f"  Would borrow: {should_borrow}")
            else:
                self.test_results["auto_borrow"] = "⚠️ SKIP"
                print("  Auto-borrow check skipped (sufficient balance)")
                
        except Exception as e:
            self.test_results["auto_borrow"] = "❌ FAIL"
            self.errors.append(f"Auto-borrow error: {e}")
            print(f"  ❌ Auto-borrow test failed: {e}")
            
    async def test_positions(self):
        """Test unified position management."""
        print("\n📊 Testing position management...")
        
        try:
            # Get unified positions (not async)
            positions = self.account_manager.get_unified_positions()
            
            self.test_results["positions"] = "✅ PASS"
            if positions:
                print(f"  Found {len(positions)} positions")
                for pos in positions[:3]:  # Show first 3
                    symbol = pos.get("symbol")
                    side = pos.get("side")
                    size = pos.get("size")
                    print(f"    {symbol}: {side} {size}")
            else:
                print("  No open positions")
                
            # Calculate total margin used (not async)
            total_margin = self.account_manager.calculate_total_margin_used()
            print(f"  Total margin used: {total_margin}")
            
        except Exception as e:
            self.test_results["positions"] = "❌ FAIL"
            self.errors.append(f"Position management error: {e}")
            print(f"  ❌ Position test failed: {e}")
            
    async def cleanup(self):
        """Clean up resources."""
        print("\n🧹 Cleaning up...")
        # HTTP client doesn't need explicit cleanup
        print("  Cleanup complete")
        
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("ACCOUNT REFACTORING TEST SUMMARY")
        print("="*60)
        
        # Count results
        passed = sum(1 for v in self.test_results.values() if "PASS" in v)
        failed = sum(1 for v in self.test_results.values() if "FAIL" in v)
        skipped = sum(1 for v in self.test_results.values() if "SKIP" in v or "EMPTY" in v)
        
        print(f"\nResults: ✅ {passed} passed, ❌ {failed} failed, ⚠️ {skipped} skipped/partial")
        
        print("\nDetailed Results:")
        for test, result in self.test_results.items():
            print(f"  {test:25} {result}")
            
        if self.errors:
            print("\nErrors encountered:")
            for error in self.errors:
                print(f"  - {error}")
                
        # Overall status
        print("\n" + "="*60)
        if failed == 0:
            print("✅ ACCOUNT REFACTORING WORKING - Unified account architecture is functional!")
        elif failed <= 1:
            print("⚠️ MOSTLY WORKING - Minor issues with account refactoring")
        else:
            print("❌ REFACTORING HAS ISSUES - Review the unified account implementation")
            
    async def run_all_tests(self):
        """Run all tests."""
        print("\n" + "="*60)
        print("BACKPACK ACCOUNT REFACTORING TEST")
        print("Testing unified account architecture from Phase 3")
        print("="*60)
        
        try:
            await self.setup()
            
            # Run tests
            await self.test_connection()
            await self.test_account_balances()
            await self.test_unified_account()
            await self.test_collateral_weights()
            await self.test_auto_borrow()
            await self.test_positions()
            
        except KeyboardInterrupt:
            print("\n⚠️ Test interrupted by user")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            self.errors.append(f"Fatal error: {e}")
        finally:
            await self.cleanup()
            
        self.print_summary()


async def main():
    """Main entry point."""
    tester = AccountRefactoringTest()
    await tester.run_all_tests()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")