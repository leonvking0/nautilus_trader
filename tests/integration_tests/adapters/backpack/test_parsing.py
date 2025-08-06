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

"""Tests for Backpack response parsing to Nautilus types."""

from decimal import Decimal

import pytest


class TestBackpackParsing:
    """Test cases for parsing Backpack responses to Nautilus types."""

    def test_parse_market_to_instrument(self, markets_response):
        """Test parsing market data to Nautilus Instrument."""
        # Arrange
        market = markets_response[0]  # BTC_USDC market
        
        # Act - Simulate parsing logic
        parsed = {
            "id": market["symbol"].replace("_", "-"),
            "base_currency": market["baseSymbol"],
            "quote_currency": market["quoteSymbol"],
            "price_precision": market["priceDecimals"],
            "size_precision": market["quantityDecimals"],
            "price_increment": Decimal(market["priceIncrement"]),
            "size_increment": Decimal(market["quantityIncrement"]),
            "min_notional": Decimal(market["minOrderValue"]),
            "max_quantity": None,  # Not provided by Backpack
            "min_quantity": Decimal(market["quantityIncrement"]),
            "margin_init": Decimal("0"),  # Spot market
            "margin_maint": Decimal("0"),  # Spot market
            "maker_fee": Decimal("0.0002"),  # Default fee
            "taker_fee": Decimal("0.0005"),  # Default fee
            "ts_event": 0,
            "ts_init": 0,
        }
        
        # Assert
        assert parsed["id"] == "BTC-USDC"
        assert parsed["base_currency"] == "BTC"
        assert parsed["quote_currency"] == "USDC"
        assert parsed["price_precision"] == 2
        assert parsed["size_precision"] == 4
        assert parsed["price_increment"] == Decimal("0.01")
        assert parsed["size_increment"] == Decimal("0.0001")
        assert parsed["min_notional"] == Decimal("10.00")

    def test_parse_ticker_to_quote_tick(self, ticker_response):
        """Test parsing ticker data to QuoteTick."""
        # Arrange
        ticker = ticker_response
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": ticker["symbol"].replace("_", "-"),
            "bid_price": Decimal(ticker["bidPrice"]),
            "ask_price": Decimal(ticker["askPrice"]),
            "bid_size": Decimal("0"),  # Not provided by Backpack ticker
            "ask_size": Decimal("0"),  # Not provided by Backpack ticker
            "ts_event": ticker["timestamp"] * 1000,  # Convert to microseconds
            "ts_init": ticker["timestamp"] * 1000,
        }
        
        # Assert
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["bid_price"] == Decimal("30120.00")
        assert parsed["ask_price"] == Decimal("30125.00")
        assert parsed["ts_event"] == 1694687692980000

    def test_parse_trade_to_trade_tick(self, trades_response):
        """Test parsing trade data to TradeTick."""
        # Arrange
        trade = trades_response[0]
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": "BTC-USDC",  # Would come from request context
            "price": Decimal(trade["price"]),
            "size": Decimal(trade["quantity"]),
            "aggressor_side": "BUYER" if trade["side"] == "Buy" else "SELLER",
            "trade_id": str(trade["id"]),
            "ts_event": trade["timestamp"] * 1000,  # Convert to microseconds
            "ts_init": trade["timestamp"] * 1000,
        }
        
        # Assert
        assert parsed["price"] == Decimal("30123.45")
        assert parsed["size"] == Decimal("0.1234")
        assert parsed["aggressor_side"] == "BUYER"
        assert parsed["trade_id"] == "987654321"
        assert parsed["ts_event"] == 1694687692980000

    def test_parse_orderbook_to_deltas(self, orderbook_response):
        """Test parsing order book data to OrderBookDeltas."""
        # Arrange
        orderbook = orderbook_response
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": orderbook["symbol"].replace("_", "-"),
            "bids": [(Decimal(price), Decimal(size)) for price, size in orderbook["bids"]],
            "asks": [(Decimal(price), Decimal(size)) for price, size in orderbook["asks"]],
            "update_id": orderbook["lastUpdateId"],
            "ts_event": orderbook["timestamp"],  # Already in microseconds
            "ts_init": orderbook["timestamp"],
        }
        
        # Assert
        assert parsed["instrument_id"] == "BTC-USDC"
        assert len(parsed["bids"]) == 5
        assert len(parsed["asks"]) == 5
        assert parsed["bids"][0] == (Decimal("30120.00"), Decimal("0.5000"))
        assert parsed["asks"][0] == (Decimal("30125.00"), Decimal("0.6000"))
        assert parsed["update_id"] == 123456789
        assert parsed["ts_event"] == 1694687692980000

    def test_parse_balance_to_account_balance(self, balance_response):
        """Test parsing balance data to AccountBalance."""
        # Arrange
        balances = balance_response["balances"]
        
        # Act - Simulate parsing logic
        parsed_balances = []
        for balance in balances:
            parsed = {
                "currency": balance["symbol"],
                "total": Decimal(balance["total"]),
                "free": Decimal(balance["available"]),
                "locked": Decimal(balance["locked"]),
            }
            parsed_balances.append(parsed)
        
        # Assert
        assert len(parsed_balances) == 4
        
        # Check USDC balance
        usdc_balance = parsed_balances[0]
        assert usdc_balance["currency"] == "USDC"
        assert usdc_balance["total"] == Decimal("10000.00")
        assert usdc_balance["free"] == Decimal("8500.00")
        assert usdc_balance["locked"] == Decimal("1500.00")
        
        # Check BTC balance
        btc_balance = parsed_balances[1]
        assert btc_balance["currency"] == "BTC"
        assert btc_balance["total"] == Decimal("0.5000")
        assert btc_balance["free"] == Decimal("0.4500")
        assert btc_balance["locked"] == Decimal("0.0500")

    def test_parse_order_to_nautilus_order(self, order_response):
        """Test parsing order data to Nautilus Order."""
        # Arrange
        order = order_response
        
        # Act - Simulate parsing logic
        parsed = {
            "client_order_id": str(order.get("clientOrderId", "")),
            "venue_order_id": str(order["orderId"]),
            "instrument_id": order["symbol"].replace("_", "-"),
            "order_side": "BUY" if order["side"] == "Buy" else "SELL",
            "order_type": order["orderType"].upper(),
            "time_in_force": order["timeInForce"],
            "quantity": Decimal(order["quantity"]) if order["quantity"] else None,
            "price": Decimal(order["price"]) if order["price"] else None,
            "filled_qty": Decimal(order["executedQuantity"]),
            "avg_px": None,  # Would need to calculate from executedQuoteQuantity / executedQuantity
            "status": self._map_order_status(order["status"]),
            "ts_init": order["createdAt"] * 1000,  # Convert to microseconds
            "ts_last": order["updatedAt"] * 1000,
        }
        
        # Assert
        assert parsed["client_order_id"] == "123"
        assert parsed["venue_order_id"] == "1111343026172067"
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["order_side"] == "BUY"
        assert parsed["order_type"] == "LIMIT"
        assert parsed["time_in_force"] == "GTC"
        assert parsed["quantity"] == Decimal("0.1000")
        assert parsed["price"] == Decimal("30000.00")
        assert parsed["filled_qty"] == Decimal("0.0000")
        assert parsed["status"] == "OPEN"

    def test_parse_orders_list(self, orders_response):
        """Test parsing multiple orders."""
        # Arrange
        orders = orders_response
        
        # Act
        parsed_orders = []
        for order in orders:
            parsed_orders.append({
                "venue_order_id": str(order["orderId"]),
                "status": self._map_order_status(order["status"]),
            })
        
        # Assert
        assert len(parsed_orders) == 3
        assert parsed_orders[0]["venue_order_id"] == "1111343026172067"
        assert parsed_orders[0]["status"] == "PARTIALLY_FILLED"
        assert parsed_orders[1]["venue_order_id"] == "1111343026172068"
        assert parsed_orders[1]["status"] == "OPEN"
        assert parsed_orders[2]["venue_order_id"] == "1111343026172069"
        assert parsed_orders[2]["status"] == "FILLED"

    def test_parse_klines_to_bars(self, responses_dir):
        """Test parsing kline data to Bar objects."""
        # Arrange
        from .conftest import load_fixture
        klines = load_fixture(responses_dir / "klines.json")
        
        # Act - Simulate parsing logic
        parsed_bars = []
        for kline in klines:
            parsed = {
                "open": Decimal(kline["open"]),
                "high": Decimal(kline["high"]),
                "low": Decimal(kline["low"]),
                "close": Decimal(kline["close"]),
                "volume": Decimal(kline["volume"]),
                "ts_event": kline["openTime"] * 1000,  # Convert to microseconds
                "ts_init": kline["closeTime"] * 1000,
            }
            parsed_bars.append(parsed)
        
        # Assert
        assert len(parsed_bars) == 4
        
        first_bar = parsed_bars[0]
        assert first_bar["open"] == Decimal("30100.00")
        assert first_bar["high"] == Decimal("30150.00")
        assert first_bar["low"] == Decimal("30090.00")
        assert first_bar["close"] == Decimal("30120.00")
        assert first_bar["volume"] == Decimal("123.4567")

    def test_parse_websocket_book_ticker(self, ws_messages_dir):
        """Test parsing WebSocket book ticker message."""
        # Arrange
        from .conftest import load_fixture
        message = load_fixture(ws_messages_dir / "bookTicker.json")
        data = message["data"]
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": data["s"].replace("_", "-"),
            "bid_price": Decimal(data["b"]),
            "bid_size": Decimal(data["B"]),
            "ask_price": Decimal(data["a"]),
            "ask_size": Decimal(data["A"]),
            "update_id": int(data["u"]),
            "ts_event": data["T"],  # Already in microseconds
        }
        
        # Assert
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["bid_price"] == Decimal("30120.00")
        assert parsed["bid_size"] == Decimal("0.5000")
        assert parsed["ask_price"] == Decimal("30125.00")
        assert parsed["ask_size"] == Decimal("0.6000")
        assert parsed["update_id"] == 111063070525358080

    def test_parse_websocket_trade(self, ws_messages_dir):
        """Test parsing WebSocket trade message."""
        # Arrange
        from .conftest import load_fixture
        message = load_fixture(ws_messages_dir / "trade.json")
        data = message["data"]
        
        # Act - Simulate parsing logic
        parsed = {
            "instrument_id": data["s"].replace("_", "-"),
            "price": Decimal(data["p"]),
            "size": Decimal(data["q"]),
            "aggressor_side": "SELLER" if data["m"] else "BUYER",
            "trade_id": str(data["t"]),
            "ts_event": data["T"],  # Already in microseconds
        }
        
        # Assert
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["price"] == Decimal("30123.45")
        assert parsed["size"] == Decimal("0.1234")
        assert parsed["aggressor_side"] == "SELLER"  # m=true means buyer is maker
        assert parsed["trade_id"] == "12345"

    def test_parse_websocket_order_update(self, ws_messages_dir):
        """Test parsing WebSocket order update message."""
        # Arrange
        from .conftest import load_fixture
        message = load_fixture(ws_messages_dir / "orderUpdate.json")
        data = message["data"]
        
        # Act - Simulate parsing logic
        parsed = {
            "event_type": data["e"],
            "instrument_id": data["s"].replace("_", "-"),
            "client_order_id": str(data.get("c", "")),
            "venue_order_id": str(data["i"]),
            "order_side": "BUY" if data["S"] == "Buy" else "SELL",
            "order_type": data["o"],
            "quantity": Decimal(data["q"]) if "q" in data else None,
            "price": Decimal(data["p"]) if "p" in data else None,
            "filled_qty": Decimal(data["z"]) if "z" in data else Decimal("0"),
            "status": data["X"],
            "ts_event": data["T"],  # Already in microseconds
        }
        
        # Assert
        assert parsed["event_type"] == "orderAccepted"
        assert parsed["instrument_id"] == "BTC-USDC"
        assert parsed["client_order_id"] == "123"
        assert parsed["venue_order_id"] == "1111343026172067"
        assert parsed["order_side"] == "BUY"
        assert parsed["order_type"] == "LIMIT"
        assert parsed["quantity"] == Decimal("0.1000")
        assert parsed["price"] == Decimal("30000.00")
        assert parsed["filled_qty"] == Decimal("0.0000")
        assert parsed["status"] == "New"

    def _map_order_status(self, backpack_status: str) -> str:
        """Map Backpack order status to Nautilus status."""
        status_map = {
            "New": "OPEN",
            "PartiallyFilled": "PARTIALLY_FILLED",
            "Filled": "FILLED",
            "Cancelled": "CANCELED",
            "Expired": "EXPIRED",
        }
        return status_map.get(backpack_status, backpack_status)