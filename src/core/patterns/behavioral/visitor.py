"""
ZENIC-AGENTS - Behavioral Pattern: Visitor

AST visitor framework with double dispatch for Python code analysis.

Concrete visitors:
  - TokenCountVisitor: counts tokens per AST node type.
  - ComplexityVisitor: calculates cyclomatic complexity.
  - RefactorVisitor: marks nodes for refactoring.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
"""

import ast
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ======================================================================
# Abstract base classes
# ======================================================================

class ASTNode(ABC):
    """
    Abstract base for visitable AST nodes.

    Subclasses must implement ``accept(visitor)`` which enables double
    dispatch — the visitor's type-specific method is called.
    """

    @abstractmethod
    def accept(self, visitor: "ASTVisitor") -> Any:
        """
        Accept a visitor, invoking the appropriate visit method.

        Args:
            visitor: An :class:`ASTVisitor` instance.

        Returns:
            The result produced by the visitor for this node.
        """
        ...


class ASTVisitor(ABC):
    """
    Abstract visitor with double dispatch.

    Subclasses implement ``visit_X(node)`` methods for each node type
    they care about.  The generic :meth:`visit` method resolves the
    specific ``visit_X`` method via the node's ``accept`` call.
    """

    @abstractmethod
    def visit(self, node: ASTNode) -> Any:
        """
        Visit a node.  Typically delegates to the node's ``accept``.
        """
        ...

    def _dispatch(self, node: ASTNode, prefix: str = "visit_") -> Any:
        """
        Resolve and call the type-specific visit method.

        Looks for ``visit_{ClassName}`` (lowercased) on *self*.  Falls
        back to ``visit_default`` if no specific method exists.
        """
        node_type = type(node).__name__.lower()
        method_name = f"{prefix}{node_type}"
        method = getattr(self, method_name, None)
        if method is not None:
            return method(node)
        default = getattr(self, f"{prefix}default", None)
        if default is not None:
            return default(node)
        return None


# ======================================================================
# VisitableAST — wraps Python ast.AST nodes
# ======================================================================

class VisitableAST(ASTNode):
    """
    Adapter that wraps a :class:`ast.AST` node to make it visitable.

    The ``accept`` method dynamically resolves the visitor method name
    from the underlying ``ast.AST`` node's class name (e.g. an
    ``ast.If`` node dispatches to ``visitor.visit_if``).
    """

    def __init__(self, node: ast.AST) -> None:
        self._node = node

    @property
    def node(self) -> ast.AST:
        """Return the underlying :class:`ast.AST` node."""
        return self._node

    def accept(self, visitor: ASTVisitor) -> Any:
        # Dynamic dispatch based on ast node class name
        node_type = type(self._node).__name__.lower()
        method_name = f"visit_{node_type}"
        method = getattr(visitor, method_name, None)
        if method is not None:
            return method(self)
        default = getattr(visitor, "visit_default", None)
        if default is not None:
            return default(self)
        return None

    def children(self) -> List["VisitableAST"]:
        """Return immediate VisitableAST children of this node."""
        result: List[VisitableAST] = []
        for child in ast.iter_child_nodes(self._node):
            result.append(VisitableAST(child))
        return result


# ======================================================================
# Concrete visitors
# ======================================================================

class TokenCountVisitor(ASTVisitor):
    """
    Counts tokens (roughly: AST nodes) per node type.

    After traversal, ``token_counts`` contains a mapping from node type
    name to count.
    """

    def __init__(self) -> None:
        self.token_counts: Dict[str, int] = {}

    def visit(self, node: ASTNode) -> Dict[str, int]:
        self.token_counts.clear()
        if isinstance(node, VisitableAST):
            self._walk(node.node)
        else:
            node.accept(self)
        return dict(self.token_counts)

    def _walk(self, node: ast.AST) -> None:
        name = type(node).__name__
        self.token_counts[name] = self.token_counts.get(name, 0) + 1
        for child in ast.iter_child_nodes(node):
            self._walk(child)

    # Type-specific overrides (optional — the generic _walk handles all)
    def visit_default(self, node: ASTNode) -> Dict[str, int]:
        if isinstance(node, VisitableAST):
            return self.visit(VisitableAST(node.node))
        self.token_counts[type(node).__name__] = self.token_counts.get(type(node).__name__, 0) + 1
        return dict(self.token_counts)


class ComplexityVisitor(ASTVisitor):
    """
    Calculates cyclomatic complexity of a Python AST.

    Cyclomatic complexity = 1 + number of decision points.

    Decision points: ``if``, ``for``, ``while``, ``except``, ``with``,
    ``and``, ``or``, ``assert``, comprehensions, ternary (``IfExp``).
    """

    # Node types that add 1 to the decision count
    _DECISION_NODES: Set[str] = {
        "If", "For", "While", "ExceptHandler",
        "With", "Assert", "IfExp",
        "ListComp", "SetComp", "DictComp", "GeneratorExp",
    }

    def __init__(self) -> None:
        self._decision_count: int = 0

    def visit(self, node: ASTNode) -> int:
        self._decision_count = 0
        if isinstance(node, VisitableAST):
            self._walk(node.node)
        else:
            node.accept(self)
        return 1 + self._decision_count

    def _walk(self, node: ast.AST) -> None:
        name = type(node).__name__
        if name in self._DECISION_NODES:
            self._decision_count += 1
        # ``and`` / ``or`` in BoolOp add one per extra operand
        if isinstance(node, ast.BoolOp):
            self._decision_count += len(node.values) - 1
        for child in ast.iter_child_nodes(node):
            self._walk(child)

    def visit_default(self, node: ASTNode) -> int:
        if isinstance(node, VisitableAST):
            return self.visit(VisitableAST(node.node))
        return 1 + self._decision_count


class RefactorVisitor(ASTVisitor):
    """
    Marks AST nodes that may need refactoring.

    Flags:
      - Functions with > 10 arguments.
      - Functions with body > 50 lines.
      - Class with > 20 methods.
      - Deeply nested blocks (> 4 levels).

    Results are stored in ``refactor_marks``.
    """

    def __init__(self) -> None:
        self.refactor_marks: List[Dict[str, Any]] = []

    def visit(self, node: ASTNode) -> List[Dict[str, Any]]:
        self.refactor_marks.clear()
        if isinstance(node, VisitableAST):
            self._walk(node.node, depth=0)
        else:
            node.accept(self)
        return list(self.refactor_marks)

    def _walk(self, node: ast.AST, depth: int) -> None:
        name = type(node).__name__

        # Too many arguments
        if isinstance(node, ast.FunctionDef):
            arg_count = len(node.args.args) + len(node.args.kwonlyargs)
            if node.args.vararg:
                arg_count += 1
            if node.args.kwarg:
                arg_count += 1
            if arg_count > 10:
                self.refactor_marks.append({
                    "type": "too_many_args",
                    "node": "FunctionDef",
                    "name": node.name,
                    "line": node.lineno,
                    "value": arg_count,
                })

            # Function body too long
            if hasattr(node, "end_lineno") and node.end_lineno:
                lines = node.end_lineno - node.lineno + 1
                if lines > 50:
                    self.refactor_marks.append({
                        "type": "function_too_long",
                        "node": "FunctionDef",
                        "name": node.name,
                        "line": node.lineno,
                        "value": lines,
                    })

        # Class with too many methods
        if isinstance(node, ast.ClassDef):
            method_count = sum(
                1 for item in node.body if isinstance(item, ast.FunctionDef)
            )
            if method_count > 20:
                self.refactor_marks.append({
                    "type": "too_many_methods",
                    "node": "ClassDef",
                    "name": node.name,
                    "line": node.lineno,
                    "value": method_count,
                })

        # Deep nesting
        if name in ("If", "For", "While", "With", "Try"):
            if depth > 4:
                self.refactor_marks.append({
                    "type": "deep_nesting",
                    "node": name,
                    "line": getattr(node, "lineno", 0),
                    "value": depth,
                })

        for child in ast.iter_child_nodes(node):
            child_depth = depth + 1 if name in ("If", "For", "While", "With", "Try", "FunctionDef", "ClassDef") else depth
            self._walk(child, child_depth)

    def visit_default(self, node: ASTNode) -> List[Dict[str, Any]]:
        if isinstance(node, VisitableAST):
            return self.visit(VisitableAST(node.node))
        return list(self.refactor_marks)
