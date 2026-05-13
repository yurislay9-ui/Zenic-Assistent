"""
ZENIC-AGENTS - AST Surgeon v16 (Robust Multi-Language)

Cirujano de AST usando ast nativo para Python y regex robusto
para Kotlin, Go, JavaScript, TypeScript, Rust, Java.

Mejoras v16:
- Python: usa ast nativo con preservacion de lineas y decoradores
- Multi-lenguaje: regex mejorados con soporte para bloques anidados
- delete_function: limpieza de lineas en blanco residuales
- insert_function: insercion inteligente antes de __main__
- Validacion de sintaxis post-mutacion para Python
- Preservacion de decoradores en mutaciones

Sin dependencias externas. Compatible con Android.
"""

import ast
import re
import logging

logger = logging.getLogger(__name__)


class ASTSurgeon:
    """Cirujano de AST robusto multi-lenguaje."""

    @staticmethod
    def _iter_top_level_functions(tree):
        """
        Yield top-level functions and class methods only.
        Skips nested functions (functions defined inside other functions),
        ensuring ast.walk() does not accidentally match inner functions.
        """
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        yield item

    def mutate_node(self, code, target_name, new_snippet, lang="python"):
        """
        Reemplaza una funcion/metodo por un nuevo snippet.

        Args:
            code: Codigo fuente completo
            target_name: Nombre de la funcion a reemplazar
            new_snippet: Nuevo codigo de la funcion
            lang: Lenguaje de programacion

        Returns:
            Codigo con la funcion reemplazada
        """
        if lang == "python":
            return self._mutate_python(code, target_name, new_snippet)
        return self._mutate_regex(code, target_name, new_snippet, lang)

    def _mutate_python(self, code, target_name, new_snippet):
        """
        Mutacion Python usando ast nativo. Preserva decoradores y
        valida sintaxis post-mutacion.
        """
        try:
            tree = ast.parse(code)
            lines = code.split('\n')

            # Encontrar la funcion target, incluyendo decoradores
            # Only match top-level functions or class methods, not nested functions
            for node in self._iter_top_level_functions(tree):
                if node.name == target_name:
                    # Calcular rango incluyendo decoradores
                    start = node.lineno - 1
                    end = node.end_lineno

                    # Buscar decoradores antes de la funcion
                    if node.decorator_list:
                        first_decorator_line = min(
                            d.lineno for d in node.decorator_list
                        )
                        start = first_decorator_line - 1

                    # Reemplazar las lineas
                    new_lines = new_snippet.split('\n')
                    lines[start:end] = new_lines

                    result = '\n'.join(lines)

                    # Validar sintaxis post-mutacion
                    try:
                        ast.parse(result)
                        return result
                    except SyntaxError:
                        # Si la mutacion rompe la sintaxis, revertir
                        logger.warning(
                            "Mutation of '%s' broke syntax, using regex fallback",
                            target_name
                        )
                        return self._mutate_regex(
                            code, target_name, new_snippet, "python"
                        )
        except SyntaxError:
            pass
        return self._mutate_regex(code, target_name, new_snippet, "python")

    def _mutate_regex(self, code, target_name, new_snippet, lang):
        """
        Mutacion basada en regex para lenguajes sin parser nativo.
        Usa patrones mejorados con soporte para bloques anidados.
        """
        try:
            pattern = self._get_function_pattern(target_name, lang)
            match = re.search(pattern, code, re.DOTALL | re.MULTILINE)
            if match:
                result = code[:match.start()] + new_snippet + code[match.end():]
                return result
        except Exception as e:
            logger.debug("AST mutate regex fallback: %s", e)
        # Fallback: return original code unchanged
        logger.warning(
            "Regex mutation failed for '%s', returning code unchanged",
            target_name
        )
        return code

    def _get_function_pattern(self, target_name, lang):
        """
        Retorna el patron regex para encontrar una funcion en el lenguaje dado.
        Los patrones usan balance de llaves para manejar bloques anidados.
        """
        escaped = re.escape(target_name)

        patterns = {
            "python": rf'(?:@[\w.]+\s*\n)*def\s+{escaped}\s*\([^)]*\)(?:\s*->[^:]+)?\s*:.*?(?=\n(?:def\s|class\s|@\w)|\Z)',

            "kotlin": rf'fun\s+{escaped}\s*[\(<].*?\{{(?:[^{{}}]|{{(?:[^{{}}]|{{[^{{}}]*}})*}})*\}}',

            "go": rf'func\s+(?:\([^)]+\)\s+)?{escaped}\s*\([^)]*\)(?:\s*\([^)]*\))?\s*\{{(?:[^{{}}]|{{(?:[^{{}}]|{{[^{{}}]*}})*}})*\}}',

            "javascript": rf'(?:async\s+)?function\s+{escaped}\s*\([^)]*\)\s*\{{(?:[^{{}}]|{{(?:[^{{}}]|{{[^{{}}]*}})*}})*\}}',

            "typescript": rf'(?:async\s+)?function\s+{escaped}\s*\([^)]*\)(?:\s*:\s*[^{{]+)?\s*\{{(?:[^{{}}]|{{(?:[^{{}}]|{{[^{{}}]*}})*}})*\}}',

            "rust": rf'(?:pub\s+)?fn\s+{escaped}\s*[\(<].*?\{{(?:[^{{}}]|{{(?:[^{{}}]|{{[^{{}}]*}})*}})*\}}',

            "java": rf'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)+{escaped}\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{{(?:[^{{}}]|{{(?:[^{{}}]|{{[^{{}}]*}})*}})*\}}',
        }

        return patterns.get(lang, patterns["javascript"])

    def insert_function(self, code, new_function, lang="python"):
        """
        Inserta una nueva funcion en el codigo.

        Para Python, intenta insertar antes del bloque __main__.
        Para otros lenguajes, inserta al final.

        Args:
            code: Codigo fuente completo
            new_function: Codigo de la nueva funcion
            lang: Lenguaje de programacion

        Returns:
            Codigo con la nueva funcion insertada
        """
        if lang == "python" and code.strip():
            # Insertar antes de if __name__ == "__main__"
            main_block = re.search(r'\nif\s+__name__', code)
            if main_block:
                return (code[:main_block.start()] + "\n\n"
                        + new_function + "\n"
                        + code[main_block.start():])

            # Insertar antes de la ultima clase si no hay __main__
            lines = code.split('\n')
            # Buscar la ultima definicion top-level
            insert_pos = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                stripped = lines[i].strip()
                if stripped and not stripped.startswith('#') and not stripped.startswith('"""'):
                    insert_pos = i + 1
                    break

            lines.insert(insert_pos, "\n" + new_function)
            return '\n'.join(lines)

        return code + "\n\n" + new_function

    def delete_function(self, code, target_name, lang="python"):
        """
        Elimina una funcion del codigo, limpiando lineas en blanco residuales.

        Args:
            code: Codigo fuente completo
            target_name: Nombre de la funcion a eliminar
            lang: Lenguaje de programacion

        Returns:
            Codigo sin la funcion eliminada
        """
        if lang == "python":
            try:
                tree = ast.parse(code)
                lines = code.split('\n')

                # Encontrar la funcion a eliminar
                # Only match top-level functions or class methods, not nested functions
                for node in self._iter_top_level_functions(tree):
                    if node.name == target_name:
                        start = node.lineno - 1
                        end = node.end_lineno

                        # Incluir decoradores
                        if node.decorator_list:
                            first_decorator_line = min(
                                d.lineno for d in node.decorator_list
                            )
                            start = first_decorator_line - 1

                        del lines[start:end]

                        # Limpiar lineas en blanco residuales
                        while (start < len(lines)
                               and lines[start].strip() == ''
                               and start > 0
                               and lines[start - 1].strip() == ''):
                            del lines[start]

                        result = '\n'.join(lines)

                        # Validar sintaxis post-eliminacion
                        try:
                            ast.parse(result)
                            return result
                        except SyntaxError:
                            # Revertir si rompe sintaxis
                            logger.warning(
                                "Deletion of '%s' broke syntax, using regex",
                                target_name
                            )
                            return self._delete_regex(code, target_name, lang)
            except SyntaxError:
                pass
        return self._delete_regex(code, target_name, lang)

    def _delete_regex(self, code, target_name, lang):
        """Eliminacion basada en regex para lenguajes sin parser nativo."""
        try:
            pattern = self._get_function_pattern(target_name, lang)
            match = re.search(pattern, code, re.DOTALL | re.MULTILINE)
            if match:
                result = code[:match.start()] + code[match.end():]
                # Limpiar lineas en blanco multiples
                result = re.sub(r'\n{3,}', '\n\n', result)
                return result
        except Exception as e:
            logger.debug("AST delete regex fallback: %s", e)
        return code
