"""
SignatureIndex class — indexes code signatures for compact context references.
"""

import os
import re
import ast
import hashlib
import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from ._imports import logger, CONTEXT_STORE_ROOT, FunctionSignature
from ._pointer import ContextPointer


class SignatureIndex:
    """
    Índice de firmas vectorizadas para un proyecto de código.

    Escanea archivos de código, extrae firmas de funciones/clases,
    y construye un índice compacto que permite buscar y referenciar
    código sin cargarlo completo en memoria.
    """

    def __init__(self, project_root: str = ""):
        self._root = project_root
        self._signatures: Dict[str, List[FunctionSignature]] = {}  # file -> [signatures]
        self._name_index: Dict[tuple, List[FunctionSignature]] = {}  # (name, file_path) -> [signatures]
        self._store_dir = CONTEXT_STORE_ROOT

    def index_project(self, project_root: str = "") -> int:
        """
        Indexa un proyecto completo, extrayendo firmas de todos los archivos.

        Returns:
            Número de firmas indexadas
        """
        root = project_root or self._root
        if not root or not os.path.isdir(root):
            logger.warning(f"SignatureIndex: Project root not found: {root}")
            return 0

        count = 0
        code_extensions = {".py", ".js", ".ts", ".kt", ".go", ".java", ".rs"}

        for filepath in Path(root).rglob("*"):
            if filepath.suffix in code_extensions:
                try:
                    content = filepath.read_text(encoding="utf-8", errors="ignore")
                    sigs = self._extract_signatures(content, str(filepath))
                    self._signatures[str(filepath)] = sigs
                    for sig in sigs:
                        self._name_index.setdefault((sig.name, sig.file_path), []).append(sig)
                    count += len(sigs)
                except Exception as e:
                    logger.debug(f"SignatureIndex: Error indexing {filepath}: {e}")

        logger.info(f"SignatureIndex: Indexed {count} signatures from {root}")
        return count

    def index_code(self, code: str, file_path: str = "input.py") -> int:
        """
        Indexa código individual, extrayendo firmas.

        Returns:
            Número de firmas extraídas
        """
        sigs = self._extract_signatures(code, file_path)
        self._signatures[file_path] = sigs
        for sig in sigs:
            self._name_index.setdefault((sig.name, sig.file_path), []).append(sig)

        # Also store the code in the context store for disk-based operations
        self._store_code(code, file_path)

        return len(sigs)

    def _extract_signatures(self, code: str, file_path: str) -> List[FunctionSignature]:
        """Extrae firmas de funciones y clases del código."""
        signatures = []

        # Detect language
        ext = Path(file_path).suffix
        if ext == ".py":
            signatures = self._extract_python_signatures(code, file_path)
        else:
            signatures = self._extract_regex_signatures(code, file_path, ext)

        return signatures

    def _extract_python_signatures(self, code: str, file_path: str) -> List[FunctionSignature]:
        """Extrae firmas usando ast nativo de Python."""
        signatures = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sig = self._parse_python_function(node, code, file_path)
                    if sig:
                        signatures.append(sig)
                elif isinstance(node, ast.ClassDef):
                    sig = self._parse_python_class(node, code, file_path)
                    if sig:
                        signatures.append(sig)

        except SyntaxError as e:
            logger.debug(f"SignatureIndex: Syntax error in {file_path}: {e}")

        return signatures

    @staticmethod
    def _parse_python_function(node, code: str, file_path: str) -> Optional[FunctionSignature]:
        """Parse a Python function definition AST node to a FunctionSignature."""
        # Extract parameters
        params = []
        for arg in node.args.args:
            param = arg.arg
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    param += f":{arg.annotation.id}"
                elif isinstance(arg.annotation, ast.Constant):
                    param += f":{arg.annotation.value}"
            params.append(param)

        # Return type
        return_type = ""
        if node.returns:
            if isinstance(node.returns, ast.Name):
                return_type = node.returns.id
            elif isinstance(node.returns, ast.Constant):
                return_type = str(node.returns.value)

        # Docstring
        docstring = ast.get_docstring(node) or ""

        # Calls
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        calls = list(set(calls))[:10]

        # Complexity
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1

        # Content hash
        content = ast.get_source_segment(code, node) or node.name
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        return FunctionSignature(
            name=node.name,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            params=params,
            return_type=return_type,
            docstring=docstring[:200],
            complexity=complexity,
            calls=calls,
            hash=content_hash,
        )

    @staticmethod
    def _parse_python_class(node, code: str, file_path: str) -> Optional[FunctionSignature]:
        """Parse a Python class definition AST node to a FunctionSignature."""
        methods = [
            n.name for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        content_hash = hashlib.sha256(node.name.encode()).hexdigest()[:16]
        docstring = ast.get_docstring(node) or ""

        return FunctionSignature(
            name=node.name,
            file_path=file_path,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            params=[f"class({', '.join(methods[:5])})"],
            return_type="class",
            docstring=docstring[:200],
            complexity=len(methods),
            calls=methods[:10],
            hash=content_hash,
        )

    def _extract_regex_signatures(self, code: str, file_path: str, ext: str) -> List[FunctionSignature]:
        """Extrae firmas usando regex para lenguajes sin parser nativo."""
        signatures = []
        patterns = {
            ".js": r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
            ".ts": r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*([^{]+))?',
            ".kt": r'fun\s+(\w+)\s*\(([^)]*)\)(?:\s*:\s*(\w+))?',
            ".go": r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(([^)]*)\)(?:\s*([^({]+))?',
            ".java": r'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)+(\w+)\s*\(([^)]*)\)',
            ".rs": r'(?:pub\s+)?fn\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^{]+))?',
        }

        pattern = patterns.get(ext, r'(?:def|function|fun|func)\s+(\w+)\s*\(([^)]*)\)')
        for match in re.finditer(pattern, code):
            name = match.group(1)
            params_str = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
            ret_type = match.group(3) if match.lastindex and match.lastindex >= 3 else ""

            # Count line number
            line_num = code[:match.start()].count('\n') + 1

            params = [p.strip().split(':')[0].strip() for p in params_str.split(',') if p.strip()]

            sig = FunctionSignature(
                name=name,
                file_path=file_path,
                line_start=line_num,
                line_end=line_num + 5,  # Estimate
                params=params[:8],
                return_type=ret_type.strip() if ret_type else "",
                hash=hashlib.sha256(match.group(0).encode()).hexdigest()[:16],
            )
            signatures.append(sig)

        return signatures

    def _store_code(self, code: str, file_path: str):
        """Almacena código en el context store para acceso desde disco."""
        os.makedirs(self._store_dir, exist_ok=True)
        safe_name = file_path.replace("/", "_").replace("\\", "_")
        store_path = os.path.join(self._store_dir, f"{safe_name}.stored")
        try:
            with open(store_path, "w", encoding="utf-8") as f:
                f.write(code)
        except Exception as e:
            logger.debug(f"SignatureIndex: Error storing code: {e}")

    # ================================================================
    #  QUERY
    # ================================================================

    def search(self, query: str, top_k: int = 10) -> List[ContextPointer]:
        """
        Busca firmas relevantes basado en una consulta.

        Returns:
            Lista de ContextPointer ordenados por relevancia
        """
        query_lower = query.lower()
        query_words = set(query_lower.replace("_", " ").split())
        pointers = []

        for (name, file_path), sigs in self._name_index.items():
            for sig in sigs:
                score = 0

                # Name match
                if query_lower == name.lower():
                    score += 100
                elif query_lower in name.lower():
                    score += 50
                else:
                    name_words = set(name.lower().replace("_", " ").split())
                    overlap = query_words & name_words
                    score += len(overlap) * 20

                # Docstring match
                if sig.docstring:
                    doc_words = set(sig.docstring.lower().split())
                    doc_overlap = query_words & doc_words
                    score += len(doc_overlap) * 5

                # Call match (functions that call the queried function)
                if query_lower in [c.lower() for c in sig.calls]:
                    score += 15

                if score > 0:
                    reason = ""
                    if query_lower in name.lower():
                        reason = f"Nombre coincide con '{query}'"
                    elif sig.docstring and any(w in sig.docstring.lower() for w in query_words):
                        reason = f"Docstring menciona términos relevantes"
                    elif query_lower in [c.lower() for c in sig.calls]:
                        reason = f"Llama a función relacionada"

                    pointers.append(ContextPointer(
                        signature=sig,
                        relevance_score=score,
                        reason=reason,
                    ))

        pointers.sort(key=lambda p: p.relevance_score, reverse=True)
        return pointers[:top_k]

    def get_by_name(self, name: str, file_path: Optional[str] = None) -> Optional[ContextPointer]:
        """Obtiene un puntero por nombre exacto de función.

        Args:
            name: Function/class name to look up.
            file_path: Optional file path for disambiguation. If provided,
                looks up (name, file_path) directly. If None, searches all
                entries and returns the first match (with a warning).
        """
        if file_path is not None:
            sigs = self._name_index.get((name, file_path))
            if sigs:
                return ContextPointer(signature=sigs[0], reason="Exact name and file match")
            return None
        # Fallback: search all entries with this name
        matches = []
        for (n, fp), sigs in self._name_index.items():
            if n == name:
                matches.extend(sigs)
        if matches:
            logger.warning(
                f"ContextPointerEngine: get_by_name('{name}') matched "
                f"{len(matches)} signature(s) across multiple files without "
                f"file_path disambiguation; returning first match"
            )
            return ContextPointer(signature=matches[0], reason="Exact name match (no file_path specified)")
        return None

    def build_compact_context(self, query: str, max_tokens: int = 2000) -> Tuple[str, List[ContextPointer]]:
        """
        Construye un contexto compacto de punteros para enviar al modelo.

        En vez de enviar 20K+ tokens de código, envía ~200-500 tokens
        de punteros con coordenadas. El modelo puede pedir código
        específico cuando lo necesite para modificar.

        Returns:
            (compact_context_string, list_of_pointers)
        """
        pointers = self.search(query, top_k=20)

        if not pointers:
            return "No se encontraron funciones relevantes.", []

        lines = [
            f"# Context Pointers for: {query}",
            f"# {len(pointers)} funciones indexadas, código en disco",
            f"# Para modificar: especifica nombre + nuevo código",
            "",
        ]

        total_chars = 0
        used_pointers = []

        for ptr in pointers:
            ctx_line = ptr.to_model_context()
            if total_chars + len(ctx_line) > max_tokens * 4:  # ~4 chars per token
                break
            lines.append(ctx_line)
            total_chars += len(ctx_line)
            used_pointers.append(ptr)

        lines.append("")
        lines.append(f"# Total: {len(used_pointers)} punteros | Código disponible en disco bajo demanda")

        return "\n".join(lines), used_pointers

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del índice."""
        total_funcs = sum(len(sigs) for sigs in self._signatures.values())
        total_files = len(self._signatures)
        return {
            "total_signatures": total_funcs,
            "total_files": total_files,
            "unique_names": len(self._name_index),
            "store_dir": self._store_dir,
        }
