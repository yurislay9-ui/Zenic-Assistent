"""
ZENIC-AGENTS - FractalGenerator v16

Fase 1 (Estructural): Generate project structure and templates.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from .types import FileBlueprint, FractalSpec

logger = logging.getLogger(__name__)


# ============================================================
#  PLANTILLAS DE PROYECTOS - Fallback determinista por tipo
# ============================================================

PROJECT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "auth_system": {
        "directories": ["src/", "src/models/", "src/routes/", "src/services/", "src/middleware/", "tests/"],
        "files": [
            {
                "path": "src/__init__.py",
                "language": "python",
                "description": "Package init",
                "classes": [],
                "functions": [],
                "imports": [],
            },
            {
                "path": "src/models/user.py",
                "language": "python",
                "description": "User model with authentication fields",
                "classes": [
                    {"name": "User", "docstring": "User model with password hashing and JWT token generation", "bases": "Base"},
                ],
                "functions": [
                    {"name": "hash_password", "docstring": "Hash a plaintext password using bcrypt", "params": "password: str"},
                    {"name": "verify_password", "docstring": "Verify a plaintext password against a hash", "params": "password: str, hashed: str"},
                ],
                "imports": ["from sqlalchemy import Column, Integer, String, Boolean", "from datetime import datetime"],
            },
            {
                "path": "src/routes/auth.py",
                "language": "python",
                "description": "Authentication routes: login, register, refresh",
                "classes": [],
                "functions": [
                    {"name": "register", "docstring": "Register a new user with validated input", "params": "request"},
                    {"name": "login", "docstring": "Authenticate user and return JWT tokens", "params": "request"},
                    {"name": "refresh_token", "docstring": "Refresh an expired access token", "params": "request"},
                    {"name": "logout", "docstring": "Invalidate the current refresh token", "params": "request"},
                ],
                "imports": ["from fastapi import APIRouter, Depends, HTTPException", "from jose import jwt"],
            },
            {
                "path": "src/services/auth_service.py",
                "language": "python",
                "description": "Business logic for authentication",
                "classes": [
                    {"name": "AuthService", "docstring": "Service handling all authentication operations", "bases": ""},
                ],
                "functions": [
                    {"name": "create_tokens", "docstring": "Create access and refresh JWT tokens", "params": "user_id: int"},
                    {"name": "validate_token", "docstring": "Validate a JWT token and return payload", "params": "token: str"},
                    {"name": "revoke_token", "docstring": "Add token to revocation list", "params": "token: str"},
                ],
                "imports": ["from datetime import timedelta", "from jose import jwt, JWTError"],
            },
            {
                "path": "src/middleware/auth_middleware.py",
                "language": "python",
                "description": "Authentication middleware for request validation",
                "classes": [
                    {"name": "AuthMiddleware", "docstring": "Middleware that validates JWT tokens on protected routes", "bases": ""},
                ],
                "functions": [],
                "imports": ["from starlette.middleware.base import BaseHTTPMiddleware"],
            },
            {
                "path": "src/main.py",
                "language": "python",
                "description": "Application entry point with FastAPI setup",
                "classes": [],
                "functions": [
                    {"name": "create_app", "docstring": "Create and configure the FastAPI application", "params": ""},
                ],
                "imports": ["from fastapi import FastAPI", "from src.routes.auth import router as auth_router"],
            },
            {
                "path": "tests/test_auth.py",
                "language": "python",
                "description": "Authentication tests",
                "classes": [
                    {"name": "TestAuth", "docstring": "Test suite for authentication flow", "bases": ""},
                ],
                "functions": [
                    {"name": "test_register", "docstring": "Test user registration with valid data", "params": "client"},
                    {"name": "test_login", "docstring": "Test user login with correct credentials", "params": "client"},
                    {"name": "test_invalid_token", "docstring": "Test that invalid tokens are rejected", "params": "client"},
                ],
                "imports": ["import pytest", "from fastapi.testclient import TestClient"],
            },
        ],
        "config_files": {
            "requirements.txt": "fastapi\nuvicorn\nsqlalchemy\npython-jose[cryptography]\npasslib[bcrypt]\npython-multipart\npytest\nhttpx",
            ".env.example": "SECRET_KEY=change-me-in-production\nALGORITHM=HS256\nACCESS_TOKEN_EXPIRE_MINUTES=30",
            "config.py": "import os\n\nSECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-prod')\nALGORITHM = os.getenv('ALGORITHM', 'HS256')\nACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '30'))",
        },
    },
    "crud_dashboard": {
        "directories": ["src/", "src/models/", "src/routes/", "src/services/", "src/templates/", "static/", "tests/"],
        "files": [
            {
                "path": "src/__init__.py",
                "language": "python",
                "description": "Package init",
                "classes": [],
                "functions": [],
                "imports": [],
            },
            {
                "path": "src/models/entities.py",
                "language": "python",
                "description": "Database models for the dashboard entities",
                "classes": [
                    {"name": "Item", "docstring": "Dashboard item model with CRUD fields", "bases": "Base"},
                ],
                "functions": [],
                "imports": ["from sqlalchemy import Column, Integer, String, Float, DateTime", "from datetime import datetime"],
            },
            {
                "path": "src/routes/dashboard.py",
                "language": "python",
                "description": "Dashboard CRUD routes",
                "classes": [],
                "functions": [
                    {"name": "list_items", "docstring": "List all items with optional filtering and pagination", "params": "request"},
                    {"name": "create_item", "docstring": "Create a new dashboard item", "params": "request"},
                    {"name": "update_item", "docstring": "Update an existing dashboard item", "params": "item_id: int, request"},
                    {"name": "delete_item", "docstring": "Delete a dashboard item by ID", "params": "item_id: int"},
                ],
                "imports": ["from fastapi import APIRouter, HTTPException"],
            },
            {
                "path": "src/services/crud_service.py",
                "language": "python",
                "description": "CRUD business logic service",
                "classes": [
                    {"name": "CRUDService", "docstring": "Generic CRUD service with validation and error handling", "bases": ""},
                ],
                "functions": [],
                "imports": ["from sqlalchemy.orm import Session"],
            },
            {
                "path": "src/main.py",
                "language": "python",
                "description": "Dashboard application entry point",
                "classes": [],
                "functions": [
                    {"name": "create_app", "docstring": "Create and configure the dashboard application", "params": ""},
                ],
                "imports": ["from fastapi import FastAPI", "from src.routes.dashboard import router"],
            },
            {
                "path": "tests/test_crud.py",
                "language": "python",
                "description": "CRUD operation tests",
                "classes": [
                    {"name": "TestCRUD", "docstring": "Test suite for CRUD operations", "bases": ""},
                ],
                "functions": [
                    {"name": "test_create", "docstring": "Test item creation", "params": "client"},
                    {"name": "test_list", "docstring": "Test item listing", "params": "client"},
                    {"name": "test_update", "docstring": "Test item update", "params": "client"},
                    {"name": "test_delete", "docstring": "Test item deletion", "params": "client"},
                ],
                "imports": ["import pytest"],
            },
        ],
        "config_files": {
            "requirements.txt": "fastapi\nuvicorn\nsqlalchemy\njinja2\npytest\nhttpx",
            ".env.example": "DATABASE_URL=sqlite:///./dashboard.db\nDEBUG=True",
        },
    },
    "inventory": {
        "directories": ["src/", "src/models/", "src/routes/", "src/services/", "tests/"],
        "files": [
            {
                "path": "src/__init__.py",
                "language": "python",
                "description": "Package init",
                "classes": [],
                "functions": [],
                "imports": [],
            },
            {
                "path": "src/models/product.py",
                "language": "python",
                "description": "Product and inventory models",
                "classes": [
                    {"name": "Product", "docstring": "Product model with pricing and category", "bases": "Base"},
                    {"name": "InventoryEntry", "docstring": "Inventory stock entry with quantity tracking", "bases": "Base"},
                ],
                "functions": [],
                "imports": ["from sqlalchemy import Column, Integer, String, Float, ForeignKey"],
            },
            {
                "path": "src/routes/inventory.py",
                "language": "python",
                "description": "Inventory management routes",
                "classes": [],
                "functions": [
                    {"name": "add_product", "docstring": "Add a new product to inventory", "params": "request"},
                    {"name": "update_stock", "docstring": "Update stock quantity for a product", "params": "product_id: int, request"},
                    {"name": "check_stock", "docstring": "Check current stock level for a product", "params": "product_id: int"},
                    {"name": "low_stock_alert", "docstring": "List products below minimum stock threshold", "params": "threshold: int = 10"},
                ],
                "imports": ["from fastapi import APIRouter, HTTPException"],
            },
            {
                "path": "src/main.py",
                "language": "python",
                "description": "Inventory application entry point",
                "classes": [],
                "functions": [
                    {"name": "create_app", "docstring": "Create and configure the inventory application", "params": ""},
                ],
                "imports": ["from fastapi import FastAPI", "from src.routes.inventory import router"],
            },
        ],
        "config_files": {
            "requirements.txt": "fastapi\nuvicorn\nsqlalchemy\npytest\nhttpx",
        },
    },
}

# Default template for unknown types
DEFAULT_TEMPLATE = {
    "directories": ["src/", "tests/"],
    "files": [
        {
            "path": "src/__init__.py",
            "language": "python",
            "description": "Package init",
            "classes": [],
            "functions": [],
            "imports": [],
        },
        {
            "path": "src/main.py",
            "language": "python",
            "description": "Application entry point",
            "classes": [],
            "functions": [
                {"name": "main", "docstring": "Main entry point for the application", "params": ""},
            ],
            "imports": [],
        },
        {
            "path": "tests/test_main.py",
            "language": "python",
            "description": "Basic test file",
            "classes": [],
            "functions": [
                {"name": "test_placeholder", "docstring": "Placeholder test", "params": ""},
            ],
            "imports": ["import pytest"],
        },
    ],
    "config_files": {
        "requirements.txt": "fastapi\nuvicorn\npytest\nhttpx",
    },
}


# ============================================================
#  StructureMixin - Fase 1: Estructural
# ============================================================

class StructureMixin:
    """
    Mixin para Fase 1 (Estructural): Generar árbol de directorios y archivos.

    Intenta usar LLM para generar una estructura personalizada.
    Si el LLM no está disponible, usa templates predefinidos.
    """

    def generate_structure(self, description: str, project_type: str = "",
                           project_name: str = "",
                           language: str = "python") -> FractalSpec:
        """
        Fase 1: Genera la estructura del proyecto.

        Intenta usar LLM para generar una estructura personalizada.
        Si el LLM no está disponible, usa templates predefinidos.

        Returns: FractalSpec con directorios, archivos y blueprints.
        """
        spec = FractalSpec(
            project_name=project_name or "generated_project",
            project_type=project_type,
            language=language,
            description=description,
            phase=1,
        )

        # Intentar LLM para estructura personalizada
        if self._agent_runner and self._mini_ai and self._mini_ai.is_loaded:
            try:
                llm_spec = self._generate_structure_llm(
                    description, project_type, project_name, language
                )
                if llm_spec:
                    return llm_spec
            except Exception as e:
                logger.debug(f"FractalGenerator Fase 1 LLM failed: {e}")

        # Fallback: usar template predefinido
        template = PROJECT_TEMPLATES.get(project_type, DEFAULT_TEMPLATE)
        spec.directories = template["directories"]
        spec.files = [
            FileBlueprint(**f) for f in template["files"]
        ]
        spec.config_files = template.get("config_files", {})

        logger.info(
            f"FractalGenerator Fase 1 (template): {len(spec.files)} files, "
            f"{len(spec.directories)} directories for '{project_type}'"
        )
        return spec

    def _generate_structure_llm(self, description: str, project_type: str,
                                 project_name: str,
                                 language: str) -> Optional[FractalSpec]:
        """Intenta generar estructura via LLM."""
        system = (
            "You are a software architect. Given a project description, "
            "generate a JSON structure with directories and files. "
            "Each file needs: path, language, description, classes (name, docstring, bases), "
            "functions (name, docstring, params), imports. "
            "Reply ONLY with valid JSON, no markdown."
        )
        user = (
            f"Project: {project_name}\n"
            f"Type: {project_type}\n"
            f"Language: {language}\n"
            f"Description: {description[:300]}\n"
            f"Generate the project structure as JSON with keys: "
            f"directories, files, config_files"
        )

        response = self._mini_ai._call_llm(system_prompt=system, user_prompt=user, max_tokens=500)
        if response:
            try:
                # Try to parse JSON from response
                text = response.strip()
                # Remove markdown code blocks if present
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
                data = json.loads(text)

                spec = FractalSpec(
                    project_name=project_name,
                    project_type=project_type,
                    language=language,
                    description=description,
                    phase=1,
                )
                spec.directories = data.get("directories", [])
                import dataclasses as _dc
                _valid_keys = {field.name for field in _dc.fields(FileBlueprint)}
                spec.files = [
                    FileBlueprint(**{k: v for k, v in f.items() if k in _valid_keys})
                    for f in data.get("files", [])
                ]
                spec.config_files = data.get("config_files", {})

                logger.info(
                    f"FractalGenerator Fase 1 (LLM): {len(spec.files)} files, "
                    f"{len(spec.directories)} directories"
                )
                return spec
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.debug(f"FractalGenerator LLM JSON parse failed: {e}")

        return None
