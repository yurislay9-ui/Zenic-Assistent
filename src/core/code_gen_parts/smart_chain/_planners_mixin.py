"""SmartPromptChain - Step Planners Mixin."""

import logging
from typing import Any, Dict, List

from ._types import GenerationStep

logger = logging.getLogger("zenic_agents.code_gen_parts.smart_chain")


class SmartChainPlannersMixin:
    """Mixin providing step planning methods."""

    def _plan_crud_steps(self, entity_name: str, fields: List[Dict],
                          language: str) -> List[GenerationStep]:
        """Plan steps for CRUD service generation."""
        field_names = [f.get("name", "field") for f in fields] if fields else ["id", "name"]
        field_types = [f.get("type", "str") for f in fields] if fields else ["int", "str"]
        fields_str = ", ".join(f"{n}: {t}" for n, t in zip(field_names, field_types))

        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description=f"Imports for {entity_name} CRUD",
                prompt=(
                    f"Generate ONLY the import statements for a Python CRUD service "
                    f"for {entity_name}. Fields: {fields_str}. "
                    f"Use typing, dataclasses, sqlite3, logging. "
                    f"Output ONLY the import lines, no other code. Max 10 lines."
                ),
            ),
            GenerationStep(
                step_id=2, step_type="schema",
                description=f"Pydantic models for {entity_name}",
                prompt=(
                    f"Generate Pydantic BaseModel classes for {entity_name}. "
                    f"Fields: {fields_str}. "
                    f"Create {entity_name}Create and {entity_name}Response models. "
                    f"Output ONLY the class definitions. Max 20 lines."
                ),
                context="IMPORTS_PLACEHOLDER",
            ),
            GenerationStep(
                step_id=3, step_type="class_def",
                description=f"CRUD service class for {entity_name}",
                prompt=(
                    f"Generate a CRUDService class for {entity_name} with __init__ "
                    f"that accepts table_name='{entity_name.lower()}s'. "
                    f"Include db_path parameter defaulting to 'data.sqlite'. "
                    f"Output ONLY the class definition with __init__. Max 15 lines."
                ),
            ),
            GenerationStep(
                step_id=4, step_type="method",
                description=f"create() method for {entity_name}",
                prompt=(
                    f"Generate a create() method for {entity_name}CRUDService "
                    f"that INSERTs a new row into SQLite. "
                    f"Use parameterized queries (NO f-strings in SQL). "
                    f"Return the created item with its id. "
                    f"Output ONLY the method. Max 15 lines."
                ),
            ),
            GenerationStep(
                step_id=5, step_type="method",
                description=f"read() and list() methods for {entity_name}",
                prompt=(
                    f"Generate read(id) and list(limit, offset) methods for "
                    f"{entity_name}CRUDService. Use parameterized SQL queries. "
                    f"Output ONLY the two methods. Max 20 lines."
                ),
            ),
            GenerationStep(
                step_id=6, step_type="method",
                description=f"update() and delete() methods for {entity_name}",
                prompt=(
                    f"Generate update(id, data) and delete(id) methods for "
                    f"{entity_name}CRUDService. Use parameterized SQL. "
                    f"Output ONLY the two methods. Max 20 lines."
                ),
            ),
        ]

        return steps

    def _plan_auth_steps(self, entity_name: str, language: str) -> List[GenerationStep]:
        """Plan steps for auth module generation."""
        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description="Auth imports",
                prompt=(
                    "Generate import statements for a JWT auth service: "
                    "hashlib, secrets, hmac, os, time, datetime, typing. "
                    "Conditional imports: jose (JWT), passlib (bcrypt). "
                    "Output ONLY imports. Max 10 lines."
                ),
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description="AuthService class with __init__",
                prompt=(
                    "Generate an AuthService class with __init__(secret_key, token_expire_minutes=30). "
                    "Store secret_key, setup password hashing (try passlib, fallback to hashlib). "
                    "Output ONLY the class with __init__. Max 20 lines."
                ),
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description="hash_password and verify_password",
                prompt=(
                    "Generate hash_password(password) using PBKDF2 with random salt, "
                    "and verify_password(password, stored_hash) with hmac.compare_digest. "
                    "Output ONLY the two methods. Max 20 lines."
                ),
            ),
            GenerationStep(
                step_id=4, step_type="method",
                description="create_token and verify_token",
                prompt=(
                    "Generate create_token(user_id, role) that creates JWT with expiration, "
                    "and verify_token(token) that decodes and validates. "
                    "Use python-jose if available, fallback to HMAC-based tokens. "
                    "Output ONLY the two methods. Max 25 lines."
                ),
            ),
        ]
        return steps

    def _plan_integration_steps(self, entity_name: str, task_desc: str,
                                 language: str) -> List[GenerationStep]:
        """Plan steps for integration module (Stripe, Email, etc.)."""
        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description=f"Integration imports for {entity_name}",
                prompt=(
                    f"Generate import statements for a {entity_name} integration service. "
                    f"Include: aiohttp (async HTTP), logging, typing, json, os. "
                    f"Output ONLY imports. Max 8 lines."
                ),
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description=f"{entity_name}Client class",
                prompt=(
                    f"Generate a {entity_name}Client class with __init__(api_key, base_url). "
                    f"Setup session, headers with auth, retry config. "
                    f"Output ONLY class with __init__. Max 15 lines."
                ),
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description=f"Core operation methods for {entity_name}",
                prompt=(
                    f"Generate 2-3 async methods for {entity_name}Client that perform "
                    f"the main API operations described in: {task_desc}. "
                    f"Each method should use aiohttp with error handling. "
                    f"Output ONLY the methods. Max 30 lines."
                ),
            ),
            GenerationStep(
                step_id=4, step_type="method",
                description="Error handling and retry logic",
                prompt=(
                    f"Generate a _request method for {entity_name}Client with "
                    f"exponential backoff retry (3 attempts), timeout handling, "
                    f"and proper error classification. "
                    f"Output ONLY the method. Max 20 lines."
                ),
            ),
        ]
        return steps

    def _plan_analytics_steps(self, entity_name: str, fields: List[Dict],
                               language: str) -> List[GenerationStep]:
        """Plan steps for analytics module."""
        steps = [
            GenerationStep(
                step_id=1, step_type="imports",
                description="Analytics imports",
                prompt="Generate imports for analytics: sqlite3, logging, typing, datetime, collections. Output ONLY imports. Max 8 lines.",
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description=f"AnalyticsService for {entity_name}",
                prompt=f"Generate AnalyticsService class with __init__(db_path). Connect to SQLite. Output ONLY class + __init__. Max 15 lines.",
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description="Aggregation methods",
                prompt=f"Generate get_summary() and get_trends(metric, period) methods using SQL aggregation. Output ONLY methods. Max 25 lines.",
            ),
        ]
        return steps

    def _plan_generic_steps(self, entity_name: str, task_desc: str,
                             language: str) -> List[GenerationStep]:
        """Plan steps for generic/unknown task type."""
        return [
            GenerationStep(
                step_id=1, step_type="imports",
                description=f"Module imports for {entity_name}",
                prompt=f"Generate Python import statements for a module that: {task_desc}. Output ONLY imports. Max 10 lines.",
            ),
            GenerationStep(
                step_id=2, step_type="class_def",
                description=f"Main class for {entity_name}",
                prompt=f"Generate a Python class {entity_name}Manager with __init__ and initialize() method. Task: {task_desc}. Output ONLY class definition. Max 20 lines.",
            ),
            GenerationStep(
                step_id=3, step_type="method",
                description=f"Core logic for {entity_name}",
                prompt=f"Generate an execute() method for {entity_name}Manager that: {task_desc}. Include error handling and input validation. Output ONLY the method. Max 30 lines.",
            ),
        ]
