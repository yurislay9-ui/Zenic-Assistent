"""
ZENIC-AGENTS - HttpExecutor (Phase 7.1)

Ejecutor de peticiones HTTP reales. Usa aiohttp si disponible, sino urllib.
"""

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict

from .base import ActionExecutor, ActionResult, _validate_url, _HAS_AIOHTTP

logger = logging.getLogger(__name__)


class HttpExecutor(ActionExecutor):
    """Ejecutor de peticiones HTTP reales. Usa aiohttp si disponible, sino urllib.
    Soporta GET, POST, PUT, PATCH, DELETE con retry (3 intentos).

    Config: {url, method, headers, body, params, timeout, auth}
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        url = config.get("url", "")
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        body = config.get("body", None)
        params = config.get("params", {})
        timeout = config.get("timeout", 30)
        auth = config.get("auth", None)

        if not url:
            return ActionResult(False, {}, "No URL provided", self._elapsed_ms(start))
        if not _validate_url(url):
            return ActionResult(False, {"url": url}, f"Invalid URL format: {url}", self._elapsed_ms(start))

        valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
        if method not in valid_methods:
            return ActionResult(False, {"method": method},
                                f"Invalid HTTP method: {method}. Must be one of {valid_methods}", self._elapsed_ms(start))

        # Agregar query params
        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode(params)}"

        max_retries = 3
        last_error = ""
        for attempt in range(max_retries):
            try:
                if _HAS_AIOHTTP:
                    result_data = await self._execute_aiohttp(url, method, headers, body, timeout, auth)
                else:
                    result_data = await asyncio.to_thread(self._execute_urllib, url, method, headers, body, timeout, auth)

                elapsed = self._elapsed_ms(start)
                status = result_data.get("status", 0)
                success = 200 <= status < 400
                logger.info(f"HttpExecutor: {method} {url} -> {status}")
                return ActionResult(success, result_data,
                                    "" if success else f"HTTP {status}: {result_data.get('body','')[:200]}", elapsed)
            except Exception as e:
                last_error = str(e)
                wait = (2 ** attempt) * 0.5
                logger.warning(f"HttpExecutor: Attempt {attempt+1}/{max_retries} failed: {e}. Retry in {wait}s")
                if attempt < max_retries - 1: await asyncio.sleep(wait)

        return ActionResult(False, {"url": url, "method": method},
                            f"HTTP request failed after {max_retries} retries: {last_error}", self._elapsed_ms(start))

    async def _execute_aiohttp(self, url, method, headers, body, timeout, auth):
        """Ejecuta petición HTTP con aiohttp."""
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        auth_obj = aiohttp.BasicAuth(auth["user"], auth.get("password","")) if auth else None
        async with aiohttp.ClientSession(timeout=timeout_obj, auth=auth_obj) as session:
            kwargs = {"headers": headers}
            if body is not None and method in ("POST", "PUT", "PATCH"):
                kwargs["json" if isinstance(body, (dict, list)) else "data"] = body if isinstance(body, (dict, list)) else str(body)
            async with session.request(method, url, **kwargs) as resp:
                try: resp_body = await resp.text()
                except Exception: resp_body = ""
                return {"status": resp.status, "headers": dict(resp.headers), "body": resp_body, "url": str(resp.url)}

    def _execute_urllib(self, url, method, headers, body, timeout, auth):
        """Ejecuta petición HTTP con urllib (fallback síncrono)."""
        data = None
        if body is not None and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, (dict, list)):
                data = json.dumps(body).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")
            else: data = str(body).encode("utf-8")
        if auth:
            import base64
            cred = base64.b64encode(f"{auth['user']}:{auth.get('password','')}".encode()).decode()
            headers["Authorization"] = f"Basic {cred}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "headers": dict(resp.headers),
                    "body": resp.read().decode("utf-8", errors="replace"), "url": resp.url}
