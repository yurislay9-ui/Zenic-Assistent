"""
SMART SCRAPER - Orquestador multi-fuente

GitHubScrapAgent que combina todos los mixins de fetching
con la logica de auto-routing, caching y backward compatibility.
"""

import logging
from typing import Dict, Any

from src.core.env_loader import (
    load_env, get_scraper_config,
)

from src.core.level5_structural_swarm.scrap_parts.metrics import GitHubMetrics
from src.core.level5_structural_swarm.scrap_parts.github_fetcher import GitHubFetcherMixin
from src.core.level5_structural_swarm.scrap_parts.devdocs_fetcher import DevDocsFetcherMixin
from src.core.level5_structural_swarm.scrap_parts.iconstack_fetcher import (
    IconStackFetcherMixin,
    PicsumFetcherMixin,
)

logger = logging.getLogger(__name__)


class GitHubScrapAgent(
    GitHubFetcherMixin,
    DevDocsFetcherMixin,
    IconStackFetcherMixin,
    PicsumFetcherMixin,
):
    """
    Smart Scraper Agent v16 - Multi-fuente, auto-routing.

    Mantiene backward compatibility con fetch_modern_code() del
    pipeline original, pero anade smart_fetch() para seleccion
    automatica de fuente y metodos individuales por fuente.

    Fuentes:
    - github:   Busca codigo en repos publicos (con GITHUB_TOKEN)
    - devdocs:  Documentacion de lenguajes y APIs (0 registro)
    - iconstack: Iconos para UIs (0 registro)
    - picsum:   Imagenes aleatorias profesionales (0 registro)

    Uso basico (backward-compatible):
        scraper = GitHubScrapAgent()
        code = await scraper.fetch_modern_code("auth login", "python")

    Uso avanzado (auto-routing):
        result = await scraper.smart_fetch("how to use asyncio", "python")
        # Auto-selecciona: devdocs (documentacion)

        result = await scraper.smart_fetch("kotlin coroutines example", "kotlin")
        # Auto-selecciona: github (codigo de ejemplo)

        result = await scraper.smart_fetch("material icon for login button", "")
        # Auto-selecciona: iconstack (iconos)

        result = await scraper.smart_fetch("hero image for dashboard", "")
        # Auto-selecciona: picsum (imagen aleatoria)
    """

    # Keywords que indican tipo de consulta para auto-routing
    CODE_KEYWORDS = {
        "example", "implement", "code", "function", "class", "module",
        "snippet", "how to", "create a", "build a", "pattern", "algorithm",
        "repository", "repo", "github", "library", "package", "import",
        "ejemplo", "implementar", "funcion", "clase", "modulo", "patron",
    }

    DOCS_KEYWORDS = {
        "docs", "documentation", "reference", "api", "syntax", "method",
        "parameter", "return", "type", "class reference", "how does",
        "what is", "explain", "tutorial", "guide", "specification",
        "documentacion", "referencia", "sintaxis", "metodo", "explicar",
        "guia", "tutorial",
    }

    ICON_KEYWORDS = {
        "icon", "icons", "svg", "symbol", "logo", "badge", "avatar",
        "button icon", "menu icon", "navigation icon", "tab icon",
        "icono", "iconos", "simbolo", "logo", "insignia",
    }

    IMAGE_KEYWORDS = {
        "image", "photo", "picture", "hero", "banner", "background",
        "cover", "thumbnail", "placeholder", "avatar image", "header",
        "imagen", "foto", "imagen de fondo", "portada", "miniatura",
        "placeholder image", "hero image",
    }

    def __init__(self):
        """Inicializa el Smart Scraper con config desde .env."""
        # Cargar .env si no se ha hecho
        load_env()

        # Configuracion del scraper
        self._config = get_scraper_config()
        self._timeout = self._config["timeout"]
        self._max_retries = self._config["max_retries"]
        self._max_chars = self._config["max_chars"]
        self._preferred_source = self._config["preferred_source"]

        # Metricas de GitHub
        self._metrics = GitHubMetrics()

        # Cache de resultados simples (evita fetch duplicado en misma sesion)
        self._cache: Dict[str, str] = {}

        logger.info(
            "SmartScraper v16: sources=[github,devdocs,iconstack,picsum] "
            "preferred=%s timeout=%ds max_chars=%d token=%s",
            self._preferred_source, self._timeout, self._max_chars,
            "YES" if self._config["github_token"] else "NO"
        )

    @property
    def metrics(self) -> GitHubMetrics:
        """Acceso a las metricas de GitHub."""
        return self._metrics

    @property
    def config(self) -> dict:
        """Acceso a la configuracion del scraper."""
        return self._config

    # ============================================================
    #  BACKWARD COMPATIBILITY - fetch_modern_code()
    # ============================================================

    async def fetch_modern_code(self, query, language="kotlin"):
        """
        Backward-compatible: Busca codigo en GitHub.

        Este es el metodo original del pipeline (SCRAPE_PATTERNS).
        Se mantiene para compatibilidad con DAGOrchestrator y
        ZenicOrchestrator existentes.

        Args:
            query: Termino de busqueda
            language: Lenguaje de programacion (default: kotlin)

        Returns:
            str: Codigo encontrado (hasta max_chars), o "" si falla
        """
        return await self.fetch_github_code(query, language)

    # ============================================================
    #  AUTO-ROUTING - smart_fetch()
    # ============================================================

    async def smart_fetch(self, query: str, language: str = "",
                          source: str = "") -> Dict[str, Any]:
        """
        Auto-routing: Selecciona la fuente optima segun el tipo de consulta.

        Si source es "auto" (default), analiza keywords en la query para
        determinar la fuente. Si se especifica una fuente, la usa directamente.

        Args:
            query: Termino de busqueda o consulta
            language: Lenguaje de programacion (opcional)
            source: Fuente forzada: github|devdocs|iconstack|picsum|auto

        Returns:
            dict con: source, content, metadata, success
        """
        # Determinar fuente
        if not source or source == "auto":
            source = self._preferred_source
            if source == "auto":
                source = self._detect_source(query)

        # Check cache
        cache_key = f"{source}:{query}:{language}"
        if cache_key in self._cache:
            logger.debug("SmartScraper: Cache hit for %s", cache_key[:60])
            return {
                "source": source,
                "content": self._cache[cache_key],
                "metadata": {"cached": True},
                "success": True,
            }

        # Dispatch a la fuente seleccionada
        result = {"source": source, "content": "", "metadata": {}, "success": False}

        if source == "github":
            content = await self.fetch_github_code(query, language)
            result["content"] = content
            result["success"] = bool(content)

        elif source == "devdocs":
            content = await self.fetch_devdocs(query, language)
            result["content"] = content
            result["success"] = bool(content)

        elif source == "iconstack":
            content = await self.fetch_iconstack(query)
            result["content"] = content
            result["success"] = bool(content)

        elif source == "picsum":
            content = await self.fetch_picsum(query)
            result["content"] = content
            result["success"] = bool(content)

        else:
            logger.warning("SmartScraper: Unknown source '%s', falling back to github", source)
            content = await self.fetch_github_code(query, language)
            result["source"] = "github"
            result["content"] = content
            result["success"] = bool(content)

        # Cache resultado exitoso
        if result["success"] and result["content"]:
            self._cache[cache_key] = result["content"]
            # Limitar tamano del cache (max 100 entradas)
            if len(self._cache) > 100:
                # Eliminar entradas mas antiguas (FIFO simplificado)
                keys = list(self._cache.keys())
                to_evict = max(20, len(self._cache) - 90)
                for k in keys[:to_evict]:
                    del self._cache[k]

        return result

    def _detect_source(self, query: str) -> str:
        """
        Detecta la fuente optima basandose en keywords de la query.

        Prioridad: iconstack > picsum > devdocs > github
        (las fuentes mas especificas tienen prioridad)
        """
        query_lower = query.lower()

        # Check iconos primero (muy especifico)
        icon_score = sum(1 for kw in self.ICON_KEYWORDS if kw in query_lower)
        if icon_score >= 1:
            return "iconstack"

        # Check imagenes (require 2+ matches to avoid false routing)
        # Single "image" or "background" keyword is too ambiguous for code requests
        image_score = sum(1 for kw in self.IMAGE_KEYWORDS if kw in query_lower)
        if image_score >= 2:
            return "picsum"

        # Check documentacion
        docs_score = sum(1 for kw in self.DOCS_KEYWORDS if kw in query_lower)
        if docs_score >= 2:
            return "devdocs"

        # Check codigo
        code_score = sum(1 for kw in self.CODE_KEYWORDS if kw in query_lower)
        if code_score >= 1:
            return "github"

        # Default: github (fuente mas versatil para codigo)
        return "github"

    # ============================================================
    #  MULTI-SOURCE FETCH - Busca en todas las fuentes
    # ============================================================

    async def fetch_all_sources(self, query: str,
                                 language: str = "") -> Dict[str, Any]:
        """
        Busca en TODAS las fuentes disponibles y retorna resultados combinados.

        Util cuando se quiere maximizar la informacion obtenida,
        por ejemplo para el nodo SCRAPE_PATTERNS del DAG.

        Fuentes consultadas (en orden):
        1. GitHub  - Codigo de repos publicos (con GITHUB_TOKEN)
        2. DevDocs - Documentacion de lenguajes y APIs (0 registro)
        3. IconStack - Iconos para UIs generadas (0 registro)
        4. Picsum  - Imagenes profesionales aleatorias (0 registro)

        Args:
            query: Termino de busqueda
            language: Lenguaje de programacion

        Returns:
            dict con resultados por fuente: {source: content, ...}
        """
        results = {}
        sources_tried = []

        # 1. GitHub (siempre, es la fuente principal de codigo)
        try:
            github_code = await self.fetch_github_code(query, language)
            if github_code:
                results["github"] = github_code
        except Exception as e:
            logger.debug("fetch_all_sources: GitHub failed: %s", str(e)[:60])
        sources_tried.append("github")

        # 2. DevDocs (documentacion de lenguajes y APIs)
        try:
            devdocs_content = await self.fetch_devdocs(query, language)
            if devdocs_content:
                results["devdocs"] = devdocs_content
        except Exception as e:
            logger.debug("fetch_all_sources: DevDocs failed: %s", str(e)[:60])
        sources_tried.append("devdocs")

        # 3. IconStack (iconos para UIs generadas)
        try:
            iconstack_content = await self.fetch_iconstack(query)
            if iconstack_content:
                results["iconstack"] = iconstack_content
        except Exception as e:
            logger.debug("fetch_all_sources: IconStack failed: %s", str(e)[:60])
        sources_tried.append("iconstack")

        # 4. Picsum (imagenes profesionales para frontends)
        try:
            picsum_content = await self.fetch_picsum(query)
            if picsum_content:
                results["picsum"] = picsum_content
        except Exception as e:
            logger.debug("fetch_all_sources: Picsum failed: %s", str(e)[:60])
        sources_tried.append("picsum")

        # Agregar metricas y fuentes consultadas
        results["_metrics"] = self._metrics.get_stats()
        results["_sources_tried"] = sources_tried
        results["_total_sources"] = len(sources_tried)
        results["_successful_sources"] = len([
            k for k in results if k and not k.startswith("_")
        ])

        return results

    # ============================================================
    #  GITHUB METRICS API - Para monitoreo externo
    # ============================================================

    async def get_github_rate_limit(self) -> Dict[str, Any]:
        """
        Obtiene el estado del rate limit de GitHub API.

        Returns:
            dict con: core, search, error
        """
        return await self._metrics.fetch_rate_limit(self._config["github_token"])

    def get_all_metrics(self) -> Dict[str, Any]:
        """
        Retorna todas las metricas recopiladas del scraper.

        Incluye:
        - GitHub rate limit, search stats, repo stats
        - Configuracion del scraper
        - Estado del cache
        """
        return {
            "github": self._metrics.get_stats(),
            "config": {
                "timeout": self._timeout,
                "max_retries": self._max_retries,
                "max_chars": self._max_chars,
                "preferred_source": self._preferred_source,
                "has_github_token": bool(self._config["github_token"]),
                "devdocs_url": self._config["devdocs_url"],
                "iconstack_url": self._config["iconstack_url"],
                "picsum_url": self._config["picsum_url"],
            },
            "cache": {
                "size": len(self._cache),
                "max_size": 100,
            },
        }
