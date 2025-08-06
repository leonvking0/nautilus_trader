#!/usr/bin/env python3
"""
Simple test using the existing Backpack HTTP client to place and cancel orders.
"""

import asyncio
import os
from decimal import Decimal

from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.common.component import LiveClock


async def test_backpack_orders():
    """Test order placement using the existing BackpackHttpClient."""
    
    api_key = os.getenv("BACKPACK_API_KEY", "SJexpqvUHpdmLASGRHSANlX1V857BhlcY5Jv7LbBB5c=")
    api_secret = os.getenv("BACKPACK_API_SECRET", "Qe4RSp5wJMqrUAjT6UKpWFDO1NdhC2Ej36EQTBAi9zM=")
    
    print("="*60)
    print("BACKPACK ORDER TEST - Using BackpackHttpClient")
    print("="*60)
    
    # Initialize client
    clock = LiveClock()
    client = BackpackHttpClient(
        clock=clock,
        api_key=api_key,
        api_secret=api_secret,
        testnet=False,  # Using mainnet
    )
    
    placed_orders = []
    
    try:
        # 1. Get account balance
        print("\n1️⃣ Getting account balance...")
        balance = await client.fetch_balance()
        if balance:
            print("  Account balances:")
            for asset in ["SOL", "USDC"]:
                if asset in balance:
                    info = balance[asset]
                    print(f"    {asset}: Available={info.get('available', 0)}, Locked={info.get('locked', 0)}")
        
        # 2. Get market price for SOL_USDC
        print("\n2️⃣ Getting market data for SOL_USDC...")
        ticker = await client.fetch_ticker("SOL_USDC")
        if ticker:
            current_price = Decimal(str(ticker.get("lastPrice", "150")))
            print(f"  Current price: {current_price}")
        else:
            current_price = Decimal("150")
            print(f"  Using default price: {current_price}")
        
        # 3. Place a small buy order 10% below market
        print("\n3️⃣ Placing test buy order...")
        buy_price = (current_price * Decimal("0.9")).quantize(Decimal("0.01"))
        quantity = Decimal("0.1")
        
        print(f"  Order details:")
        print(f"    Symbol: SOL_USDC")
        print(f"    Side: Buy")
        print(f"    Quantity: {quantity} SOL")
        print(f"    Price: {buy_price} USDC (10% below market)")
        
        order_result = await client.create_order(
            symbol="SOL_USDC",
            side="Bid",
            order_type="Limit",
            quantity=str(quantity),
            price=str(buy_price),
            time_in_force="GTC",
            post_only=True,
            auto_borrow=True,  # Use margin if needed
        )
        
        if order_result:
            if "id" in order_result:
                order_id = order_result["id"]
                placed_orders.append(("SOL_USDC", order_id))
                print(f"  ✅ Order placed successfully!")
                print(f"     Order ID: {order_id}")
                print(f"     Status: {order_result.get('status', 'Unknown')}")
            else:
                print(f"  ❌ Unexpected response: {order_result}")
        else:
            print("  ❌ Failed to place order")
        
        # 4. Wait a bit
        if placed_orders:
            print("\n⏳ Waiting 5 seconds before checking orders...")
            await asyncio.sleep(5)
            
            # 5. Check open orders
            print("\n4️⃣ Checking open orders...")
            open_orders = await client.fetch_open_orders("SOL_USDC")
            if open_orders:
                print(f"  Found {len(open_orders)} open orders")
                our_orders = [o for o in open_orders if o.get("id") in [oid for _, oid in placed_orders]]
                if our_orders:
                    print("  Our test orders:")
                    for order in our_orders:
                        print(f"    - ID: {order.get('id')}")
                        print(f"      Side: {order.get('side')}")
                        print(f"      Quantity: {order.get('quantity')}")
                        print(f"      Price: {order.get('price')}")
                        print(f"      Status: {order.get('status')}")
            
            # 6. Cancel orders
            print("\n5️⃣ Cancelling test orders...")
            for symbol, order_id in placed_orders:
                result = await client.cancel_order(symbol=symbol, order_id=order_id)
                if result:
                    print(f"  ✅ Order {order_id} cancelled")
                else:
                    print(f"  ❌ Failed to cancel order {order_id}")
        
        # 7. If we have SOL, try a sell order too
        if balance and "SOL" in balance:
            sol_available = Decimal(str(balance["SOL"].get("available", "0")))
            if sol_available >= Decimal("0.1"):
                print("\n6️⃣ Testing sell order...")
                sell_price = (current_price * Decimal("1.1")).quantize(Decimal("0.01"))
                
                print(f"  Order details:")
                print(f"    Symbol: SOL_USDC")
                print(f"    Side: Sell")
                print(f"    Quantity: {quantity} SOL")
                print(f"    Price: {sell_price} USDC (10% above market)")
                
                sell_result = await client.create_order(
                    symbol="SOL_USDC",
                    side="Ask",
                    order_type="Limit",
                    quantity=str(quantity),
                    price=str(sell_price),
                    time_in_force="GTC",
                    post_only=True,
                )
                
                if sell_result and "id" in sell_result:
                    sell_order_id = sell_result["id"]
                    print(f"  ✅ Sell order placed: {sell_order_id}")
                    
                    await asyncio.sleep(3)
                    
                    # Cancel it
                    await client.cancel_order(symbol="SOL_USDC", order_id=sell_order_id)
                    print(f"  ✅ Sell order cancelled")
        
        print("\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Emergency cleanup
        if placed_orders:
            print("\n🚨 Emergency cleanup...")
            for symbol, order_id in placed_orders:
                try:
                    await client.cancel_order(symbol=symbol, order_id=order_id)
                    print(f"  Cancelled: {order_id}")
                except:
                    pass
    
    finally:
        # No need to close the HTTP client explicitly
        pass


if __name__ == "__main__":
    asyncio.run(test_backpack_orders())