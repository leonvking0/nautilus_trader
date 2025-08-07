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
"""
Integration tests for Backpack unified account management.
"""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.common.account import BackpackUnifiedAccountManager
from nautilus_trader.adapters.backpack.common.borrow import BackpackAutoBorrow
from nautilus_trader.adapters.backpack.common.collateral import BackpackCollateralCalculator
from nautilus_trader.adapters.backpack.execution import BackpackExecutionClient
from nautilus_trader.adapters.backpack.factories import create_backpack_unified_execution_clients
from nautilus_trader.adapters.backpack.futures.execution import BackpackFuturesExecutionClient
from nautilus_trader.adapters.backpack.http.account import BackpackAccountHttpAPI
from nautilus_trader.adapters.backpack.schemas.account import (
    BackpackBalance,
    BackpackBorrowPosition,
    BackpackCapital,
    BackpackCollateral,
    BackpackCollateralWeight,
    BackpackCollateralDetail,
    BackpackUnifiedAccount,
)
from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.component import LiveClock, Logger, MessageBus
from nautilus_trader.model.currencies import USDC
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import TraderId


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_account_http():
    """Create mock account HTTP API."""
    mock = MagicMock(spec=BackpackAccountHttpAPI)
    
    # Mock capital response
    mock.fetch_capital = AsyncMock(return_value=BackpackCapital(
        balances=[
            BackpackBalance(symbol="USDC", available="10000", locked="500", staked="0"),
            BackpackBalance(symbol="BTC", available="0.5", locked="0", staked="0"),
            BackpackBalance(symbol="SOL", available="100", locked="10", staked="0"),
        ],
        totalCollateral="25000",
        availableCollateral="20000",
        initialMarginRate="0.1",
        maintenanceMarginRate="0.05",
        totalBorrowLiability="0",
        unsettledBalances="0",
        unrealizedPnl="0",
    ))
    
    # Mock collateral response
    mock.fetch_collateral = AsyncMock(return_value=BackpackCollateral(
        assets=[
            BackpackCollateralWeight(asset="USDC", weight="1.0"),
            BackpackCollateralWeight(asset="BTC", weight="0.95"),
            BackpackCollateralWeight(asset="SOL", weight="0.9"),
        ],
        totalWeightedCollateral="25000",
    ))
    
    # Mock collateral details
    mock.fetch_collateral_details = AsyncMock(return_value=[
        BackpackCollateralDetail(
            asset="USDC",
            quantity="10500",
            markPrice="1.0",
            collateralValue="10500",
            weight="1.0",
            usdValue="10500",
        ),
        BackpackCollateralDetail(
            asset="BTC",
            quantity="0.5",
            markPrice="50000",
            collateralValue="23750",
            weight="0.95",
            usdValue="25000",
        ),
        BackpackCollateralDetail(
            asset="SOL",
            quantity="110",
            markPrice="100",
            collateralValue="9900",
            weight="0.9",
            usdValue="11000",
        ),
    ])
    
    # Mock borrow positions
    mock.fetch_borrow_positions = AsyncMock(return_value=[])
    
    # Mock account limits
    mock.fetch_account_limits = AsyncMock(return_value={
        "maxLeverage": "20",
        "maxPositions": "100",
    })
    
    return mock


@pytest.fixture
def logger():
    """Create logger for tests."""
    return Logger(name="TestLogger")


class TestBackpackUnifiedAccountManager:
    """Test Backpack unified account manager."""
    
    @pytest.mark.asyncio
    async def test_initialize(self, mock_account_http, logger):
        """Test account manager initialization."""
        # Arrange
        manager = BackpackUnifiedAccountManager(
            account_http=mock_account_http,
            logger=logger,
        )
        account_id = AccountId("BACKPACK-UNIFIED-001")
        
        # Act
        account = await manager.initialize(
            account_id=account_id,
            base_currency=USDC,
        )
        
        # Assert
        assert account is not None
        assert account.id == account_id
        assert manager._unified_account is not None
        assert len(manager._collateral_weights) == 3
        assert manager._collateral_weights["USDC"] == Decimal("1.0")
        assert manager._collateral_weights["BTC"] == Decimal("0.95")
        
    @pytest.mark.asyncio
    async def test_refresh_account_state(self, mock_account_http, logger):
        """Test refreshing account state."""
        # Arrange
        manager = BackpackUnifiedAccountManager(
            account_http=mock_account_http,
            logger=logger,
        )
        
        # Act
        account = await manager.refresh_account_state()
        
        # Assert
        assert account is not None
        assert account.totalCollateral == "25000"
        assert account.availableCollateral == "20000"
        assert len(account.balances) == 3
        mock_account_http.fetch_capital.assert_called_once()
        mock_account_http.fetch_collateral.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_auto_borrow_check(self, mock_account_http, logger):
        """Test auto-borrow checking."""
        # Arrange
        manager = BackpackUnifiedAccountManager(
            account_http=mock_account_http,
            logger=logger,
        )
        await manager.refresh_account_state()
        
        # Mock borrow execution
        mock_account_http.execute_borrow = AsyncMock(return_value=True)
        
        # Act - no borrow needed
        success = await manager.check_and_execute_auto_borrow(
            required_usdc=Decimal("5000"),
        )
        
        # Assert
        assert success is True
        mock_account_http.execute_borrow.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_get_unified_positions(self, mock_account_http, logger):
        """Test getting unified positions."""
        # Arrange
        manager = BackpackUnifiedAccountManager(
            account_http=mock_account_http,
            logger=logger,
        )
        await manager.refresh_account_state()
        
        # Act
        positions = manager.get_unified_positions()
        
        # Assert
        assert len(positions) == 3  # 3 spot balances
        assert positions[0]["type"] == "spot"
        assert positions[0]["symbol"] == "USDC"
        assert Decimal(positions[0]["quantity"]) == Decimal("10500")
        
    @pytest.mark.asyncio
    async def test_calculate_total_margin_used(self, mock_account_http, logger):
        """Test calculating total margin used."""
        # Arrange
        manager = BackpackUnifiedAccountManager(
            account_http=mock_account_http,
            logger=logger,
        )
        await manager.refresh_account_state()
        
        # Act
        margin_used = manager.calculate_total_margin_used()
        
        # Assert
        assert margin_used == Decimal("0")  # No futures positions or borrows


class TestBackpackCollateralCalculator:
    """Test Backpack collateral calculator."""
    
    def test_calculate_weighted_collateral(self, logger):
        """Test calculating weighted collateral."""
        # Arrange
        calculator = BackpackCollateralCalculator(logger)
        
        # Act - calculate collateral for each asset
        usdc_collateral = calculator.calculate_asset_collateral(
            asset="USDC",
            quantity=Decimal("10000"),
            mark_price=Decimal("1"),
            weight=Decimal("1.0"),
        )
        
        btc_collateral = calculator.calculate_asset_collateral(
            asset="BTC",
            quantity=Decimal("1"),
            mark_price=Decimal("50000"),
            weight=Decimal("0.95"),
        )
        
        sol_collateral = calculator.calculate_asset_collateral(
            asset="SOL",
            quantity=Decimal("100"),
            mark_price=Decimal("100"),
            weight=Decimal("0.9"),
        )
        
        total_collateral = usdc_collateral + btc_collateral + sol_collateral
        
        # Assert
        expected = (
            Decimal("10000") * Decimal("1") * Decimal("1.0") +  # USDC
            Decimal("1") * Decimal("50000") * Decimal("0.95") +  # BTC
            Decimal("100") * Decimal("100") * Decimal("0.9")  # SOL
        )
        assert total_collateral == expected


class TestBackpackAutoBorrow:
    """Test Backpack auto-borrow functionality."""
    
    def test_check_borrow_needed(self, logger):
        """Test checking if borrow is needed."""
        # Arrange
        auto_borrow = BackpackAutoBorrow(logger)
        
        # Act - no borrow needed
        needs_borrow, shortage = auto_borrow.check_borrow_needed(
            required_usdc=Decimal("1000"),
            available_usdc=Decimal("2000"),
        )
        
        # Assert
        assert needs_borrow is False
        assert shortage == Decimal("0")
        
        # Act - borrow needed
        needs_borrow, shortage = auto_borrow.check_borrow_needed(
            required_usdc=Decimal("3000"),
            available_usdc=Decimal("2000"),
        )
        
        # Assert
        assert needs_borrow is True
        assert shortage == Decimal("1000")  # Actual shortage amount


class TestUnifiedExecutionClients:
    """Test unified execution clients integration."""
    
    @pytest.mark.asyncio
    async def test_create_unified_clients(self, event_loop):
        """Test creating unified spot and futures clients."""
        # Arrange
        trader_id = TraderId("TESTER-001")
        clock = LiveClock()
        msgbus = MessageBus(
            trader_id=trader_id,
            clock=clock,
        )
        cache = Cache()
        
        with patch("nautilus_trader.adapters.backpack.factories.get_cached_backpack_http_client") as mock_http:
            mock_http.return_value = MagicMock()
            
            # Act
            spot_client, futures_client = create_backpack_unified_execution_clients(
                loop=event_loop,
                msgbus=msgbus,
                cache=cache,
                clock=clock,
            )
            
            # Assert
            assert isinstance(spot_client, BackpackExecutionClient)
            assert isinstance(futures_client, BackpackFuturesExecutionClient)
            assert spot_client._account_manager is not None
            assert futures_client._account_manager is not None
            # Both clients should share the same account manager
            assert spot_client._account_manager is futures_client._account_manager
    
    @pytest.mark.asyncio
    async def test_unified_account_state_update(self, event_loop):
        """Test updating account state with unified account."""
        # Arrange
        trader_id = TraderId("TESTER-001")
        clock = LiveClock()
        msgbus = MessageBus(
            trader_id=trader_id,
            clock=clock,
        )
        cache = Cache()
        
        with patch("nautilus_trader.adapters.backpack.factories.get_cached_backpack_http_client") as mock_http:
            mock_http_client = MagicMock()
            mock_http.return_value = mock_http_client
            
            spot_client, futures_client = create_backpack_unified_execution_clients(
                loop=event_loop,
                msgbus=msgbus,
                cache=cache,
                clock=clock,
            )
            
            # Mock account manager methods
            spot_client._account_manager.refresh_account_state = AsyncMock(
                return_value=BackpackUnifiedAccount(
                    accountId="unified",
                    subaccountId=None,
                    balances=[],
                    totalCollateral="10000",
                    availableCollateral="8000",
                    collateralWeights=[],
                    initialMarginRate="0.1",
                    maintenanceMarginRate="0.05",
                    marginRatio="0.01",
                    spotBalances=[],
                    futuresPositions=[],
                    borrowPositions=[],
                    totalBorrowLiability="0",
                    unsettledBalances="0",
                    unrealizedPnl="0",
                    realizedPnl="0",
                    liquidationPrice=None,
                    timeTillLiquidation=None,
                    limits={},
                    timestamp=0,
                )
            )
            spot_client._account_manager.get_unified_positions = MagicMock(return_value=[])
            spot_client._account_manager.calculate_total_margin_used = MagicMock(
                return_value=Decimal("1000")
            )
            spot_client._account_manager._nautilus_account = MagicMock()
            spot_client._account_manager._nautilus_account.balances = MagicMock(return_value=[])
            spot_client._account_manager._nautilus_account.margins = MagicMock(return_value=[])
            
            # Act
            await spot_client._update_account_state()
            
            # Assert
            spot_client._account_manager.refresh_account_state.assert_called_once()
            spot_client._account_manager.get_unified_positions.assert_called_once()
            spot_client._account_manager.calculate_total_margin_used.assert_called_once()


@pytest.mark.asyncio
async def test_integration_flow():
    """Test complete integration flow."""
    # This test demonstrates the full integration flow
    # In production, both clients share the same account manager
    # and work together to manage the unified account
    
    # 1. Create unified clients
    # 2. Initialize account
    # 3. Submit spot order (with auto-borrow if needed)
    # 4. Submit futures order
    # 5. Update account state (includes both spot and futures)
    # 6. Check margin requirements across all positions
    
    # This would require a full test environment with mocked exchange responses
    pass