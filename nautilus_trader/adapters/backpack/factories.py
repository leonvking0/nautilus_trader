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

"""Backpack adapter factory implementations."""

import asyncio
import os
from functools import lru_cache

from nautilus_trader.adapters.backpack.common.constants import BACKPACK_VENUE
from nautilus_trader.adapters.backpack.config import BackpackDataClientConfig
from nautilus_trader.adapters.backpack.config import BackpackExecClientConfig
from nautilus_trader.adapters.backpack.data import BackpackDataClient
from nautilus_trader.adapters.backpack.execution import BackpackExecutionClient
from nautilus_trader.adapters.backpack.http.client import BackpackHttpClient
from nautilus_trader.adapters.backpack.providers import BackpackInstrumentProvider
from nautilus_trader.adapters.backpack.spot.providers import BackpackSpotInstrumentProvider
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock
from nautilus_trader.common.component import MessageBus
from nautilus_trader.config import InstrumentProviderConfig
from nautilus_trader.live.factories import LiveDataClientFactory
from nautilus_trader.live.factories import LiveExecClientFactory


def get_backpack_api_key(testnet: bool = False) -> str | None:
    """
    Get the Backpack API key from environment variables.

    Parameters
    ----------
    testnet : bool, default False
        Whether to get the testnet API key.

    Returns
    -------
    str | None

    """
    if testnet:
        return os.getenv("BACKPACK_TESTNET_API_KEY")
    return os.getenv("BACKPACK_API_KEY")


def get_backpack_api_secret(testnet: bool = False) -> str | None:
    """
    Get the Backpack API secret from environment variables.

    Parameters
    ----------
    testnet : bool, default False
        Whether to get the testnet API secret.

    Returns
    -------
    str | None

    """
    if testnet:
        return os.getenv("BACKPACK_TESTNET_API_SECRET")
    return os.getenv("BACKPACK_API_SECRET")


@lru_cache(1)
def get_cached_backpack_http_client(
    clock: LiveClock,
    api_key: str | None = None,
    api_secret: str | None = None,
    testnet: bool = False,
) -> BackpackHttpClient:
    """
    Cache and return a Backpack HTTP client with the given key and secret.

    If a cached client with matching parameters already exists, the cached client 
    will be returned.

    Parameters
    ----------
    clock : LiveClock
        The clock for the client.
    api_key : str, optional
        The API key for the client.
    api_secret : str, optional
        The API secret for the client.
    testnet : bool, default False
        If the client is connecting to the testnet API.

    Returns
    -------
    BackpackHttpClient

    """
    api_key = api_key or get_backpack_api_key(testnet)
    api_secret = api_secret or get_backpack_api_secret(testnet)

    return BackpackHttpClient(
        clock=clock,
        api_key=api_key,
        api_secret=api_secret,
        testnet=testnet,
    )


class BackpackLiveDataClientFactory(LiveDataClientFactory):
    """
    Provides a Backpack live data client factory.
    """

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str | None = None,
        config: BackpackDataClientConfig | None = None,
        msgbus: MessageBus | None = None,
        cache: Cache | None = None,
        clock: LiveClock | None = None,
    ) -> BackpackDataClient:
        """
        Create a new Backpack data client.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop for the client.
        name : str, optional
            The custom client ID.
        config : BackpackDataClientConfig, optional
            The configuration for the client.
        msgbus : MessageBus, optional
            The message bus for the client.
        cache : Cache, optional
            The cache for the client.
        clock : LiveClock, optional
            The clock for the client.

        Returns
        -------
        BackpackDataClient

        """
        config = config or BackpackDataClientConfig()
        
        client = get_cached_backpack_http_client(
            clock=clock,
            api_key=config.api_key,
            api_secret=config.api_secret,
            testnet=config.testnet,
        )

        return BackpackDataClient(
            loop=loop,
            client=client,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
            name=name,
        )


class BackpackLiveExecClientFactory(LiveExecClientFactory):
    """
    Provides a Backpack live execution client factory.
    """

    @staticmethod
    def create(
        loop: asyncio.AbstractEventLoop,
        name: str | None = None,
        config: BackpackExecClientConfig | None = None,
        msgbus: MessageBus | None = None,
        cache: Cache | None = None,
        clock: LiveClock | None = None,
    ) -> BackpackExecutionClient:
        """
        Create a new Backpack execution client.

        Parameters
        ----------
        loop : asyncio.AbstractEventLoop
            The event loop for the client.
        name : str, optional
            The custom client ID.
        config : BackpackExecClientConfig, optional
            The configuration for the client.
        msgbus : MessageBus, optional
            The message bus for the client.
        cache : Cache, optional
            The cache for the client.
        clock : LiveClock, optional
            The clock for the client.

        Returns
        -------
        BackpackExecutionClient

        """
        config = config or BackpackExecClientConfig()
        
        client = get_cached_backpack_http_client(
            clock=clock,
            api_key=config.api_key,
            api_secret=config.api_secret,
            testnet=config.testnet,
        )

        return BackpackExecutionClient(
            loop=loop,
            client=client,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
            config=config,
            name=name,
        )


def get_backpack_instrument_provider(
    client: BackpackHttpClient,
    clock: LiveClock,
    market_type: str = "spot",
    testnet: bool = False,
    config: InstrumentProviderConfig | None = None,
) -> BackpackInstrumentProvider:
    """
    Get a Backpack instrument provider for the specified market type.

    Parameters
    ----------
    client : BackpackHttpClient
        The HTTP client for the provider.
    clock : LiveClock
        The clock for the provider.
    market_type : str, default "spot"
        The market type ("spot" or "futures").
    testnet : bool, default False
        If the provider is for the testnet.
    config : InstrumentProviderConfig, optional
        The configuration for the provider.

    Returns
    -------
    BackpackInstrumentProvider

    """
    if market_type == "spot":
        return BackpackSpotInstrumentProvider(
            client=client,
            clock=clock,
            testnet=testnet,
            config=config,
        )
    else:
        # For futures/perps when implemented
        return BackpackInstrumentProvider(
            client=client,
            clock=clock,
            testnet=testnet,
            config=config,
        )