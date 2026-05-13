"""
ZENIC-AGENTS - ContextPointerEngine (Vectorización de Firmas para Code Path)

Resuelve la pérdida de datos en contextos de 20K+ tokens implementando
un sistema de PUNTEROS DE CONTEXTO que reemplaza los resúmenes semánticos.

Problema:
  Cuando OpenClaw envía un payload masivo de código (>20K tokens),
  comprimirlo en un resumen semántico pierde detalles críticos.
  El modelo Qwen no puede modificar código que no ve.

Solución:
  1. Vectorización de Firmas: cada función/clase se indexa por su firma
  2. Cuando se necesita modificar código, se pasan solo las COORDENADAS
  3. El código puro se almacena en disco de forma aislada
  4. Cuando el modelo genera una modificación, el AST Surgeon opera
     directamente sobre el archivo en disco, no sobre el contexto comprimido

Flujo:
  Código grande → SignatureIndex → ContextPointer[] → Modelo Qwen
       ↓                                              ↓
  Almacenado en disco                    Modificación → AST Surgeon → Archivo en disco

Ventajas:
  - El modelo ve "coordenadas" compactas (~100 tokens vs 20K)
  - El código real nunca se pierde (está en disco)
  - El AST Surgeon opera directamente sobre archivos
  - Compatible con SemanticEngine para búsqueda semántica de funciones
"""

from .context_ptr_parts import *  # noqa: F401,F403
from .context_ptr_parts import FunctionSignature, ContextPointer, SignatureIndex  # noqa: F401

__all__ = [
    "FunctionSignature",
    "ContextPointer",
    "SignatureIndex",
    "CONTEXT_STORE_ROOT",
]
