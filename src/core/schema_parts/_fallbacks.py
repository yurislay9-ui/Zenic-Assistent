"""
SchemaDesigner fallback methods mixin.
"""

import re
import logging
from typing import Dict, Any, List

from ._imports import logger


class FallbackMixin:
    """Fallback methods for SchemaDesigner."""

    # ================================================================
    #  FALLBACK METHODS
    # ================================================================

    def _fallback_entities(self, description: str) -> List[Dict[str, Any]]:
        """Fallback: extrae entidades de la descripción con keywords."""
        entities = []
        desc_lower = description.lower()

        if any(kw in desc_lower for kw in ["cliente", "customer", "crm", "ventas"]):
            entities.append({
                "name": "Customer",
                "fields": ["name:str", "email:str", "phone:str", "address:str", "tax_id:str"]
            })
        if any(kw in desc_lower for kw in ["producto", "product", "inventario", "inventory", "stock"]):
            entities.append({
                "name": "Product",
                "fields": ["name:str", "sku:str", "quantity:int", "price:float", "category:str"]
            })
        if any(kw in desc_lower for kw in ["factura", "invoice", "billing", "cobro"]):
            entities.append({
                "name": "Invoice",
                "fields": ["customer_id:int", "total:float", "status:str", "due_date:str"]
            })
        if any(kw in desc_lower for kw in ["tarea", "task", "proyecto", "project"]):
            entities.append({
                "name": "Task",
                "fields": ["title:str", "description:str", "status:str", "priority:str", "due_date:str"]
            })
        if any(kw in desc_lower for kw in ["usuario", "user", "auth", "login"]):
            entities.append({
                "name": "User",
                "fields": ["username:str", "email:str", "password_hash:str", "role:str", "active:bool"]
            })

        if not entities:
            entities.append({
                "name": "Item",
                "fields": ["name:str", "description:str", "status:str"]
            })

        return entities

    def _extract_db_name(self, description: str) -> str:
        """Extrae un nombre de BD de la descripción."""
        words = re.sub(r'[^a-zA-Z0-9\s]', '', description.lower()).split()[:2]
        return "_".join(words) if words else "app"
