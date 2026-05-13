"""
Tipos de respuesta del asistente.

Modela las respuestas del asistente incluyendo formato,
metadata, streaming chunks y soporte para tool calls.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResponseFormat(str, Enum):
    """Formato de la respuesta del asistente."""
    TEXT = "text"                    # Texto plano
    MARKDOWN = "markdown"            # Markdown formateado
    CODE_BLOCK = "code_block"        # Bloque de codigo
    MIXED = "mixed"                  # Mixto: texto + codigo
    TOOL_RESULT = "tool_result"      # Resultado de herramienta
    ERROR = "error"                  # Mensaje de error


@dataclass
class ResponseMetadata:
    """Metadata de la respuesta generada."""
    timestamp: float = 0.0
    latency_ms: float = 0.0
    token_count: int = 0
    format: ResponseFormat = ResponseFormat.MARKDOWN
    source: str = "deterministic"     # deterministic, cached, llm, fallback
    intent_category: str = ""
    route_taken: str = ""
    confidence: float = 0.0
    engine_used: bool = False         # Si uso el motor Zenic-Agents
    tools_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class AssistantResponse:
    """
    Respuesta completa del asistente.

    Contiene el contenido principal, formato, metadata
    y opcionalmente tool calls y resultados.
    """
    content: str = ""
    format: ResponseFormat = ResponseFormat.MARKDOWN
    metadata: ResponseMetadata = field(default_factory=ResponseMetadata)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.content.strip()) == 0

    @property
    def has_code(self) -> bool:
        """True si la respuesta contiene bloques de codigo."""
        return "```" in self.content or self.format == ResponseFormat.CODE_BLOCK

    @property
    def has_tools(self) -> bool:
        return len(self.tool_calls) > 0 or len(self.tool_results) > 0

    @property
    def is_error(self) -> bool:
        return self.format == ResponseFormat.ERROR

    def to_openai_format(self) -> dict[str, Any]:
        """Convierte a formato OpenAI chat completion response."""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": self.content,
        }
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg

    @classmethod
    def from_text(
        cls,
        text: str,
        fmt: ResponseFormat = ResponseFormat.MARKDOWN,
        source: str = "deterministic",
    ) -> AssistantResponse:
        """Crea una respuesta simple desde texto."""
        return cls(
            content=text,
            format=fmt,
            metadata=ResponseMetadata(source=source),
        )

    @classmethod
    def from_error(cls, error: str, source: str = "fallback") -> AssistantResponse:
        """Crea una respuesta de error."""
        return cls(
            content=error,
            format=ResponseFormat.ERROR,
            metadata=ResponseMetadata(source=source),
        )


@dataclass
class StreamingChunk:
    """
    Chunk de respuesta para streaming.

    Cada chunk es una parte incremental de la respuesta
    que se envia al cliente conforme se genera.
    """
    chunk_id: str = ""
    content: str = ""
    is_final: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, content: str, chunk_id: str = "", is_final: bool = False) -> StreamingChunk:
        """Crea un chunk de streaming."""
        return cls(
            chunk_id=chunk_id or str(time.time_ns()),
            content=content,
            is_final=is_final,
        )

    def to_sse(self) -> str:
        """Convierte a formato Server-Sent Events."""
        import json
        data = {
            "id": self.chunk_id,
            "content": self.content,
            "is_final": self.is_final,
        }
        if self.metadata:
            data["metadata"] = self.metadata
        return f"data: {json.dumps(data)}\n\n"
