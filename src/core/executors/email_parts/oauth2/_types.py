"""
OAuth2 — Data types: grant type enum, config, and token dataclasses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class OAuth2GrantType(str, Enum):
    """Supported OAuth2 grant types."""
    CLIENT_CREDENTIALS = "client_credentials"
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"


@dataclass
class OAuth2Config:
    """Configuration for an OAuth2 service registration.

    All fields can be populated from environment variables via
    config_from_env() or register_service_from_env().
    """
    client_id: str = ""
    client_secret: str = ""
    token_url: str = ""
    authorize_url: str = ""
    scopes: List[str] = field(default_factory=list)
    redirect_uri: str = ""
    grant_type: OAuth2GrantType = OAuth2GrantType.CLIENT_CREDENTIALS
    resource: str = ""  # For resource-parameter flows (e.g. Azure AD v1)

    @property
    def is_configured(self) -> bool:
        """Check if minimum required fields are set."""
        return bool(self.client_id and self.token_url)


@dataclass
class OAuth2Token:
    """An OAuth2 access token with metadata.

    Provides convenience properties for checking expiry and refreshability.
    """
    access_token: str = ""
    token_type: str = "Bearer"
    expires_at: float = 0.0  # Unix timestamp
    refresh_token: str = ""
    scope: str = ""
    id_token: str = ""

    @property
    def is_expired(self) -> bool:
        """Check if the token has expired (with 60-second safety margin)."""
        if self.expires_at <= 0:
            return True
        return time.time() >= (self.expires_at - 60)

    @property
    def is_refreshable(self) -> bool:
        """Check if the token can be refreshed."""
        return bool(self.refresh_token)

    @property
    def authorization_header(self) -> str:
        """Get the Authorization header value."""
        return f"{self.token_type} {self.access_token}"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize token to dictionary (excludes access_token for safety)."""
        return {
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "is_expired": self.is_expired,
            "is_refreshable": self.is_refreshable,
            "scope": self.scope,
            "has_id_token": bool(self.id_token),
        }
