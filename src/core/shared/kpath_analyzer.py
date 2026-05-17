"""
ZENIC-AGENTS - K-Path Analyzer v16

Analizador de K-Paths basado en el grafo de dependencias real.

Implementa lo que el documento especifica:
- Mide la profundidad de dependencias desde el nodo mutado
- Si la mutacion afecta mas de K (10) nodos, se bloquea
- Usa el grafo AST almacenado en SQLite (Nivel 3)
"""

import ast
import json
import logging
from collections import deque

logger = logging.getLogger(__name__)


# ============================================================
#  K-PATH ANALYZER - Analisis de K-Paths basado en Grafo AST
# ============================================================

__all__ = ["KPathAnalyzer"]


class KPathAnalyzer:
    """
    Analizador de K-Paths basado en el grafo de dependencias real.

    Implementa lo que el documento especifica:
    - Mide la profundidad de dependencias desde el nodo mutado
    - Si la mutacion afecta mas de K (10) nodos, se bloquea
    - Usa el grafo AST almacenado en SQLite (Nivel 3)
    """

    def __init__(self, k_limit=10):
        self.k_limit = k_limit

    def measure_dependency_depth(self, target_name):
        """
        Mide la profundidad de dependencias desde un nodo en el grafo AST.

        Usa BFS desde el nodo target para contar cuantos nodos
        estan conectados a distancia <= k_limit.

        Returns:
            dict con depth, nodes_affected, exceeds_limit
        """
        import sqlite3
        from .db_initializer import get_connection

        conn = None
        try:
            conn = get_connection("graph_ast.sqlite")

            # Buscar nodo(s) por nombre
            escaped = target_name.replace("%", "\\%").replace("_", "\\_")
            target_rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT name, node_type, connections FROM ast_nodes WHERE name LIKE ? ESCAPE '\\'",
                (f"%{escaped}%",)
            ).fetchall()

            if not target_rows:
                return {
                    "depth": 0,
                    "nodes_affected": 0,
                    "exceeds_limit": False,
                    "affected_nodes": [],
                }

            # BFS desde el nodo target
            visited = set()
            queue = deque()
            all_affected = []

            for row in target_rows:
                node_name = row["name"]
                if node_name not in visited:
                    queue.append((node_name, 0))
                    visited.add(node_name)

            while queue:
                current, depth = queue.popleft()

                if depth > self.k_limit:
                    continue

                all_affected.append({
                    "name": current,
                    "depth": depth,
                })

                # Buscar conexiones del nodo actual
                conn_rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT name, connections FROM ast_nodes WHERE name = ?",
                    (current,)
                ).fetchall()

                for c_row in conn_rows:
                    try:
                        connections = json.loads(c_row["connections"]) if c_row["connections"] else []
                    except (json.JSONDecodeError, TypeError):
                        connections = []

                    for conn_item in connections:
                        conn_str = str(conn_item)
                        if ":" in conn_str:
                            _, dep_name = conn_str.split(":", 1)
                        else:
                            dep_name = conn_str

                        dep_rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                            "SELECT name FROM ast_nodes WHERE name = ?",
                            (dep_name,)
                        ).fetchall()

                        for dr in dep_rows:
                            if dr["name"] not in visited:
                                visited.add(dr["name"])
                                queue.append((dr["name"], depth + 1))

            max_depth = max((n["depth"] for n in all_affected), default=0)

            return {
                "depth": max_depth,
                "nodes_affected": len(all_affected),
                "exceeds_limit": len(all_affected) > self.k_limit,
                "affected_nodes": all_affected,
            }

        except Exception as e:
            logger.debug("K-Path analysis error: %s", e)
            return {
                "depth": 0,
                "nodes_affected": 0,
                "exceeds_limit": False,
                "affected_nodes": [],
                "error": str(e),
            }

    def estimate_code_k_paths(self, code, language="python"):
        """
        Estima K-Paths analizando el AST del codigo directamente.
        Alternativa cuando no hay grafo en SQLite.

        Cuenta las ramas condicionales y estima los caminos de ejecucion,
        similar a como KLEE contaria los paths simbolicos.
        """
        branch_count = 0

        if language == "python":
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.If, ast.While, ast.For)):
                        branch_count += 1
                    elif isinstance(node, ast.BoolOp):
                        branch_count += len(node.values) - 1
                    elif isinstance(node, ast.ExceptHandler):
                        branch_count += 1
            except SyntaxError:
                pass
        else:
            import re
            patterns = {
                "kotlin": r'\bif\b|\bwhen\b|\belse\b|\btry\b',
                "go": r'\bif\b|\bswitch\b|\belse\b|\bselect\b',
                "javascript": r'\bif\b|\bswitch\b|\belse\b|\btry\b|\?.*:',
                "typescript": r'\bif\b|\bswitch\b|\belse\b|\btry\b|\?.*:',
            }
            pattern = patterns.get(language, r'\bif\b|\belse\b')
            branch_count = len(re.findall(pattern, code))

        if branch_count == 0:
            return 1

        estimated = min(2 ** branch_count, 1000)
        return estimated
