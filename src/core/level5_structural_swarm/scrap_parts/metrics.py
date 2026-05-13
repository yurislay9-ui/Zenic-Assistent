"""
GITHUB METRICS - Recopilacion de metricas de la API
"""

import json
import time
import logging
import urllib.request

from typing import Dict, Any

from src.core.env_loader import (
    get_env_int, get_env_bool, get_env_list, get_github_token,
)

logger = logging.getLogger(__name__)


class GitHubMetrics:
    """
    Recopila metricas de uso de la API de GitHub.

    Metricas disponibles:
    - rate_limit: Requests restantes y reset time
    - search_results: Conteo de resultados por query
    - repo_stats: Estadisticas de repos encontrados
    """

    def __init__(self):
        self.enabled = get_env_bool("GITHUB_METRICS_ENABLED", True)
        self.collect = get_env_list(
            "GITHUB_METRICS_COLLECT",
            ["rate_limit", "search_results", "repo_stats"]
        )
        self.refresh_interval = get_env_int("GITHUB_METRICS_REFRESH_INTERVAL", 300)

        # Estado interno
        self._rate_limit_remaining = 0
        self._rate_limit_limit = 0
        self._rate_limit_reset = 0
        self._rate_limit_last_check = 0
        self._search_count = 0
        self._search_results_total = 0
        self._repos_seen: set = set()
        self._repos_seen_max = 10000
        self._last_refresh = 0.0

    def update_rate_limit(self, response_headers: dict):
        """Actualiza metricas de rate limit desde headers de respuesta GitHub."""
        if not self.enabled or "rate_limit" not in self.collect:
            return

        try:
            self._rate_limit_remaining = int(
                response_headers.get("X-RateLimit-Remaining", "0")
            )
        except (ValueError, TypeError):
            self._rate_limit_remaining = 0
        try:
            self._rate_limit_limit = int(
                response_headers.get("X-RateLimit-Limit", "0")
            )
        except (ValueError, TypeError):
            self._rate_limit_limit = 0
        try:
            self._rate_limit_reset = int(
                response_headers.get("X-RateLimit-Reset", "0")
            )
        except (ValueError, TypeError):
            self._rate_limit_reset = 0
        self._rate_limit_last_check = time.time()

    def update_search_stats(self, total_count: int, query: str):
        """Actualiza estadisticas de busqueda."""
        if not self.enabled or "search_results" not in self.collect:
            return
        self._search_count += 1
        self._search_results_total += total_count

    def update_repo_stats(self, repo_full_name: str, stars: int = 0):
        """Actualiza estadisticas de repositorios."""
        if not self.enabled or "repo_stats" not in self.collect:
            return
        self._repos_seen.add(repo_full_name)
        if len(self._repos_seen) > self._repos_seen_max:
            # Clear half to prevent unbounded growth
            remove = list(self._repos_seen)[:len(self._repos_seen) // 2]
            for item in remove:
                self._repos_seen.discard(item)

    async def fetch_rate_limit(self, token: str = "") -> Dict[str, Any]:
        """
        Obtiene el estado actual del rate limit de GitHub API.
        Requiere token para el endpoint /rate_limit.
        """
        if not token:
            token = get_github_token()
        if not token:
            return {"error": "No GITHUB_TOKEN configured"}

        url = "https://api.github.com/rate_limit"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ZENIC-SmartScraper",
            "Authorization": f"token {token}",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                resources = data.get("resources", {})
                search = resources.get("search", {})
                core = resources.get("core", {})

                self._rate_limit_remaining = core.get("remaining", 0)
                self._rate_limit_limit = core.get("limit", 0)
                self._rate_limit_reset = core.get("reset", 0)
                self._rate_limit_last_check = time.time()

                return {
                    "core": {
                        "remaining": core.get("remaining", 0),
                        "limit": core.get("limit", 0),
                        "reset": core.get("reset", 0),
                    },
                    "search": {
                        "remaining": search.get("remaining", 0),
                        "limit": search.get("limit", 0),
                        "reset": search.get("reset", 0),
                    },
                }
        except Exception as e:
            logger.debug("GitHubMetrics: Failed to fetch rate_limit: %s", e)
            return {"error": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Retorna todas las metricas recopiladas."""
        stats = {}
        if "rate_limit" in self.collect:
            stats["rate_limit"] = {
                "remaining": self._rate_limit_remaining,
                "limit": self._rate_limit_limit,
                "reset_timestamp": self._rate_limit_reset,
                "last_check": self._rate_limit_last_check,
            }
        if "search_results" in self.collect:
            stats["search"] = {
                "queries_made": self._search_count,
                "total_results": self._search_results_total,
            }
        if "repo_stats" in self.collect:
            stats["repos"] = {
                "unique_repos_seen": len(self._repos_seen),
                "repo_names": list(self._repos_seen)[:20],  # Ultimos 20
            }
        return stats
