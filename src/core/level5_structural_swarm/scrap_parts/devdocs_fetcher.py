"""
FUENTE 2: DEVDOCS - Documentacion de lenguajes (0 registro)

Mixin que anade fetch_devdocs() y _devdocs_search() a un agente scraper.
Espera que la clase contenedora tenga:
  - self._config (con "devdocs_url")
  - self._timeout
  - self._max_chars
  - self._max_retries

FIX (Phase 2): Added retry with backoff for network transient failures.
DevDocs API can fail with 5xx or connection errors that resolve on retry.
"""

import json
import asyncio
import logging
import urllib.request
import urllib.error
import urllib.parse


logger = logging.getLogger(__name__)


class DevDocsFetcherMixin:
    """
    Mixin para busqueda de documentacion en DevDocs (https://devdocs.io).

    DevDocs es 100% gratuito, sin registro y sin API key.
    Agrega documentacion de Python, JavaScript, TypeScript,
    HTML, CSS, Kotlin, y decenas de lenguajes mas.
    """

    async def fetch_devdocs(self, query: str, language: str = "") -> str:
        """
        Busca documentacion en DevDocs (https://devdocs.io).

        La API de DevDocs permite buscar y obtener documentacion
        directamente: https://devdocs.io/docs/{doc}/index.json
        y buscar: https://devdocs.io/docs/{doc}/search.json?q={query}

        Args:
            query: Termino de busqueda (ej: "asyncio.gather", "Array.map")
            language: Lenguaje para acotar la busqueda

        Returns:
            str: Documentacion encontrada, o "" si falla
        """
        # Mapear lenguaje a documento DevDocs
        lang_to_doc = {
            "python": "python~3.12",
            "python3": "python~3.12",
            "kotlin": "kotlin",
            "javascript": "javascript",
            "js": "javascript",
            "typescript": "typescript",
            "ts": "typescript",
            "html": "html",
            "css": "css",
            "react": "react",
            "node": "node",
            "nodejs": "node",
            "go": "go",
            "rust": "rust",
            "java": "java",
            "ruby": "ruby",
            "php": "php",
            "c": "c",
            "cpp": "cpp",
            "csharp": "csharp",
            "swift": "swift",
            "dart": "dart",
            "flutter": "flutter",
        }

        doc_name = lang_to_doc.get(language.lower(), "") if language else ""

        # Si no tenemos doc para el lenguaje, probar con Python como default
        if not doc_name and language:
            doc_name = lang_to_doc.get(language.lower(), "python~3.12")

        # Estrategia 1: Buscar en un documento especifico
        if doc_name:
            result = await self._devdocs_search(doc_name, query)
            if result:
                return result

        # Estrategia 2: Buscar en documentos populares si no se especifico lenguaje
        popular_docs = ["python~3.12", "javascript", "typescript", "html", "css", "kotlin"]
        for doc in popular_docs[:3]:  # Solo probar los 3 mas relevantes
            if doc == doc_name:
                continue  # Ya lo probamos
            result = await self._devdocs_search(doc, query)
            if result:
                return result

        return ""

    async def _devdocs_search(self, doc_name: str, query: str) -> str:
        """
        Busca en un documento especifico de DevDocs.

        Usa la API de busqueda: /docs/{doc}/search.json?q={query}
        y la API de entradas: /docs/{doc}/index.json

        FIX (Phase 2): Added retry with exponential backoff for transient
        network failures (5xx errors, connection resets).
        """
        base_url = self._config.get("devdocs_url", "https://devdocs.io")

        # Primero buscar entradas relevantes
        search_url = f"{base_url}/docs/{doc_name}/search.json?q={urllib.parse.quote(query, safe='')}"
        headers = {
            "User-Agent": "ZENIC-SmartScraper",
            "Accept": "application/json",
        }

        max_retries = getattr(self, '_max_retries', 2)
        for attempt in range(max_retries + 1):
            try:
                req = urllib.request.Request(search_url, headers=headers)
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    data = json.loads(resp.read().decode())

                    if not data:
                        return ""

                    # DevDocs search.json retorna una lista de [name, path, signature?]
                    # Formato: [["name", "path", "signature"], ...]
                    results = []
                    for entry in data[:5]:
                        if isinstance(entry, list) and len(entry) >= 2:
                            name = entry[0]
                            path = entry[1]
                            sig = entry[2] if len(entry) > 2 else ""
                            results.append(f"**{name}**\n  Path: {path}\n  Signature: {sig}")
                        elif isinstance(entry, dict):
                            name = entry.get("name", "")
                            path = entry.get("path", "")
                            sig = entry.get("signature", entry.get("doc", ""))
                            results.append(f"**{name}**\n  Path: {path}\n  Signature: {sig}")

                    if results:
                        doc_text = (
                            f"[DevDocs: {doc_name}]\n\n"
                            + "\n\n".join(results)
                        )
                        logger.info(
                            "DevDocs: Found %d results for '%s' in %s",
                            len(results), query[:30], doc_name
                        )
                        return doc_text[:self._max_chars]
                    return ""

            except urllib.error.HTTPError as e:
                if e.code >= 500 and attempt < max_retries:
                    wait = (attempt + 1) * 2
                    logger.debug(
                        "DevDocs: Server error %d for %s search, retrying in %ds",
                        e.code, doc_name, wait
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.debug("DevDocs: HTTP %d for %s search", e.code, doc_name)
                return ""
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                if attempt < max_retries:
                    wait = (attempt + 1) * 2
                    logger.debug(
                        "DevDocs: Connection error for %s search: %s, retrying in %ds",
                        doc_name, str(e)[:50], wait
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.debug("DevDocs: Error searching %s: %s", doc_name, str(e)[:80])
                return ""
            except Exception as e:
                logger.debug("DevDocs: Error searching %s: %s", doc_name, str(e)[:80])
                return ""

        return ""
