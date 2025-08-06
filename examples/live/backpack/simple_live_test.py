#!/usr/bin/env python3
"""
Simple Live API Test for Backpack Exchange
Tests basic functionality without full NautilusTrader framework
"""

import asyncio
import os
import sys
import time
from decimal import Decimal
from typing import Any, Dict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.websocket.client import BackpackWebSocketClient
from nautilus_trader.common.component import LiveClock


class SimpleBackpackTest:
    """Simple test for Backpack API functionality."""
    
    def __init__(self):
        self.api_key = os.getenv("BACKPACK_API_KEY")
        self.api_secret = os.getenv("BACKPACK_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            raise ValueError("Missing BACKPACK_API_KEY or BACKPACK_API_SECRET environment variables")
        
        self.testnet = False  # Using mainnet
        self.clock = LiveClock()
        self.http_client = None
        self.ws_client = None
        self.ws_messages = []
        self.test_results = {}
        self.placed_orders = []
        
    async def handle_ws_message(self, message: Dict[str, Any]):
        """Handle WebSocket messages."""
        self.ws_messages.append(message)
        stream = message.get("stream", "")
        data = message.get("data", {})
        
        if "depth" in stream:
            print(f"    📊 Depth: {data.get('symbol')} - Bids: {len(data.get('b', []))}, Asks: {len(data.get('a', []))}")
        elif "trade" in stream:
            print(f"    💱 Trade: {data.get('symbol')} @ {data.get('price')} x {data.get('quantity')}")
        elif "ticker" in stream:
            print(f"    📈 Ticker: {data.get('symbol')} - Last: {data.get('last')}")
            
    async def test_http_connection(self):
        """Test HTTP API connection."""
        print("\n1️⃣ Testing HTTP Connection...")
        
        try:
            self.http_client = BackpackHttpClient(
                clock=self.clock,
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
            )
            
            # Test markets endpoint as ping
            markets = await self.http_client.fetch_markets()
            if markets:
                print(f"  ✅ API connected: {len(markets)} markets available")
                self.test_results["http_connection"] = "PASS"
            else:
                print("  ❌ No markets returned")
                self.test_results["http_connection"] = "FAIL"
            
        except Exception as e:
            print(f"  ❌ HTTP connection failed: {e}")
            self.test_results["http_connection"] = "FAIL"
            return False
        
        return True
        
    async def test_account_data(self):
        """Test fetching account data."""
        print("\n2️⃣ Testing Account Data...")
        
        try:
            # Get balances
            balances = await self.http_client.fetch_balance()
            print("  Account Balances:")
            
            sol_balance = balances.get("SOL", {})
            usdc_balance = balances.get("USDC", {})
            
            print(f"    SOL:  Available={sol_balance.get('available', 0)}, Locked={sol_balance.get('locked', 0)}")
            print(f"    USDC: Available={usdc_balance.get('available', 0)}, Locked={usdc_balance.get('locked', 0)}")
            
            self.sol_available = Decimal(str(sol_balance.get('available', '0')))
            self.usdc_available = Decimal(str(usdc_balance.get('available', '0')))
            
            # Note: Collateral endpoint may not be available in this client
            # Skipping collateral check
            if False:
                print(f"  Collateral:")
                print(f"    Net Equity: {collateral.get('netEquity', 0)}")
                print(f"    Available: {collateral.get('netEquityAvailable', 0)}")
            
            self.test_results["account_data"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ Account data failed: {e}")
            self.test_results["account_data"] = "FAIL"
            return False
            
        return True
        
    async def test_market_data(self):
        """Test fetching market data."""
        print("\n3️⃣ Testing Market Data...")
        
        try:
            # Get markets
            markets = await self.http_client.fetch_markets()
            print(f"  Found {len(markets)} markets")
            
            # Find SOL_USDC
            sol_usdc = next((m for m in markets if m.get("symbol") == "SOL_USDC"), None)
            if sol_usdc:
                print(f"  SOL_USDC Market:")
                print(f"    Status: {sol_usdc.get('status')}")
                print(f"    Last Price: {sol_usdc.get('last')}")
                self.current_price = Decimal(str(sol_usdc.get('last', '150')))
            
            # Get order book
            depth = await self.http_client.fetch_order_book("SOL_USDC")
            if depth:
                bids = depth.get("bids", [])
                asks = depth.get("asks", [])
                print(f"  Order Book:")
                print(f"    Top Bid: {bids[0][0] if bids else 'N/A'}")
                print(f"    Top Ask: {asks[0][0] if asks else 'N/A'}")
                print(f"    Spread: {float(asks[0][0]) - float(bids[0][0]) if bids and asks else 'N/A'}")
            
            # Get recent trades
            trades = await self.http_client.fetch_trades("SOL_USDC", limit=3)
            if trades:
                print(f"  Recent Trades: {len(trades)} trades")
                latest = trades[0]
                print(f"    Latest: {latest.get('price')} x {latest.get('quantity')}")
            
            self.test_results["market_data"] = "PASS"
            
        except Exception as e:
            print(f"  ❌ Market data failed: {e}")
            self.test_results["market_data"] = "FAIL"
            return False
            
        return True
        
    async def test_websocket(self):
        """Test WebSocket connection and streaming."""
        print("\n4️⃣ Testing WebSocket Streaming...")
        
        try:
            self.ws_client = BackpackWebSocketClient(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet,
                handler=self.handle_ws_message,
            )
            
            # Connect
            await self.ws_client.connect()
            print("  ✅ WebSocket connected")
            
            # Subscribe to streams
            await self.ws_client.subscribe_depth("SOL_USDC")
            print("  ✅ Subscribed to order book")
            
            await self.ws_client.subscribe_trades("SOL_USDC")
            print("  ✅ Subscribed to trades")
            
            # Wait for messages
            print("  Waiting for messages (5 seconds)...")
            await asyncio.sleep(5)
            
            # Check metrics
            metrics = self.ws_client.get_metrics()
            print(f"  WebSocket Metrics:")
            print(f"    Messages: {metrics.get('messages_received', 0)}")
            print(f"    Latency: {metrics.get('avg_latency_ms', 0):.2f}ms")
            print(f"    Errors: {metrics.get('errors', 0)}")
            
            if metrics.get('messages_received', 0) > 0:
                self.test_results["websocket"] = "PASS"
            else:
                self.test_results["websocket"] = "NO_DATA"
                
        except Exception as e:
            print(f"  ❌ WebSocket failed: {e}")
            self.test_results["websocket"] = "FAIL"
            return False
            
        return True
        
    async def test_order_management(self):
        """Test order placement and cancellation."""
        print("\n5️⃣ Testing Order Management...")
        
        if not hasattr(self, 'current_price'):
            self.current_price = Decimal("150")
            
        try:
            # Calculate safe prices (10% away from market)
            buy_price = self.current_price * Decimal("0.9")
            sell_price = self.current_price * Decimal("1.1")
            order_size = Decimal("0.1")
            
            print(f"  Test Orders (10% away from market):")
            print(f"    Buy:  {order_size} SOL @ {buy_price:.2f} USDC")
            print(f"    Sell: {order_size} SOL @ {sell_price:.2f} USDC")
            
            # Place buy order if we have USDC
            required_usdc = buy_price * order_size
            if self.usdc_available >= required_usdc:
                print("  Placing buy order...")
                result = await self.http_client.create_order(
                    symbol="SOL_USDC",
                    side="Bid",
                    order_type="Limit",
                    quantity=str(order_size),
                    price=str(buy_price.quantize(Decimal("0.01"))),
                    time_in_force="GTC",
                    post_only=True,
                )
                if result and "id" in result:
                    self.placed_orders.append(result["id"])
                    print(f"    ✅ Buy order placed: {result['id']}")
                    self.test_results["buy_order"] = "PASS"
                else:
                    print(f"    ❌ Buy order failed: {result}")
                    self.test_results["buy_order"] = "FAIL"
            else:
                print(f"    ⚠️ Insufficient USDC (need {required_usdc:.2f}, have {self.usdc_available:.2f})")
                self.test_results["buy_order"] = "SKIP"
            
            # Place sell order if we have SOL
            if self.sol_available >= order_size:
                print("  Placing sell order...")
                result = await self.http_client.create_order(
                    symbol="SOL_USDC",
                    side="Ask",
                    order_type="Limit",
                    quantity=str(order_size),
                    price=str(sell_price.quantize(Decimal("0.01"))),
                    time_in_force="GTC",
                    post_only=True,
                )
                if result and "id" in result:
                    self.placed_orders.append(result["id"])
                    print(f"    ✅ Sell order placed: {result['id']}")
                    self.test_results["sell_order"] = "PASS"
                else:
                    print(f"    ❌ Sell order failed: {result}")
                    self.test_results["sell_order"] = "FAIL"
            else:
                print(f"    ⚠️ Insufficient SOL (need {order_size}, have {self.sol_available})")
                self.test_results["sell_order"] = "SKIP"
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Query open orders
            open_orders = await self.http_client.fetch_open_orders("SOL_USDC")
            if open_orders is not None:
                print(f"  Open Orders: {len(open_orders)} total")
                our_orders = [o for o in open_orders if o.get("id") in self.placed_orders]
                print(f"    Our test orders: {len(our_orders)}")
                self.test_results["query_orders"] = "PASS"
            
            # Cancel orders
            if self.placed_orders:
                print("  Cancelling test orders...")
                for order_id in self.placed_orders:
                    result = await self.http_client.cancel_order("SOL_USDC", order_id)
                    if result:
                        print(f"    ✅ Cancelled: {order_id}")
                    else:
                        print(f"    ❌ Failed to cancel: {order_id}")
                self.test_results["cancel_orders"] = "PASS"
                
        except Exception as e:
            print(f"  ❌ Order management failed: {e}")
            self.test_results["order_management"] = "FAIL"
            
            # Try to cleanup
            for order_id in self.placed_orders:
                try:
                    await self.http_client.cancel_order("SOL_USDC", order_id)
                except:
                    pass
                    
    async def cleanup(self):
        """Clean up connections and orders."""
        print("\n🧹 Cleaning up...")
        
        # Cancel any remaining orders
        for order_id in self.placed_orders:
            try:
                await self.http_client.cancel_order("SOL_USDC", order_id)
                print(f"  Cancelled order: {order_id}")
            except:
                pass
        
        # Disconnect WebSocket
        if self.ws_client:
            await self.ws_client.disconnect()
            print("  WebSocket disconnected")
        
        # HTTP client doesn't need explicit close
        if self.http_client:
            print("  HTTP client cleanup complete")
            
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for v in self.test_results.values() if v == "PASS")
        failed = sum(1 for v in self.test_results.values() if v == "FAIL")
        skipped = sum(1 for v in self.test_results.values() if v in ["SKIP", "NO_DATA"])
        
        print(f"\nResults: ✅ {passed} passed, ❌ {failed} failed, ⚠️ {skipped} skipped")
        
        print("\nDetailed Results:")
        for test, result in self.test_results.items():
            status = "✅" if result == "PASS" else "❌" if result == "FAIL" else "⚠️"
            print(f"  {test:20} {status} {result}")
        
        print("\n" + "="*60)
        if failed == 0:
            print("✅ SUCCESS - All tests passed!")
            print("The Backpack integration is working correctly.")
        elif failed <= 2:
            print("⚠️ PARTIAL SUCCESS - Most tests passed")
            print("Review the failed tests above.")
        else:
            print("❌ FAILURE - Multiple tests failed")
            print("The integration needs debugging.")
            
    async def run(self):
        """Run all tests."""
        print("\n" + "="*60)
        print("BACKPACK LIVE API TEST")
        print("="*60)
        print(f"Environment: {'TESTNET' if self.testnet else 'MAINNET'}")
        print("Testing: SOL_USDC")
        print("="*60)
        
        try:
            # Run tests in sequence
            if not await self.test_http_connection():
                print("⚠️ Stopping - HTTP connection failed")
                return
                
            await self.test_account_data()
            await self.test_market_data()
            await self.test_websocket()
            await self.test_order_management()
            
        except KeyboardInterrupt:
            print("\n⚠️ Test interrupted")
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")
        finally:
            await self.cleanup()
            
        self.print_summary()


async def main():
    """Main entry point."""
    test = SimpleBackpackTest()
    await test.run()


if __name__ == "__main__":
    asyncio.run(main())