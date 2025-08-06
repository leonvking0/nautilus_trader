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

"""Exceptions for the Backpack adapter."""

from nautilus_trader.adapters.backpack.common.enums import BackpackErrorCode


class BackpackError(Exception):
    """Base exception for Backpack-related errors."""

    def __init__(self, code: int, message: str) -> None:
        """
        Initialize the BackpackError.

        Parameters
        ----------
        code : int
            The error code from Backpack API.
        message : str
            The error message.

        """
        self.code = code
        self.message = message
        super().__init__(f"Backpack API error {code}: {message}")


class BackpackClientError(BackpackError):
    """Exception for Backpack client-side errors (4xx status codes)."""

    pass


class BackpackServerError(BackpackError):
    """Exception for Backpack server-side errors (5xx status codes)."""

    pass


class BackpackAuthenticationError(BackpackClientError):
    """Exception for authentication-related errors."""

    pass


class BackpackRateLimitError(BackpackClientError):
    """Exception for rate limit errors."""

    pass


class BackpackInsufficientBalanceError(BackpackClientError):
    """Exception for insufficient balance errors."""

    pass


class BackpackOrderNotFoundError(BackpackClientError):
    """Exception for order not found errors."""

    pass


def parse_backpack_error(code: int, message: str) -> BackpackError:
    """
    Parse a Backpack error code and message into the appropriate exception.

    Parameters
    ----------
    code : int
        The error code from Backpack API.
    message : str
        The error message.

    Returns
    -------
    BackpackError
        The appropriate exception for the error.

    """
    # Authentication errors
    if code in (
        BackpackErrorCode.UNAUTHORIZED.value,
        BackpackErrorCode.INVALID_SIGNATURE.value,
        BackpackErrorCode.INVALID_API_KEY.value,
    ):
        return BackpackAuthenticationError(code, message)
    
    # Rate limit error
    if code == BackpackErrorCode.TOO_MANY_REQUESTS.value:
        return BackpackRateLimitError(code, message)
    
    # Insufficient balance
    if code == BackpackErrorCode.INSUFFICIENT_BALANCE.value:
        return BackpackInsufficientBalanceError(code, message)
    
    # Order not found
    if code == BackpackErrorCode.ORDER_NOT_FOUND.value:
        return BackpackOrderNotFoundError(code, message)
    
    # Server errors (5xx equivalent)
    if code in (
        BackpackErrorCode.DISCONNECTED.value,
        BackpackErrorCode.SERVICE_UNAVAILABLE.value,
        BackpackErrorCode.TIMEOUT.value,
        BackpackErrorCode.UNEXPECTED_RESPONSE.value,
    ):
        return BackpackServerError(code, message)
    
    # Default to client error
    return BackpackClientError(code, message)