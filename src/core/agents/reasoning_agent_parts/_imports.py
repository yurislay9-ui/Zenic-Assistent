"""
Shared imports and constants for reasoning_agent_parts.
"""

import re
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import (
    ReasoningInput, ReasoningOutput, ReasoningStep,
)
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Reasoning configuration
MAX_REASONING_STEPS = 3
MIN_CONFIDENCE_ACCEPT = 0.5

# Problem type → fallback response templates
PROBLEM_TEMPLATES = {
    "api": "Design a REST API with proper endpoints, request/response schemas, "
           "authentication middleware, and error handling. Use FastAPI for the "
           "framework and SQLite for persistence.",
    "auth": "Implement JWT-based authentication with token refresh, password "
            "hashing (bcrypt/PBKDF2), RBAC for authorization, and API key "
            "support for service-to-service communication.",
    "database": "Design a normalized database schema with proper foreign keys, "
                "indexes for query performance, parameterized queries for "
                "security, and migration scripts for schema evolution.",
    "invoice": "Build an invoice system with line items, tax calculation, "
               "discount support, PDF generation, and payment tracking.",
    "inventory": "Create an inventory management system with stock tracking, "
                 "low-stock alerts, movement history, and reporting.",
    "crm": "Develop a CRM with lead pipeline management, contact tracking, "
           "sales stage progression, and conversion analytics.",
    "automation": "Design an automation workflow with triggers, scheduled "
                  "actions, error handling, and notification dispatch.",
}

# Problem type detection keywords (EN + ES)
PROBLEM_KEYWORDS = {
    "api": ["api", "endpoint", "rest", "servidor", "server"],
    "auth": ["auth", "login", "seguridad", "security", "jwt", "token"],
    "database": ["database", "datos", "schema", "base de datos", "db"],
    "invoice": ["invoice", "factura", "billing", "cobro", "pago"],
    "inventory": ["inventory", "inventario", "stock", "almacen"],
    "crm": ["crm", "cliente", "customer", "ventas", "sales"],
    "automation": ["automat", "workflow", "schedule", "scheduler"],
}
