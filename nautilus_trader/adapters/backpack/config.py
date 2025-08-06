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

"""Configuration for Backpack adapter."""

import os
from typing import Any

import msgspec

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_BASE_URL_PROD
from nautilus_trader.adapters.backpack.common.constants import BACKPACK_WS_URL_PROD
from nautilus_trader.config import LiveDataClientConfig
from nautilus_trader.config import LiveExecClientConfig


class BackpackDataClientConfig(LiveDataClientConfig, frozen=True):
    """
    Configuration for Backpack data client.

    Parameters
    ----------
    api_key : str, optional
        The Backpack API key (base64 encoded public key).
        If None, will look for BACKPACK_API_KEY environment variable.
    api_secret : str, optional
        The Backpack API secret (base64 encoded private key).
        If None, will look for BACKPACK_API_SECRET environment variable.
    base_url : str, optional
        The base URL for the REST API.
    ws_url : str, optional
        The URL for the WebSocket API.
    testnet : bool, default False
        Whether to use testnet environment.
    
    """

    api_key: str | None = None
    api_secret: str | None = None
    base_url: str | None = None
    ws_url: str | None = None
    testnet: bool = False

    def __post_init__(self) -> None:
        """Post-initialization to set defaults from environment."""
        # Override with environment variables if not set
        if self.api_key is None:
            object.__setattr__(self, "api_key", os.getenv("BACKPACK_API_KEY"))
        if self.api_secret is None:
            object.__setattr__(self, "api_secret", os.getenv("BACKPACK_API_SECRET"))
        if self.base_url is None:
            object.__setattr__(self, "base_url", BACKPACK_BASE_URL_PROD)
        if self.ws_url is None:
            object.__setattr__(self, "ws_url", BACKPACK_WS_URL_PROD)


class BackpackExecClientConfig(LiveExecClientConfig, frozen=True):
    """
    Configuration for Backpack execution client.

    Parameters
    ----------
    api_key : str, optional
        The Backpack API key (base64 encoded public key).
        If None, will look for BACKPACK_API_KEY environment variable.
    api_secret : str, optional
        The Backpack API secret (base64 encoded private key).
        If None, will look for BACKPACK_API_SECRET environment variable.
    base_url : str, optional
        The base URL for the REST API.
    ws_url : str, optional
        The URL for the WebSocket API.
    testnet : bool, default False
        Whether to use testnet environment.
    
    """

    api_key: str | None = None
    api_secret: str | None = None
    base_url: str | None = None
    ws_url: str | None = None
    testnet: bool = False

    def __post_init__(self) -> None:
        """Post-initialization to set defaults from environment."""
        # Override with environment variables if not set
        if self.api_key is None:
            object.__setattr__(self, "api_key", os.getenv("BACKPACK_API_KEY"))
        if self.api_secret is None:
            object.__setattr__(self, "api_secret", os.getenv("BACKPACK_API_SECRET"))
        if self.base_url is None:
            object.__setattr__(self, "base_url", BACKPACK_BASE_URL_PROD)
        if self.ws_url is None:
            object.__setattr__(self, "ws_url", BACKPACK_WS_URL_PROD)