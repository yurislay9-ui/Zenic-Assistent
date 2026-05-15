"""
ZENIC-AGENTS — OAuth2 Token Manager (Phase 2)

OAuth2 token management for services that require authorization
(Microsoft Graph API, ServiceNow, custom OAuth2 providers, etc.).

Features:
  - Multiple grant types (client_credentials, authorization_code, refresh_token)
  - Automatic token refresh with thread-safe locking
  - PKCE support for authorization code flow
  - Environment variable configuration helpers
  - Global singleton manager
  - Optional aiohttp dependency (graceful fallback)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zenic_agents.email_parts.oauth2")

# ──────────────────────────────────────────────────────────────
#  OPTIONAL DEPENDENCY CHECK
# ──────────────────────────────────────────────────────────────

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False


# ──────────────────────────────────────────────────────────────
#  GRANT TYPE ENUM
# ──────────────────────────────────────────────────────────────

class OAuth2GrantType(str, Enum):
    """Supported OAuth2 grant types."""
    CLIENT_CREDENTIALS = "client_credentials"
    AUTHORIZATION_CODE = "authorization_code"
    REFRESH_TOKEN = "refresh_token"


# ──────────────────────────────────────────────────────────────
#  CONFIG & TOKEN DATACLASSES
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
#  PKCE HELPERS
# ──────────────────────────────────────────────────────────────

def generate_pkce_pair() -> Tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge pair.

    Uses S256 method as per RFC 7636:
      code_verifier  = 43-128 char random string (unreserved chars)
      code_challenge = BASE64URL(SHA256(code_verifier))

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate 32 bytes of randomness → 43 base64url chars
    verifier_bytes = secrets.token_bytes(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode("ascii")

    # S256: BASE64URL(SHA256(code_verifier))
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    return code_verifier, code_challenge


def build_authorization_url(
    config: OAuth2Config,
    state: str = "",
    code_challenge: str = "",
    extra_params: Optional[Dict[str, str]] = None,
) -> str:
    """Build an authorization URL for the authorization code flow.

    Args:
        config: OAuth2Config with authorize_url, client_id, etc.
        state: Anti-CSRF state parameter (auto-generated if empty).
        code_challenge: PKCE code_challenge (optional).
        extra_params: Additional query parameters.

    Returns:
        Fully formed authorization URL string.
    """
    if not config.authorize_url:
        raise ValueError("authorize_url is required for authorization code flow")

    if not state:
        state = secrets.token_urlsafe(32)

    params: Dict[str, str] = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "state": state,
    }

    if config.scopes:
        params["scope"] = " ".join(config.scopes)

    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    if config.resource:
        params["resource"] = config.resource

    if extra_params:
        params.update(extra_params)

    separator = "&" if "?" in config.authorize_url else "?"
    return f"{config.authorize_url}{separator}{urllib.parse.urlencode(params)}"


# ──────────────────────────────────────────────────────────────
#  ENVIRONMENT HELPERS
# ──────────────────────────────────────────────────────────────

def config_from_env(prefix: str) -> OAuth2Config:
    """Build an OAuth2Config from environment variables with the given prefix.

    Environment variables mapped:
        {PREFIX}_CLIENT_ID        → client_id
        {PREFIX}_CLIENT_SECRET    → client_secret
        {PREFIX}_TOKEN_URL        → token_url
        {PREFIX}_AUTHORIZE_URL    → authorize_url
        {PREFIX}_SCOPES           → scopes (comma-separated)
        {PREFIX}_REDIRECT_URI     → redirect_uri
        {PREFIX}_GRANT_TYPE       → grant_type
        {PREFIX}_RESOURCE         → resource
        {PREFIX}_TENANT_ID        → used to construct token_url/authorize_url if not set

    Example:
        config = config_from_env("MSGRAPH")
        # Reads MSGRAPH_CLIENT_ID, MSGRAPH_CLIENT_SECRET, etc.
    """
    def _env(key: str) -> str:
        return os.environ.get(f"{prefix}_{key}", "")

    client_id = _env("CLIENT_ID")
    client_secret = _env("CLIENT_SECRET")
    token_url = _env("TOKEN_URL")
    authorize_url = _env("AUTHORIZE_URL")
    redirect_uri = _env("REDIRECT_URI")
    resource = _env("RESOURCE")
    tenant_id = _env("TENANT_ID")

    # If tenant_id is provided but not token_url, construct default endpoints
    if tenant_id and not token_url:
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    if tenant_id and not authorize_url:
        authorize_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"

    # Parse scopes
    scopes_str = _env("SCOPES")
    scopes = [s.strip() for s in scopes_str.split(",") if s.strip()] if scopes_str else []

    # Parse grant type
    grant_type_str = _env("GRANT_TYPE")
    grant_type = OAuth2GrantType.CLIENT_CREDENTIALS
    if grant_type_str:
        try:
            grant_type = OAuth2GrantType(grant_type_str.lower())
        except ValueError:
            logger.warning(
                "config_from_env: Invalid grant_type '%s', defaulting to client_credentials",
                grant_type_str,
            )

    return OAuth2Config(
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
        authorize_url=authorize_url,
        scopes=scopes,
        redirect_uri=redirect_uri,
        grant_type=grant_type,
        resource=resource,
    )


def register_service_from_env(
    manager: OAuth2TokenManager,
    service_name: str,
    prefix: str,
) -> bool:
    """Register a service in the token manager from environment variables.

    Args:
        manager: The OAuth2TokenManager instance.
        service_name: Name to register the service under.
        prefix: Environment variable prefix.

    Returns:
        True if the service was registered (has minimum config), False otherwise.
    """
    config = config_from_env(prefix)
    if not config.is_configured:
        logger.debug(
            "register_service_from_env: Service '%s' not configured (prefix=%s)",
            service_name, prefix,
        )
        return False

    manager.register_service(service_name, config)
    logger.info(
        "register_service_from_env: Registered '%s' from env prefix '%s'",
        service_name, prefix,
    )
    return True


# ──────────────────────────────────────────────────────────────
#  OAUTH2 TOKEN MANAGER
# ──────────────────────────────────────────────────────────────

class OAuth2TokenManager:
    """Manages OAuth2 tokens for multiple services.

    Thread-safe: uses asyncio.Lock for token refresh operations to
    prevent concurrent refresh races.

    Features:
      - Register multiple services with different OAuth2 configurations
      - Automatic token refresh when expired
      - PKCE-aware authorization URL generation
      - Token status introspection
      - Dry-run mode when aiohttp is not available
    """

    def __init__(self) -> None:
        self._configs: Dict[str, OAuth2Config] = {}
        self._tokens: Dict[str, OAuth2Token] = {}
        self._pkce_verifiers: Dict[str, str] = {}  # state → code_verifier
        self._lock = asyncio.Lock()
        self._refresh_count: int = 0
        self._request_count: int = 0
        self._error_count: int = 0

    # ── Service Management ────────────────────────────────────

    def register_service(self, service_name: str, config: OAuth2Config) -> None:
        """Register an OAuth2 service configuration.

        Args:
            service_name: Unique identifier for the service (e.g. "msgraph", "servicenow").
            config: OAuth2 configuration for the service.
        """
        self._configs[service_name] = config
        logger.info(
            "OAuth2TokenManager: Registered service '%s' (grant_type=%s, configured=%s)",
            service_name, config.grant_type.value, config.is_configured,
        )

    # ── Token Retrieval ───────────────────────────────────────

    async def get_token(self, service_name: str) -> OAuth2Token:
        """Get a valid token for the given service.

        Automatically refreshes expired tokens if a refresh_token is available.
        For client_credentials grant, automatically requests a new token.

        Args:
            service_name: The registered service name.

        Returns:
            A valid (non-expired) OAuth2Token, or an empty token on failure.
        """
        config = self._configs.get(service_name)
        if not config:
            logger.warning("OAuth2TokenManager: Service '%s' not registered", service_name)
            return OAuth2Token()

        # Check existing token
        token = self._tokens.get(service_name)
        if token and not token.is_expired:
            return token

        # Need to refresh or acquire — use lock to prevent race
        async with self._lock:
            # Double-check after acquiring lock (another coroutine may have refreshed)
            token = self._tokens.get(service_name)
            if token and not token.is_expired:
                return token

            # Try refresh_token flow first
            if token and token.is_refreshable:
                new_token = await self._refresh_token(service_name, config, token.refresh_token)
                if new_token and not new_token.is_expired:
                    self._tokens[service_name] = new_token
                    self._refresh_count += 1
                    return new_token
                logger.warning(
                    "OAuth2TokenManager: Refresh failed for '%s', falling back to grant flow",
                    service_name,
                )

            # Try grant-specific flow
            if config.grant_type == OAuth2GrantType.CLIENT_CREDENTIALS:
                new_token = await self._client_credentials_flow(service_name, config)
                if new_token:
                    self._tokens[service_name] = new_token
                    return new_token

            # Cannot auto-acquire token
            logger.warning(
                "OAuth2TokenManager: Cannot auto-acquire token for '%s' "
                "(grant_type=%s, no refresh_token available)",
                service_name, config.grant_type.value,
            )
            return token if token else OAuth2Token()

    def get_token_status(self, service_name: str) -> Dict[str, Any]:
        """Get the current token status for a service.

        Returns:
            Dictionary with token info, config status, and metadata.
            Safe for logging (excludes access_token).
        """
        config = self._configs.get(service_name)
        token = self._tokens.get(service_name)

        if not config:
            return {"registered": False, "service": service_name}

        return {
            "registered": True,
            "service": service_name,
            "configured": config.is_configured,
            "grant_type": config.grant_type.value,
            "has_token": token is not None,
            "token": token.to_dict() if token else None,
        }

    # ── Authorization Code Flow Helpers ───────────────────────

    def get_authorization_url(
        self,
        service_name: str,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str]:
        """Get an authorization URL for the authorization code flow.

        Generates PKCE parameters automatically.

        Args:
            service_name: The registered service name.
            extra_params: Additional query parameters.

        Returns:
            Tuple of (authorization_url, state).

        Raises:
            ValueError: If the service is not registered or lacks authorize_url.
        """
        config = self._configs.get(service_name)
        if not config:
            raise ValueError(f"Service '{service_name}' not registered")

        state = secrets.token_urlsafe(32)
        code_verifier, code_challenge = generate_pkce_pair()

        # Store verifier for later use in exchange_code
        self._pkce_verifiers[state] = code_verifier

        url = build_authorization_url(
            config,
            state=state,
            code_challenge=code_challenge,
            extra_params=extra_params,
        )

        logger.info(
            "OAuth2TokenManager: Generated authorization URL for '%s' (state=%s...)",
            service_name, state[:8],
        )
        return url, state

    async def exchange_code(
        self,
        service_name: str,
        code: str,
        state: str,
    ) -> OAuth2Token:
        """Exchange an authorization code for tokens.

        Uses PKCE code_verifier if the state has a stored verifier.

        Args:
            service_name: The registered service name.
            code: The authorization code received from the callback.
            state: The state parameter from the callback (used for PKCE lookup).

        Returns:
            The obtained OAuth2Token, or empty token on failure.
        """
        config = self._configs.get(service_name)
        if not config:
            logger.warning("OAuth2TokenManager: Service '%s' not registered", service_name)
            return OAuth2Token()

        # Build token request
        data: Dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": config.redirect_uri,
        }

        # Add PKCE code_verifier if available
        code_verifier = self._pkce_verifiers.pop(state, "")
        if code_verifier:
            data["code_verifier"] = code_verifier

        if config.resource:
            data["resource"] = config.resource

        token = await self._token_request(service_name, config.token_url, data)
        if token:
            self._tokens[service_name] = token
            logger.info(
                "OAuth2TokenManager: Exchanged code for token (service=%s)",
                service_name,
            )
        return token or OAuth2Token()

    # ── Direct Token Management ───────────────────────────────

    def set_token(self, service_name: str, token: OAuth2Token) -> None:
        """Directly set a token for a service.

        Useful when tokens are obtained externally (e.g., manual authorization).
        """
        self._tokens[service_name] = token
        logger.info(
            "OAuth2TokenManager: Token set for '%s' (expires_at=%.0f)",
            service_name, token.expires_at,
        )

    def clear_token(self, service_name: str) -> None:
        """Clear the stored token for a service."""
        self._tokens.pop(service_name, None)
        logger.info("OAuth2TokenManager: Token cleared for '%s'", service_name)

    # ── Stats ─────────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Get token manager statistics."""
        return {
            "registered_services": list(self._configs.keys()),
            "services_with_tokens": [
                name for name, token in self._tokens.items()
                if token and not token.is_expired
            ],
            "total_refreshes": self._refresh_count,
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "aiohttp_available": _HAS_AIOHTTP,
        }

    # ── Private: Token Acquisition Flows ──────────────────────

    async def _client_credentials_flow(
        self,
        service_name: str,
        config: OAuth2Config,
    ) -> Optional[OAuth2Token]:
        """Acquire token using client_credentials grant."""
        data: Dict[str, str] = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        }
        if config.scopes:
            data["scope"] = " ".join(config.scopes)
        if config.resource:
            data["resource"] = config.resource

        return await self._token_request(service_name, config.token_url, data)

    async def _refresh_token(
        self,
        service_name: str,
        config: OAuth2Config,
        refresh_token: str,
    ) -> Optional[OAuth2Token]:
        """Refresh an expired token using refresh_token grant."""
        data: Dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": refresh_token,
        }
        if config.scopes:
            data["scope"] = " ".join(config.scopes)
        if config.resource:
            data["resource"] = config.resource

        return await self._token_request(service_name, config.token_url, data)

    async def _token_request(
        self,
        service_name: str,
        token_url: str,
        data: Dict[str, str],
    ) -> Optional[OAuth2Token]:
        """Make a token request to the OAuth2 endpoint.

        Uses aiohttp if available, otherwise returns None (dry-run).
        """
        self._request_count += 1

        if not _HAS_AIOHTTP:
            logger.debug(
                "OAuth2TokenManager: aiohttp not available, cannot make token request "
                "for '%s' (dry-run)",
                service_name,
            )
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    token_url,
                    data=data,
                    headers={"Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    body = await response.json()

                    if response.status != 200:
                        error_desc = body.get("error_description", body.get("error", "unknown"))
                        logger.warning(
                            "OAuth2TokenManager: Token request failed for '%s': "
                            "status=%d, error=%s",
                            service_name, response.status, error_desc,
                        )
                        self._error_count += 1
                        return None

                    return self._parse_token_response(body)

        except asyncio.TimeoutError:
            logger.warning(
                "OAuth2TokenManager: Token request timed out for '%s'", service_name,
            )
            self._error_count += 1
            return None
        except Exception as exc:
            logger.warning(
                "OAuth2TokenManager: Token request error for '%s': %s",
                service_name, exc,
            )
            self._error_count += 1
            return None

    @staticmethod
    def _parse_token_response(body: Dict[str, Any]) -> OAuth2Token:
        """Parse an OAuth2 token response into an OAuth2Token."""
        expires_in = body.get("expires_in", 3600)
        # Handle both numeric and string expires_in
        try:
            expires_in_seconds = float(expires_in)
        except (ValueError, TypeError):
            expires_in_seconds = 3600

        return OAuth2Token(
            access_token=body.get("access_token", ""),
            token_type=body.get("token_type", "Bearer"),
            expires_at=time.time() + expires_in_seconds,
            refresh_token=body.get("refresh_token", ""),
            scope=body.get("scope", ""),
            id_token=body.get("id_token", ""),
        )


# ──────────────────────────────────────────────────────────────
#  GLOBAL SINGLETON
# ──────────────────────────────────────────────────────────────

_default_token_manager: Optional[OAuth2TokenManager] = None


def get_default_token_manager() -> OAuth2TokenManager:
    """Get the global default OAuth2TokenManager instance.

    Lazily created on first access. Auto-registers services from
    well-known environment variable prefixes (MSGRAPH, SERVICENOW).
    """
    global _default_token_manager
    if _default_token_manager is None:
        _default_token_manager = OAuth2TokenManager()
        # Auto-register common services from environment
        register_service_from_env(_default_token_manager, "msgraph", "MSGRAPH")
        register_service_from_env(_default_token_manager, "servicenow", "SERVICENOW")
    return _default_token_manager


def reset_default_token_manager() -> None:
    """Reset the global default token manager (for testing)."""
    global _default_token_manager
    _default_token_manager = None
