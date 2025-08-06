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

"""Backpack user data response schemas."""

import msgspec


class BackpackUserPreferences(msgspec.Struct, frozen=True):
    """User preferences configuration."""

    default_order_type: str | None = "Limit"
    default_time_in_force: str | None = "GTC"
    post_only_default: bool | None = False
    reduce_only_default: bool | None = False
    display_name: str | None = None
    timezone: str | None = "UTC"
    language: str | None = "en"
    theme: str | None = "dark"


class BackpackUserPermissions(msgspec.Struct, frozen=True):
    """User account permissions."""

    can_trade: bool
    can_withdraw: bool
    can_deposit: bool
    trading_enabled: bool
    funding_enabled: bool
    two_factor_enabled: bool
    api_enabled: bool
    read_only: bool | None = False


class BackpackUserNotifications(msgspec.Struct, frozen=True):
    """User notification preferences."""

    email_enabled: bool | None = True
    email_trade_fills: bool | None = True
    email_order_updates: bool | None = False
    email_withdrawals: bool | None = True
    email_deposits: bool | None = True
    email_liquidations: bool | None = True
    push_enabled: bool | None = False
    push_trade_fills: bool | None = False
    push_order_updates: bool | None = False
    push_price_alerts: bool | None = False


class BackpackUserLimits(msgspec.Struct, frozen=True):
    """User account limits and restrictions."""

    max_open_orders: int | None = None
    max_open_orders_per_symbol: int | None = None
    daily_withdrawal_limit: str | None = None
    monthly_withdrawal_limit: str | None = None
    maker_fee_rate: str | None = None
    taker_fee_rate: str | None = None
    tier: str | None = None
    vip_level: int | None = 0


class BackpackUserStats(msgspec.Struct, frozen=True):
    """User trading statistics."""

    total_volume_30d: str | None = None
    total_volume_24h: str | None = None
    total_trades_30d: int | None = None
    total_trades_24h: int | None = None
    maker_volume_30d: str | None = None
    taker_volume_30d: str | None = None
    fees_paid_30d: str | None = None
    fees_paid_24h: str | None = None
    pnl_30d: str | None = None
    pnl_24h: str | None = None


class BackpackUserProfile(msgspec.Struct, frozen=True):
    """User profile information."""

    user_id: str
    email: str | None = None
    username: str | None = None
    created_at: int | None = None
    last_login: int | None = None
    kyc_level: int | None = 0
    kyc_verified: bool | None = False
    country: str | None = None
    referral_code: str | None = None
    referred_by: str | None = None


class BackpackApiKey(msgspec.Struct, frozen=True):
    """API key information."""

    key_id: str
    name: str | None = None
    permissions: list[str] | None = None
    created_at: int | None = None
    last_used: int | None = None
    expires_at: int | None = None
    ip_whitelist: list[str] | None = None
    is_active: bool | None = True


class BackpackUserSession(msgspec.Struct, frozen=True):
    """User session information."""

    session_id: str
    user_id: str
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: int
    expires_at: int
    is_active: bool | None = True


class BackpackUser(msgspec.Struct, frozen=True):
    """Complete user account information."""

    profile: BackpackUserProfile
    preferences: BackpackUserPreferences | None = None
    permissions: BackpackUserPermissions | None = None
    notifications: BackpackUserNotifications | None = None
    limits: BackpackUserLimits | None = None
    stats: BackpackUserStats | None = None


class BackpackDepositAddress(msgspec.Struct, frozen=True):
    """Deposit address information."""

    blockchain: str
    address: str
    tag: str | None = None
    created_at: int | None = None
    is_default: bool | None = False


class BackpackWithdrawal(msgspec.Struct, frozen=True):
    """Withdrawal transaction information."""

    id: str
    blockchain: str
    address: str
    tag: str | None = None
    amount: str
    fee: str
    status: str
    transaction_hash: str | None = None
    created_at: int
    processed_at: int | None = None
    confirmed_at: int | None = None
    confirmations: int | None = None


class BackpackDeposit(msgspec.Struct, frozen=True):
    """Deposit transaction information."""

    id: str
    blockchain: str
    address: str
    tag: str | None = None
    amount: str
    fee: str | None = None
    status: str
    transaction_hash: str | None = None
    provider_id: str | None = None
    created_at: int
    credited_at: int | None = None
    confirmations: int | None = None
    required_confirmations: int | None = None


class BackpackTransferHistory(msgspec.Struct, frozen=True):
    """Internal transfer history."""

    id: str
    from_account: str
    to_account: str
    asset: str
    amount: str
    status: str
    created_at: int
    completed_at: int | None = None
    notes: str | None = None


class BackpackReferralInfo(msgspec.Struct, frozen=True):
    """User referral information."""

    referral_code: str
    referral_link: str
    total_referrals: int
    active_referrals: int
    referral_volume_30d: str | None = None
    referral_commission_30d: str | None = None
    commission_rate: str
    tier: str | None = None


class BackpackSecurityLog(msgspec.Struct, frozen=True):
    """Security event log entry."""

    event_id: str
    event_type: str
    ip_address: str | None = None
    user_agent: str | None = None
    location: str | None = None
    timestamp: int
    status: str
    details: str | None = None


class BackpackTradingFees(msgspec.Struct, frozen=True):
    """Trading fee structure."""

    tier: str
    maker_fee: str
    taker_fee: str
    volume_30d: str
    volume_requirement: str | None = None
    next_tier_volume: str | None = None
    discount_rate: str | None = None
    uses_token_discount: bool | None = False