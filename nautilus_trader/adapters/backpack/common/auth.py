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

"""Authentication utilities for Backpack exchange."""

import base64
import time
from typing import Any

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_DEFAULT_WINDOW
from nautilus_trader.core.nautilus_pyo3 import ed25519_signature


def sort_parameters(params: dict[str, Any]) -> str:
    """
    Sort parameters alphabetically and convert to query string format.

    Parameters
    ----------
    params : dict[str, Any]
        The parameters to sort.

    Returns
    -------
    str
        Query string format of sorted parameters.

    """
    if not params:
        return ""
    
    # Sort keys alphabetically
    sorted_keys = sorted(params.keys())
    
    # Build query string
    query_parts = []
    for key in sorted_keys:
        value = params[key]
        # Convert boolean to lowercase string
        if isinstance(value, bool):
            value = str(value).lower()
        query_parts.append(f"{key}={value}")
    
    return "&".join(query_parts)


def build_signature_payload(
    instruction: str,
    params: dict[str, Any] | None = None,
    timestamp: int | None = None,
    window: int = BACKPACK_DEFAULT_WINDOW,
) -> str:
    """
    Build the signature payload for Backpack API requests.

    Parameters
    ----------
    instruction : str
        The instruction type for the request.
    params : dict[str, Any], optional
        The request parameters.
    timestamp : int, optional
        Unix timestamp in milliseconds. If None, current time is used.
    window : int, default 5000
        Time window in milliseconds.

    Returns
    -------
    str
        The payload to be signed.

    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    
    # Start with instruction
    payload_parts = [f"instruction={instruction}"]
    
    # Add sorted parameters if present
    if params:
        sorted_params = sort_parameters(params)
        if sorted_params:
            payload_parts.append(sorted_params)
    
    # Add timestamp and window
    payload_parts.append(f"timestamp={timestamp}")
    payload_parts.append(f"window={window}")
    
    return "&".join(payload_parts)


def build_batch_order_payload(
    orders: list[dict[str, Any]],
    timestamp: int | None = None,
    window: int = BACKPACK_DEFAULT_WINDOW,
) -> str:
    """
    Build the signature payload for batch order requests.

    Parameters
    ----------
    orders : list[dict[str, Any]]
        List of order dictionaries.
    timestamp : int, optional
        Unix timestamp in milliseconds. If None, current time is used.
    window : int, default 5000
        Time window in milliseconds.

    Returns
    -------
    str
        The payload to be signed.

    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    
    payload_parts = []
    
    # Process each order
    for order in orders:
        # Add instruction for each order
        payload_parts.append("instruction=orderExecute")
        # Sort and add order parameters
        sorted_params = sort_parameters(order)
        if sorted_params:
            payload_parts.append(sorted_params)
    
    # Add timestamp and window at the end
    payload_parts.append(f"timestamp={timestamp}")
    payload_parts.append(f"window={window}")
    
    return "&".join(payload_parts)


def sign_request(
    private_key: bytes,
    instruction: str,
    params: dict[str, Any] | None = None,
    timestamp: int | None = None,
    window: int = BACKPACK_DEFAULT_WINDOW,
) -> tuple[str, int, int]:
    """
    Sign a request for Backpack API.

    Parameters
    ----------
    private_key : bytes
        The ED25519 private key (32 bytes).
    instruction : str
        The instruction type for the request.
    params : dict[str, Any], optional
        The request parameters.
    timestamp : int, optional
        Unix timestamp in milliseconds. If None, current time is used.
    window : int, default 5000
        Time window in milliseconds.

    Returns
    -------
    tuple[str, int, int]
        Tuple of (base64 encoded signature, timestamp, window).

    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    
    # Build the payload
    payload = build_signature_payload(instruction, params, timestamp, window)
    
    # Sign the payload
    signature_bytes = ed25519_signature(private_key, payload)
    
    # Base64 encode the signature
    signature = base64.b64encode(signature_bytes).decode()
    
    return signature, timestamp, window


def sign_batch_order_request(
    private_key: bytes,
    orders: list[dict[str, Any]],
    timestamp: int | None = None,
    window: int = BACKPACK_DEFAULT_WINDOW,
) -> tuple[str, int, int]:
    """
    Sign a batch order request for Backpack API.

    Parameters
    ----------
    private_key : bytes
        The ED25519 private key (32 bytes).
    orders : list[dict[str, Any]]
        List of order dictionaries.
    timestamp : int, optional
        Unix timestamp in milliseconds. If None, current time is used.
    window : int, default 5000
        Time window in milliseconds.

    Returns
    -------
    tuple[str, int, int]
        Tuple of (base64 encoded signature, timestamp, window).

    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)
    
    # Build the payload for batch orders
    payload = build_batch_order_payload(orders, timestamp, window)
    
    # Sign the payload
    signature_bytes = ed25519_signature(private_key, payload)
    
    # Base64 encode the signature
    signature = base64.b64encode(signature_bytes).decode()
    
    return signature, timestamp, window