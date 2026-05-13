"""
FUENTE 1: GITHUB - Busqueda de codigo con API key

Mixin que anade fetch_github_code() a un agente scraper.
Espera que la clase contenedora tenga:
  - self._config["github_token"]
  - self._timeout
  - self._max_retries
  - self._max_chars
  - self._metrics (GitHubMetrics)
"""

import asyncio
import json
import time
import logging
import urllib.request
import urllib.error
import urllib.parse


logger = logging.getLogger(__name__)


class GitHubFetcherMixin:
    """
    Mixin para busqueda de codigo en repositorios publicos de GitHub.

    Usa GITHUB_TOKEN del .env para autenticacion.
    Sin token: 60 requests/hora | Con token: 5000 requests/hora.
    """

    async def fetch_github_code(self, query: str, language: str = "python") -> str:
        """
        Busca codigo en repositorios publicos de GitHub.

        Args:
            query: Termino de busqueda
            language: Lenguaje de programacion

        Returns:
            str: Codigo encontrado (hasta max_chars), o "" si falla
        """
        # Obtener token desde .env
        github_token = self._config["github_token"]

        encoded_query = urllib.parse.quote(query, safe='')
        lang_param = f"+language:{language}" if language else ""
        url = (
            f"https://api.github.com/search/code?"
            f"q={encoded_query}{lang_param}&sort=stars&per_page=5"
        )

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ZENIC-SmartScraper",
        }

        # Usar token si esta disponible (5000 req/h vs 60 req/h)
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        # Reintentos con backoff
        for attempt in range(self._max_retries + 1):
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    # Actualizar metricas de rate limit
                    resp_headers = dict(resp.headers)
                    self._metrics.update_rate_limit(resp_headers)

                    data = json.loads(resp.read().decode())

                    # Metricas de busqueda
                    total_count = data.get("total_count", 0)
                    self._metrics.update_search_stats(total_count, query)

                    if not data.get("items"):
                        logger.debug(
                            "GitHub: No results for '%s' (lang=%s, total=%d)",
                            query[:50], language, total_count
                        )
                        return ""

                    # Probar cada resultado hasta encontrar codigo valido
                    for item in data["items"][:3]:
                        repo_name = item.get("repository", {}).get("full_name", "")
                        file_path = item.get("path", "")

                        # Metricas de repo
                        self._metrics.update_repo_stats(repo_name)

                        # Construir URL al archivo raw
                        # Probar main primero, luego master
                        for branch in ("main", "master"):
                            raw_url = (
                                f"https://raw.githubusercontent.com/"
                                f"{repo_name}/{branch}/{file_path}"
                            )
                            raw_req = urllib.request.Request(
                                raw_url, headers=headers
                            )
                            try:
                                with urllib.request.urlopen(
                                    raw_req, timeout=self._timeout
                                ) as raw_resp:
                                    code = raw_resp.read().decode()
                                    if code.strip():
                                        logger.info(
                                            "GitHub: Found code from %s/%s "
                                            "(%d chars, branch=%s)",
                                            repo_name, file_path,
                                            len(code), branch
                                        )
                                        return code[:self._max_chars]
                            except Exception:
                                continue

                    logger.debug("GitHub: Found items but no raw code accessible")
                    return ""

            except urllib.error.HTTPError as e:
                if e.code == 403:
                    # Rate limit alcanzado
                    reset_time = e.headers.get("X-RateLimit-Reset", "0")
                    remaining = e.headers.get("X-RateLimit-Remaining", "0")
                    logger.warning(
                        "GitHub API rate limit (remaining=%s, reset=%s). "
                        "Configura GITHUB_TOKEN en .env para 5000 req/h.",
                        remaining, reset_time
                    )
                    # No reintentar si es rate limit
                    return ""
                elif e.code == 422:
                    logger.debug("GitHub: Invalid query '%s'", query[:50])
                    return ""
                elif e.code >= 500:
                    # Error del servidor, reintentar
                    if attempt < self._max_retries:
                        wait = (attempt + 1) * 2
                        logger.debug(
                            "GitHub: Server error %d, retrying in %ds",
                            e.code, wait
                        )
                        await asyncio.sleep(wait)
                        continue
                else:
                    logger.debug("GitHub: HTTP %d for '%s'", e.code, query[:50])
                    return ""

            except urllib.error.URLError as e:
                if attempt < self._max_retries:
                    wait = (attempt + 1) * 2
                    logger.debug(
                        "GitHub: URL error %s, retrying in %ds",
                        str(e.reason)[:50], wait
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.warning("GitHub: URL error: %s", e.reason)

            except Exception as e:
                logger.warning("GitHub: Error fetching '%s': %s", query[:50], e)
                return ""

        return ""
