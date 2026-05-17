"""
Formateador de respuestas del motor Zenic-Agents.

Convierte los resultados del motor (dict) en texto
formateado como respuesta del asistente.
"""

from __future__ import annotations

from typing import Any

from ..types.personality import PersonalityProfile


class EngineFormatter:
    """
    Formatea resultados del motor Zenic-Agents como
    respuestas legibles del asistente.
    """

    def format(
        self, engine_result: dict[str, Any], profile: PersonalityProfile
    ) -> str:
        """
        Formatea un resultado del motor como respuesta.

        Args:
            engine_result: Diccionario resultado del motor.
            profile: Perfil de personalidad actual.

        Returns:
            Texto formateado con markdown.
        """
        status = engine_result.get("status", "UNKNOWN")
        code = engine_result.get("code", "")
        explanations = engine_result.get("explanations", [])
        error = engine_result.get("error", "")
        route = engine_result.get("route", "")
        verdict = engine_result.get("verdict", "")
        processing_time = engine_result.get("processing_time_ms", 0)

        parts: list[str] = []

        # Encabezado de estado
        self._format_status(parts, status, verdict, error)

        # Codigo generado
        if code:
            parts.append(f"\n```python\n{code}\n```")

        # Explicaciones
        if explanations:
            self._format_explanations(parts, explanations)

        # Metadata del motor
        self._format_metadata(parts, route, processing_time)

        return "\n".join(parts)

    @staticmethod
    def _format_status(
        parts: list[str], status: str, verdict: str, error: str
    ) -> None:
        """Formatea el encabezado de estado."""
        if status == "SUCCESS":
            parts.append("**Resultado:** Aprobado")
            if verdict:
                parts.append(f"- Veredicto: {verdict}")
        elif status == "REJECTED":
            parts.append("**Resultado:** Rechazado")
            if error:
                parts.append(f"- Razon: {error}")
        elif status == "CACHED":
            parts.append("**Resultado:** Cache hit (respuesta previa)")
        elif status == "UNAVAILABLE":
            parts.append("**Resultado:** Motor no disponible")
            parts.append("- Funcionando en modo conversacional puro")
        else:
            parts.append(f"**Resultado:** {status}")

    @staticmethod
    def _format_explanations(
        parts: list[str], explanations: list
    ) -> None:
        """Formatea la seccion de explicaciones."""
        parts.append("\n**Explicaciones:**")
        for exp in explanations:
            parts.append(f"- {exp}")

    @staticmethod
    def _format_metadata(
        parts: list[str], route: str, processing_time: float
    ) -> None:
        """Formatea la metadata del motor."""
        meta_parts = []
        if route:
            meta_parts.append(f"Ruta: {route}")
        if processing_time:
            meta_parts.append(f"Tiempo: {processing_time}ms")
        if meta_parts:
            parts.append(f"\n*{' | '.join(meta_parts)}*")
