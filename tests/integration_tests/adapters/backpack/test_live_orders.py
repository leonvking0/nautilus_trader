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

"""Live order lifecycle tests for Backpack adapter."""

import asyncio
import time
from decimal import Decimal
from typing import Optional

import pytest

from nautilus_trader.core.uuid import UUID4

from .base import BackpackTestBase, live_only


class TestBackpackLiveOrders(BackpackTestBase):
    """Test cases for order lifecycle with live Backpack API."""
    
    def __init__(self):
        super().__init__()
        self.placed_orders = []  # Track orders for cleanup
    
    async def teardown_method(self, method):
        """Clean up any orders placed during tests."""
        if self.test_mode.value == "live" and self.placed_orders:
            for order_id in self.placed_orders:
                try:
                    await self.http_client.cancel_order("SOL_USDC", order_id)
                except Exception:
                    pass  # Order might already be cancelled or filled
            self.placed_orders.clear()
    
    @live_only
    @pytest.mark.asyncio
    async def test_order_lifecycle_complete(self):
        """Test complete order lifecycle with real API."""
        self.require_live_mode()
        
        # Get current market price
        ticker = await self.http_client.get_ticker("SOL_USDC")
        market_price = Decimal(ticker["lastPrice"])
        
        # Calculate safe test price (10% below market for buy order)
        test_price = self.get_safe_test_price(float(market_price), is_buy=True)
        test_price = Decimal(str(round(test_price, 2)))  # Round to tick size
        
        # Place a limit order
        order_params = {
            "symbol": "SOL_USDC",
            "side": "Bid",  # Buy side
            "orderType": "Limit",
            "price": str(test_price),
            "quantity": "0.1",  # Minimum size
            "timeInForce": "GTC",
            "postOnly": True,  # Ensure we're maker
            "clientOrderId": f"TEST_{UUID4()}",
        }
        
        # Place the order
        order_result = await self.http_client.place_order(**order_params)
        assert "id" in order_result, f"Order placement failed: {order_result}"
        
        order_id = order_result["id"]
        self.placed_orders.append(order_id)
        
        # Verify order appears in open orders
        await asyncio.sleep(0.5)  # Brief delay for order to register
        open_orders = await self.http_client.get_orders("SOL_USDC")
        
        order_found = False
        for order in open_orders:
            if order["id"] == order_id:
                order_found = True
                assert order["status"] == "New", f"Order status should be New: {order}"
                assert order["symbol"] == "SOL_USDC"
                assert Decimal(order["price"]) == test_price
                assert Decimal(order["quantity"]) == Decimal("0.1")
                break
        
        assert order_found, f"Order {order_id} not found in open orders"
        
        # Modify the order (change price slightly)
        new_price = test_price - Decimal("0.01")
        modify_result = await self.http_client.modify_order(
            symbol="SOL_USDC",
            order_id=order_id,
            price=str(new_price),
        )
        
        # Verify modification
        await asyncio.sleep(0.5)
        open_orders = await self.http_client.get_orders("SOL_USDC")
        for order in open_orders:
            if order["id"] == order_id:
                assert Decimal(order["price"]) == new_price, "Order price should be updated"
                break
        
        # Cancel the order
        cancel_result = await self.http_client.cancel_order("SOL_USDC", order_id)
        assert cancel_result.get("success") or "id" in cancel_result, \
            f"Cancel failed: {cancel_result}"
        
        # Verify order is cancelled
        await asyncio.sleep(0.5)
        open_orders = await self.http_client.get_orders("SOL_USDC")
        for order in open_orders:
            assert order["id"] != order_id, f"Order {order_id} should not be in open orders"
        
        # Remove from cleanup list since we cancelled it
        self.placed_orders.remove(order_id)
    
    @live_only
    @pytest.mark.asyncio
    async def test_post_only_order_rejection(self):
        """Test that post-only orders at market price are rejected."""
        self.require_live_mode()
        
        # Get current market price
        depth = await self.http_client.get_depth("SOL_USDC")
        best_ask = Decimal(depth["asks"][0][0])
        
        # Try to place post-only buy at or above best ask (should be rejected)
        order_params = {
            "symbol": "SOL_USDC",
            "side": "Bid",
            "orderType": "Limit",
            "price": str(best_ask),  # At market price
            "quantity": "0.1",
            "timeInForce": "GTC",
            "postOnly": True,
        }
        
        with pytest.raises(Exception) as exc_info:
            await self.http_client.place_order(**order_params)
        
        # Order should be rejected for crossing the spread
        assert "rejected" in str(exc_info.value).lower() or \
               "post" in str(exc_info.value).lower(), \
               f"Expected post-only rejection: {exc_info.value}"
    
    @live_only
    @pytest.mark.asyncio
    async def test_batch_order_operations(self):
        """Test placing and cancelling multiple orders."""
        self.require_live_mode()
        
        # Get current market price
        ticker = await self.http_client.get_ticker("SOL_USDC")
        market_price = Decimal(ticker["lastPrice"])
        
        # Place multiple orders at different price levels
        orders_to_place = []
        for i in range(3):
            price = market_price * Decimal(f"0.{90 - i}")  # 0.90, 0.89, 0.88
            price = Decimal(str(round(float(price), 2)))
            
            orders_to_place.append({
                "symbol": "SOL_USDC",
                "side": "Bid",
                "orderType": "Limit",
                "price": str(price),
                "quantity": "0.1",
                "timeInForce": "GTC",
                "clientOrderId": f"BATCH_TEST_{i}_{UUID4()}",
            })
        
        # Place all orders
        placed_ids = []
        for params in orders_to_place:
            try:
                result = await self.http_client.place_order(**params)
                if "id" in result:
                    placed_ids.append(result["id"])
                    self.placed_orders.append(result["id"])
            except Exception as e:
                print(f"Failed to place order: {e}")
        
        assert len(placed_ids) > 0, "Should place at least one order"
        
        # Verify all orders are open
        await asyncio.sleep(0.5)
        open_orders = await self.http_client.get_orders("SOL_USDC")
        open_ids = {order["id"] for order in open_orders}
        
        for order_id in placed_ids:
            assert order_id in open_ids, f"Order {order_id} should be open"
        
        # Cancel all orders
        for order_id in placed_ids:
            await self.http_client.cancel_order("SOL_USDC", order_id)
            self.placed_orders.remove(order_id)
        
        # Verify all cancelled
        await asyncio.sleep(0.5)
        open_orders = await self.http_client.get_orders("SOL_USDC")
        open_ids = {order["id"] for order in open_orders}
        
        for order_id in placed_ids:
            assert order_id not in open_ids, f"Order {order_id} should be cancelled"
    
    @live_only
    @pytest.mark.asyncio
    async def test_order_fills_tracking(self):
        """Test tracking partial fills and order status changes."""
        self.require_live_mode()
        
        # This test would require an order that actually gets filled
        # For safety, we'll just test order status tracking
        
        # Get current market price
        ticker = await self.http_client.get_ticker("SOL_USDC")
        market_price = Decimal(ticker["lastPrice"])
        
        # Place order far from market
        test_price = Decimal(str(round(float(market_price) * 0.8, 2)))
        
        order_params = {
            "symbol": "SOL_USDC",
            "side": "Bid",
            "orderType": "Limit",
            "price": str(test_price),
            "quantity": "0.5",
            "timeInForce": "GTC",
        }
        
        result = await self.http_client.place_order(**order_params)
        order_id = result["id"]
        self.placed_orders.append(order_id)
        
        # Poll order status
        for _ in range(3):
            await asyncio.sleep(1)
            
            orders = await self.http_client.get_orders("SOL_USDC")
            for order in orders:
                if order["id"] == order_id:
                    # Check order fields
                    assert "executedQuantity" in order
                    assert "executedQuoteQuantity" in order
                    assert Decimal(order["executedQuantity"]) >= 0
                    
                    # If partially filled, verify consistency
                    if Decimal(order["executedQuantity"]) > 0:
                        assert order["status"] in ["PartiallyFilled", "Filled"]
                    break
        
        # Clean up
        await self.http_client.cancel_order("SOL_USDC", order_id)
        self.placed_orders.remove(order_id)
    
    @live_only
    @pytest.mark.asyncio
    async def test_order_validation_errors(self):
        """Test various order validation error scenarios."""
        self.require_live_mode()
        
        # Test 1: Invalid symbol
        with pytest.raises(Exception) as exc_info:
            await self.http_client.place_order(
                symbol="INVALID_SYMBOL",
                side="Bid",
                orderType="Limit",
                price="100",
                quantity="1",
            )
        assert "symbol" in str(exc_info.value).lower() or \
               "invalid" in str(exc_info.value).lower()
        
        # Test 2: Quantity below minimum
        ticker = await self.http_client.get_ticker("SOL_USDC")
        market_price = Decimal(ticker["lastPrice"])
        
        with pytest.raises(Exception) as exc_info:
            await self.http_client.place_order(
                symbol="SOL_USDC",
                side="Bid",
                orderType="Limit",
                price=str(market_price * Decimal("0.9")),
                quantity="0.001",  # Below minimum
            )
        assert "quantity" in str(exc_info.value).lower() or \
               "min" in str(exc_info.value).lower()
        
        # Test 3: Price not aligned to tick size
        with pytest.raises(Exception) as exc_info:
            await self.http_client.place_order(
                symbol="SOL_USDC",
                side="Bid",
                orderType="Limit",
                price="123.456789",  # Too many decimals
                quantity="0.1",
            )
        # API might round or reject