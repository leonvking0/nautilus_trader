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


def _get_api_key(api_key: str | None = None) -> str | None:
    """Get API key from parameter or environment."""
    return api_key if api_key is not None else os.getenv("BACKPACK_API_KEY")


def _get_api_secret(api_secret: str | None = None) -> str | None:
    """Get API secret from parameter or environment."""
    return api_secret if api_secret is not None else os.getenv("BACKPACK_API_SECRET")


def _get_base_url(base_url: str | None = None) -> str:
    """Get base URL from parameter or default."""
    return base_url if base_url is not None else BACKPACK_BASE_URL_PROD


def _get_ws_url(ws_url: str | None = None) -> str:
    """Get WebSocket URL from parameter or default."""
    return ws_url if ws_url is not None else BACKPACK_WS_URL_PROD


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

    @classmethod
    def with_env_defaults(
        cls,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        ws_url: str | None = None,
        testnet: bool = False,
        **kwargs,
    ) -> "BackpackDataClientConfig":
        """Create config with environment defaults."""
        return cls(
            api_key=_get_api_key(api_key),
            api_secret=_get_api_secret(api_secret),
            base_url=_get_base_url(base_url),
            ws_url=_get_ws_url(ws_url),
            testnet=testnet,
            **kwargs,
        )


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

    @classmethod
    def with_env_defaults(
        cls,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str | None = None,
        ws_url: str | None = None,
        testnet: bool = False,
        **kwargs,
    ) -> "BackpackExecClientConfig":
        """Create config with environment defaults."""
        return cls(
            api_key=_get_api_key(api_key),
            api_secret=_get_api_secret(api_secret),
            base_url=_get_base_url(base_url),
            ws_url=_get_ws_url(ws_url),
            testnet=testnet,
            **kwargs,
        )