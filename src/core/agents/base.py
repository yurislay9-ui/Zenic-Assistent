"""
ZENIC-AGENTS - BaseAgent

Clase base abstracta para todos los agentes IA.
Cada agente hereda de BaseAgent e implementa:
  - build_prompt(): Construye el prompt específico del agente
  - parse_response(): Valida y estructura la respuesta del LLM
  - fallback(): Respuesta determinista cuando el LLM no está disponible
"""

import time
import json
import re
import threading
import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar, Union

# ── Unified AgentResult: re-export from v2 schemas (single source of truth) ──
from src.core.agents_v2.schemas.types import AgentResult  # noqa: F401 — re-export

logger = logging.getLogger(__name__)

T = TypeVar('T')  # Output type


class BaseAgent(ABC, Generic[T]):
    """
    Clase base abstracta para todos los agentes IA.

    Flujo de ejecución:
    1. run() → llama al AgentRunner
    2. AgentRunner → intenta LLM → parse_response()
    3. Si LLM falla → fallback()
    4. Resultado se cachea si es exitoso

    Cada agente concreto implementa:
    - name: Nombre del agente
    - build_prompt(): Construye system + user prompt
    - parse_response(): Parsea la respuesta del LLM al esquema de salida
    - fallback(): Respuesta determinista sin LLM
    """

    def __init__(self, name: str = "base") -> None:
        self.name = name
        self._call_count = 0
        self._llm_success_count = 0
        self._fallback_count = 0
        self._cache_hit_count = 0
        self._total_duration_ms = 0
        self._last_error = ""
        self._stats_lock = threading.Lock()

    @property
    def stats(self) -> dict[str, Any]:
        """Estadísticas de uso del agente."""
        return {
            "name": self.name,
            "total_calls": self._call_count,
            "llm_success": self._llm_success_count,
            "fallback_calls": self._fallback_count,
            "cache_hits": self._cache_hit_count,
            "llm_rate": self._llm_success_count / max(self._call_count, 1),
            "fallback_rate": self._fallback_count / max(self._call_count, 1),
            "avg_duration_ms": self._total_duration_ms / max(self._call_count, 1),
            "last_error": self._last_error,
        }

    @abstractmethod
    def build_prompt(self, input_data: Any) -> tuple[str, str]:
        """
        Construye el prompt para el LLM.

        Returns:
            tuple: (system_prompt, user_prompt)
        """
        ...

    @abstractmethod
    def parse_response(self, raw_response: str, input_data: Any) -> Optional[T]:
        """
        Parsea y valida la respuesta del LLM.

        Args:
            raw_response: Texto crudo del LLM
            input_data: Datos de entrada originales (para contexto)

        Returns:
            Objeto de salida del esquema, o None si la respuesta es inválida
        """
        ...

    @abstractmethod
    def fallback(self, input_data: Any) -> T:
        """
        Respuesta determinista cuando el LLM no está disponible.

        Debe producir una respuesta útil pero básica.
        Sin LLM, sin dependencias externas, 100% determinista.
        """
        ...

    def validate_output(self, output: T) -> bool:
        """
        Validación post-parseo. Override para validación personalizada.
        Retorna True si el output es válido.
        """
        return output is not None

    def _update_stats(self, source: str, duration_ms: int, error: str = "") -> None:
        """Actualiza estadísticas internas del agente."""
        with self._stats_lock:
            self._call_count += 1
            self._total_duration_ms += duration_ms
            if source == "llm":
                self._llm_success_count += 1
            elif source == "fallback":
                self._fallback_count += 1
            elif source == "cache":
                self._cache_hit_count += 1
            if error:
                self._last_error = error

    @staticmethod
    def extract_json(text: str) -> Optional[Union[dict[str, Any], list[Any]]]:
        """
        Extrae JSON de una respuesta del LLM.
        Maneja bloques de código markdown y texto circundante.
        """
        # Try direct parse first
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to find JSON in markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Balanced-brace extraction for nested JSON objects
        for i, ch in enumerate(text):
            if ch == '{':
                depth = 0
                for j in range(i, len(text)):
                    if text[j] == '{':
                        depth += 1
                    elif text[j] == '}':
                        depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[i:j + 1])
                        except json.JSONDecodeError:
                            break

        # Try to find JSON array
        for i, ch in enumerate(text):
            if ch == '[':
                depth = 0
                for j in range(i, len(text)):
                    if text[j] == '[':
                        depth += 1
                    elif text[j] == ']':
                        depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[i:j + 1])
                        except json.JSONDecodeError:
                            break

        return None

    @staticmethod
    def extract_list(text: str) -> list:
        """Extrae una lista de items numerados o con bullets de texto."""
        items = []
        for line in text.strip().split('\n'):
            line = line.strip()
            # Match numbered items: "1. item" or "1) item"
            match = re.match(r'^\d+[\.\)]\s*(.+)', line)
            if match:
                items.append(match.group(1).strip())
            # Match bullet items: "- item" or "* item"
            elif line.startswith('- ') or line.startswith('* '):
                items.append(line[2:].strip())
        return items

    @staticmethod
    def clean_llm_text(text: str) -> str:
        """Limpia texto del LLM: quita think blocks, markdown, etc."""
        # Quitar think blocks de Qwen3 (formato: <think...>...</think > o <think...>...</think\n>)
        text = re.sub(r'<think[^>]*>.*?</think\s*>', '', text, flags=re.DOTALL)
        # Quitar markdown code fences
        text = re.sub(r'```(?:\w+)?\s*', '', text)
        text = re.sub(r'\s*```', '', text)
        # Quitar asteriscos de bold/markdown
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        # Limpiar espacios extra
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()
