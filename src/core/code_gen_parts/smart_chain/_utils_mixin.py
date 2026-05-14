"""SmartPromptChain - Utility Methods."""

import re
import logging
from typing import Optional

logger = logging.getLogger("zenic_agents.code_gen_parts.smart_chain")


class SmartChainUtilsMixin:
    """Mixin providing utility methods."""

    def _fallback_tests(self, desc: str) -> str:
        """Generate basic pytest tests."""
        return (
            "\n\nimport pytest\n\n\n"
            "class TestService:\n"
            "    \"\"\"Auto-generated tests for the service.\"\"\"\n\n"
            "    def setup_method(self):\n"
            "        \"\"\"Setup test fixtures.\"\"\"\n"
            "        self.service = None  # Initialize with your service\n\n"
            "    def test_create(self):\n"
            "        \"\"\"Test create operation.\"\"\"\n"
            "        result = self.service.create({'name': 'test', 'status': 'active'})\n"
            "        assert result['success'] is True\n\n"
            "    def test_read(self):\n"
            "        \"\"\"Test read operation.\"\"\"\n"
            "        result = self.service.read(1)\n"
            "        assert result is not None or result == {'success': True}\n\n"
            "    def test_list(self):\n"
            "        \"\"\"Test list operation.\"\"\"\n"
            "        result = self.service.list(limit=10)\n"
            "        assert isinstance(result, list)\n"
        )

    # ================================================================
    #  HELPERS
    # ================================================================

    @staticmethod
    def _detect_task_type(description: str) -> str:
        """Detect what type of generation task this is."""
        desc = description.lower()
        if any(kw in desc for kw in ["crud", "create", "read", "update", "delete",
                                      "service", "api", "resource", "manage"]):
            return "crud"
        if any(kw in desc for kw in ["auth", "jwt", "login", "token", "password",
                                      "registro", "signup"]):
            return "auth"
        if any(kw in desc for kw in ["stripe", "payment", "email", "smtp",
                                      "telegram", "webhook", "integration",
                                      "pago", "correo"]):
            return "integration"
        if any(kw in desc for kw in ["analytics", "report", "dashboard",
                                      "stats", "metric", "analisis"]):
            return "analytics"
        return "generic"

    @staticmethod
    def _extract_code(text: str, language: str = "python") -> Optional[str]:
        """Extract code from markdown code blocks."""
        # Try ```python ... ``` or ``` ... ```
        pattern = rf'```(?:{language})?\s*\n(.*?)```'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None
