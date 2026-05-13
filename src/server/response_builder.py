"""
ZENIC-AGENTS v16 - Response Builder

Construye respuestas OpenAI-compatible para el servidor HTTP.
Centraliza el formateo de respuestas normales, partial reasoning y errores,
eliminando la duplicacion entre main.py (TUI/Textual) y main_headless.py (Termux).

Open Design: Supports <artifact> wrapping when visual requests are detected.
"""

import time
import uuid
from typing import Any, Dict, Optional

from src.core.shared.contracts import HAS_Z3
from src.core.shared._version import ZENIC_VERSION_STR, ZENIC_FULL_NAME


def _solver_name():
    """Retorna el nombre del solver activo."""
    return "Z3" if HAS_Z3 else "AC-3"


def build_normal_response(data: Dict[str, Any], result: Dict[str, Any], user_msg: str, governor: Optional[Any] = None) -> Dict[str, Any]:
    """Construye la respuesta OpenAI-compatible para un resultado normal del pipeline.

    Robustness: Handles DAG_TIMEOUT, empty results, and missing fields gracefully.
    Cline MUST always receive valid OpenAI JSON — never an empty response.

    Args:
        data: JSON original de la peticion del cliente
        result: Dict resultado del ZenicOrchestrator.execute()
        user_msg: Mensaje del usuario (str)
        governor: ResourceGovernor opcional (headless mode)

    Returns:
        Dict con la respuesta OpenAI-compatible
    """
    # Defensive: ensure data is never None
    if not isinstance(data, dict):
        data = {}
    # Defensive: ensure result is a dict with required fields
    if not isinstance(result, dict):
        result = {"status": "ERROR", "code": "", "error": "Empty result from pipeline"}

    status = result.get("status", "UNKNOWN")

    # Handle DAG_TIMEOUT explicitly — Cline needs to know the pipeline was interrupted
    if status == "DAG_TIMEOUT":
        content_parts = [
            f"{ZENIC_FULL_NAME} - DAG_TIMEOUT",
            "The pipeline exceeded maximum iterations and was interrupted.",
            "This usually means the model is slow on ARM (first request after startup).",
            "Please try again — subsequent requests will be faster after warm-up.",
        ]
        if result.get("explanations"):
            for exp in result["explanations"]:
                content_parts.append(f"  {exp}")
        response_content = "\n".join(content_parts)
        return {
            "id": f"zenic-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": data.get("model", "zenic-agents"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_content},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": len(user_msg.split()), "completion_tokens": len(response_content.split()), "total_tokens": len(user_msg.split()) + len(response_content.split())},
            "zenic_metadata": {"status": "DAG_TIMEOUT", "processing_time_ms": result.get("processing_time_ms", 0)},
        }

    content_parts = [f"{ZENIC_FULL_NAME} - {status}"]

    if result.get("explanations"):
        for exp in result["explanations"]:
            content_parts.append(f"  {exp}")

    if result.get("code"):
        lang = result.get("ast_analysis", {}).get("language", "python")
        content_parts.append(f"\n```{lang}\n{result['code']}\n```")
    elif not result.get("explanations") and status not in ("CACHED", "NO_OP"):
        # No code AND no explanations — likely a pipeline issue
        content_parts.append("\nNo output was generated. The pipeline may have timed out.")

    if result.get("warnings"):
        content_parts.append("\nWarnings:")
        for w in result["warnings"]:
            content_parts.append(f"  - {w}")

    if result.get("cache_source"):
        content_parts.append(
            f"\nCache hit: {result['cache_source']} (hits: {result.get('cache_hits', 0)})"
        )

    # Metadata del solver y MCTS
    solver_status = result.get('solver_status', 'N/A')
    mcts_sims = result.get('mcts_simulations', 0)
    mcts_depth = result.get('mcts_depth_reached', 0)
    paths_explored = result.get('paths_explored', 0)
    paths_pruned = result.get('paths_pruned', 0)

    sname = _solver_name()
    meta_parts = [
        f"\nTime: {result.get('processing_time_ms', 0)}ms",
        f"Route: {result.get('route', 'N/A')}",
        f"Hash: {result.get('hash', 'N/A')}",
        f"Solver({sname}): {solver_status}",
        f"MCTS: {mcts_sims} sims, depth {mcts_depth}",
    ]
    if paths_explored:
        meta_parts.append(f"Paths: {paths_explored} explored, {paths_pruned} pruned")

    # Info de recursos si governor disponible (headless mode)
    if governor:
        res = governor.get_status()
        meta_parts.append(f"RAM: {res['ram_usage_mb']}MB/{res['ram_limit_mb']}MB")
        meta_parts.append(f"CPU: {res['cpu_usage_pct']}%")

    content_parts.append(" | ".join(meta_parts))
    response_content = "\n".join(content_parts)

    zenic_metadata = {
        "status": result["status"],
        "hash": result.get("hash", "N/A"),
        "processing_time_ms": result.get("processing_time_ms", 0),
        "route": result.get("route", ""),
        "criticality": result.get("criticality", 0),
        "solver_type": sname,
        "solver_status": solver_status,
        "solver_proof": result.get("solver_proof"),
        "mcts_simulations": mcts_sims,
        "mcts_depth_reached": mcts_depth,
        "cache_hit": bool(result.get("cache_source")),
        "paths_explored": paths_explored,
        "paths_pruned": paths_pruned,
        "symbolic_execution": True,
    }
    if governor:
        zenic_metadata["platform"] = "termux-proot"

    return {
        "id": f"zenic-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": data.get("model", "zenic-agents"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_content
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": len(user_msg.split()),
            "completion_tokens": len(response_content.split()),
            "total_tokens": len(user_msg.split()) + len(response_content.split()),
        },
        "zenic_metadata": zenic_metadata,
    }


def build_partial_reasoning_response(data: Dict[str, Any], result: Dict[str, Any], user_msg: str) -> Dict[str, Any]:
    """Construye la respuesta de Razonamiento Parcial con tool_calls.

    El payload JSON incluye tool_calls para que el cliente (Cline/Aide)
    pueda continuar la operacion subdividida.

    Args:
        data: JSON original de la peticion del cliente
        result: Dict resultado del ZenicOrchestrator con partial_reasoning
        user_msg: Mensaje del usuario (str)

    Returns:
        Dict con la respuesta OpenAI-compatible con tool_calls
    """
    # Defensive: ensure result is never None
    if not isinstance(result, dict):
        result = {"status": "ERROR", "partial_reasoning_payload": {}}
    partial = result.get("partial_reasoning_payload", {})

    return {
        "id": f"zenic-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": data.get("model", "zenic-agents"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": partial.get(
                    "content",
                    result.get("explanations", [""])[0] if result.get("explanations") else ""
                ),
                "tool_calls": partial.get("tool_calls", []),
            },
            "finish_reason": partial.get("finish_reason", "tool_calls"),
        }],
        "usage": result.get("usage_metadata", {
            "prompt_tokens": len(user_msg.split()),
            "completion_tokens": 0,
            "total_tokens": len(user_msg.split()),
        }),
        "zenic_metadata": {
            "status": "PARTIAL_REASONING",
            "processing_time_ms": result.get("processing_time_ms", 0),
            "route": result.get("route", ""),
            "criticality": result.get("criticality", 0),
            "solver_status": result.get("solver_status", ""),
            "paths_explored": result.get("paths_explored", 0),
            "paths_pruned": result.get("paths_pruned", 0),
            "partial_reasoning": True,
        }
    }


def build_error_response(error_msg: str) -> Dict[str, Any]:
    """
    Construye la respuesta de error interno compatible con OpenAI.

    Args:
        error_msg: Mensaje de error (str)

    Returns:
        Dict con la respuesta OpenAI-compatible de error
    """
    error_content = (
        f"{ZENIC_FULL_NAME} - Internal Error\n"
        f"{error_msg}\n\nTry reformulating your request."
    )
    return {
        "id": f"zenic-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "zenic-agents",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": error_content
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_overloaded_response() -> Dict[str, Any]:
    """
    Construye la respuesta de servidor sobrecargado (503).

    Returns:
        Dict con la respuesta de error 503 in OpenAI-compatible format.
        Cline expects OpenAI format for ALL responses, including errors.
    """
    error_content = (
        f"{ZENIC_FULL_NAME} - Server Overloaded\n"
        "Server RAM is critically low. Retry later.\n"
        "This is common on ARM devices — the model may still be loading."
    )
    return {
        "id": f"zenic-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "zenic-agents",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": error_content
            },
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def build_artifact_response(data: Dict[str, Any], result: Dict[str, Any],
                             user_msg: str, governor: Optional[Any] = None) -> Dict[str, Any]:
    """Construye la respuesta OpenAI-compatible con código envuelto en <artifact> tags.

    Usado cuando Open Design envía una petición visual/UI y espera el código
    final envuelto en etiquetas <artifact> para renderizado en su iframe.

    Args:
        data: JSON original de la petición del cliente.
        result: Dict resultado del orquestador.
        user_msg: Mensaje del usuario.
        governor: ResourceGovernor opcional.

    Returns:
        Dict con la respuesta OpenAI-compatible con artifact wrapping.
    """
    # Defensive: ensure result is never None
    if not isinstance(result, dict):
        result = {"status": "ERROR", "code": "", "error": "Empty result from pipeline"}
    # First build the normal response content
    base_response = build_normal_response(data, result, user_msg, governor)

    # Wrap the content in <artifact> tags if code is present
    content = base_response["choices"][0]["message"]["content"]
    lang = result.get("ast_analysis", {}).get("language", "html")

    try:
        from src.core.open_design import ArtifactBuilder, get_open_design_config
        config = get_open_design_config()
        if config.artifact_wrapping_enabled:
            # Extract code from markdown blocks and wrap in artifacts
            wrapped = ArtifactBuilder.wrap_response_content(
                content,
                detection_result={"is_open_design": True, "is_visual_request": True},
                language=lang,
            )
            base_response["choices"][0]["message"]["content"] = wrapped
    except ImportError:
        pass  # Open Design module not available — return unwrapped

    # Add visual bypass metadata
    if result.get("visual_bypass"):
        base_response["zenic_metadata"]["visual_bypass"] = result["visual_bypass"]

    return base_response
