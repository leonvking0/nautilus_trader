#!/usr/bin/env python3
"""
Test Backpack order placement using PyNaCl directly (workaround for build issues).
This will actually place and cancel a real order on Backpack.
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


class BackpackOrderTestFixed:
    """Backpack order test with fixed signature generation."""
    
    def __init__(self):
        self.api_key = os.getenv("BACKPACK_API_KEY", "SJexpqvUHpdmLASGRHSANlX1V857BhlcY5Jv7LbBB5c=")
        self.api_secret = os.getenv("BACKPACK_API_SECRET", "Qe4RSp5wJMqrUAjT6UKpWFDO1NdhC2Ej36EQTBAi9zM=")
        self.base_url = "https://api.backpack.exchange"
        self.placed_orders = []
        
    def sign_request(self, instruction: str, params: Optional[Dict] = None) -> tuple[str, int, int]:
        """Sign a request using Ed25519 with PyNaCl."""
        timestamp = int(time.time() * 1000)
        window = 5000
        
        # Build the signature payload
        sign_str = f"instruction={instruction}"
        if params:
            # Convert booleans to lowercase strings as required by Backpack
            processed_params = {}
            for k, v in params.items():
                if isinstance(v, bool):
                    processed_params[k] = str(v).lower()
                else:
                    processed_params[k] = v
            
            sorted_params = sorted(processed_params.items())
            param_str = "&".join([f"{k}={v}" for k, v in sorted_params])
            sign_str = f"{sign_str}&{param_str}"
        sign_str = f"{sign_str}&timestamp={timestamp}&window={window}"
        
        # Sign with Ed25519 using PyNaCl
        private_key = base64.b64decode(self.api_secret)
        signing_key = SigningKey(private_key)
        signature_bytes = signing_key.sign(sign_str.encode()).signature
        signature = base64.b64encode(signature_bytes).decode()
        
        return signature, timestamp, window
        
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
        ticker = await self.make_request("GET", f"/api/v1/ticker", params={"symbol": symbol})
        if ticker and "lastPrice" in ticker:
            price = Decimal(str(ticker["lastPrice"]))
            return price
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
            result = {}
            for asset in ["SOL", "USDC"]:
                if asset in balances:
                    info = balances[asset]
                    available = Decimal(str(info.get("available", 0)))
                    locked = Decimal(str(info.get("locked", 0)))
                    result[asset] = {"available": available, "locked": locked}
                    print(f"  {asset}: Available={available}, Locked={locked}")
            return result
        
        print("  ⚠️ Could not get balances")
        return {}
        
    async def place_order(
        self,
        symbol: str,
        side: str,
        price: Decimal,
        quantity: Decimal,
    ) -> Optional[str]:
        """Place a limit order."""
        print(f"\n📝 Placing {side} order on {symbol}...")
        print(f"  Quantity: {quantity} SOL")
        print(f"  Price: {price} USDC")
        
        order_data = {
            "symbol": symbol,
            "side": side,
            "orderType": "Limit",
            "quantity": str(quantity),
            "price": str(price),
            "timeInForce": "GTC",
            "postOnly": True,
            "autoBorrow": True if side == "Bid" else False,  # Use margin for buys if needed
        }
        
        result = await self.make_request(
            "POST",
            "/api/v1/order",
            data=order_data,
            auth=True,
            instruction="orderExecute",
        )
        
        if result:
            if "id" in result:
                order_id = result["id"]
                print(f"  ✅ Order placed successfully! ID: {order_id}")
                self.placed_orders.append((symbol, order_id))
                return order_id
            else:
                print(f"  ❌ Unexpected response: {result}")
        else:
            print(f"  ❌ Failed to place order")
            
        return None
        
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an order."""
        print(f"\n🚫 Cancelling order {order_id}...")
        
        # Cancel endpoint expects data in body, not params
        cancel_data = {
            "symbol": symbol,
            "orderId": order_id,
        }
        
        result = await self.make_request(
            "DELETE",
            "/api/v1/order",
            data=cancel_data,  # Pass as data, not params
            auth=True,
            instruction="orderCancel",
        )
        
        if result or result == {}:
            print(f"  ✅ Order cancelled successfully")
            return True
        else:
            print(f"  ❌ Failed to cancel order")
            return False
            
    async def run_test(self):
        """Run the order placement test."""
        print("\n" + "="*60)
        print("BACKPACK ORDER TEST - WITH FIXED SIGNATURE")
        print("="*60)
        print("Using PyNaCl for Ed25519 signatures")
        print("="*60)
        
        try:
            # Get balances
            balances = await self.get_balances()
            
            # Get current market price
            print("\n📊 Getting market price for SOL_USDC...")
            current_price = await self.get_market_price("SOL_USDC")
            if current_price:
                print(f"  Current price: {current_price} USDC")
            else:
                current_price = Decimal("150")
                print(f"  Using default price: {current_price} USDC")
            
            # Place a small buy order 10% below market
            buy_price = (current_price * Decimal("0.9")).quantize(Decimal("0.01"))
            quantity = Decimal("0.1")
            
            print(f"\n🎯 Test Order Details:")
            print(f"  Type: Buy (using margin if needed)")
            print(f"  Price: {buy_price} USDC (10% below market)")
            print(f"  Quantity: {quantity} SOL")
            print(f"  Total: {buy_price * quantity} USDC")
            
            order_id = await self.place_order(
                symbol="SOL_USDC",
                side="Bid",
                price=buy_price,
                quantity=quantity,
            )
            
            if order_id:
                print(f"\n✅ SUCCESS! Order placed with ID: {order_id}")
                
                # Wait a bit
                print("\n⏳ Waiting 5 seconds before cancellation...")
                await asyncio.sleep(5)
                
                # Cancel the order
                cancelled = await self.cancel_order("SOL_USDC", order_id)
                if cancelled:
                    print("\n🎉 COMPLETE SUCCESS!")
                    print("  ✅ Order placed successfully")
                    print("  ✅ Order cancelled successfully")
                    print("  ✅ Signature generation fixed!")
            else:
                print("\n❌ Order placement failed")
                
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            
            # Emergency cleanup
            if self.placed_orders:
                print("\n🚨 Emergency cleanup...")
                for symbol, order_id in self.placed_orders:
                    try:
                        await self.cancel_order(symbol, order_id)
                    except:
                        pass


async def main():
    """Main entry point."""
    test = BackpackOrderTestFixed()
    await test.run_test()


if __name__ == "__main__":
    asyncio.run(main())