"""
ZENIC-AGENTS - Graph AST Engine v16 (ast nativo + regex)

Motor de AST usando el modulo nativo ast de Python para codigo Python,
y regex para otros lenguajes. Almacena nodos en SQLite con conexiones.

v16 FIX: Usa connection pool de db_initializer en vez de abrir
conexiones nuevas por cada operacion. Batch inserts para scan_project.

FIX (Phase 2): Added retry with exponential backoff for DB write
operations (_store_node, _store_nodes_batch). SQLite can fail
transiently (database locked, busy timeout) especially under
concurrent access.

Sin dependencias externas. Compatible con Android.
"""

import ast
import re
import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from src.core.shared.db_initializer import get_connection
from src.core.shared.constants import EXT_LANG_MAP
from src.core.shared.retry import with_retry
from src.core.shared.db_utils import escape_sql_like, purge_tenant_rows
from src.core.shared.tenant_utils import resolve_tenant_id
from src.core.shared.ast_utils import compute_cyclomatic_complexity, extract_function_calls, extract_class_connections

logger = logging.getLogger(__name__)

SKIP_DIRS = {'.git', 'node_modules', 'venv', '__pycache__', '.venv', 'dist', 'build'}


@lru_cache(maxsize=32)
def _detect_language_cached(suffix: str) -> str:
    """Detect programming language from file extension.

    Cached because the same extension is looked up repeatedly during
    project scans. Uses EXT_LANG_MAP from shared.constants as the
    single source of truth.
    """
    return EXT_LANG_MAP.get(suffix, "python")


class GraphASTEngine:
    """Motor de AST usando ast nativo para Python, regex para otros. Tenant-aware (Phase 2)."""

    def __init__(self):
        self._tenant_id: str = resolve_tenant_id()
        logger.debug("GraphASTEngine initialized with tenant_id='%s'", self._tenant_id)
        self._init_db()

    def set_tenant_id(self, tenant_id: str) -> None:
        """Update the current tenant_id for this AST engine instance."""
        old = self._tenant_id
        self._tenant_id = tenant_id
        logger.info("GraphASTEngine tenant_id changed: '%s' -> '%s'", old, tenant_id)

    def _init_db(self):
        conn = get_connection("graph_ast.sqlite")
        conn.execute("""CREATE TABLE IF NOT EXISTS ast_nodes (  # nosemgrep: sqlalchemy-execute-raw-query
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL, node_type TEXT NOT NULL,
            name TEXT NOT NULL, start_byte INTEGER NOT NULL,
            end_byte INTEGER NOT NULL, content_hash TEXT NOT NULL,
            docstring TEXT, complexity INTEGER DEFAULT 1,
            connections TEXT DEFAULT '[]',
            tenant_id TEXT NOT NULL DEFAULT '__anonymous__',
            UNIQUE(file_path, name, node_type, tenant_id))""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_name ON ast_nodes(name)")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_type ON ast_nodes(node_type)")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_tenant ON ast_nodes(tenant_id)")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ast_tenant_file ON ast_nodes(tenant_id, file_path)")  # nosemgrep: sqlalchemy-execute-raw-query
        conn.commit()
        # Migrate: add tenant_id column if it doesn't exist
        try:
            # Tenant module removed — skip tenant isolation migration
            # from src.core.tenant._isolation import TenantIsolation
            # TenantIsolation.migrate_add_tenant_id(conn, "ast_nodes", "__anonymous__")
            pass
        except Exception as e:
            logger.debug("ast_nodes tenant migration skipped: %s", e)

    def scan_code(self, code, file_path="input.py", language="python"):
        """Parse source code and return a list of AST node dicts.

        Dispatches to _parse_python for Python code and _parse_regex
        for all other languages.

        Args:
            code: Source code string to parse.
            file_path: Logical file path for the source (default "input.py").
            language: Programming language identifier (default "python").

        Returns:
            List of node dicts with keys: file_path, node_type, name,
            start_byte, end_byte, content_hash, docstring, complexity,
            connections.
        """
        if language == "python":
            return self._parse_python(code, file_path)
        return self._parse_regex(code, file_path, language)

    def scan_project(self, project_dir):
        """Escanear proyecto completo. Usa connection pool + batch insert."""
        base_path = Path(project_dir)
        if not base_path.exists():
            return

        # Recolectar todos los nodos primero, luego batch insert
        all_nodes = []
        for f in base_path.rglob("*"):
            if any(skip in f.parts for skip in SKIP_DIRS):
                continue
            if f.suffix in [".py", ".kt", ".go", ".js", ".ts", ".java", ".rs"]:
                try:
                    lang = self._detect_language(f.suffix)
                    source = f.read_text(encoding="utf-8", errors="ignore")
                    nodes = self.scan_code(source, str(f.relative_to(base_path)), lang)
                    all_nodes.extend(nodes)
                except Exception as e:
                    logging.getLogger(__name__).warning("Error parsing %s: %s", f, e)

        # Batch insert en una sola transaccion
        if all_nodes:
            self._store_nodes_batch(all_nodes)

    def _detect_language(self, suffix):
        """Detect programming language from file extension.

        Delegates to the module-level cached function for O(1) repeated
        lookups during project scans.
        """
        return _detect_language_cached(suffix)

    def _parse_python(self, code, file_path):
        """Parse Python source using the ast module.

        Extracts functions, classes, and imports with their metadata
        including complexity, connections, and docstrings.

        Args:
            code: Python source code string.
            file_path: Logical file path for the source.

        Returns:
            List of node dicts for all detected AST elements.
        """
        nodes = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = self._cyclomatic_complexity(node)
                    docstring = ast.get_docstring(node) or ""
                    connections = self._extract_calls(node)
                    start = node.lineno
                    end = node.end_lineno or start
                    content = ast.get_source_segment(code, node) or ""
                    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    nodes.append({
                        "file_path": file_path, "node_type": "function",
                        "name": node.name, "start_byte": start, "end_byte": end,
                        "content_hash": content_hash, "docstring": docstring,
                        "complexity": complexity, "connections": json.dumps(connections),
                    })
                elif isinstance(node, ast.ClassDef):
                    connections = self._extract_class_connections(node)
                    content_hash = hashlib.sha256(node.name.encode()).hexdigest()[:16]
                    docstring = ast.get_docstring(node) or ""
                    nodes.append({
                        "file_path": file_path, "node_type": "class",
                        "name": node.name, "start_byte": node.lineno,
                        "end_byte": node.end_lineno or node.lineno,
                        "content_hash": content_hash, "docstring": docstring,
                        "complexity": 1, "connections": json.dumps(connections),
                    })
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = []
                    for alias in node.names:
                        names.append(alias.asname or alias.name)
                    if isinstance(node, ast.ImportFrom) and node.module:
                        names.insert(0, node.module)
                    content_hash = hashlib.sha256(",".join(names).encode()).hexdigest()[:16]
                    nodes.append({
                        "file_path": file_path, "node_type": "import",
                        "name": ",".join(names), "start_byte": node.lineno,
                        "end_byte": node.end_lineno or node.lineno,
                        "content_hash": content_hash, "docstring": "",
                        "complexity": 0, "connections": "[]",
                    })
        except SyntaxError as e:
            logging.getLogger(__name__).warning("Syntax error in %s: %s", file_path, e)
        return nodes

    def _parse_regex(self, code, file_path, language):
        """Parse non-Python source using regex patterns.

        Falls back to regex-based function detection for languages
        that cannot be parsed by Python's ast module.

        Args:
            code: Source code string.
            file_path: Logical file path for the source.
            language: Programming language identifier.

        Returns:
            List of node dicts for detected function definitions.
        """
        nodes = []
        patterns = {
            "kotlin": r'(?:fun|companion object)\s+(\w+)\s*[\(<]',
            "go": r'func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(',
            "javascript": r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))',
            "typescript": r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))',
            "java": r'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)+(\w+)\s*\(',
            "rust": r'(?:pub\s+)?fn\s+(\w+)\s*[\(<]',
        }
        pattern = patterns.get(language, r'(?:def|function|fun|func)\s+(\w+)\s*[\(\{]')
        for match in re.finditer(pattern, code):
            name = match.group(1) or (match.group(2) if match.lastindex and match.lastindex >= 2 else None)
            if name is None:
                continue
            content_hash = hashlib.sha256(match.group(0).encode()).hexdigest()[:16]
            nodes.append({
                "file_path": file_path, "node_type": "function",
                "name": name, "start_byte": match.start(),
                "end_byte": match.end(), "content_hash": content_hash,
                "docstring": "", "complexity": 1, "connections": "[]",
            })
        return nodes

    def _store_node(self, node_data):
        """Insert a single node using connection pool. Tenant-aware.

        Uses shared retry utility for transient SQLite failures.
        """
        def _insert():
            conn = get_connection("graph_ast.sqlite")
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO ast_nodes
                (file_path, node_type, name, start_byte, end_byte,
                 content_hash, docstring, complexity, connections, tenant_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (node_data["file_path"], node_data["node_type"],
                 node_data["name"], node_data["start_byte"],
                 node_data["end_byte"], node_data["content_hash"],
                 node_data["docstring"], node_data["complexity"],
                 node_data["connections"], self._tenant_id)
            )
            conn.commit()

        with_retry(_insert, label="GraphAST store_node")

    def _store_nodes_batch(self, nodes):
        """Batch insert multiple nodes in a single transaction. Tenant-aware.

        Uses shared retry utility for transient SQLite failures.
        """
        tid = self._tenant_id

        def _batch_insert():
            conn = get_connection("graph_ast.sqlite")
            conn.executemany(
                """INSERT OR REPLACE INTO ast_nodes
                (file_path, node_type, name, start_byte, end_byte,
                 content_hash, docstring, complexity, connections, tenant_id)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [(n["file_path"], n["node_type"], n["name"],
                  n["start_byte"], n["end_byte"], n["content_hash"],
                  n["docstring"], n["complexity"], n["connections"], tid)
                 for n in nodes]
            )
            conn.commit()

        with_retry(_batch_insert, base_delay=0.2, label="GraphAST store_nodes_batch")

    def _cyclomatic_complexity(self, func_node):
        """Compute McCabe cyclomatic complexity using shared ast_utils."""
        return compute_cyclomatic_complexity(func_node)

    def _extract_calls(self, func_node):
        """Extract unique function call names using shared ast_utils."""
        return extract_function_calls(func_node)

    def _extract_class_connections(self, class_node):
        """Extract class connections using shared ast_utils."""
        return extract_class_connections(class_node)

    def get_node_info(self, target_name):
        """Get node info filtered by current tenant_id.

        Security: Escapes SQL LIKE wildcards AND backslash to prevent
        LIKE injection attacks (e.g. target_name='%' matches everything).
        """
        conn = get_connection("graph_ast.sqlite")
        # Security: Use shared escape utility to prevent LIKE injection
        escaped_name = escape_sql_like(target_name)
        return [dict(r) for r in conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            "SELECT * FROM ast_nodes WHERE name LIKE ? ESCAPE '\\' AND tenant_id = ?",
            (f"%{escaped_name}%", self._tenant_id)).fetchall()]

    def purge_tenant_data(self, tenant_id: str) -> int:
        """Delete all AST data for a specific tenant (GDPR / deprovisioning)."""
        try:
            conn = get_connection("graph_ast.sqlite")
            return purge_tenant_rows(conn, "ast_nodes", tenant_id)
        except Exception as e:
            logger.error("GraphASTEngine: purge failed for tenant '%s': %s", tenant_id, e)
            return 0

    def analyze_structure(self, code, language="python"):
        """Analyze code structure and return summary statistics.

        Parses the code, persists detected nodes, and returns aggregate
        metrics including function/class/import counts, complexity stats,
        and connection information.

        Args:
            code: Source code string to analyze.
            language: Programming language identifier (default "python").

        Returns:
            Dict with keys: functions, classes, imports, max_complexity,
            total_complexity, avg_complexity, connections, function_names,
            class_names.
        """
        nodes = self.scan_code(code, "analysis_target", language)
        # Persistir nodos individuales (para consultas posteriores)
        if nodes:
            self._store_nodes_batch(nodes)
        if not nodes:
            return {"functions": 0, "classes": 0, "imports": 0,
                    "max_complexity": 0, "total_complexity": 0,
                    "avg_complexity": 0, "connections": [],
                    "function_names": [], "class_names": []}
        functions = [n for n in nodes if n["node_type"] == "function"]
        classes = [n for n in nodes if n["node_type"] == "class"]
        imports = [n for n in nodes if n["node_type"] == "import"]
        all_connections = []
        for n in nodes:
            try:
                conns = json.loads(n.get("connections", "[]"))
                all_connections.extend(conns)
            except Exception as e:
                logger.debug(f"GraphASTEngine: Failed to parse connections JSON: {e}")
        return {
            "functions": len(functions), "classes": len(classes),
            "imports": len(imports),
            "max_complexity": max((n["complexity"] for n in functions), default=0),
            "total_complexity": sum(n["complexity"] for n in functions),
            "avg_complexity": round(sum(n["complexity"] for n in functions) / max(len(functions), 1), 1),
            "connections": list(set(all_connections)),
            "function_names": [n["name"] for n in functions],
            "class_names": [n["name"] for n in classes],
        }
