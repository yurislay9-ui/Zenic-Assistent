"""Plan definitions with resource quotas for multi-tenant support."""

from typing import Dict, Any

PLAN_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "free": {
        "display_name": "Free",
        "max_requests_per_minute": 10,
        "max_requests_per_day": 500,
        "max_tokens_per_day": 50000,
        "max_concurrent": 2,
        "max_storage_mb": 50,
        "features": ["basic_pipeline", "chat_completions"],
    },
    "pro": {
        "display_name": "Professional",
        "max_requests_per_minute": 60,
        "max_requests_per_day": 5000,
        "max_tokens_per_day": 500000,
        "max_concurrent": 10,
        "max_storage_mb": 500,
        "features": [
            "basic_pipeline", "chat_completions", "app_generation",
            "automation_generation", "schema_design", "thinking_engine",
            "reasoning_engine", "logic_chains",
        ],
    },
    "enterprise": {
        "display_name": "Enterprise",
        "max_requests_per_minute": 200,
        "max_requests_per_day": 50000,
        "max_tokens_per_day": 5000000,
        "max_concurrent": 50,
        "max_storage_mb": 5000,
        "features": "all",
    },
}
