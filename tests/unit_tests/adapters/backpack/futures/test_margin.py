"""
Unit tests for BackpackFuturesMarginCalculator.
"""

from decimal import Decimal

import pytest

from nautilus_trader.adapters.backpack.futures.margin import BackpackFuturesMarginCalculator


class TestBackpackFuturesMarginCalculator:
    """Test suite for Backpack futures margin calculations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = BackpackFuturesMarginCalculator()
        
    def test_initial_margin_calculation(self):
        """Test initial margin calculation with leverage."""
        quantity = Decimal("100")  # 100 SOL
        price = Decimal("50")       # $50 per SOL
        leverage = 10              # 10x leverage
        
        initial_margin = self.calculator.calculate_initial_margin(
            quantity=quantity,
            price=price,
            leverage=leverage,
        )
        
        # Initial margin = (position_size * entry_price) / leverage
        # = (100 * 50) / 10 = 500
        assert initial_margin == Decimal("500")
        
    def test_maintenance_margin_tiered_small_position(self):
        """Test maintenance margin for small position (tier 1)."""
        quantity = Decimal("100")  # 100 units
        price = Decimal("50")      # $50 per unit = $5,000 position
        
        maintenance_margin = self.calculator.calculate_maintenance_margin(quantity, price)
        
        # Tier 1: 0.4% for positions up to $10,000 + 0 maint_amount
        # = 5000 * 0.004 + 0 = 20
        assert maintenance_margin == Decimal("20")
        
    def test_maintenance_margin_tiered_medium_position(self):
        """Test maintenance margin for medium position (multiple tiers)."""
        quantity = Decimal("1500")  # 1500 units
        price = Decimal("50")       # $50 per unit = $75,000 position
        
        maintenance_margin = self.calculator.calculate_maintenance_margin(quantity, price)
        
        # Tier 3: notional_cap=$250,000, rate=1.0%, maint_amount=$260
        # = 75000 * 0.01 + 260 = 750 + 260 = 1010
        assert maintenance_margin == Decimal("1010")
        
    def test_maintenance_margin_tiered_large_position(self):
        """Test maintenance margin for large position (all tiers)."""
        quantity = Decimal("10000")  # 10000 units
        price = Decimal("50")        # $50 per unit = $500,000 position
        
        maintenance_margin = self.calculator.calculate_maintenance_margin(quantity, price)
        
        # Tier 4: notional_cap=$1,000,000, rate=2.5%, maint_amount=$4,010
        # = 500000 * 0.025 + 4010 = 12500 + 4010 = 16510
        assert maintenance_margin == Decimal("16510")
        
    def test_liquidation_price_long_position(self):
        """Test liquidation price calculation for long position."""
        entry_price = Decimal("100")
        quantity = Decimal("10")
        leverage = 10
        collateral = Decimal("100")  # Initial margin
        
        liquidation_price = self.calculator.calculate_liquidation_price(
            quantity=quantity,
            entry_price=entry_price,
            is_long=True,
            collateral=collateral,
            leverage=leverage,
        )
        
        # For long position with 10x leverage:
        # Liquidation price = entry_price * (1 - 1/leverage + mm_rate)
        # mm_rate for $1000 notional = 0.004 (first tier)
        # ≈ 100 * (1 - 0.1 + 0.004) = 100 * 0.904 = 90.4
        assert liquidation_price == pytest.approx(Decimal("90.4"), rel=Decimal("0.01"))
        
    def test_liquidation_price_short_position(self):
        """Test liquidation price calculation for short position."""
        entry_price = Decimal("100")
        quantity = Decimal("10")
        leverage = 10
        collateral = Decimal("100")  # Initial margin
        
        liquidation_price = self.calculator.calculate_liquidation_price(
            quantity=quantity,
            entry_price=entry_price,
            is_long=False,
            collateral=collateral,
            leverage=leverage,
        )
        
        # For short position with 10x leverage:
        # Liquidation price = entry_price * (1 + 1/leverage - mm_rate)
        # mm_rate for $1000 notional = 0.004 (first tier)
        # ≈ 100 * (1 + 0.1 - 0.004) = 100 * 1.096 = 109.6
        assert liquidation_price == pytest.approx(Decimal("109.6"), rel=Decimal("0.01"))
        
    def test_margin_ratio_calculation(self):
        """Test margin ratio calculation."""
        position_value = Decimal("10000")
        unrealized_pnl = Decimal("100")
        collateral = Decimal("2000")
        maintenance_margin = Decimal("500")
        
        margin_ratio = self.calculator.calculate_margin_ratio(
            position_value=position_value,
            unrealized_pnl=unrealized_pnl,
            collateral=collateral,
            maintenance_margin=maintenance_margin,
        )
        
        # Margin ratio = maintenance_margin / (collateral + unrealized_pnl)
        # = 500 / (2000 + 100) = 500 / 2100 = 0.238
        assert margin_ratio == pytest.approx(Decimal("0.238"), rel=Decimal("0.01"))
        
    def test_margin_ratio_zero_collateral(self):
        """Test margin ratio with zero collateral."""
        position_value = Decimal("10000")
        unrealized_pnl = Decimal("-100")
        collateral = Decimal("0")
        maintenance_margin = Decimal("500")
        
        margin_ratio = self.calculator.calculate_margin_ratio(
            position_value=position_value,
            unrealized_pnl=unrealized_pnl,
            collateral=collateral,
            maintenance_margin=maintenance_margin,
        )
        
        # Should return 1.0 (100%) when collateral is 0 or negative equity
        assert margin_ratio == Decimal("1.0")
        
    def test_funding_payment_positive_rate(self):
        """Test funding payment with positive rate."""
        position_value = Decimal("10000")  # $10,000 position
        funding_rate = Decimal("0.01")     # 1% funding rate (positive)
        
        payment = self.calculator.calculate_funding_payment(
            position_value=position_value,
            funding_rate=funding_rate,
        )
        
        # Payment = position_value * funding_rate
        # = 10000 * 0.01 = 100
        # Note: Sign depends on position side (handled externally)
        assert payment == Decimal("100")
        
    def test_funding_payment_negative_rate(self):
        """Test funding payment with negative rate."""
        position_value = Decimal("10000")   # $10,000 position
        funding_rate = Decimal("-0.01")     # -1% funding rate (negative)
        
        payment = self.calculator.calculate_funding_payment(
            position_value=position_value,
            funding_rate=funding_rate,
        )
        
        # Payment = position_value * funding_rate
        # = 10000 * -0.01 = -100
        assert payment == Decimal("-100")
        
    # Removed duplicate funding tests - position side is handled externally
        
    def test_max_position_size_calculation(self):
        """Test maximum position size calculation based on available balance."""
        available_balance = Decimal("1000")  # $1,000 available
        price = Decimal("50")                # $50 per unit
        leverage = 10                        # 10x leverage
        
        max_size = self.calculator.calculate_max_position_size(
            available_balance=available_balance,
            price=price,
            leverage=leverage,
        )
        
        # Max position value = available_balance * leverage = 1000 * 10 = 10000
        # Max position size = max_value / entry_price = 10000 / 50 = 200
        assert max_size == Decimal("200")
        
    # Removed tests for methods that don't exist in the calculator
    # (is_margin_healthy, set_leverage, get_leverage)