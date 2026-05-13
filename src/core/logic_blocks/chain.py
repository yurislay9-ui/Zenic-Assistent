"""
ZENIC-AGENTS - LogicBlock Base & LogicChain

Base class for composable logic blocks and the LogicChain pipeline
that executes them sequentially with branching support.
"""

import re
import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from copy import deepcopy

logger = logging.getLogger(__name__)


def _validate_identifier(name: str) -> str:
    """Validate SQL identifier to prevent injection. Only alphanumeric + underscore."""
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


# ============================================================
#  LOGIC BLOCK BASE
# ============================================================


class LogicBlock(ABC):
    """Clase base abstracta para bloques de logica composable.

    Cada bloque representa una unidad atómica de logica de negocio
    que puede ejecutarse independientemente y componerse en chains.
    """

    name: str = ""
    category: str = ""  # business_logic, integrations, auth, data, flow, transform, validation, output
    description: str = ""
    _inputs: list[str] | None = None
    _outputs: list[str] | None = None

    @property
    def inputs(self) -> list[str]:
        """Inputs list — always returns a list (never shared between instances)."""
        if self._inputs is None:
            self._inputs = []
        return self._inputs

    @inputs.setter
    def inputs(self, value: list[str]) -> None:
        self._inputs = value

    @property
    def outputs(self) -> list[str]:
        """Outputs list — always returns a list (never shared between instances)."""
        if self._outputs is None:
            self._outputs = []
        return self._outputs

    @outputs.setter
    def outputs(self, value: list[str]) -> None:
        self._outputs = value

    @abstractmethod
    def execute(self, data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Ejecuta la logica del bloque.

        Args:
            data: Datos de entrada para el bloque
            context: Contexto compartido (db, config, user, etc.)

        Returns:
            Dict con resultado de la ejecucion. Siempre incluye 'success' key.
            En caso de error, retorna {'success': False, 'error': str}.
        """
        ...

    def __repr__(self) -> str:
        return f"LogicBlock({self.name}, {self.category})"


# ============================================================
#  LOGIC CHAIN
# ============================================================


class LogicChain:
    """Cadena de LogicBlocks que ejecutan secuencialmente, pasando datos entre ellos.

    Soporta branching condicional (if/else) y manejo de errores
    en cada paso de la cadena.
    """

    def __init__(self, name: str = "unnamed") -> None:
        self.name = name
        self._blocks: list[dict[str, Any]] = []
        self._log: list[dict[str, Any]] = []

    def execute(self, initial_data: dict[str, Any], context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Ejecuta la cadena completa de bloques secuencialmente.

        Args:
            initial_data: Datos iniciales para el primer bloque
            context: Contexto compartido entre bloques

        Returns:
            Dict con el resultado final de la cadena
        """
        ctx = context or {}
        data = deepcopy(initial_data)
        self._log = []

        for i, step in enumerate(self._blocks):
            step_type = step.get("type", "block")

            if step_type == "block":
                block: LogicBlock = step["block"]
                try:
                    logger.debug(f"LogicChain[{self.name}] Step {i}: {block.name}")
                    result = block.execute(data, ctx)
                    self._log.append({
                        "step": i, "block": block.name,
                        "success": result.get("success", True),
                        "timestamp": time.time(),
                    })
                    # Merge result into data (result keys override)
                    data.update(result)
                    # If a block explicitly fails, stop chain
                    if result.get("success") is False:
                        data["_chain_stopped"] = True
                        data["_stopped_at"] = block.name
                        break
                except Exception as e:
                    logger.error(f"LogicChain[{self.name}] Error in {block.name}: {e}")
                    self._log.append({
                        "step": i, "block": block.name,
                        "success": False, "error": str(e),
                        "timestamp": time.time(),
                    })
                    data.update({"success": False, "error": f"{block.name}: {str(e)}"})
                    data["_chain_stopped"] = True
                    data["_stopped_at"] = block.name
                    break

            elif step_type == "condition":
                condition_func: Callable = step["condition"]
                true_branch: LogicChain = step["true_branch"]
                false_branch: LogicChain = step["false_branch"]
                try:
                    cond_result = condition_func(data, ctx)
                    branch = true_branch if cond_result else false_branch
                    logger.debug(f"LogicChain[{self.name}] Step {i}: condition -> {branch.name}")
                    if branch._blocks:
                        branch_result = branch.execute(data, ctx)
                        data.update(branch_result)
                        self._log.append({
                            "step": i, "type": "condition",
                            "branch_taken": branch.name,
                            "success": branch_result.get("success", True),
                            "timestamp": time.time(),
                        })
                        if branch_result.get("success") is False:
                            data["_chain_stopped"] = True
                            break
                except Exception as e:
                    logger.error(f"LogicChain[{self.name}] Condition error: {e}")
                    self._log.append({
                        "step": i, "type": "condition",
                        "success": False, "error": str(e),
                        "timestamp": time.time(),
                    })

        # Clean up internal keys
        data.pop("_chain_stopped", None)
        data.pop("_stopped_at", None)
        return data

    def add_block(self, block: LogicBlock) -> 'LogicChain':
        """Agrega un bloque al final de la cadena. Retorna self para fluent API."""
        self._blocks.append({"type": "block", "block": block})
        return self

    def add_condition(
        self,
        condition_func: Callable[[dict, dict], bool],
        true_branch: 'LogicChain',
        false_branch: 'LogicChain',
    ) -> 'LogicChain':
        """Agrega un branch condicional a la cadena.

        Args:
            condition_func: Funcion que recibe (data, context) y retorna bool
            true_branch: Chain a ejecutar si la condicion es True
            false_branch: Chain a ejecutar si la condicion es False
        """
        self._blocks.append({
            "type": "condition",
            "condition": condition_func,
            "true_branch": true_branch,
            "false_branch": false_branch,
        })
        return self

    @property
    def blocks(self) -> list[LogicBlock]:
        """Lista de bloques en la cadena (solo bloques, no condiciones)."""
        return [s["block"] for s in self._blocks if s["type"] == "block"]

    @property
    def block_names(self) -> list[str]:
        """Nombres de los bloques en la cadena."""
        return [b.name for b in self.blocks]

    @property
    def execution_log(self) -> list[dict[str, Any]]:
        """Log de la ultima ejecucion."""
        return self._log

    def __repr__(self) -> str:
        return f"LogicChain({self.name}, blocks={self.block_names})"
