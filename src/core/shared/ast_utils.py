"""
ZENIC-AGENTS — Shared AST Utility Functions.

Eliminates duplicated AST analysis code across engine modules.
Both GraphASTEngine and ReflexionSandbox had identical cyclomatic
complexity calculations; this module provides a single source of truth.
"""

import ast
from typing import List


def compute_cyclomatic_complexity(node: ast.AST) -> int:
    """Compute McCabe cyclomatic complexity for an AST node.

    Counts decision points: if, while, for, except, boolean operators,
    and comprehensions. Base complexity is 1.

    Args:
        node: An AST node (typically FunctionDef or AsyncFunctionDef).

    Returns:
        Cyclomatic complexity as a positive integer (minimum 1).
    """
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            complexity += 1
    return complexity


def extract_function_calls(func_node: ast.AST) -> List[str]:
    """Extract unique function call names from an AST node.

    Args:
        func_node: An AST node (typically FunctionDef).

    Returns:
        Sorted list of unique function/method names called.
    """
    calls = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
    return sorted(set(calls))


def extract_class_connections(class_node: ast.ClassDef) -> List[str]:
    """Extract inheritance and method connections from a class node.

    Args:
        class_node: A ClassDef AST node.

    Returns:
        List of connection strings like 'extends:BaseClass' and 'method:foo'.
    """
    connections = []
    for base in class_node.bases:
        if isinstance(base, ast.Name):
            connections.append(f"extends:{base.id}")
        elif isinstance(base, ast.Attribute):
            connections.append(f"extends:{base.attr}")
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            connections.append(f"method:{node.name}")
    return connections
