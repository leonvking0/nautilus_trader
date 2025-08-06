#!/usr/bin/env python3
"""
Test script to place and cancel real orders on Backpack Exchange using margin.
This script will check collateral/margin and place orders accordingly.
"""

import asyncio
import base64
import json
import os
import time
from decimal import Decimal
from typing import Any, Dict, Optional

import aiohttp
from nacl.signing import SigningKey


class BackpackMarginOrderTest:
    """Backpack order placement test with margin support."""
    
    def __init__(self):
        self.api_key = os.getenv("BACKPACK_API_KEY", "SJexpqvUHpdmLASGRHSANlX1V857BhlcY5Jv7LbBB5c=")
        self.api_secret = os.getenv("BACKPACK_API_SECRET", "Qe4RSp5wJMqrUAjT6UKpWFDO1NdhC2Ej36EQTBAi9zM=")
        self.base_url = "https://api.backpack.exchange"
        self.placed_orders = []
        
    def sign_request(self, instruction: str, params: Optional[Dict] = None) -> tuple[str, int, int]:
        """Sign a request using Ed25519."""
        timestamp = int(time.time() * 1000)
        window = 5000
        
        # Build the signature payload
        sign_str = f"instruction={instruction}"
        if params:
            sorted_params = sorted(params.items())
            param_str = "&".join([f"{k}={v}" for k, v in sorted_params])
            sign_str = f"{sign_str}&{param_str}"
        sign_str = f"{sign_str}&timestamp={timestamp}&window={window}"
        
        # Sign with Ed25519
        signing_key = SigningKey(base64.b64decode(self.api_secret))
        signature = signing_key.sign(sign_str.encode()).signature
        encoded_signature = base64.b64encode(signature).decode()
        
        return encoded_signature, timestamp, window
        
    async def make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        auth: bool = False,
        instruction: Optional[str] = None,
    ) -> Any:
        """Make an HTTP request to Backpack API."""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-KEY": self.api_key,
        }
        
        if auth and instruction:
            sign_params = params if method == "GET" else data
            signature, timestamp, window = self.sign_request(instruction, sign_params)
            headers.update({
                "X-SIGNATURE": signature,
                "X-TIMESTAMP": str(timestamp),
                "X-WINDOW": str(window),
            })
        
        async with aiohttp.ClientSession() as session:
            kwargs = {"headers": headers}
            if params:
                kwargs["params"] = params
            if data:
                kwargs["json"] = data
                
            async with session.request(method, url, **kwargs) as response:
                text = await response.text()
                if response.status >= 400:
                    print(f"❌ API Error ({response.status}): {text}")
                    return None
                    
                try:
                    return json.loads(text) if text else None
                except json.JSONDecodeError:
                    print(f"Failed to parse response: {text}")
                    return None
                    
    async def get_market_price(self, symbol: str) -> Optional[Decimal]:
        """Get current market price for a symbol."""
        print(f"\n📊 Getting market price for {symbol}...")
        
        # Try ticker endpoint
        ticker = await self.make_request("GET", f"/api/v1/ticker", params={"symbol": symbol})
        if ticker and "lastPrice" in ticker:
            price = Decimal(str(ticker["lastPrice"]))
            print(f"  Current price: {price}")
            return price
            
        # Fallback to order book
        depth = await self.make_request("GET", f"/api/v1/depth", params={"symbol": symbol})
        if depth and "asks" in depth and depth["asks"]:
            price = Decimal(str(depth["asks"][0][0]))
            print(f"  Current ask price: {price}")
            return price
            
        print(f"  ⚠️ Could not get price for {symbol}")
        return None
        
    async def get_balances(self) -> Dict[str, Dict]:
        """Get account balances."""
        print("\n💰 Getting account balances...")
        
        balances = await self.make_request(
            "GET",
            "/api/v1/capital",
            auth=True,
            instruction="balanceQuery",
        )
        
        if balances:
            # Extract SOL and USDC balances
            result = {}
            for asset, details in balances.items():
                if asset in ["SOL", "USDC"]:
                    available = details.get("available", 0)
                    locked = details.get("locked", 0)
                    result[asset] = {
                        "available": Decimal(str(available)),
                        "locked": Decimal(str(locked)),
                    }
                    print(f"  {asset}: Available={available}, Locked={locked}")
            return result
        
        print("  ⚠️ Could not get balances")
        return {}
        
    async def get_collateral(self) -> Dict[str, Any]:
        """Get collateral/margin information."""
        print("\n💳 Getting collateral/margin info...")
        
        collateral = await self.make_request(
            "GET",
            "/capital/collateral",  # Try without /api/v1 prefix as per docs
            auth=True,
            instruction="collateralQuery",
        )
        
        if not collateral:
            # Try with /api/v1 prefix
            collateral = await self.make_request(
                "GET",
                "/api/v1/capital/collateral",
                auth=True,
                instruction="collateralQuery",
            )
        
        if collateral:
            net_equity = collateral.get("netEquity", 0)
            available = collateral.get("netEquityAvailable", 0)
            print(f"  Net Equity: {net_equity}")
            print(f"  Net Equity Available: {available}")
            return collateral
        
        print("  ⚠️ Could not get collateral info")
        return {}
        
    async def place_order_with_margin(
        self,
        symbol: str,
        side: str,
        price: Decimal,
        quantity: Decimal,
        auto_borrow: bool = True,
    ) -> Optional[str]:
        """Place a limit order with auto-borrow if needed."""
        print(f"\n📝 Placing {side} order on {symbol} (with auto-borrow: {auto_borrow})...")
        print(f"  Quantity: {quantity}")
        print(f"  Price: {price}")
        
        order_data = {
            "symbol": symbol,
            "side": side,
            "orderType": "Limit",
            "quantity": str(quantity),
            "price": str(price),
            "timeInForce": "GTC",
            "postOnly": True,  # Ensure maker order
        }
        
        # Add auto-borrow flag if buying with no USDC
        if side == "Bid" and auto_borrow:
            order_data["autoBorrow"] = True
        
        # Try different endpoints
        endpoints = ["/orders/execute", "/api/v1/order", "/api/order"]
        result = None
        
        for endpoint in endpoints:
            print(f"  Trying endpoint: {endpoint}")
            result = await self.make_request(
                "POST",
                endpoint,
                data=order_data,
                auth=True,
                instruction="orderExecute",
            )
            
            if result:
                break
        
        if result:
            if "id" in result:
                order_id = result["id"]
                print(f"  ✅ Order placed successfully! ID: {order_id}")
                self.placed_orders.append((symbol, order_id))
                return order_id
            elif "status" in result and result["status"] == "Filled":
                print(f"  ⚠️ Order filled immediately: {result}")
                return result.get("id")
            else:
                print(f"  ❌ Unexpected response: {result}")
        else:
            print(f"  ❌ Failed to place order")
            
        return None
        
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        print(f"\n🚫 Cancelling order {order_id} on {symbol}...")
        
        # Try different endpoints
        endpoints = ["/orders", "/api/v1/order", "/api/order"]
        
        for endpoint in endpoints:
            result = await self.make_request(
                "DELETE",
                endpoint,
                params={"symbol": symbol, "orderId": order_id},
                auth=True,
                instruction="orderCancel",
            )
            
            if result or result == {}:  # Empty response might mean success
                print(f"  ✅ Order cancelled successfully")
                return True
        
        print(f"  ❌ Failed to cancel order")
        return False
            
    async def get_open_orders(self, symbol: str) -> list:
        """Get open orders for a symbol."""
        print(f"\n📋 Getting open orders for {symbol}...")
        
        # Try different endpoints
        endpoints = ["/orders", "/api/v1/orders", "/api/orders"]
        
        for endpoint in endpoints:
            orders = await self.make_request(
                "GET",
                endpoint,
                params={"symbol": symbol},
                auth=True,
                instruction="orderQueryAll",
            )
            
            if orders is not None:
                if isinstance(orders, list):
                    print(f"  Found {len(orders)} open orders")
                    for order in orders[:3]:  # Show first 3
                        print(f"    - {order.get('side')}: {order.get('quantity')} @ {order.get('price')} (ID: {order.get('id')})")
                    return orders
                break
        
        print("  No open orders found")
        return []
        
    async def get_available_markets(self) -> list:
        """Get all available markets."""
        print("\n📈 Getting available markets...")
        
        markets = await self.make_request("GET", "/api/v1/markets")
        
        if markets:
            print(f"  Found {len(markets)} markets")
            # Filter for SOL markets
            sol_markets = [m for m in markets if "SOL" in m.get("symbol", "")]
            print(f"  SOL markets:")
            for market in sol_markets[:5]:  # Show first 5
                print(f"    - {market.get('symbol')}: {market.get('status')}")
            return markets
        
        return []
            
    async def run_test(self):
        """Run the complete order test."""
        print("\n" + "="*60)
        print("BACKPACK LIVE ORDER TEST WITH MARGIN")
        print("="*60)
        print("This test will place REAL orders using margin/auto-borrow")
        print("Orders will be placed far from market and cancelled immediately")
        print("="*60)
        
        try:
            # Step 1: Get available markets first
            await self.get_available_markets()
            
            # Step 2: Get account balances
            balances = await self.get_balances()
            
            usdc_available = balances.get("USDC", {}).get("available", Decimal("0"))
            sol_available = balances.get("SOL", {}).get("available", Decimal("0"))
            
            # Step 3: Get collateral/margin info
            collateral = await self.get_collateral()
            net_equity_available = Decimal(str(collateral.get("netEquityAvailable", 0))) if collateral else Decimal("0")
            
            print(f"\n💼 Account Summary:")
            print(f"  USDC Available: {usdc_available}")
            print(f"  SOL Available: {sol_available}")
            print(f"  Net Equity Available (for margin): {net_equity_available}")
            
            # Step 4: Test SPOT market (SOL_USDC) with margin
            print("\n" + "-"*40)
            print("TESTING SPOT MARKET: SOL_USDC")
            print("-"*40)
            
            spot_price = await self.get_market_price("SOL_USDC")
            
            if spot_price and (usdc_available > 10 or net_equity_available > 10):
                # Place buy order 10% below market
                buy_price = (spot_price * Decimal("0.9")).quantize(Decimal("0.01"))
                quantity = Decimal("0.1")
                
                # Use auto-borrow if no USDC but have margin
                use_auto_borrow = usdc_available < (buy_price * quantity) and net_equity_available > 10
                
                if use_auto_borrow:
                    print(f"ℹ️ Using auto-borrow (no USDC but {net_equity_available} margin available)")
                
                spot_order_id = await self.place_order_with_margin(
                    symbol="SOL_USDC",
                    side="Bid",  # Buy
                    price=buy_price,
                    quantity=quantity,
                    auto_borrow=use_auto_borrow,
                )
                
                if spot_order_id:
                    print(f"✅ SPOT order placed: {spot_order_id}")
                    
                    # Wait a bit to let order settle
                    print("\n⏳ Waiting 5 seconds before cancellation...")
                    await asyncio.sleep(5)
                    
                    # Check open orders
                    await self.get_open_orders("SOL_USDC")
                    
                    # Cancel the order
                    cancelled = await self.cancel_order("SOL_USDC", spot_order_id)
                    if cancelled:
                        print("✅ SPOT order cancelled successfully")
                else:
                    print("❌ Failed to place SPOT order")
            else:
                print(f"⚠️ Cannot place order: No USDC ({usdc_available}) or margin ({net_equity_available})")
            
            # Step 5: Try with SOL if we have some (sell order)
            if sol_available >= Decimal("0.1") and spot_price:
                print("\n" + "-"*40)
                print("TESTING SELL ORDER: SOL_USDC")
                print("-"*40)
                
                # Place sell order 10% above market
                sell_price = (spot_price * Decimal("1.1")).quantize(Decimal("0.01"))
                quantity = Decimal("0.1")
                
                sell_order_id = await self.place_order_with_margin(
                    symbol="SOL_USDC",
                    side="Ask",  # Sell
                    price=sell_price,
                    quantity=quantity,
                    auto_borrow=False,  # No borrow needed for sells
                )
                
                if sell_order_id:
                    print(f"✅ SELL order placed: {sell_order_id}")
                    
                    # Wait a bit
                    print("\n⏳ Waiting 5 seconds before cancellation...")
                    await asyncio.sleep(5)
                    
                    # Cancel the order
                    cancelled = await self.cancel_order("SOL_USDC", sell_order_id)
                    if cancelled:
                        print("✅ SELL order cancelled successfully")
            
            # Step 6: Final cleanup
            print("\n" + "-"*40)
            print("FINAL CLEANUP")
            print("-"*40)
            
            for symbol, order_id in self.placed_orders:
                try:
                    await self.cancel_order(symbol, order_id)
                except:
                    pass
                    
            print("\n✅ Test completed!")
            
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            
            # Emergency cleanup
            print("\n🚨 Emergency cleanup...")
            for symbol, order_id in self.placed_orders:
                try:
                    await self.cancel_order(symbol, order_id)
                except:
                    pass


async def main():
    """Main entry point."""
    test = BackpackMarginOrderTest()
    await test.run_test()


if __name__ == "__main__":
    asyncio.run(main())