"""Mixin: AST analysis helpers for ReflexionSandbox."""

import ast


class AnalysisMixin:
    """Mixin providing AST analysis helper methods."""

    def _cyclomatic(self, func_node):
        """Calcula la complejidad ciclomatica de una funcion."""
        complexity = 1
        for node in ast.walk(func_node):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1
        return complexity

    def _detect_io_calls(self, tree):
        """Detecta llamadas I/O que deben ser mockeadas (Path Pruning)."""
        io_call_names = {
            "open", "read", "write", "input", "print",
            "fetch", "requests.get", "requests.post", "urlopen",
            "socket.connect", "http", "urllib", "aiohttp",
            "db.execute", "cursor.execute", "session.query",
            "redis.get", "redis.set", "cache.get", "cache.set"
        }
        io_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in io_call_names:
                    io_calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    full = f"{node.func.value.id}.{node.func.attr}" if isinstance(node.func.value, ast.Name) else node.func.attr
                    if full in io_call_names or node.func.attr in io_call_names:
                        io_calls.append(full)
        return list(set(io_calls))

    def _detect_dangerous(self, tree):
        """Detecta llamadas potencialmente peligrosas."""
        dangerous_names = {
            "eval", "exec", "compile", "__import__",
            "os.system", "os.popen", "subprocess.call", "subprocess.run",
            "shutil.rmtree", "os.remove", "os.unlink"
        }
        dangerous = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in dangerous_names:
                    dangerous.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    full = f"{node.func.value.id}.{node.func.attr}" if isinstance(node.func.value, ast.Name) else node.func.attr
                    if full in dangerous_names or node.func.attr in dangerous_names:
                        dangerous.append(full)
        return list(set(dangerous))
