"""
Logic modules API mixin for DNALoader.
"""

import logging
from typing import List, Optional

from ._imports import logger, LogicModule


class LogicModulesMixin:
    """Mixin with logic module query API methods."""

    # ================================================================
    #  LOGIC MODULES API
    # ================================================================

    def get_module(self, module_id: str) -> Optional[LogicModule]:
        """Obtiene un módulo de lógica por ID."""
        if not self._loaded:
            self.load_all()
        return self._logic_modules.get(module_id)

    def get_modules_by_domain(self, domain: str) -> List[LogicModule]:
        """Obtiene todos los módulos de un dominio."""
        if not self._loaded:
            self.load_all()
        ids = self._modules_by_domain.get(domain, [])
        return [self._logic_modules[i] for i in ids if i in self._logic_modules]

    def search_modules(self, query: str, limit: int = 10) -> List[LogicModule]:
        """Busca módulos relevantes basado en una descripción."""
        if not self._loaded:
            self.load_all()

        query_lower = query.lower()
        scored = []

        for mod in self._logic_modules.values():
            score = 0
            # ID match
            if query_lower in mod.id.lower():
                score += 50
            # Domain match
            if query_lower in mod.domain.lower():
                score += 30
            # Description match
            desc_words = set(mod.description.lower().split())
            query_words = set(query_lower.split())
            overlap = desc_words & query_words
            score += len(overlap) * 10
            # Input/output match
            for inp in mod.inputs:
                if query_lower in inp.lower():
                    score += 5
            if score > 0:
                scored.append((score, mod))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def resolve_modules_for_niche(self, niche_name: str, niche_blocks: List[str]) -> List[LogicModule]:
        """
        Resuelve qué módulos de lógica necesita un nicho basado en sus blocks.

        Mapea bloques del TemplateEngine a módulos de lógica.
        """
        if not self._loaded:
            self.load_all()

        # Map template blocks to logic module IDs
        block_to_modules = {
            "jwt_auth": ["auth_jwt_standard", "jwt_create", "jwt_verify"],
            "api_key_auth": ["api_key_validate"],
            "rbac": ["rbac_check"],
            "stripe_payments": ["stripe_charge", "refund_process", "invoice_generate"],
            "email_smtp": ["email_send"],
            "whatsapp_api": ["whatsapp_send"],
            "telegram_bot": ["telegram_notify"],
            "notification_manager": ["push_send", "in_app_notify"],
            "task_scheduler": ["appointment_create", "reminder_schedule"],
            "inventory_tracker": ["stock_check", "reorder_alert"],
            "invoice_calculator": ["invoice_generate"],
            "data_analyzer": ["metrics_calculate"],
            "report_generator": ["report_generate"],
            "pdf_generator": [],
            "crud_service": ["crud_create"],
            "backup_restore": ["backup_execute"],
            "webhook_server": [],
            "google_sheets": [],
            "seed_data": [],
            "migration": ["migration_run"],
        }

        resolved = []
        seen = set()

        for block in niche_blocks:
            module_ids = block_to_modules.get(block, [])
            for mid in module_ids:
                if mid not in seen:
                    mod = self._logic_modules.get(mid)
                    if mod:
                        resolved.append(mod)
                        seen.add(mid)

        return resolved
