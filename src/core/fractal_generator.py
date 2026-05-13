"""
ZENIC-AGENTS - FractalGenerator v16

Generación Fractal (Top-Down) para apps avanzadas de múltiples archivos.

El límite de 600 tokens por llamada a Qwen3-0.6B impide generar una
app completa de una vez. FractalGenerator divide el trabajo en 3 fases:

  Fase 1 (Estructural): La IA solo genera el árbol de directorios y
    los nombres de archivos (main.py, models.py, auth.py, etc.).
    Output: Estructura del proyecto como FractalSpec.

  Fase 2 (Esqueletos): Usando el AST Surgeon (Nivel 5), inyecta las
    clases y funciones vacías con sus docstrings. Cada archivo se
    procesa individualmente, respetando el límite de tokens.
    Output: Archivos con esqueletos de código.

  Fase 3 (Relleno): El LLM toma archivo por archivo, lee el docstring
    de cada función/clase, y rellena la lógica paso a paso. Cada
    llamada al LLM se enfoca en UNA función o UNA clase.
    Output: Archivos completos con lógica implementada.

Integración con DAGOrchestrator:
  - Se invoca via acción SCAFFOLD_FRACTAL en _execute_step()
  - Usa CodeAgent + ASTSurgeon como componentes subyacentes
  - Compatible con F5 (ValidationAgent valida cada fase)
  - Compatible con F4 (CriticalityAgent ajusta defensividad)

Restricciones de diseño:
  - Cada llamada LLM ≤ 600 tokens (ventana de Qwen3-0.6B)
  - Todo tiene fallback determinista
  - Compatible con Android/Termux, 500MB RAM

Facade module — all implementation lives in the fractal_parts sub-package.
"""

from .fractal_parts import (
    FileBlueprint,
    FractalSpec,
    FractalResult,
    FractalGenerator,
    PROJECT_TEMPLATES,
    DEFAULT_TEMPLATE,
)

__all__ = [
    "FileBlueprint",
    "FractalSpec",
    "FractalResult",
    "FractalGenerator",
    "PROJECT_TEMPLATES",
    "DEFAULT_TEMPLATE",
]
