"""
A02 EntityExtractor — SINGLE RESPONSIBILITY: Extract named entities from text.

Deterministic regex + pattern matching. No AI.
Extracts: files, languages, functions, code blocks, frameworks, domains.
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import EntityResult

# ──────────────────────────────────────────────────────────────
# ENTITY EXTRACTION CONSTANTS
# ──────────────────────────────────────────────────────────────

EXT_LANG_MAP: dict[str, str] = {
    ".py": "python", ".kt": "kotlin", ".go": "go", ".js": "javascript",
    ".ts": "typescript", ".java": "java", ".rs": "rust", ".c": "c",
    ".cpp": "cpp", ".rb": "ruby", ".cs": "csharp", ".php": "php",
    ".swift": "swift", ".scala": "scala",
}

FRAMEWORKS = {
    "django", "flask", "fastapi", "react", "vue", "angular", "spring",
    "express", "nestjs", "stripe", "twilio", "firebase", "supabase",
    "postgres", "mongodb", "redis", "docker", "kubernetes",
}

DOMAINS = {
    "payment", "auth", "notification", "email", "database", "api",
    "inventory", "crm", "invoice", "scheduler", "analytics", "report",
    "webhook", "streaming", "cache", "queue",
}

# Regex patterns
FILE_PATTERN = re.compile(r'\b[\w\-]+\.(?:py|kt|go|js|ts|java|rs|c|cpp|rb|cs|php|swift|scala)\b')
FUNCTION_PATTERN_EN = re.compile(r'\b(?:function|def|fun|func|method|class)\s+(\w+)')
FUNCTION_PATTERN_ES = re.compile(r'\b(?:funcion|metodo|clase)\s+(\w+)')
CLASS_PATTERN = re.compile(r'\bclass\s+(\w+)')
CODE_BLOCK_PATTERN = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)


class EntityExtractor(BaseAgent[EntityResult]):
    """
    A02: Extract named entities from text.

    Single Responsibility: Entity extraction ONLY.
    Method: Regex + keyword matching (deterministic).
    Fallback: Return empty EntityResult.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A02_EntityExtractor", **kwargs)

    def execute(self, input_data: Any) -> EntityResult:
        text = str(input_data) if input_data else ""
        if not text:
            return self.fallback(input_data)

        files = self._extract_files(text)
        langs = self._infer_languages(files, text)
        functions = self._extract_functions(text)
        code_blocks = self._extract_code_blocks(text)
        frameworks = self._extract_frameworks(text)
        domains = self._extract_domains(text)

        return EntityResult(
            files=files,
            langs=langs,
            functions=functions,
            code_blocks=code_blocks,
            frameworks=frameworks,
            domains=domains,
            source="deterministic",
        )

    def _extract_files(self, text: str) -> list[str]:
        """Extract file names from text."""
        return list(set(FILE_PATTERN.findall(text)))

    def _infer_languages(self, files: list[str], text: str) -> list[str]:
        """Infer programming languages from file extensions + text."""
        langs = set()
        for f in files:
            for ext, lang in EXT_LANG_MAP.items():
                if f.endswith(ext):
                    langs.add(lang)
        # Fallback: scan text for language mentions
        for lang in set(EXT_LANG_MAP.values()):
            if lang in text.lower():
                langs.add(lang)
        return list(langs)

    def _extract_functions(self, text: str) -> list[str]:
        """Extract function/method/class names."""
        names = set()
        for pattern in [FUNCTION_PATTERN_EN, FUNCTION_PATTERN_ES, CLASS_PATTERN]:
            for match in pattern.finditer(text):
                names.add(match.group(1))
        return list(names)

    def _extract_code_blocks(self, text: str) -> list[str]:
        """Extract code blocks from markdown fences."""
        blocks = []
        for match in CODE_BLOCK_PATTERN.finditer(text):
            blocks.append(match.group(2))
        return blocks

    def _extract_frameworks(self, text: str) -> list[str]:
        """Detect framework mentions."""
        text_lower = text.lower()
        return [fw for fw in FRAMEWORKS if fw in text_lower]

    def _extract_domains(self, text: str) -> list[str]:
        """Detect domain mentions."""
        text_lower = text.lower()
        return [d for d in DOMAINS if d in text_lower]

    def fallback(self, input_data: Any) -> EntityResult:
        return EntityResult(source="fallback")
