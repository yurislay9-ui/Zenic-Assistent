"""oauth2 — Core implementation."""

from __future__ import annotations

from ._types import *  # noqa: F403

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
