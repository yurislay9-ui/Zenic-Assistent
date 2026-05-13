"""
ZENIC-AGENTS - FractalGenerator v16

Main FractalGenerator class combining all mixins + pattern implementation
+ project generation helpers.
"""

import time
import asyncio
import logging
from typing import Dict, Any, List, AsyncIterator, Iterator

from .types import FileBlueprint, FractalSpec, FractalResult
from .structure import StructureMixin, PROJECT_TEMPLATES
from .skeletons import SkeletonsMixin
from .fill import FillMixin

logger = logging.getLogger(__name__)


# ============================================================
#  FractalGenerator - Motor de generación fractal
# ============================================================

class FractalGenerator(StructureMixin, SkeletonsMixin, FillMixin):
    """
    Generador Fractal (Top-Down) para proyectos de múltiples archivos.

    Divide la generación de una app completa en 3 fases, respetando
    el límite de 600 tokens por llamada al LLM:

    Fase 1 (Estructural): Genera el árbol de directorios + nombres
      de archivos + descripciones. Output: FractalSpec completo.

    Fase 2 (Esqueletos): Para cada archivo en el FractalSpec, inyecta
      imports, clases vacías y funciones vacías con docstrings usando
      AST Surgeon. Output: Archivos con esqueletos compilables.

    Fase 3 (Relleno): Para cada función/clase vacía, el LLM lee el
      docstring y genera la lógica. Se procesa item por item.
      Output: Archivos completos con lógica implementada.
    """

    def __init__(self, code_agent=None, ast_surgeon=None,
                 agent_runner=None, mini_ai=None) -> None:
        self._code_agent = code_agent
        self._ast_surgeon = ast_surgeon
        self._agent_runner = agent_runner
        self._mini_ai = mini_ai

    def _generate_pattern_implementation(self, func_signature: str,
                                           bp: FileBlueprint,
                                           spec: FractalSpec,
                                           indent: str) -> List[str]:
        """Genera implementación basada en patrones comunes de nombres."""
        name = func_signature.lower()
        impl_lines = []

        # Patrones comunes de implementación
        if "create" in name or "add" in name or "register" in name:
            impl_lines = [
                f"{indent}try:",
                f"{indent}    # TODO: Add validation",
                f"{indent}    # TODO: Save to database",
                f"{indent}    return {{'status': 'created'}}",
                f"{indent}except Exception as e:",
                f"{indent}    raise ValueError(str(e))",
            ]
        elif "get" in name or "list" in name or "find" in name or "check" in name:
            impl_lines = [
                f"{indent}try:",
                f"{indent}    # TODO: Query database",
                f"{indent}    return []",
                f"{indent}except Exception as e:",
                f"{indent}    raise ValueError(str(e))",
            ]
        elif "update" in name or "modify" in name or "refresh" in name:
            impl_lines = [
                f"{indent}try:",
                f"{indent}    # TODO: Validate input",
                f"{indent}    # TODO: Update database",
                f"{indent}    return {{'status': 'updated'}}",
                f"{indent}except Exception as e:",
                f"{indent}    raise ValueError(str(e))",
            ]
        elif "delete" in name or "remove" in name or "revoke" in name:
            impl_lines = [
                f"{indent}try:",
                f"{indent}    # TODO: Verify existence",
                f"{indent}    # TODO: Delete from database",
                f"{indent}    return {{'status': 'deleted'}}",
                f"{indent}except Exception as e:",
                f"{indent}    raise ValueError(str(e))",
            ]
        elif "validate" in name or "verify" in name or "authenticate" in name:
            impl_lines = [
                f"{indent}try:",
                f"{indent}    # TODO: Implement validation logic",
                f"{indent}    return True",
                f"{indent}except Exception as e:",
                f"{indent}    raise ValueError(str(e))",
            ]
        elif "hash" in name:
            impl_lines = [
                f"{indent}import hashlib",
                f"{indent}return hashlib.sha256(password.encode()).hexdigest()",
            ]
        elif "login" in name:
            impl_lines = [
                f"{indent}try:",
                f"{indent}    # TODO: Verify credentials",
                f"{indent}    # TODO: Generate tokens",
                f"{indent}    return {{'access_token': '', 'token_type': 'bearer'}}",
                f"{indent}except Exception as e:",
                f"{indent}    raise ValueError(str(e))",
            ]
        elif "main" in name or "create_app" in name:
            impl_lines = [
                f"{indent}app = FastAPI(title='{spec.project_name}')",
                f"{indent}return app",
            ]
        elif "test_" in name:
            impl_lines = [
                f"{indent}# TODO: Implement test",
                f"{indent}assert True",
            ]
        else:
            impl_lines = [
                f"{indent}# TODO: Implement",
                f"{indent}raise NotImplementedError('Not yet implemented')",
            ]

        return impl_lines

    # ============================================================
    #  PIPELINE COMPLETO - Ejecutar las 3 fases secuencialmente
    # ============================================================

    def generate_project(self, description: str,
                          project_type: str = "",
                          project_name: str = "",
                          language: str = "python",
                          output_dir: str = "") -> FractalResult:
        """
        Ejecuta las 3 fases de generación fractal secuencialmente.

        Fase 1 → Fase 2 → Fase 3 → Resultado final.

        Este es el método principal llamado desde el DAGOrchestrator
        cuando la acción es SCAFFOLD_FRACTAL.
        """
        start_time = time.time()

        # Fase 1: Estructural
        spec = self.generate_structure(
            description, project_type, project_name, language
        )

        # Fase 2: Esqueletos
        spec = self.generate_skeletons(spec)

        # Fase 3: Relleno
        result = self.fill_logic(spec, output_dir)

        elapsed = time.time() - start_time
        logger.info(
            f"FractalGenerator: Project '{project_name}' generated in "
            f"{elapsed:.2f}s - {len(result.files_generated)} files, "
            f"phase={result.current_phase}"
        )
        return result

    async def generate_project_streaming(self, description: str,
                                          project_type: str = "",
                                          project_name: str = "",
                                          language: str = "python",
                                          output_dir: str = "") -> AsyncIterator[Dict[str, Any]]:
        """
        Ejecuta las 3 fases de generación fractal con streaming SSE para Open Design.

        Cada fase emite un evento SSE con los datos parciales, permitiendo
        que Open Design renderice progresivamente el resultado en su iframe.

        Yields:
            Dict with 'event' (str) and 'data' (dict) for each phase.
        """
        start_time = time.time()

        # Fase 1: Estructural
        spec = self.generate_structure(description, project_type, project_name, language)
        yield {
            "event": "fractal_structure",
            "data": {
                "phase": "structure",
                "project_name": spec.project_name,
                "directories": len(spec.directories),
                "files": len(spec.files),
                "summary": self.get_spec_summary(spec),
            },
        }

        # Fase 2: Esqueletos
        spec = self.generate_skeletons(spec)
        yield {
            "event": "fractal_skeleton",
            "data": {
                "phase": "skeletons",
                "project_name": spec.project_name,
                "files": len(spec.files),
                "classes": sum(len(f.classes) for f in spec.files),
                "functions": sum(len(f.functions) for f in spec.files),
            },
        }

        # Fase 3: Relleno
        result = self.fill_logic(spec, output_dir)
        elapsed = time.time() - start_time

        # Build artifact data for Open Design
        artifacts = {}
        for fp, content in result.files_generated.items():
            artifacts[fp] = content

        yield {
            "event": "fractal_fill",
            "data": {
                "phase": "fill",
                "project_name": spec.project_name,
                "files_generated": len(result.files_generated),
                "artifacts": artifacts,
                "elapsed_s": round(elapsed, 2),
            },
        }

    def generate_project_streaming_sync(self, description: str,
                                         project_type: str = "",
                                         project_name: str = "",
                                         language: str = "python",
                                         output_dir: str = "") -> Iterator[Dict[str, Any]]:
        """
        Synchronous version of generate_project_streaming for stdlib server.
        """
        start_time = time.time()

        # Fase 1: Estructural
        spec = self.generate_structure(description, project_type, project_name, language)
        yield {
            "event": "fractal_structure",
            "data": {
                "phase": "structure",
                "project_name": spec.project_name,
                "directories": len(spec.directories),
                "files": len(spec.files),
                "summary": self.get_spec_summary(spec),
            },
        }

        # Fase 2: Esqueletos
        spec = self.generate_skeletons(spec)
        yield {
            "event": "fractal_skeleton",
            "data": {
                "phase": "skeletons",
                "project_name": spec.project_name,
                "files": len(spec.files),
                "classes": sum(len(f.classes) for f in spec.files),
                "functions": sum(len(f.functions) for f in spec.files),
            },
        }

        # Fase 3: Relleno
        result = self.fill_logic(spec, output_dir)
        elapsed = time.time() - start_time

        artifacts = {}
        for fp, content in result.files_generated.items():
            artifacts[fp] = content

        yield {
            "event": "fractal_fill",
            "data": {
                "phase": "fill",
                "project_name": spec.project_name,
                "files_generated": len(result.files_generated),
                "artifacts": artifacts,
                "elapsed_s": round(elapsed, 2),
            },
        }

    # ============================================================
    #  UTILIDADES
    # ============================================================

    def get_template_types(self) -> List[str]:
        """Retorna los tipos de template disponibles."""
        return list(PROJECT_TEMPLATES.keys())

    def get_spec_summary(self, spec: FractalSpec) -> Dict[str, Any]:
        """Retorna un resumen del FractalSpec para logging/monitoring."""
        return {
            "project_name": spec.project_name,
            "project_type": spec.project_type,
            "language": spec.language,
            "directories": len(spec.directories),
            "files": len(spec.files),
            "classes": sum(len(f.classes) for f in spec.files),
            "functions": sum(len(f.functions) for f in spec.files),
            "config_files": len(spec.config_files),
            "phase": spec.phase,
        }
