"""
CodeAssembler — Connects Jinja2 templates + niche YAML + executors
to generate REAL functional code instead of stubs.

This is the bridge that closes GAP 1:
  Before: CodeGenerator._process() -> {"processed": True, "input": payload}
  After:  CodeAssembler assembles real modules from .j2 templates

Architecture:
  1. resolve_modules() — maps intent -> blocks -> templates
  2. assemble_project() — renders templates + wires imports
  3. build_service_method() — generates _process() with REAL logic

BUG FIX: Previously, generated CRUD/analytics code called async DatabaseExecutor
methods synchronously (db.execute_query() which didn't exist). Now uses sqlite3
directly (stdlib) so generated code is standalone, synchronous, and actually runs.
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zenic_agents.code_gen_parts.assembler")

# ── Block -> Template mapping (matches src/templates/blocks/) ──
BLOCK_TEMPLATE_MAP = {
    # Auth
    "jwt_auth": "blocks/auth/jwt_auth.py.j2",
    "api_key_auth": "blocks/auth/api_key_auth.py.j2",
    "rbac": "blocks/auth/rbac.py.j2",
    # Data
    "crud_service": "blocks/data/crud_service.py.j2",
    "seed_data": "blocks/data/seed_data.py.j2",
    "backup_restore": "blocks/data/backup_restore.py.j2",
    "database_migrations": "blocks/data/database_migrations.py.j2",
    # Integrations
    "stripe_payments": "blocks/integrations/stripe_payments.py.j2",
    "email_smtp": "blocks/integrations/email_smtp.py.j2",
    "telegram_bot": "blocks/integrations/telegram_bot.py.j2",
    "webhook_server": "blocks/integrations/webhook_server.py.j2",
    "pdf_generator": "blocks/integrations/pdf_generator.py.j2",
    "google_sheets": "blocks/integrations/google_sheets.py.j2",
    # Business Logic
    "notification_manager": "blocks/business_logic/notification_manager.py.j2",
    "data_analyzer": "blocks/business_logic/data_analyzer.py.j2",
    "inventory_tracker": "blocks/business_logic/inventory_tracker.py.j2",
    "invoice_calculator": "blocks/business_logic/invoice_calculator.py.j2",
    "crm_pipeline": "blocks/business_logic/crm_pipeline.py.j2",
    "report_generator": "blocks/business_logic/report_generator.py.j2",
}

# ── Keyword -> Block suggestion mapping ──
KEYWORD_BLOCK_MAP = {
    "auth": ["jwt_auth"],
    "login": ["jwt_auth"],
    "token": ["jwt_auth"],
    "password": ["jwt_auth"],
    "jwt": ["jwt_auth"],
    "rol": ["jwt_auth", "rbac"],
    "rbac": ["rbac"],
    "api key": ["api_key_auth"],
    "crud": ["crud_service"],
    "database": ["crud_service", "backup_restore"],
    "db": ["crud_service"],
    "sql": ["crud_service"],
    "stripe": ["stripe_payments"],
    "payment": ["stripe_payments"],
    "pago": ["stripe_payments"],
    "subscription": ["stripe_payments"],
    "email": ["email_smtp"],
    "correo": ["email_smtp"],
    "smtp": ["email_smtp"],
    "telegram": ["telegram_bot"],
    "bot": ["telegram_bot"],
    "webhook": ["webhook_server"],
    "pdf": ["pdf_generator"],
    "invoice": ["invoice_calculator", "pdf_generator"],
    "factura": ["invoice_calculator", "pdf_generator"],
    "notification": ["notification_manager"],
    "notificacion": ["notification_manager"],
    "analytics": ["data_analyzer"],
    "analisis": ["data_analyzer"],
    "inventory": ["inventory_tracker"],
    "inventario": ["inventory_tracker"],
    "crm": ["crm_pipeline"],
    "backup": ["backup_restore"],
    "report": ["report_generator"],
    "google sheets": ["google_sheets"],
    "seed": ["seed_data"],
}
