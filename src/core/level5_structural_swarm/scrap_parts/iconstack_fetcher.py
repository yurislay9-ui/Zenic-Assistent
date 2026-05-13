"""
FUENTE 3: ICONSTACK - Iconos para UIs (0 registro)
FUENTE 4: PICSUM PHOTOS - Imagenes profesionales (0 registro)

Mixin que anade fetch_iconstack(), _extract_icon_urls() y fetch_picsum()
a un agente scraper.
Espera que la clase contenedora tenga:
  - self._config (con "iconstack_url", "iconstack_style", "picsum_url", "picsum_width", "picsum_height")
  - self._timeout
  - self._max_chars
  - self._max_retries

FIX (Phase 2): Added retry with backoff for IconStack network failures.
"""

import re
import json
import asyncio
import logging
import urllib.request
import urllib.error
import urllib.parse


logger = logging.getLogger(__name__)


class IconStackFetcherMixin:
    """
    Mixin para busqueda de iconos en IconStack (https://icon-icons.com).

    IconStack es 100% gratuito, sin registro y sin API key.
    Provee miles de iconos en multiples estilos (Material,
    FontAwesome, etc.) para apps y frontends generados.
    """

    async def fetch_iconstack(self, query: str) -> str:
        """
        Busca iconos en IconStack (https://icon-icons.com).

        Retorna URLs de iconos que el motor puede usar para
        inyectar en frontends generados automaticamente.

        Args:
            query: Nombre del icono (ej: "login", "menu", "settings")

        Returns:
            str: JSON con URLs de iconos, o "" si falla
        """
        base_url = self._config.get("iconstack_url", "https://icon-icons.com")
        style = self._config.get("iconstack_style", "material")

        # IconStack search URL
        search_url = (
            f"{base_url}/api/search?"
            f"q={urllib.parse.quote(query, safe='')}"
            f"&style={style}"
        )

        headers = {
            "User-Agent": "ZENIC-SmartScraper",
            "Accept": "application/json, text/html",
        }

        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")

                # Si retorna JSON (API)
                if "json" in content_type:
                    data = json.loads(resp.read().decode())
                    icons = data if isinstance(data, list) else data.get("icons", [])
                    results = []
                    for icon in icons[:5]:
                        name = icon.get("name", "")
                        svg_url = icon.get("svg_url", icon.get("url", ""))
                        png_url = icon.get("png_url", "")
                        results.append({
                            "name": name,
                            "svg_url": svg_url,
                            "png_url": png_url,
                            "style": style,
                        })
                    if results:
                        output = json.dumps({
                            "source": "iconstack",
                            "query": query,
                            "icons": results,
                        }, ensure_ascii=False, indent=2)
                        logger.info(
                            "IconStack: Found %d icons for '%s'",
                            len(results), query[:30]
                        )
                        return output[:self._max_chars]

                # Si retorna HTML, extraer URLs de iconos con parseo simple
                elif "html" in content_type:
                    html = resp.read().decode()
                    # Buscar URLs de iconos en el HTML
                    icon_urls = self._extract_icon_urls(html, query)
                    if icon_urls:
                        output = json.dumps({
                            "source": "iconstack",
                            "query": query,
                            "icons": icon_urls[:5],
                        }, ensure_ascii=False, indent=2)
                        logger.info(
                            "IconStack: Found %d icons for '%s' (HTML parse)",
                            len(icon_urls), query[:30]
                        )
                        return output[:self._max_chars]

        except urllib.error.HTTPError as e:
            if e.code >= 500:
                # FIX (Phase 2): Retry server errors
                max_retries = getattr(self, '_max_retries', 2)
                for retry_attempt in range(max_retries):
                    wait = (retry_attempt + 1) * 2
                    logger.debug(
                        "IconStack: Server error %d, retrying in %ds",
                        e.code, wait
                    )
                    try:
                        await asyncio.sleep(wait)
                        req2 = urllib.request.Request(search_url, headers=headers)
                        with urllib.request.urlopen(req2, timeout=self._timeout) as resp2:
                            data = json.loads(resp2.read().decode())
                            icons = data if isinstance(data, list) else data.get("icons", [])
                            if icons:
                                results = [{"name": i.get("name", ""), "svg_url": i.get("svg_url", i.get("url", "")), "png_url": i.get("png_url", ""), "style": style} for i in icons[:5]]
                                return json.dumps({"source": "iconstack", "query": query, "icons": results}, ensure_ascii=False, indent=2)[:self._max_chars]
                    except Exception:
                        continue
                    break
            logger.debug("IconStack: HTTP %d for '%s'", e.code, query[:30])
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            # FIX (Phase 2): Retry connection errors
            max_retries = getattr(self, '_max_retries', 2)
            for retry_attempt in range(max_retries):
                wait = (retry_attempt + 1) * 2
                logger.debug("IconStack: Connection error: %s, retrying in %ds", str(e)[:50], wait)
                try:
                    await asyncio.sleep(wait)
                    req3 = urllib.request.Request(search_url, headers=headers)
                    with urllib.request.urlopen(req3, timeout=self._timeout) as resp3:
                        data = json.loads(resp3.read().decode())
                        icons = data if isinstance(data, list) else data.get("icons", [])
                        if icons:
                            results = [{"name": i.get("name", ""), "svg_url": i.get("svg_url", i.get("url", "")), "png_url": i.get("png_url", ""), "style": style} for i in icons[:5]]
                            return json.dumps({"source": "iconstack", "query": query, "icons": results}, ensure_ascii=False, indent=2)[:self._max_chars]
                except Exception:
                    continue
                break
        except Exception as e:
            logger.debug("IconStack: Error: %s", str(e)[:80])

        # Fallback: Generar URLs de iconos conocidos (Material Design)
        # Estos son URLs directos que siempre funcionan
        material_icons = {
            "login": "https://icon-icons.com/icons2/2099/PNG/512/login_enter_icon_128544.png",
            "logout": "https://icon-icons.com/icons2/2099/PNG/512/logout_icon_128543.png",
            "menu": "https://icon-icons.com/icons2/2099/PNG/512/menu_hamburger_icon_128549.png",
            "settings": "https://icon-icons.com/icons2/2099/PNG/512/settings_gear_icon_128533.png",
            "home": "https://icon-icons.com/icons2/2099/PNG/512/home_house_icon_128540.png",
            "user": "https://icon-icons.com/icons2/2099/PNG/512/user_person_icon_128546.png",
            "search": "https://icon-icons.com/icons2/2099/PNG/512/search_magnifier_icon_128542.png",
            "add": "https://icon-icons.com/icons2/2099/PNG/512/plus_add_icon_128536.png",
            "delete": "https://icon-icons.com/icons2/2099/PNG/512/trash_delete_icon_128538.png",
            "edit": "https://icon-icons.com/icons2/2099/PNG/512/edit_pencil_icon_128539.png",
            "save": "https://icon-icons.com/icons2/2099/PNG/512/floppy_save_icon_128541.png",
            "dashboard": "https://icon-icons.com/icons2/2099/PNG/512/dashboard_icon_128545.png",
            "notification": "https://icon-icons.com/icons2/2099/PNG/512/bell_notification_icon_128547.png",
            "email": "https://icon-icons.com/icons2/2099/PNG/512/email_mail_icon_128548.png",
            "lock": "https://icon-icons.com/icons2/2099/PNG/512/lock_security_icon_128534.png",
        }

        query_lower = query.lower().strip()
        # Buscar match directo o parcial
        matched = None
        for key, url in material_icons.items():
            if key == query_lower or key in query_lower or query_lower in key:
                matched = {"name": key, "png_url": url, "style": "material"}
                break

        if matched:
            output = json.dumps({
                "source": "iconstack",
                "query": query,
                "icons": [matched],
                "note": "Fallback Material Design icon (offline)",
            }, ensure_ascii=False, indent=2)
            logger.info("IconStack: Found fallback icon for '%s'", query[:30])
            return output[:self._max_chars]

        logger.debug("IconStack: No icons found for '%s'", query[:30])
        return ""

    def _extract_icon_urls(self, html: str, query: str) -> list:
        """
        Extrae URLs de iconos de HTML de IconStack.
        Busca patrones como href="..." y src="..." con extensiones de imagen.
        """
        icons = []
        # Buscar URLs de imagenes PNG/SVG en el HTML
        img_pattern = re.compile(
            r'(?:src|href)=["\']([^"\']*icon[^"\']*\.(?:png|svg|jpg))["\']',
            re.IGNORECASE
        )
        for match in img_pattern.findall(html)[:5]:
            url = match
            if not url.startswith("http"):
                url = f"{self._config.get('iconstack_url', 'https://icon-icons.com')}{url}"
            name = url.split("/")[-1].replace(".png", "").replace("_", " ")
            icons.append({"name": name, "url": url, "style": "parsed"})
        return icons


class PicsumFetcherMixin:
    """
    Mixin para obtener imagenes aleatorias profesionales de Picsum.photos.

    Picsum.photos es 100% gratuito, sin API key y sin registro.
    Ideal para generar prototipos de frontend con imagenes
    profesionales al instante.
    """

    async def fetch_picsum(self, query: str = "") -> str:
        """
        Obtiene imagenes aleatorias profesionales de Picsum.photos.

        Ejemplo de uso en el motor:
            https://picsum.photos/800/600  -> Imagen aleatoria 800x600
            https://picsum.photos/id/237/800/600 -> Imagen especifica

        Args:
            query: Descripcion opcional (se ignora, Picsum es aleatorio)
                   Pero se puede usar para dimensiones: "1200x800"

        Returns:
            str: JSON con URL de la imagen y metadata, o "" si falla
        """
        base_url = self._config.get("picsum_url", "https://picsum.photos")
        default_w = self._config.get("picsum_width", 800)
        default_h = self._config.get("picsum_height", 600)

        # Parsear dimensiones de la query si vienen en formato "WxH" o "WxH id=N"
        width, height = default_w, default_h
        image_id = None

        if query:
            # Intentar parsear "1200x800" o "1200x800 id=237"
            dim_match = re.match(r'(\d+)\s*[xX×]\s*(\d+)', query.strip())
            if dim_match:
                width = int(dim_match.group(1))
                height = int(dim_match.group(2))
                # Limitar dimensiones para no pedir imagenes enormes
                width = min(width, 1920)
                height = min(height, 1080)

            # Intentar parsear "id=237"
            id_match = re.search(r'id\s*=\s*(\d+)', query)
            if id_match:
                image_id = int(id_match.group(1))

        # Construir URL de Picsum
        if image_id:
            image_url = f"{base_url}/id/{image_id}/{width}/{height}"
            info_url = f"{base_url}/id/{image_id}/info"
        else:
            image_url = f"{base_url}/{width}/{height}"
            info_url = ""

        # Intentar obtener metadata de la imagen
        metadata = {"width": width, "height": height}
        if info_url:
            headers = {"User-Agent": "ZENIC-SmartScraper"}
            try:
                req = urllib.request.Request(info_url, headers=headers)
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    data = json.loads(resp.read().decode())
                    metadata["author"] = data.get("author", "")
                    metadata["author_url"] = data.get("author_url", "")
                    metadata["original_url"] = data.get("url", "")
                    metadata["image_id"] = data.get("id", image_id)
            except Exception:
                pass  # Metadata es opcional

        # Verificar que la URL de imagen funciona (HEAD request)
        headers = {"User-Agent": "ZENIC-SmartScraper"}
        try:
            req = urllib.request.Request(image_url, headers=headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                actual_url = resp.url  # URL final (con redirect de Picsum)
                content_type = resp.headers.get("Content-Type", "")
                content_length = resp.headers.get("Content-Length", "0")

                if "image" in content_type:
                    metadata["actual_url"] = actual_url
                    metadata["content_type"] = content_type
                    try:
                        metadata["size_bytes"] = int(content_length)
                    except (ValueError, TypeError):
                        metadata["size_bytes"] = 0

        except Exception as e:
            # Incluso si falla el HEAD, la URL probablemente funciona
            logger.debug("Picsum: HEAD check failed, using URL as-is: %s", str(e)[:50])
            metadata["actual_url"] = image_url

        output = json.dumps({
            "source": "picsum",
            "image_url": metadata.get("actual_url", image_url),
            "direct_url": image_url,
            "metadata": metadata,
            "usage": {
                "html": f'<img src="{image_url}" alt="placeholder" width="{width}" height="{height}">',
                "css": f"background-image: url('{image_url}');",
                "markdown": f"![placeholder]({image_url})",
                "react": f'<img src="{{"{image_url}"}}" alt="placeholder" />',
            },
        }, ensure_ascii=False, indent=2)

        logger.info(
            "Picsum: Generated image URL %dx%d (id=%s)",
            width, height, image_id or "random"
        )
        return output[:self._max_chars]
