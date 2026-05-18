"""
OAuth2 — PKCE helpers, authorization URL builder, and environment helpers.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import urllib.parse
from typing import Dict, Optional, Tuple

from ._types import OAuth2Config, OAuth2GrantType

logger = logging.getLogger("zenic_agents.email_parts.oauth2")


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
    manager: "OAuth2TokenManager",
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
