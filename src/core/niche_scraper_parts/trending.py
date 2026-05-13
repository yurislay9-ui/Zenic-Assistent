"""
TrendingAnalyzer: Analyzes trending GitHub repos for emerging patterns.
"""

import re
import logging
from typing import Dict, Any, List, Optional

from ._imports import EvolutionEntry, logger


class TrendingAnalyzer:
    """
    Analiza repositorios trending de GitHub para detectar
    patrones emergentes que deban incorporarse a los nichos.
    """

    # Patrones de dependencias por lenguaje
    DEP_PATTERNS = {
        "python": {
            "file": "requirements.txt",
            "parse": "requirements",
        },
        "javascript": {
            "file": "package.json",
            "parse": "package_json",
        },
        "go": {
            "file": "go.mod",
            "parse": "gomod",
        },
        "rust": {
            "file": "Cargo.toml",
            "parse": "cargotoml",
        },
    }

    # Mapeo de librerías populares a entidades/blocks de nichos
    LIBRARY_TO_BLOCK = {
        # Auth
        "fastapi-users": "jwt_auth",
        "authlib": "jwt_auth",
        "python-jose": "jwt_auth",
        "passport": "jwt_auth",
        "next-auth": "jwt_auth",
        # Payments
        "stripe": "stripe_payments",
        "razorpay": "stripe_payments",
        # Email
        "sendgrid": "email_smtp",
        "nodemailer": "email_smtp",
        "celery": "task_scheduler",
        # Data
        "pandas": "data_analyzer",
        "numpy": "data_analyzer",
        "polars": "data_analyzer",
        # PDF
        "weasyprint": "pdf_generator",
        "reportlab": "pdf_generator",
        "pdfkit": "pdf_generator",
        # Notifications
        "firebase-admin": "notification_manager",
        "onesignal": "notification_manager",
        # Webhooks
        "svix": "webhook_server",
        # Sheets
        "gspread": "google_sheets",
        # Inventory
        "stockpy": "inventory_tracker",
        # CRM
        "hubspot-api-client": "crm_pipeline",
    }

    # Mapeo de librerías a entidades que debería tener el nicho
    LIBRARY_TO_ENTITIES = {
        "stripe": [{"name": "Payment", "fields": ["amount:float", "currency:str", "status:str", "customer_id:str", "created_at:datetime"]}],
        "sendgrid": [{"name": "EmailLog", "fields": ["recipient:str", "subject:str", "status:str", "sent_at:datetime"]}],
        "firebase-admin": [{"name": "PushNotification", "fields": ["token:str", "title:str", "body:str", "sent_at:datetime"]}],
        "pandas": [{"name": "Dataset", "fields": ["name:str", "source:str", "rows:int", "columns:int", "created_at:datetime"]}],
    }

    def __init__(self, scrap_agent=None):
        self._scrap_agent = scrap_agent
        self._evolution_log: List[EvolutionEntry] = []

    async def analyze_trending(self, language: str = "python", since: str = "weekly") -> List[Dict[str, Any]]:
        """
        Analiza repositorios trending de GitHub para detectar patrones emergentes.

        Args:
            language: Lenguaje de programación a filtrar
            since: Período de tiempo (daily, weekly, monthly)

        Returns:
            Lista de dicts con info de repos y patrones detectados
        """
        if not self._scrap_agent:
            logger.warning("TrendingAnalyzer: No scrap agent available")
            return []

        results = []

        try:
            # Buscar repos trending vía GitHub search
            query = f"stars:>100 language:{language} topic:saas OR topic:startup OR topic:web-app"
            code = await self._scrap_agent.fetch_github_code(query, language)

            if not code:
                # Fallback: buscar por tópicos de nicho
                for niche_topic in ["healthcare", "fintech", "ecommerce", "education", "saas"]:
                    q = f"topic:{niche_topic} language:{language} stars:>50"
                    c = await self._scrap_agent.fetch_github_code(q, language)
                    if c:
                        results.append({
                            "topic": niche_topic,
                            "language": language,
                            "patterns_detected": self._extract_patterns(c, language),
                        })

            if code:
                results.append({
                    "topic": "trending",
                    "language": language,
                    "patterns_detected": self._extract_patterns(code, language),
                })

        except Exception as e:
            logger.error(f"TrendingAnalyzer: Error analyzing trending: {e}")

        return results

    def _extract_patterns(self, code: str, language: str) -> Dict[str, Any]:
        """
        Extrae patrones de dependencias y estructura de código.
        """
        patterns = {
            "libraries": [],
            "suggested_blocks": [],
            "suggested_entities": [],
        }

        # Detectar imports/requires
        if language == "python":
            imports = re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', code, re.MULTILINE)
        elif language in ("javascript", "typescript"):
            imports = re.findall(r'(?:import|require)\s*\(?[\'"]([^\'"/]+)', code)
        else:
            imports = []

        for lib in set(imports):
            lib_lower = lib.lower().replace("-", "_").replace(".", "_")
            # Check if this library maps to a block
            if lib_lower in self.LIBRARY_TO_BLOCK:
                block = self.LIBRARY_TO_BLOCK[lib_lower]
                if block not in patterns["suggested_blocks"]:
                    patterns["suggested_blocks"].append(block)
                    patterns["libraries"].append(lib)

            # Check if this library suggests entities
            if lib_lower in self.LIBRARY_TO_ENTITIES:
                for entity in self.LIBRARY_TO_ENTITIES[lib_lower]:
                    if entity not in patterns["suggested_entities"]:
                        patterns["suggested_entities"].append(entity)

        return patterns

    def get_evolution_log(self, niche_name: str = "") -> List[EvolutionEntry]:
        """Obtiene el log de evolución, filtrado por nicho opcionalmente."""
        if niche_name:
            return [e for e in self._evolution_log if e.niche_name == niche_name]
        return list(self._evolution_log)
