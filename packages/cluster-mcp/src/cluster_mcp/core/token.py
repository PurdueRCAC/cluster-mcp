# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""JWT token generation for cluster-mcp."""


# Type annotations
from __future__ import annotations
from typing import Final

# Standard libs
from datetime import datetime, timezone, timedelta

# External libs
import jwt

# Public interface
__all__ = ['ISSUER', 'AUDIENCE', 'ALGORITHM', 'generate_token']


# Constant claims
ISSUER: Final[str] = 'rcac-mcp'
AUDIENCE: Final[str] = 'rcac-mcp'
ALGORITHM: Final[str] = 'HS256'


def generate_token(secret: str, lifetime: int = 3600, subject: str | None = None) -> str:
    """
    Generate a JWT token for authenticating with the MCP server.

    Args:
        secret: The shared secret key for HS256 signing.
        lifetime: Token lifetime in seconds (default: 3600 = 1 hour).
        subject: Optional subject identifier (username or user ID).

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        'iss': ISSUER,
        'aud': AUDIENCE,
        'iat': now,
        'exp': now + timedelta(seconds=lifetime),
    }
    if subject:
        payload['sub'] = subject
    return jwt.encode(payload, secret, algorithm=ALGORITHM)
