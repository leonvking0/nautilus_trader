// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

//! HTTP error types for Lighter API client.

use std::fmt;

/// Error type for Lighter HTTP client operations.
#[derive(Debug)]
pub enum LighterHttpError {
    /// Rate limit exceeded (HTTP 429).
    RateLimited {
        /// Optional retry-after duration in seconds.
        retry_after_secs: Option<u64>,
        /// Response body message.
        message: String,
    },
    /// Request failed with non-success status.
    RequestFailed {
        /// HTTP status code.
        status: u16,
        /// Response body message.
        message: String,
    },
    /// Network or connection error.
    Network(String),
    /// JSON deserialization error.
    Decode(String),
    /// Other error.
    Other(anyhow::Error),
}

impl fmt::Display for LighterHttpError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::RateLimited {
                retry_after_secs,
                message,
            } => {
                if let Some(secs) = retry_after_secs {
                    write!(f, "Rate limited (retry after {secs}s): {message}")
                } else {
                    write!(f, "Rate limited: {message}")
                }
            }
            Self::RequestFailed { status, message } => {
                write!(f, "Request failed ({status}): {message}")
            }
            Self::Network(msg) => write!(f, "Network error: {msg}"),
            Self::Decode(msg) => write!(f, "Decode error: {msg}"),
            Self::Other(err) => write!(f, "{err}"),
        }
    }
}

impl std::error::Error for LighterHttpError {}

impl LighterHttpError {
    /// Returns true if this is a rate limit error.
    #[must_use]
    pub const fn is_rate_limited(&self) -> bool {
        matches!(self, Self::RateLimited { .. })
    }

    /// Returns the retry-after duration in seconds if this is a rate limit error.
    #[must_use]
    pub const fn retry_after_secs(&self) -> Option<u64> {
        match self {
            Self::RateLimited {
                retry_after_secs, ..
            } => *retry_after_secs,
            _ => None,
        }
    }

    /// Returns true if this error is transient and should be retried.
    #[must_use]
    pub const fn is_transient(&self) -> bool {
        match self {
            Self::RateLimited { .. } => true,
            Self::Network(_) => true,
            Self::RequestFailed { status, .. } => {
                // Retry on 5xx server errors
                *status >= 500
            }
            Self::Decode(_) | Self::Other(_) => false,
        }
    }
}

impl From<anyhow::Error> for LighterHttpError {
    fn from(err: anyhow::Error) -> Self {
        Self::Other(err)
    }
}

/// Parse the Retry-After header value to seconds.
pub fn parse_retry_after(header_value: &str) -> Option<u64> {
    // Try parsing as integer seconds first
    if let Ok(secs) = header_value.trim().parse::<u64>() {
        return Some(secs);
    }

    // Try parsing as HTTP-date (simplified: just extract seconds)
    // For production, this should use proper HTTP date parsing
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rate_limited_display() {
        let err = LighterHttpError::RateLimited {
            retry_after_secs: Some(60),
            message: "Too many requests".to_string(),
        };
        assert!(err.to_string().contains("Rate limited"));
        assert!(err.to_string().contains("60s"));
    }

    #[test]
    fn test_is_rate_limited() {
        let err = LighterHttpError::RateLimited {
            retry_after_secs: None,
            message: "test".to_string(),
        };
        assert!(err.is_rate_limited());

        let err = LighterHttpError::RequestFailed {
            status: 400,
            message: "test".to_string(),
        };
        assert!(!err.is_rate_limited());
    }

    #[test]
    fn test_is_transient() {
        assert!(
            LighterHttpError::RateLimited {
                retry_after_secs: None,
                message: "test".to_string(),
            }
            .is_transient()
        );

        assert!(LighterHttpError::Network("timeout".to_string()).is_transient());

        assert!(
            LighterHttpError::RequestFailed {
                status: 503,
                message: "test".to_string(),
            }
            .is_transient()
        );

        assert!(
            !LighterHttpError::RequestFailed {
                status: 400,
                message: "test".to_string(),
            }
            .is_transient()
        );
    }

    #[test]
    fn test_parse_retry_after() {
        assert_eq!(parse_retry_after("60"), Some(60));
        assert_eq!(parse_retry_after(" 120 "), Some(120));
        assert_eq!(parse_retry_after("invalid"), None);
    }
}
