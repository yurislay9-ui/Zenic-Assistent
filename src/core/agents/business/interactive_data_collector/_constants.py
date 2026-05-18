"""
Constants and validation registries for InteractiveDataCollector.
"""

import re

# ──────────────────────────────────────────────────────────────
# LIMITS
# ──────────────────────────────────────────────────────────────

MAX_ANSWER_LENGTH = 10000
MAX_QUESTIONS_PER_ROUND = 10
MAX_ROUNDS = 20

# ──────────────────────────────────────────────────────────────
# FIELD TYPE VALIDATORS (deterministic, no AI)
# ──────────────────────────────────────────────────────────────

FIELD_VALIDATORS = {
    "text": lambda v: len(v) > 0,
    "string": lambda v: len(v) > 0,
    "email": lambda v: bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v)),
    "url": lambda v: bool(re.match(r"^https?://[^\s]+$", v)),
    "number": lambda v: v.replace(".", "", 1).replace("-", "", 1).isdigit(),
    "integer": lambda v: v.lstrip("-").isdigit(),
    "boolean": lambda v: v.lower() in ("true", "false", "yes", "no", "1", "0"),
    "enum": lambda v: len(v) > 0,  # validated against variants separately
    "date": lambda v: bool(re.match(r"^\d{4}-\d{2}-\d{2}$", v)),
    "phone": lambda v: bool(re.match(r"^\+?[\d\s\-\(\)]{7,}$", v)),
    "currency": lambda v: bool(re.match(r"^[A-Z]{3}$", v)) or v.replace(".", "", 1).isdigit(),
    "json": lambda v: v.startswith("{") or v.startswith("[") or v.startswith('"'),
}

# ──────────────────────────────────────────────────────────────
# FIELD TYPE SUGGESTIONS
# ──────────────────────────────────────────────────────────────

FIELD_SUGGESTIONS = {
    "business_name": ["Mi Empresa S.A.", "Startup Inc.", "Consultora ABC"],
    "business_email": ["contacto@miempresa.com", "info@startup.com"],
    "business_phone": ["+1 555 0100", "+34 91 123 4567"],
    "currency": ["USD", "EUR", "MXN", "COP", "ARS", "CLP"],
    "country": ["US", "ES", "MX", "CO", "AR", "CL"],
    "language": ["es", "en", "pt", "fr"],
    "timezone": ["America/Havana", "Europe/Madrid", "America/Mexico_City", "America/Bogota"],
    "website": ["https://miempresa.com", "https://startup.io"],
    "industry": ["technology", "healthcare", "finance", "education", "retail"],
    "team_size": ["1-5", "6-20", "21-50", "51-200", "200+"],
}
