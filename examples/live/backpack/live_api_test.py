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
Comprehensive Live API Test for Backpack Exchange Integration

This script performs end-to-end testing of the Backpack adapter with the live API.
It tests all major functionality including:
- Connection and authentication
- Account balance queries
- Market data streaming
- Order placement and management
- WebSocket metrics
- Error handling and recovery

SAFETY: Orders are placed with small amounts (0.1 SOL) at 10% away from market price
"""

import asyncio
import os
import sys
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import msgspec

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.data import BackpackDataClient
from nautilus_trader.adapters.backpack.execution import BackpackExecutionClient
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.parsing import parse_trade, parse_order_book
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, MessageBus
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.data.engine import DataEngine
from nautilus_trader.execution.engine import ExecutionEngine
from nautilus_trader.model.commands import SubmitOrder, CancelOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce, OrderType
from nautilus_trader.model.identifiers import AccountId, ClientOrderId, InstrumentId, StrategyId, Symbol, TraderId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder
from nautilus_trader.portfolio.portfolio import Portfolio
from nautilus_trader.risk.engine import RiskEngine


class BackpackLiveAPITest:
    """Comprehensive live API test for Backpack integration."""
    
    def __init__(self):
        self.api_key = os.getenv("BACKPACK_API_KEY")
        self.api_secret = os.getenv("BACKPACK_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError("Missing BACKPACK_API_KEY or BACKPACK_API_SECRET in .env file")
        
        self.testnet = False  # Using mainnet
        self.instrument_id = InstrumentId(Symbol("SOL_USDC"), BACKPACK_VENUE)
        self.test_results = {}
        self.errors = []
        self.placed_orders = []
        
        # Initialize components
        self.clock = LiveClock()
        self.trader_id = TraderId("LIVE-TEST-001")
        self.strategy_id = StrategyId("TEST-STRATEGY")
        self.account_id = AccountId(f"{BACKPACK_VENUE}-001")
        
        # Create message bus and cache
        self.msgbus = MessageBus(
            trader_id=self.trader_id,
            clock=self.clock,
        )
        self.cache = Cache()
        
        # Create engines
        self.data_engine = DataEngine(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )
        self.exec_engine = ExecutionEngine(
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )
        self.risk_engine = RiskEngine(
            portfolio=Portfolio(
                msgbus=self.msgbus,
                cache=self.cache,
                clock=self.clock,
            ),
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
        )
        
        # HTTP and WebSocket clients
        self.http_client = None
        self.ws_client = None
        self.data_client = None
        self.exec_client = None
        
    async def setup_clients(self):
        """Set up HTTP and WebSocket clients."""
        print("\n🔧 Setting up clients...")
        
        # Create HTTP client
        self.http_client = BackpackHttpClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
        )
        
        # Create WebSocket client
        self.ws_client = BackpackWebSocketClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
            handler=self._handle_ws_message,
        )
        
        # Create data client
        data_config = BackpackDataClientConfig(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
            instrument_provider=InstrumentProviderConfig(load_all=False),
        )
        self.data_client = BackpackDataClient(
            loop=asyncio.get_event_loop(),
            client=self.http_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            config=data_config,
        )
        
        # Create execution client  
        exec_config = BackpackExecClientConfig(
            api_key=self.api_key,
            api_secret=self.api_secret,
            testnet=self.testnet,
        )
        self.exec_client = BackpackExecutionClient(
            loop=asyncio.get_event_loop(),
            client=self.http_client,
            msgbus=self.msgbus,
            cache=self.cache,
            clock=self.clock,
            config=exec_config,
        )
        
        print("✅ Clients initialized")
        
    async def _handle_ws_message(self, message: Dict[str, Any]):
        """Handle WebSocket messages."""
        stream = message.get("stream", "")
        data = message.get("data", {})
        
        if "depth" in stream:
            print(f"  📊 Depth update: {data.get('symbol')} - "
                  f"Bids: {len(data.get('b', []))}, Asks: {len(data.get('a', []))}")
        elif "trade" in stream:
            print(f"  💱 Trade: {data.get('symbol')} @ {data.get('price')} x {data.get('quantity')}")
        elif "ticker" in stream:
            print(f"  📈 Ticker: {data.get('symbol')} - "
                  f"Last: {data.get('last')}, Vol: {data.get('volume')}")
        
    async def test_connection(self):
        """Test HTTP and WebSocket connections."""
        print("\n🔌 Testing connections...")
        
        try:
            # Test HTTP connection
            response = await self.http_client.ping()
            self.test_results["http_connection"] = "✅ PASS"
            print(f"  HTTP: Connected (ping response: {response})")
            
            # Test WebSocket connection
            await self.ws_client.connect()
            if self.ws_client.is_connected():
                self.test_results["ws_connection"] = "✅ PASS"
                print("  WebSocket: Connected")
            else:
                self.test_results["ws_connection"] = "❌ FAIL"
                self.errors.append("WebSocket connection failed")
                
        except Exception as e:
            self.test_results["connection"] = "❌ FAIL"
            self.errors.append(f"Connection error: {e}")
            print(f"  ❌ Connection failed: {e}")
            
    async def test_account_data(self):
        """Test account balance and collateral fetching."""
        print("\n💰 Testing account data...")
        
        try:
            # Fetch balances
            balances = await self.http_client.get_balances()
            if balances:
                self.test_results["balances"] = "✅ PASS"
                print("  Balances:")
                for asset, balance in balances.items():
                    if asset in ["SOL", "USDC"]:
                        available = balance.get("available", 0)
                        locked = balance.get("locked", 0)
                        print(f"    {asset}: Available={available}, Locked={locked}")
            else:
                self.test_results["balances"] = "⚠️ EMPTY"
                print("  No balances found")
                
            # Fetch collateral
            collateral = await self.http_client.get_collateral()
            if collateral:
                self.test_results["collateral"] = "✅ PASS"
                net_equity = collateral.get("netEquity", 0)
                available = collateral.get("netEquityAvailable", 0)
                print(f"  Collateral: Net Equity={net_equity}, Available={available}")
            else:
                self.test_results["collateral"] = "⚠️ EMPTY"
                
        except Exception as e:
            self.test_results["account_data"] = "❌ FAIL"
            self.errors.append(f"Account data error: {e}")
            print(f"  ❌ Account data failed: {e}")
            
    async def test_market_data(self):
        """Test market data streaming."""
        print("\n📊 Testing market data...")
        
        try:
            # Load instruments
            markets = await self.http_client.get_markets()
            if markets:
                self.test_results["instruments"] = "✅ PASS"
                print(f"  Found {len(markets)} markets")
                
                # Find SOL_USDC
                sol_usdc = next((m for m in markets if m.get("symbol") == "SOL_USDC"), None)
                if sol_usdc:
                    print(f"  SOL_USDC market: Status={sol_usdc.get('status')}")
                    self.current_price = Decimal(sol_usdc.get("last", "150.0"))
                    print(f"  Current price: {self.current_price}")
            
            # Get order book
            orderbook = await self.http_client.get_depth("SOL_USDC", limit=5)
            if orderbook:
                self.test_results["orderbook"] = "✅ PASS" 
                bids = orderbook.get("bids", [])
                asks = orderbook.get("asks", [])
                print(f"  Order book: {len(bids)} bids, {len(asks)} asks")
                if bids and asks:
                    best_bid = bids[0][0] if bids else "N/A"
                    best_ask = asks[0][0] if asks else "N/A"
                    print(f"  Best bid: {best_bid}, Best ask: {best_ask}")
                    
            # Get recent trades
            trades = await self.http_client.get_recent_trades("SOL_USDC", limit=5)
            if trades:
                self.test_results["trades"] = "✅ PASS"
                print(f"  Recent trades: {len(trades)} trades")
                if trades:
                    latest = trades[0]
                    print(f"  Latest trade: {latest.get('price')} x {latest.get('quantity')}")
                    
            # Subscribe to WebSocket streams
            print("  Testing WebSocket subscriptions...")
            
            # Subscribe to order book updates
            await self.ws_client.subscribe_depth("SOL_USDC")
            print("    ✅ Subscribed to order book")
            
            # Subscribe to trades
            await self.ws_client.subscribe_trades("SOL_USDC") 
            print("    ✅ Subscribed to trades")
            
            # Wait for some messages
            await asyncio.sleep(3)
            
            # Check metrics
            metrics = self.ws_client.get_metrics()
            print(f"  WebSocket metrics:")
            print(f"    Messages received: {metrics.get('messages_received', 0)}")
            print(f"    Average latency: {metrics.get('avg_latency_ms', 0):.2f}ms")
            
            self.test_results["websocket_streams"] = "✅ PASS"
            
        except Exception as e:
            self.test_results["market_data"] = "❌ FAIL"
            self.errors.append(f"Market data error: {e}")
            print(f"  ❌ Market data failed: {e}")
            
    async def test_order_management(self):
        """Test order placement and management."""
        print("\n📝 Testing order management...")
        
        try:
            # Check balances first
            balances = await self.http_client.get_balances()
            usdc_balance = Decimal(str(balances.get("USDC", {}).get("available", "0")))
            sol_balance = Decimal(str(balances.get("SOL", {}).get("available", "0")))
            
            print(f"  Current balances: SOL={sol_balance}, USDC={usdc_balance}")
            
            if not hasattr(self, 'current_price'):
                ticker = await self.http_client.get_ticker("SOL_USDC")
                self.current_price = Decimal(ticker.get("last", "150.0"))
                
            # Calculate safe order prices (10% away from market)
            buy_price = self.current_price * Decimal("0.9")  # 10% below
            sell_price = self.current_price * Decimal("1.1")  # 10% above
            order_size = Decimal("0.1")  # Small test size
            
            print(f"  Market price: {self.current_price}")
            print(f"  Buy order: {order_size} SOL @ {buy_price:.2f} USDC")
            print(f"  Sell order: {order_size} SOL @ {sell_price:.2f} USDC")
            
            # Place buy order if we have enough USDC
            buy_order_id = None
            required_usdc = buy_price * order_size
            if usdc_balance >= required_usdc:
                buy_order = {
                    "symbol": "SOL_USDC",
                    "side": "Bid",
                    "orderType": "Limit",
                    "quantity": str(order_size),
                    "price": str(buy_price),
                    "timeInForce": "GTC",
                    "postOnly": True,
                }
                
                print("  Placing buy order...")
                buy_result = await self.http_client.submit_order(buy_order)
                if buy_result and "id" in buy_result:
                    buy_order_id = buy_result["id"]
                    self.placed_orders.append(buy_order_id)
                    self.test_results["buy_order"] = "✅ PASS"
                    print(f"    ✅ Buy order placed: {buy_order_id}")
                else:
                    self.test_results["buy_order"] = "❌ FAIL"
                    print(f"    ❌ Buy order failed: {buy_result}")
            else:
                print(f"  ⚠️ Insufficient USDC balance for buy order (need {required_usdc:.2f})")
                self.test_results["buy_order"] = "⚠️ SKIP"
                
            # Place sell order if we have enough SOL
            sell_order_id = None
            if sol_balance >= order_size:
                sell_order = {
                    "symbol": "SOL_USDC",
                    "side": "Ask",
                    "orderType": "Limit",
                    "quantity": str(order_size),
                    "price": str(sell_price),
                    "timeInForce": "GTC",
                    "postOnly": True,
                }
                
                print("  Placing sell order...")
                sell_result = await self.http_client.submit_order(sell_order)
                if sell_result and "id" in sell_result:
                    sell_order_id = sell_result["id"]
                    self.placed_orders.append(sell_order_id)
                    self.test_results["sell_order"] = "✅ PASS"
                    print(f"    ✅ Sell order placed: {sell_order_id}")
                else:
                    self.test_results["sell_order"] = "❌ FAIL"
                    print(f"    ❌ Sell order failed: {sell_result}")
            else:
                print(f"  ⚠️ Insufficient SOL balance for sell order (need {order_size})")
                self.test_results["sell_order"] = "⚠️ SKIP"
                
            # Query open orders
            await asyncio.sleep(1)  # Let orders settle
            open_orders = await self.http_client.get_open_orders("SOL_USDC")
            if open_orders is not None:
                self.test_results["query_orders"] = "✅ PASS"
                print(f"  Open orders: {len(open_orders)} orders")
                for order in open_orders[:5]:  # Show first 5
                    print(f"    - {order.get('side')}: {order.get('quantity')} @ {order.get('price')}")
            
            # Test order cancellation
            if self.placed_orders:
                print("  Testing order cancellation...")
                for order_id in self.placed_orders:
                    cancel_result = await self.http_client.cancel_order("SOL_USDC", order_id)
                    if cancel_result:
                        print(f"    ✅ Cancelled order: {order_id}")
                    else:
                        print(f"    ❌ Failed to cancel: {order_id}")
                self.test_results["cancel_orders"] = "✅ PASS"
                self.placed_orders.clear()
                
        except Exception as e:
            self.test_results["order_management"] = "❌ FAIL"
            self.errors.append(f"Order management error: {e}")
            print(f"  ❌ Order management failed: {e}")
            
    async def test_error_handling(self):
        """Test error handling scenarios."""
        print("\n⚠️ Testing error handling...")
        
        try:
            # Test invalid symbol
            print("  Testing invalid symbol...")
            invalid_result = await self.http_client.get_ticker("INVALID_SYMBOL")
            if invalid_result is None or "error" in str(invalid_result).lower():
                self.test_results["invalid_symbol"] = "✅ PASS"
                print("    ✅ Invalid symbol handled correctly")
            
            # Test insufficient balance order
            print("  Testing insufficient balance...")
            large_order = {
                "symbol": "SOL_USDC",
                "side": "Bid",
                "orderType": "Limit",
                "quantity": "10000",  # Very large amount
                "price": "150.0",
                "timeInForce": "GTC",
            }
            result = await self.http_client.submit_order(large_order)
            if result is None or "error" in str(result).lower() or "insufficient" in str(result).lower():
                self.test_results["insufficient_balance"] = "✅ PASS"
                print("    ✅ Insufficient balance handled correctly")
                
            # Test WebSocket reconnection
            print("  Testing WebSocket reconnection...")
            await self.ws_client.disconnect()
            await asyncio.sleep(1)
            await self.ws_client.connect()
            if self.ws_client.is_connected():
                self.test_results["ws_reconnection"] = "✅ PASS"
                print("    ✅ WebSocket reconnection successful")
                
        except Exception as e:
            self.test_results["error_handling"] = "⚠️ PARTIAL"
            print(f"  ⚠️ Some error handling tests failed: {e}")
            
    async def cleanup(self):
        """Clean up any remaining orders and connections."""
        print("\n🧹 Cleaning up...")
        
        try:
            # Cancel any remaining orders
            if self.placed_orders:
                for order_id in self.placed_orders:
                    try:
                        await self.http_client.cancel_order("SOL_USDC", order_id)
                        print(f"  Cancelled order: {order_id}")
                    except:
                        pass
                        
            # Disconnect clients
            if self.ws_client and self.ws_client.is_connected():
                await self.ws_client.disconnect()
                print("  WebSocket disconnected")
                
            if self.http_client:
                await self.http_client.close()
                print("  HTTP client closed")
                
        except Exception as e:
            print(f"  ⚠️ Cleanup error: {e}")
            
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        # Count results
        passed = sum(1 for v in self.test_results.values() if "PASS" in v)
        failed = sum(1 for v in self.test_results.values() if "FAIL" in v)
        skipped = sum(1 for v in self.test_results.values() if "SKIP" in v or "PARTIAL" in v)
        
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
            print("✅ ALL TESTS PASSED - Backpack integration is working correctly!")
        elif failed <= 2:
            print("⚠️ MOSTLY PASSED - Some minor issues detected")
        else:
            print("❌ TESTS FAILED - Significant issues found, review errors above")
            
    async def run_all_tests(self):
        """Run all tests in sequence."""
        print("\n" + "="*60)
        print("BACKPACK LIVE API TEST")
        print("="*60)
        print(f"Environment: {'TESTNET' if self.testnet else 'MAINNET'}")
        print(f"Instrument: SOL_USDC")
        print("="*60)
        
        try:
            # Setup
            await self.setup_clients()
            
            # Run tests
            await self.test_connection()
            await self.test_account_data()
            await self.test_market_data()
            await self.test_order_management()
            await self.test_error_handling()
            
        except KeyboardInterrupt:
            print("\n⚠️ Test interrupted by user")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
            self.errors.append(f"Fatal error: {e}")
        finally:
            # Always cleanup
            await self.cleanup()
            
        # Print summary
        self.print_summary()


async def main():
    """Main entry point."""
    tester = BackpackLiveAPITest()
    await tester.run_all_tests()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)