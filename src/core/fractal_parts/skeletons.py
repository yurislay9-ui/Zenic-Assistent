"""
ZENIC-AGENTS - FractalGenerator v16

Fase 2 (Esqueletos): Generate code skeletons with empty classes and functions.
"""

import ast
import logging

from .types import FileBlueprint, FractalSpec

logger = logging.getLogger(__name__)


# ============================================================
#  SkeletonsMixin - Fase 2: Esqueletos
# ============================================================

class SkeletonsMixin:
    """
    Mixin para Fase 2 (Esqueletos): Inyectar clases y funciones vacías.

    Para cada FileBlueprint en el spec:
    1. Genera los imports
    2. Genera las clases vacías con docstrings
    3. Genera las funciones vacías con docstrings
    4. Valida que el código compila (AST parse para Python)
    """

    def generate_skeletons(self, spec: FractalSpec) -> FractalSpec:
        """
        Fase 2: Genera esqueletos de código para cada archivo.

        Para cada FileBlueprint en el spec:
        1. Genera los imports
        2. Genera las clases vacías con docstrings
        3. Genera las funciones vacías con docstrings
        4. Valida que el código compila (AST parse para Python)

        Returns: FractalSpec actualizado con contenido en cada FileBlueprint.
        """
        spec.phase = 2
        total_items = 0
        completed_items = 0

        for file_bp in spec.files:
            if file_bp.language == "python":
                skeleton_code = self._generate_python_skeleton(file_bp)
            elif file_bp.language in ("javascript", "typescript"):
                skeleton_code = self._generate_js_skeleton(file_bp)
            elif file_bp.language == "kotlin":
                skeleton_code = self._generate_kotlin_skeleton(file_bp)
            else:
                skeleton_code = self._generate_generic_skeleton(file_bp)

            # Para archivos __init__.py vacíos
            if not skeleton_code.strip() and file_bp.path.endswith("__init__.py"):
                skeleton_code = ""

            # Validar sintaxis Python via AST
            if file_bp.language == "python" and skeleton_code.strip():
                try:
                    ast.parse(skeleton_code)
                except SyntaxError as e:
                    logger.warning(
                        f"FractalGenerator Fase 2: Syntax error in {file_bp.path}: {e}. "
                        f"Attempting fix..."
                    )
                    skeleton_code = self._fix_python_skeleton(skeleton_code)

            # Almacenar contenido generado en el FileBlueprint
            file_bp.generated_content = skeleton_code

            total_items += len(file_bp.classes) + len(file_bp.functions)
            completed_items += len(file_bp.classes) + len(file_bp.functions)

        logger.info(
            f"FractalGenerator Fase 2: Generated skeletons for "
            f"{len(spec.files)} files, {completed_items}/{total_items} items"
        )
        return spec

    def _generate_python_skeleton(self, bp: FileBlueprint) -> str:
        """Genera esqueleto Python con imports, clases y funciones vacías."""
        lines = []

        # Docstring del archivo
        if bp.description:
            lines.append(f'"""{bp.description}"""')
            lines.append("")

        # Imports
        for imp in bp.imports:
            lines.append(imp)
        if bp.imports:
            lines.append("")

        # Clases
        for cls in bp.classes:
            name = cls.get("name", "Unnamed")
            docstring = cls.get("docstring", "")
            bases = cls.get("bases", "")

            if bases and bases.strip():
                lines.append(f"class {name}({bases}):")
            else:
                lines.append(f"class {name}:")

            if docstring:
                lines.append(f'    """{docstring}"""')
            else:
                lines.append("    pass")
            lines.append("")

        # Funciones
        for func in bp.functions:
            name = func.get("name", "unnamed")
            docstring = func.get("docstring", "")
            params = func.get("params", "")

            if params:
                lines.append(f"def {name}({params}):")
            else:
                lines.append(f"def {name}():")

            if docstring:
                lines.append(f'    """{docstring}"""')
            lines.append("    pass  # TODO: Implement")
            lines.append("")

        return "\n".join(lines)

    def _generate_js_skeleton(self, bp: FileBlueprint) -> str:
        """Genera esqueleto JavaScript/TypeScript."""
        lines = []

        if bp.description:
            lines.append(f"// {bp.description}")
            lines.append("")

        # Imports
        for imp in bp.imports:
            lines.append(imp)
        if bp.imports:
            lines.append("")

        # Classes
        for cls in bp.classes:
            name = cls.get("name", "Unnamed")
            docstring = cls.get("docstring", "")
            lines.append(f"class {name} {{")
            if docstring:
                lines.append(f"  // {docstring}")
            lines.append("  constructor() {")
            lines.append("    // TODO: Implement")
            lines.append("  }")
            lines.append("}")
            lines.append("")

        # Functions
        for func in bp.functions:
            name = func.get("name", "unnamed")
            docstring = func.get("docstring", "")
            params = func.get("params", "")
            lines.append(f"function {name}({params}) {{")
            if docstring:
                lines.append(f"  // {docstring}")
            lines.append("  // TODO: Implement")
            lines.append("}")
            lines.append("")

        return "\n".join(lines)

    def _generate_kotlin_skeleton(self, bp: FileBlueprint) -> str:
        """Genera esqueleto Kotlin."""
        lines = []

        if bp.description:
            lines.append(f"// {bp.description}")
            lines.append("")

        # Imports
        for imp in bp.imports:
            lines.append(imp)
        if bp.imports:
            lines.append("")

        # Classes
        for cls in bp.classes:
            name = cls.get("name", "Unnamed")
            docstring = cls.get("docstring", "")
            lines.append(f"/** {docstring} */")
            lines.append(f"class {name} {{")
            lines.append("    // TODO: Implement")
            lines.append("}}")
            lines.append("")

        # Functions
        for func in bp.functions:
            name = func.get("name", "unnamed")
            docstring = func.get("docstring", "")
            params = func.get("params", "")
            lines.append(f"/** {docstring} */")
            lines.append(f"fun {name}({params}) {{")
            lines.append("    // TODO: Implement")
            lines.append("}}")
            lines.append("")

        return "\n".join(lines)

    def _generate_generic_skeleton(self, bp: FileBlueprint) -> str:
        """Genera esqueleto genérico para lenguajes no específicos."""
        lines = []
        if bp.description:
            lines.append(f"# {bp.description}")
        lines.append("# TODO: Implement")
        return "\n".join(lines)

    def _fix_python_skeleton(self, code: str) -> str:
        """Intenta arreglar errores de sintaxis en esqueletos Python."""
        # Estrategia simple: si hay error, agregar pass donde falte
        lines = code.split("\n")
        fixed_lines = []
        for i, line in enumerate(lines):
            fixed_lines.append(line)
            stripped = line.rstrip()
            # Si la línea termina en : y la siguiente no está indentada
            if stripped.endswith(":") and i + 1 < len(lines):
                next_line = lines[i + 1]
                if not next_line.strip() or not next_line[0].isspace():
                    # Verificar que no es la última línea o que la siguiente es vacía
                    if not next_line.strip():
                        fixed_lines.append("    pass")
        return "\n".join(fixed_lines)
