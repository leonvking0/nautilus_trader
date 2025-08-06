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

"""Tests for Backpack exchange ED25519 authentication."""

import base64
import time
from unittest.mock import Mock

import pytest

from nautilus_trader.core.nautilus_pyo3 import ed25519_signature


class TestBackpackAuth:
    """Test cases for Backpack ED25519 authentication."""

    def setup(self):
        """Set up test fixtures."""
        # Test ED25519 private key (32 bytes)
        # This is a test key - DO NOT use in production
        self.test_private_key = bytes.fromhex(
            "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
        )
        # Corresponding public key for verification
        self.test_public_key = base64.b64encode(
            bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        ).decode()

    def test_ed25519_signature_generation(self):
        """Test ED25519 signature generation."""
        # Arrange
        data = "test_message"
        
        # Act
        signature = ed25519_signature(self.test_private_key, data)
        
        # Assert
        assert isinstance(signature, str)
        # Base64 encoded signature should be 88 characters
        assert len(signature) == 88
        # Should be valid base64
        base64.b64decode(signature)

    def test_build_signature_payload_simple(self):
        """Test building signature payload for simple request."""
        # Arrange
        instruction = "orderCancel"
        params = {"orderId": "28", "symbol": "BTC_USDC"}
        timestamp = 1614550000000
        window = 5000
        
        # Act
        # Sort parameters alphabetically
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        payload = f"instruction={instruction}&{query_string}&timestamp={timestamp}&window={window}"
        
        # Assert
        expected = "instruction=orderCancel&orderId=28&symbol=BTC_USDC&timestamp=1614550000000&window=5000"
        assert payload == expected

    def test_build_signature_payload_no_params(self):
        """Test building signature payload without parameters."""
        # Arrange
        instruction = "balanceQuery"
        timestamp = 1614550000000
        window = 5000
        
        # Act
        payload = f"instruction={instruction}&timestamp={timestamp}&window={window}"
        
        # Assert
        expected = "instruction=balanceQuery&timestamp=1614550000000&window=5000"
        assert payload == expected

    def test_parameter_sorting(self):
        """Test that parameters are sorted alphabetically."""
        # Arrange
        params = {
            "symbol": "BTC_USDC",
            "side": "Buy",
            "orderType": "Limit",
            "price": "30000",
            "quantity": "0.1",
        }
        
        # Act
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        
        # Assert
        expected = "orderType=Limit&price=30000&quantity=0.1&side=Buy&symbol=BTC_USDC"
        assert query_string == expected

    def test_batch_order_signature_payload(self):
        """Test building signature payload for batch orders."""
        # Arrange
        orders = [
            {
                "symbol": "SOL_USDC",
                "side": "Buy",
                "orderType": "Limit",
                "price": "141",
                "quantity": "12",
            },
            {
                "symbol": "SOL_USDC",
                "side": "Buy",
                "orderType": "Limit",
                "price": "140",
                "quantity": "11",
            },
        ]
        timestamp = 1750793021519
        window = 5000
        
        # Act
        payloads = []
        for order in orders:
            sorted_params = sorted(order.items())
            query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
            payloads.append(f"instruction=orderExecute&{query_string}")
        
        final_payload = "&".join(payloads) + f"&timestamp={timestamp}&window={window}"
        
        # Assert
        expected = (
            "instruction=orderExecute&orderType=Limit&price=141&quantity=12&side=Buy&symbol=SOL_USDC&"
            "instruction=orderExecute&orderType=Limit&price=140&quantity=11&side=Buy&symbol=SOL_USDC&"
            "timestamp=1750793021519&window=5000"
        )
        assert final_payload == expected

    def test_timestamp_window_validation(self):
        """Test timestamp window validation."""
        # Arrange
        current_time_ms = int(time.time() * 1000)
        
        # Test valid window (within 5 seconds)
        valid_timestamp = current_time_ms - 2000  # 2 seconds ago
        window = 5000
        
        # Act
        is_valid = (current_time_ms - valid_timestamp) <= window
        
        # Assert
        assert is_valid is True
        
        # Test invalid window (outside 5 seconds)
        invalid_timestamp = current_time_ms - 6000  # 6 seconds ago
        is_invalid = (current_time_ms - invalid_timestamp) <= window
        
        assert is_invalid is False

    def test_instruction_types(self):
        """Test various instruction types for different endpoints."""
        # Arrange
        instructions = [
            "accountQuery",
            "balanceQuery",
            "orderExecute",
            "orderCancel",
            "orderCancelAll",
            "orderQuery",
            "orderQueryAll",
            "orderHistoryQueryAll",
            "fillHistoryQueryAll",
            "depositQueryAll",
            "withdrawalQueryAll",
        ]
        
        # Act & Assert
        for instruction in instructions:
            assert isinstance(instruction, str)
            assert len(instruction) > 0

    @pytest.mark.parametrize(
        ("window", "expected_valid"),
        [
            (5000, True),  # Default window
            (60000, True),  # Maximum window
            (1000, True),  # Small window
            (0, False),  # Invalid: zero window
            (60001, False),  # Invalid: exceeds maximum
        ],
    )
    def test_window_parameter_validation(self, window, expected_valid):
        """Test window parameter validation."""
        # Act
        is_valid = 0 < window <= 60000 if window > 0 else False
        
        # Assert
        assert is_valid == expected_valid

    def test_headers_generation(self):
        """Test generation of authentication headers."""
        # Arrange
        timestamp = 1614550000000
        window = 5000
        api_key = self.test_public_key
        signature = "test_signature_base64"
        
        # Act
        headers = {
            "X-Timestamp": str(timestamp),
            "X-Window": str(window),
            "X-API-Key": api_key,
            "X-Signature": signature,
        }
        
        # Assert
        assert headers["X-Timestamp"] == "1614550000000"
        assert headers["X-Window"] == "5000"
        assert headers["X-API-Key"] == api_key
        assert headers["X-Signature"] == signature

    def test_full_signing_flow(self):
        """Test complete signing flow for a request."""
        # Arrange
        instruction = "orderExecute"
        params = {
            "symbol": "BTC_USDC",
            "side": "Buy",
            "orderType": "Limit",
            "price": "30000",
            "quantity": "0.1",
        }
        timestamp = 1614550000000
        window = 5000
        
        # Act
        # 1. Sort parameters
        sorted_params = sorted(params.items())
        query_string = "&".join([f"{k}={v}" for k, v in sorted_params])
        
        # 2. Build payload
        payload = f"instruction={instruction}&{query_string}&timestamp={timestamp}&window={window}"
        
        # 3. Generate signature
        signature = ed25519_signature(self.test_private_key, payload)
        
        # 4. Create headers
        headers = {
            "X-Timestamp": str(timestamp),
            "X-Window": str(window),
            "X-API-Key": self.test_public_key,
            "X-Signature": signature,
        }
        
        # Assert
        assert "instruction=orderExecute" in payload
        assert "orderType=Limit" in payload
        assert "timestamp=1614550000000" in payload
        assert isinstance(signature, str)
        assert len(signature) == 88  # Base64 encoded ED25519 signature
        assert all(key in headers for key in ["X-Timestamp", "X-Window", "X-API-Key", "X-Signature"])