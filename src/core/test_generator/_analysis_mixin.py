"""
TestGenerator — AST Analysis Mixin.

Extracts class and function information from Python AST trees.
"""

import ast
import logging
from typing import Any, Dict, List

from ._helpers import annotation_to_str, detect_class_type

logger = logging.getLogger(__name__)


class ASTAnalysisMixin:
    """Mixin providing AST analysis methods for TestGenerator."""

    def _extract_classes(self, tree: ast.AST) -> List[Dict]:
        """Extract class information from AST."""
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Extract method info
                        args = [
                            {
                                "name": a.arg,
                                "annotation": annotation_to_str(a.annotation),
                            }
                            for a in item.args.args
                            if a.arg != "self"
                        ]
                        is_async = isinstance(item, ast.AsyncFunctionDef)
                        is_private = item.name.startswith("_") and not item.name.startswith("__")

                        methods.append({
                            "name": item.name,
                            "args": args,
                            "is_async": is_async,
                            "is_private": is_private,
                            "has_return": item.returns is not None,
                            "docstring": ast.get_docstring(item) or "",
                        })

                # Detect class type
                class_type = detect_class_type(node.name, methods)

                classes.append({
                    "name": node.name,
                    "methods": methods,
                    "type": class_type,
                    "bases": [b.id if isinstance(b, ast.Name) else str(b) for b in node.bases],
                })
        return classes

    def _extract_functions(self, tree: ast.AST) -> List[Dict]:
        """Extract standalone function information from AST."""
        functions = []
        class_methods = set()
        # Collect all class method names to exclude
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        class_methods.add(id(item))

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if id(node) not in class_methods:
                    args = [
                        {"name": a.arg, "annotation": annotation_to_str(a.annotation)}
                        for a in node.args.args
                    ]
                    functions.append({
                        "name": node.name,
                        "args": args,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                    })
        return functions
