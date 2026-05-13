"""
ZENIC-AGENTS - Flow Logic Blocks

Control flow blocks: conditional, loop, parallel, switch, try_catch.
"""

import logging
from typing import Any, Dict, List, Tuple
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed

from .chain import LogicBlock, LogicChain

logger = logging.getLogger(__name__)


# ============================================================
#  FLOW BLOCKS (5)
# ============================================================


class ConditionalBlock(LogicBlock):
    """If/else branching basado en un campo de datos."""

    name = "conditional"
    category = "flow"
    description = "If/else branching based on data field value"
    inputs = ["field", "value", "data"]
    outputs = ["branch_taken", "data"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            field_name = data.get("field", data.get("_condition_field", ""))
            expected_value = data.get("value", data.get("_condition_value", None))
            if not field_name:
                return {"success": False, "error": "No field specified for conditional"}

            actual_value = data.get(field_name)
            # Support comparison operators
            operator = data.get("operator", "==")
            ops = {
                "==": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
                ">": lambda a, b: a > b,
                "<": lambda a, b: a < b,
                ">=": lambda a, b: a >= b,
                "<=": lambda a, b: a <= b,
                "in": lambda a, b: a in b,
                "not_in": lambda a, b: a not in b,
                "contains": lambda a, b: b in a if a else False,
            }
            op_func = ops.get(operator, ops["=="])
            result = op_func(actual_value, expected_value)
            branch = "true" if result else "false"

            logger.debug(f"ConditionalBlock: {field_name}={actual_value} {operator} {expected_value} -> {branch}")
            return {"success": True, "branch_taken": branch, "condition_result": result}
        except Exception as e:
            return {"success": False, "error": f"ConditionalBlock: {str(e)}"}


class LoopBlock(LogicBlock):
    """Itera sobre una lista campo, aplicando una sub-chain a cada elemento."""

    name = "loop"
    category = "flow"
    description = "Iterate over a list field, apply sub-chain to each item"
    inputs = ["items_field", "item_name", "sub_chain"]
    outputs = ["results", "processed_count"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            items_field = data.get("items_field", "items")
            items = data.get(items_field, [])
            item_name = data.get("item_name", "item")
            sub_chain = data.get("_sub_chain", None)

            if not isinstance(items, list):
                return {"success": False, "error": f"Field '{items_field}' is not a list"}

            results = []
            for idx, item in enumerate(items):
                if sub_chain and isinstance(sub_chain, LogicChain):
                    # Create item-specific data
                    item_data = deepcopy(data)
                    item_data[item_name] = item
                    item_data["_loop_index"] = idx
                    result = sub_chain.execute(item_data, context)
                    results.append(result)
                else:
                    # No sub-chain, just collect items
                    results.append({item_name: item, "_loop_index": idx})

            logger.debug(f"LoopBlock: Processed {len(results)} items from '{items_field}'")
            return {
                "success": True,
                "results": results,
                "processed_count": len(results),
            }
        except Exception as e:
            return {"success": False, "error": f"LoopBlock: {str(e)}"}


class ParallelBlock(LogicBlock):
    """Ejecuta multiples bloques concurrentemente."""

    name = "parallel"
    category = "flow"
    description = "Execute multiple blocks concurrently"
    inputs = ["blocks", "max_workers"]
    outputs = ["results", "errors"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            blocks = data.get("_parallel_blocks", [])
            max_workers = data.get("max_workers", 4)

            if not blocks:
                return {"success": True, "results": [], "errors": []}

            results = {}
            errors = {}

            def run_block(block: LogicBlock) -> Tuple[str, Dict]:
                try:
                    return block.name, block.execute(deepcopy(data), context)
                except Exception as e:
                    return block.name, {"success": False, "error": str(e)}

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(run_block, b): b.name for b in blocks}
                for future in as_completed(futures):
                    name, result = future.result()
                    if result.get("success", True):
                        results[name] = result
                    else:
                        errors[name] = result.get("error", "Unknown error")

            # Merge all successful results
            merged = {}
            for r in results.values():
                merged.update(r)

            logger.debug(f"ParallelBlock: {len(results)} ok, {len(errors)} errors")
            return {
                "success": len(errors) == 0,
                "results": merged,
                "errors": errors,
            }
        except Exception as e:
            return {"success": False, "error": f"ParallelBlock: {str(e)}"}


class SwitchBlock(LogicBlock):
    """Multi-way branching basado en el valor de un campo."""

    name = "switch"
    category = "flow"
    description = "Multi-way branching on data value"
    inputs = ["field", "cases", "default"]
    outputs = ["matched_case", "data"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            field_name = data.get("switch_field", data.get("field", "type"))
            field_value = data.get(field_name)
            cases = data.get("cases", {})
            default_chain = data.get("_default_chain", None)

            matched_key = None
            for key, chain in cases.items():
                if str(field_value) == str(key):
                    matched_key = key
                    if isinstance(chain, LogicChain):
                        result = chain.execute(deepcopy(data), context)
                        result["matched_case"] = key
                        return result
                    break

            if matched_key is None and default_chain and isinstance(default_chain, LogicChain):
                result = default_chain.execute(deepcopy(data), context)
                result["matched_case"] = "default"
                return result

            logger.debug(f"SwitchBlock: field={field_name}, value={field_value}, matched={matched_key}")
            return {
                "success": True,
                "matched_case": matched_key or "default",
                "field_value": field_value,
            }
        except Exception as e:
            return {"success": False, "error": f"SwitchBlock: {str(e)}"}


class TryCatchBlock(LogicBlock):
    """Wrapper de manejo de errores para sub-chain."""

    name = "try_catch"
    category = "flow"
    description = "Error handling wrapper for sub-chain execution"
    inputs = ["try_chain", "catch_chain", "finally_chain"]
    outputs = ["data", "error", "caught"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try_chain = data.get("_try_chain", None)
        catch_chain = data.get("_catch_chain", None)
        finally_chain = data.get("_finally_chain", None)

        result_data = deepcopy(data)
        caught_error = None

        try:
            if try_chain and isinstance(try_chain, LogicChain):
                result_data = try_chain.execute(result_data, context)
                if result_data.get("success") is False:
                    caught_error = result_data.get("error", "Unknown error in try chain")
        except Exception as e:
            caught_error = str(e)

        if caught_error:
            logger.debug(f"TryCatchBlock: Caught error -> {caught_error}")
            result_data["caught_error"] = caught_error
            if catch_chain and isinstance(catch_chain, LogicChain):
                catch_data = deepcopy(data)
                catch_data["error"] = caught_error
                result_data = catch_chain.execute(catch_data, context)

        try:
            if finally_chain and isinstance(finally_chain, LogicChain):
                finally_result = finally_chain.execute(deepcopy(data), context)
                result_data.update(finally_result)
        except Exception as e:
            logger.error(f"TryCatchBlock: Finally chain error: {e}")

        result_data["caught"] = caught_error is not None
        result_data.setdefault("success", True)
        return result_data
