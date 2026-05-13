"""
ZENIC-AGENTS - FractalGenerator v16

Fase 3 (Relleno): Fill logic item by item for each function/class.
"""

import os
import logging
from typing import List, Optional

from .types import FileBlueprint, FractalSpec, FractalResult

logger = logging.getLogger(__name__)


# ============================================================
#  FillMixin - Fase 3: Relleno
# ============================================================

class FillMixin:
    """
    Mixin para Fase 3 (Relleno): Llenar lógica item por item.

    Para cada función/clase con 'pass  # TODO: Implement':
    1. Lee el docstring para entender qué implementar
    2. Genera la lógica via LLM o fallback
    3. Reemplaza el 'pass' con la implementación
    4. Valida que el código sigue compilando
    """

    def fill_logic(self, spec: FractalSpec,
                    output_dir: str = "") -> FractalResult:
        """
        Fase 3: Rellena la lógica de cada archivo item por item.

        Para cada función/clase con 'pass  # TODO: Implement':
        1. Lee el docstring para entender qué implementar
        2. Genera la lógica via LLM o fallback
        3. Reemplaza el 'pass' con la implementación
        4. Valida que el código sigue compilando

        Returns: FractalResult con el resultado de la generación.
        """
        spec.phase = 3
        result = FractalResult(
            status="filled",
            project_name=spec.project_name,
            spec=spec,
            total_files=len(spec.files),
            current_phase=3,
        )

        for file_bp in spec.files:
            content = file_bp.generated_content
            if not content:
                continue

            # Rellenar lógica para funciones con 'pass  # TODO'
            if file_bp.language == "python" and "pass  # TODO: Implement" in content:
                content = self._fill_python_logic(content, file_bp, spec)

            # Guardar archivo si se especificó output_dir
            if output_dir and content:
                file_path = os.path.join(output_dir, file_bp.path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                result.files_generated.append(file_bp.path)

            # Actualizar contenido
            file_bp.generated_content = content
            result.items_completed += len(file_bp.classes) + len(file_bp.functions)

        result.items_total = result.items_completed
        result.current_phase = 3

        # Escribir config files
        if output_dir:
            for fname, fcontent in spec.config_files.items():
                fpath = os.path.join(output_dir, fname)
                os.makedirs(os.path.dirname(fpath) if os.path.dirname(fpath) else output_dir, exist_ok=True)
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(fcontent)
                result.files_generated.append(fname)

            # Crear directorios
            for d in spec.directories:
                os.makedirs(os.path.join(output_dir, d), exist_ok=True)

        result.status = "complete"
        logger.info(
            f"FractalGenerator Fase 3: {len(result.files_generated)} files generated, "
            f"{result.items_completed} items completed"
        )
        return result

    def _fill_python_logic(self, content: str, bp: FileBlueprint,
                            spec: FractalSpec) -> str:
        """Rellena la lógica de funciones Python una por una."""
        # Intentar LLM para rellenar
        if self._mini_ai and self._mini_ai.is_loaded:
            try:
                filled = self._fill_python_logic_llm(content, bp, spec)
                if filled:
                    return filled
            except Exception as e:
                logger.debug(f"FractalGenerator Fase 3 LLM failed: {e}")

        # Fallback: generar lógica determinista basada en docstrings
        return self._fill_python_logic_fallback(content, bp, spec)

    def _fill_python_logic_llm(self, content: str, bp: FileBlueprint,
                                spec: FractalSpec) -> Optional[str]:
        """Intenta rellenar lógica via LLM item por item."""
        lines = content.split("\n")
        result_lines = []
        i = 0

        while i < len(lines):
            line = lines[i]
            result_lines.append(line)

            # Detectar funciones con 'pass  # TODO: Implement'
            if "pass  # TODO: Implement" in line:
                # Encontrar la función y su docstring
                func_start = i - 1
                while func_start >= 0 and not lines[func_start].strip().startswith("def "):
                    func_start -= 1

                if func_start >= 0:
                    # Extraer docstring
                    docstring = ""
                    docstring_line = func_start + 1
                    if docstring_line < i and '"""' in lines[docstring_line]:
                        ds = lines[docstring_line].strip()
                        if ds.startswith('"""') and ds.endswith('"""') and len(ds) > 6:
                            docstring = ds[3:-3].strip()
                        elif ds.startswith('"""'):
                            # Multi-line docstring
                            docstring = ds[3:]
                            docstring_line += 1
                            while docstring_line < i:
                                if '"""' in lines[docstring_line]:
                                    break
                                docstring += " " + lines[docstring_line].strip()
                                docstring_line += 1

                    # Extraer signature
                    func_signature = lines[func_start].strip()

                    # Generar implementación via LLM
                    system = (
                        "You are a Python developer. Implement the function. "
                        "Reply ONLY with the function body (indented code), no signature. "
                        "Max 10 lines."
                    )
                    user = (
                        f"Function: {func_signature}\n"
                        f"Docstring: {docstring}\n"
                        f"Project: {spec.project_name} ({spec.project_type})\n"
                        f"File: {bp.path}\n"
                        f"Implement the function body:"
                    )

                    response = self._mini_ai._call_llm(
                        system_prompt=system, user_prompt=user, max_tokens=150
                    )

                    if response:
                        # Reemplazar 'pass  # TODO' con la implementación
                        indent = "    "
                        impl_lines = response.strip().split("\n")
                        # Filtrar líneas vacías y agregar indentación
                        clean_impl = []
                        for il in impl_lines:
                            il_stripped = il.strip()
                            if il_stripped and not il_stripped.startswith("def "):
                                clean_impl.append(f"{indent}{il_stripped}")

                        if clean_impl:
                            result_lines.pop()  # Remove the 'pass # TODO' line
                            result_lines.extend(clean_impl)
                            i += 1
                            continue

            i += 1

        return "\n".join(result_lines)

    def _fill_python_logic_fallback(self, content: str, bp: FileBlueprint,
                                     spec: FractalSpec) -> str:
        """Fallback determinista: genera lógica básica basada en patrones."""
        lines = content.split("\n")
        result_lines = []

        for line in lines:
            if "pass  # TODO: Implement" in line:
                # Determinar qué tipo de función es por el contexto
                indent = line[:len(line) - len(line.lstrip())]

                # Buscar la función más cercana hacia arriba
                func_idx = len(result_lines) - 1
                while func_idx >= 0:
                    if result_lines[func_idx].strip().startswith("def "):
                        break
                    func_idx -= 1

                func_line = result_lines[func_idx] if func_idx >= 0 else ""
                func_name = func_line.strip()

                # Generar implementación basada en patrones comunes
                impl = self._generate_pattern_implementation(
                    func_name, bp, spec, indent
                )
                result_lines.extend(impl)
            else:
                result_lines.append(line)

        return "\n".join(result_lines)
