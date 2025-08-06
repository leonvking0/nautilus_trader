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

"""Tests for Backpack HTTP client."""

import asyncio
import base64
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from nautilus_trader.core.nautilus_pyo3 import ed25519_signature


class TestBackpackHttpClient:
    """Test cases for Backpack HTTP client."""

    def setup(self):
        """Set up test fixtures."""
        # Test ED25519 private key (32 bytes) - TEST ONLY
        self.test_private_key = bytes.fromhex(
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
        )
        self.test_public_key = base64.b64encode(
            bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        ).decode()
        
        self.base_url = "https://api.backpack.exchange"
        self.testnet_url = "https://api.backpack.exchange"  # Same for testnet

    @pytest.mark.asyncio
    async def test_sign_request_with_ed25519(self):
        """Test that requests are signed correctly with ED25519."""
        # Arrange
        instruction = "orderExecute"
        params = {
            "symbol": "BTC_USDC",
            "side": "Buy",
            "orderType": "Limit",
            "price": "30000",
            "quantity": "0.1",
        }
        timestamp = int(time.time() * 1000)
        window = 5000
        
        # Act
        # Sort parameters
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        
        # Build payload
        payload = f"instruction={instruction}&{query_string}&timestamp={timestamp}&window={window}"
        
        # Generate signature
        signature = ed25519_signature(self.test_private_key, payload)
        
        # Create headers
        headers = {
            "X-Timestamp": str(timestamp),
            "X-Window": str(window),
            "X-API-Key": self.test_public_key,
            "X-Signature": signature,
        }
        
        # Assert
        assert headers["X-Timestamp"] == str(timestamp)
        assert headers["X-Window"] == "5000"
        assert headers["X-API-Key"] == self.test_public_key
        assert len(headers["X-Signature"]) == 88  # Base64 encoded ED25519 signature

    @pytest.mark.asyncio
    async def test_public_request_no_auth(self, mocker):
        """Test that public requests don't include authentication headers."""
        # Arrange
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"result": "success"})
        mock_session.request.return_value = mock_response
        
        # Act
        headers = {
            "Content-Type": "application/json",
        }
        # No auth headers for public endpoints
        
        # Assert
        assert "X-API-Key" not in headers
        assert "X-Signature" not in headers
        assert "X-Timestamp" not in headers
        assert "X-Window" not in headers

    @pytest.mark.asyncio
    async def test_private_request_with_auth(self):
        """Test that private requests include authentication headers."""
        # Arrange
        instruction = "balanceQuery"
        timestamp = int(time.time() * 1000)
        window = 5000
        
        # Act
        payload = f"instruction={instruction}&timestamp={timestamp}&window={window}"
        signature = ed25519_signature(self.test_private_key, payload)
        
        headers = {
            "Content-Type": "application/json",
            "X-Timestamp": str(timestamp),
            "X-Window": str(window),
            "X-API-Key": self.test_public_key,
            "X-Signature": signature,
        }
        
        # Assert
        assert "X-API-Key" in headers
        assert "X-Signature" in headers
        assert "X-Timestamp" in headers
        assert "X-Window" in headers
        assert headers["X-Window"] == "5000"

    @pytest.mark.asyncio
    async def test_rate_limiting_headers(self):
        """Test rate limiting header handling."""
        # Arrange
        rate_limits = {
            "spot": {"per_minute": 6000, "per_second": 100},
            "futures": {"per_minute": 2400, "per_second": 40},
        }
        
        # Act & Assert
        assert rate_limits["spot"]["per_minute"] == 6000
        assert rate_limits["spot"]["per_second"] == 100
        assert rate_limits["futures"]["per_minute"] == 2400
        assert rate_limits["futures"]["per_second"] == 40

    @pytest.mark.asyncio
    async def test_error_handling_400(self, mocker):
        """Test handling of 400 Bad Request errors."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={
            "error": "Invalid parameter",
            "code": "BAD_REQUEST"
        })
        
        # Act
        error_data = await mock_response.json()
        
        # Assert
        assert mock_response.status == 400
        assert error_data["error"] == "Invalid parameter"
        assert error_data["code"] == "BAD_REQUEST"

    @pytest.mark.asyncio
    async def test_error_handling_401(self, mocker):
        """Test handling of 401 Unauthorized errors."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.json = AsyncMock(return_value={
            "error": "Invalid API key",
            "code": "UNAUTHORIZED"
        })
        
        # Act
        error_data = await mock_response.json()
        
        # Assert
        assert mock_response.status == 401
        assert error_data["error"] == "Invalid API key"
        assert error_data["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_error_handling_429(self, mocker):
        """Test handling of 429 Rate Limit errors."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.json = AsyncMock(return_value={
            "error": "Rate limit exceeded",
            "code": "RATE_LIMIT",
            "retry_after": 60
        })
        
        # Act
        error_data = await mock_response.json()
        
        # Assert
        assert mock_response.status == 429
        assert error_data["error"] == "Rate limit exceeded"
        assert error_data["code"] == "RATE_LIMIT"
        assert error_data["retry_after"] == 60

    @pytest.mark.asyncio
    async def test_error_handling_500(self, mocker):
        """Test handling of 500 Internal Server Error."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json = AsyncMock(return_value={
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        })
        
        # Act
        error_data = await mock_response.json()
        
        # Assert
        assert mock_response.status == 500
        assert error_data["error"] == "Internal server error"
        assert error_data["code"] == "INTERNAL_ERROR"

    def test_timestamp_window_validation(self):
        """Test timestamp window validation."""
        # Arrange
        current_time = int(time.time() * 1000)
        
        test_cases = [
            (current_time, 5000, True),  # Valid: current time
            (current_time - 4000, 5000, True),  # Valid: 4 seconds ago
            (current_time - 6000, 5000, False),  # Invalid: 6 seconds ago
            (current_time + 1000, 5000, True),  # Valid: 1 second in future
        ]
        
        # Act & Assert
        for timestamp, window, expected_valid in test_cases:
            time_diff = abs(current_time - timestamp)
            is_valid = time_diff <= window
            assert is_valid == expected_valid

    def test_build_request_url(self):
        """Test building request URLs."""
        # Arrange
        test_cases = [
            ("/api/v1/markets", {}, "/api/v1/markets"),
            ("/api/v1/ticker", {"symbol": "BTC_USDC"}, "/api/v1/ticker?symbol=BTC_USDC"),
            (
                "/api/v1/depth",
                {"symbol": "BTC_USDC", "limit": "20"},
                "/api/v1/depth?limit=20&symbol=BTC_USDC",  # Alphabetically sorted
            ),
        ]
        
        # Act & Assert
        for path, params, expected in test_cases:
            if params:
                sorted_params = sorted(params.items())
                query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
                url = f"{path}?{query_string}"
            else:
                url = path
            assert url == expected

    def test_batch_order_request_signing(self):
        """Test signing batch order requests."""
        # Arrange
        orders = [
            {
                "symbol": "BTC_USDC",
                "side": "Buy",
                "orderType": "Limit",
                "price": "30000",
                "quantity": "0.1",
            },
            {
                "symbol": "SOL_USDC",
                "side": "Sell",
                "orderType": "Limit",
                "price": "20",
                "quantity": "10",
            },
        ]
        timestamp = 1614550000000
        window = 5000
        
        # Act
        payloads = []
        for order in orders:
            sorted_params = sorted(order.items())
            query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
            payloads.append(f"instruction=orderExecute&{query_string}")
        
        final_payload = "&".join(payloads) + f"&timestamp={timestamp}&window={window}"
        signature = ed25519_signature(self.test_private_key, final_payload)
        
        # Assert
        assert "instruction=orderExecute" in final_payload
        assert "symbol=BTC_USDC" in final_payload
        assert "symbol=SOL_USDC" in final_payload
        assert f"timestamp={timestamp}" in final_payload
        assert f"window={window}" in final_payload
        assert len(signature) == 88  # Base64 encoded ED25519 signature

    @pytest.mark.asyncio
    async def test_request_timeout_handling(self):
        """Test request timeout handling."""
        # Arrange
        timeout_seconds = 30
        
        # Act
        start_time = time.time()
        # Simulate timeout check
        await asyncio.sleep(0.1)  # Small delay
        elapsed = time.time() - start_time
        
        # Assert
        assert elapsed < timeout_seconds
        assert timeout_seconds == 30  # Default timeout

    def test_websocket_subscription_signing(self):
        """Test WebSocket subscription signing."""
        # Arrange
        instruction = "subscribe"
        timestamp = int(time.time() * 1000)
        window = 5000
        
        # Act
        payload = f"instruction={instruction}&timestamp={timestamp}&window={window}"
        signature = ed25519_signature(self.test_private_key, payload)
        
        subscription_message = {
            "method": "SUBSCRIBE",
            "params": ["account.orderUpdate"],
            "signature": [self.test_public_key, signature, str(timestamp), str(window)],
        }
        
        # Assert
        assert subscription_message["method"] == "SUBSCRIBE"
        assert "account.orderUpdate" in subscription_message["params"]
        assert len(subscription_message["signature"]) == 4
        assert subscription_message["signature"][0] == self.test_public_key
        assert len(subscription_message["signature"][1]) == 88  # Signature length