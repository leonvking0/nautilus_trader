"""
Unit tests for BackpackFuturesPositionManager.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from nautilus_trader.adapters.backpack.futures.position_manager import BackpackFuturesPositionManager
from nautilus_trader.adapters.backpack.futures.types import BackpackPosition
from nautilus_trader.common.component import Logger


class TestBackpackFuturesPositionManager:
    """Test suite for Backpack futures position manager."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.logger = MagicMock(spec=Logger)
        self.manager = BackpackFuturesPositionManager(logger=self.logger)
        
        # Create test position
        self.test_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_123",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            mark_price=Decimal("105"),
            liquidation_price=Decimal("90"),
            unrealized_pnl=Decimal("50"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.3"),
            initial_margin=Decimal("100"),
            maintenance_margin=Decimal("25"),
        )
        
    def test_update_position_new(self):
        """Test updating a new position."""
        self.manager.update_position(self.test_position)
        
        # Verify position is stored
        assert "pos_123" in self.manager._positions
        assert self.manager._positions["pos_123"] == self.test_position
        
        # Verify position by symbol mapping
        assert self.manager._positions_by_symbol["SOL-PERP"] == "pos_123"
        
    def test_update_position_existing(self):
        """Test updating an existing position."""
        # Add initial position
        self.manager.update_position(self.test_position)
        
        # Update position with new values
        updated_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_123",
            side="long",
            quantity=Decimal("15"),  # Increased quantity
            entry_price=Decimal("102"),  # New average entry
            mark_price=Decimal("110"),
            liquidation_price=Decimal("92"),
            unrealized_pnl=Decimal("120"),
            realized_pnl=Decimal("10"),
            margin_ratio=Decimal("0.35"),
            initial_margin=Decimal("150"),
            maintenance_margin=Decimal("38"),
        )
        
        self.manager.update_position(updated_position)
        
        # Verify position is updated
        stored_position = self.manager._positions["pos_123"]
        assert stored_position.quantity == Decimal("15")
        assert stored_position.entry_price == Decimal("102")
        assert stored_position.unrealized_pnl == Decimal("120")
        
    def test_close_position(self):
        """Test closing a position."""
        # Add position
        self.manager.update_position(self.test_position)
        
        # Close position
        self.manager.close_position("pos_123", Decimal("100"))
        
        # Verify position is marked as closed
        closed_position = self.manager._positions["pos_123"]
        assert closed_position.quantity == Decimal("0")
        assert closed_position.realized_pnl == Decimal("100")
        
        # Verify position is removed from symbol mapping
        assert "SOL-PERP" not in self.manager._positions_by_symbol
        
    def test_close_nonexistent_position(self):
        """Test closing a position that doesn't exist."""
        self.manager.close_position("nonexistent", Decimal("0"))
        
        # Should log warning
        self.logger.warning.assert_called_once()
        
    def test_get_position_by_id(self):
        """Test retrieving position by ID."""
        self.manager.update_position(self.test_position)
        
        position = self.manager.get_position("pos_123")
        
        assert position == self.test_position
        
    def test_get_position_by_symbol(self):
        """Test retrieving position by symbol."""
        self.manager.update_position(self.test_position)
        
        position = self.manager.get_position_by_symbol("SOL-PERP")
        
        assert position == self.test_position
        
    def test_get_nonexistent_position(self):
        """Test retrieving non-existent position."""
        position = self.manager.get_position("nonexistent")
        
        assert position is None
        
    def test_get_all_positions(self):
        """Test retrieving all positions."""
        # Add multiple positions
        position2 = BackpackPosition(
            symbol="BTC-PERP",
            position_id="pos_456",
            side="short",
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            mark_price=Decimal("49500"),
            liquidation_price=Decimal("55000"),
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.25"),
            initial_margin=Decimal("5000"),
            maintenance_margin=Decimal("1250"),
        )
        
        self.manager.update_position(self.test_position)
        self.manager.update_position(position2)
        
        all_positions = self.manager.get_all_positions()
        
        assert len(all_positions) == 2
        assert "pos_123" in all_positions
        assert "pos_456" in all_positions
        
    def test_get_open_positions(self):
        """Test retrieving only open positions."""
        # Add open position
        self.manager.update_position(self.test_position)
        
        # Add closed position
        closed_position = BackpackPosition(
            symbol="BTC-PERP",
            position_id="pos_456",
            side="short",
            quantity=Decimal("0"),  # Closed
            entry_price=Decimal("50000"),
            mark_price=Decimal("50000"),
            liquidation_price=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            realized_pnl=Decimal("100"),
            margin_ratio=Decimal("0"),
            initial_margin=Decimal("0"),
            maintenance_margin=Decimal("0"),
        )
        self.manager.update_position(closed_position)
        
        open_positions = self.manager.get_open_positions()
        
        assert len(open_positions) == 1
        assert "pos_123" in open_positions
        assert "pos_456" not in open_positions
        
    def test_calculate_unrealized_pnl_long(self):
        """Test unrealized PnL calculation for long position."""
        entry_price = Decimal("100")
        mark_price = Decimal("110")
        quantity = Decimal("10")
        
        pnl = self.manager.calculate_unrealized_pnl(
            side="long",
            entry_price=entry_price,
            mark_price=mark_price,
            quantity=quantity,
        )
        
        # PnL = (mark_price - entry_price) * quantity
        # = (110 - 100) * 10 = 100
        assert pnl == Decimal("100")
        
    def test_calculate_unrealized_pnl_short(self):
        """Test unrealized PnL calculation for short position."""
        entry_price = Decimal("100")
        mark_price = Decimal("95")
        quantity = Decimal("10")
        
        pnl = self.manager.calculate_unrealized_pnl(
            side="short",
            entry_price=entry_price,
            mark_price=mark_price,
            quantity=quantity,
        )
        
        # PnL = (entry_price - mark_price) * quantity
        # = (100 - 95) * 10 = 50
        assert pnl == Decimal("50")
        
    def test_update_mark_price(self):
        """Test updating mark price for a position."""
        self.manager.update_position(self.test_position)
        
        new_mark_price = Decimal("115")
        self.manager.update_mark_price("SOL-PERP", new_mark_price)
        
        position = self.manager.get_position("pos_123")
        assert position.mark_price == new_mark_price
        
        # Verify unrealized PnL is recalculated
        # PnL = (115 - 100) * 10 = 150
        assert position.unrealized_pnl == Decimal("150")
        
    def test_reconcile_positions_add_missing(self):
        """Test reconciliation adds missing positions."""
        exchange_positions = [
            BackpackPosition(
                symbol="SOL-PERP",
                position_id="pos_new",
                side="long",
                quantity=Decimal("5"),
                entry_price=Decimal("98"),
                mark_price=Decimal("100"),
                liquidation_price=Decimal("88"),
                unrealized_pnl=Decimal("10"),
                realized_pnl=Decimal("0"),
                margin_ratio=Decimal("0.2"),
                initial_margin=Decimal("49"),
                maintenance_margin=Decimal("12"),
            )
        ]
        
        discrepancies = self.manager.reconcile_positions(exchange_positions)
        
        # Verify position was added
        assert "pos_new" in self.manager._positions
        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "missing_local"
        
    def test_reconcile_positions_remove_extra(self):
        """Test reconciliation removes extra local positions."""
        # Add local position
        self.manager.update_position(self.test_position)
        
        # Exchange has no positions
        exchange_positions = []
        
        discrepancies = self.manager.reconcile_positions(exchange_positions)
        
        # Verify position was marked as closed
        position = self.manager.get_position("pos_123")
        assert position.quantity == Decimal("0")
        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "extra_local"
        
    def test_reconcile_positions_update_mismatched(self):
        """Test reconciliation updates mismatched positions."""
        # Add local position
        self.manager.update_position(self.test_position)
        
        # Exchange has different values
        exchange_position = BackpackPosition(
            symbol="SOL-PERP",
            position_id="pos_123",
            side="long",
            quantity=Decimal("12"),  # Different quantity
            entry_price=Decimal("101"),  # Different entry
            mark_price=Decimal("105"),
            liquidation_price=Decimal("91"),
            unrealized_pnl=Decimal("48"),
            realized_pnl=Decimal("5"),
            margin_ratio=Decimal("0.32"),
            initial_margin=Decimal("121"),
            maintenance_margin=Decimal("30"),
        )
        
        discrepancies = self.manager.reconcile_positions([exchange_position])
        
        # Verify position was updated
        position = self.manager.get_position("pos_123")
        assert position.quantity == Decimal("12")
        assert position.entry_price == Decimal("101")
        assert len(discrepancies) == 1
        assert discrepancies[0]["type"] == "mismatch"
        
    def test_get_total_unrealized_pnl(self):
        """Test calculating total unrealized PnL across all positions."""
        # Add multiple positions
        position2 = BackpackPosition(
            symbol="BTC-PERP",
            position_id="pos_456",
            side="short",
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            mark_price=Decimal("49500"),
            liquidation_price=Decimal("55000"),
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.25"),
            initial_margin=Decimal("5000"),
            maintenance_margin=Decimal("1250"),
        )
        
        self.manager.update_position(self.test_position)
        self.manager.update_position(position2)
        
        total_pnl = self.manager.get_total_unrealized_pnl()
        
        # Total = 50 + 500 = 550
        assert total_pnl == Decimal("550")
        
    def test_get_total_margin_used(self):
        """Test calculating total margin used across all positions."""
        # Add multiple positions
        position2 = BackpackPosition(
            symbol="BTC-PERP",
            position_id="pos_456",
            side="short",
            quantity=Decimal("1"),
            entry_price=Decimal("50000"),
            mark_price=Decimal("49500"),
            liquidation_price=Decimal("55000"),
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("0"),
            margin_ratio=Decimal("0.25"),
            initial_margin=Decimal("5000"),
            maintenance_margin=Decimal("1250"),
        )
        
        self.manager.update_position(self.test_position)
        self.manager.update_position(position2)
        
        total_margin = self.manager.get_total_margin_used()
        
        # Total = 100 + 5000 = 5100
        assert total_margin == Decimal("5100")
        
    def test_clear_all_positions(self):
        """Test clearing all positions."""
        # Add multiple positions
        self.manager.update_position(self.test_position)
        
        self.manager.clear_all_positions()
        
        assert len(self.manager._positions) == 0
        assert len(self.manager._positions_by_symbol) == 0