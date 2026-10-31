# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Authentication provider implementations."""


# Type annotations
from __future__ import annotations
from typing import Dict, Final, Callable

# Standard libs
import os

# External libs
from fastmcp.server.auth import OIDCProxy, AuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier

# Internal libs
from cluster_mcp.core.token import ISSUER, AUDIENCE, ALGORITHM

# Public interface
__all__ = ['create_jwt_auth', 'create_auth_oidc', 'AUTH_MODES']


def create_jwt_auth() -> JWTVerifier:
    """Create JWT-based authentication provider."""
    secret = os.environ.get('JWT_SECRET')
    if not secret:
        raise ValueError('JWT_SECRET environment variable required for jwt auth mode')
    if len(secret) < 32:
        raise ValueError('JWT_SECRET must be at least 32 characters')
    return JWTVerifier(
        public_key=secret,
        issuer=ISSUER,
        audience=AUDIENCE,
        algorithm=ALGORITHM,
    )


def create_auth_oidc() -> OIDCProxy:
    """Create authentication provider based on mode."""

    config_url = os.environ.get('OIDC_CONFIG_URL')
    client_id = os.environ.get('OIDC_CLIENT_ID')
    client_secret = os.environ.get('OIDC_CLIENT_SECRET')
    base_url = os.environ.get('MCP_BASE_URL')

    if not all([config_url, client_id, client_secret, base_url]):
        raise ValueError(
            'OIDC auth requires: OIDC_CONFIG_URL, OIDC_CLIENT_ID, '
            'OIDC_CLIENT_SECRET, MCP_BASE_URL'
        )

    return OIDCProxy(
        config_url=config_url,
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        # Held at the FastMCP 2.x posture pending a deliberate decision: FastMCP 4 turns both on by
        # default (fetching client-supplied metadata documents, CIMD, and forwarding the `resource`
        # parameter upstream).
        enable_cimd=False,
        forward_resource=False,
    )


AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider | None]]] = {
    'none': lambda: None,
    'jwt': create_jwt_auth,
    'oidc': create_auth_oidc,
}
