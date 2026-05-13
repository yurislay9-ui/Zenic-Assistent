"""
ZENIC-AGENTS - TransformExecutor (Phase 7.1)

Ejecutor de transformación y mapeo de datos.
"""

import csv
import logging
from typing import Any, Dict

from .base import ActionExecutor, ActionResult

logger = logging.getLogger(__name__)


class TransformExecutor(ActionExecutor):
    """Ejecutor de transformación y mapeo de datos.

    Operations: map_fields, filter, sort, aggregate, format_convert, merge, deduplicate, pivot

    Config: {operation, data, mapping, format, key, keys, ascending, aggregation,
             value_field, group_by, separator, merge_data, merge_on,
             index_field, column_field}
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        operation = config.get("operation", "map_fields").lower()
        data = config.get("data", None)

        valid_ops = {"map_fields", "filter", "sort", "aggregate",
                     "format_convert", "merge", "deduplicate", "pivot"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid transform operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))
        if data is None:
            return ActionResult(False, {}, "No input data provided", self._elapsed_ms(start))

        try:
            dispatch = {"map_fields": lambda: self._map_fields(data, config.get("mapping", {})),
                        "filter": lambda: self._filter(data, config),
                        "sort": lambda: self._sort(data, config),
                        "aggregate": lambda: self._aggregate(data, config),
                        "format_convert": lambda: self._format_convert(data, config),
                        "merge": lambda: self._merge(data, config),
                        "deduplicate": lambda: self._deduplicate(data, config),
                        "pivot": lambda: self._pivot(data, config)}
            result_data = dispatch[operation]()
            elapsed = self._elapsed_ms(start)
            logger.info(f"TransformExecutor: {operation} completed")
            return ActionResult(True, {"result": result_data, "operation": operation}, duration_ms=elapsed)
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"TransformExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation}, str(e), elapsed)

    def _map_fields(self, data, mapping):
        if isinstance(data, dict):
            return {mapping.get(k, k): v for k, v in data.items()}
        elif isinstance(data, list):
            return [{mapping.get(k, k): v for k, v in item.items()} for item in data if isinstance(item, dict)]
        raise ValueError(f"map_fields requires dict or list of dicts, got {type(data).__name__}")

    def _filter(self, data, config):
        if not isinstance(data, list): raise ValueError(f"filter requires a list, got {type(data).__name__}")
        key, operator, value = config.get("key", ""), config.get("operator", "eq"), config.get("value", None)
        if not key: raise ValueError("filter requires 'key' in config")
        ops = {"eq": lambda a,b: a==b, "neq": lambda a,b: a!=b, "gt": lambda a,b: a>b,
               "lt": lambda a,b: a<b, "gte": lambda a,b: a>=b, "lte": lambda a,b: a<=b,
               "contains": lambda a,b: b in str(a)}
        fn = ops.get(operator, ops["eq"])
        return [item for item in data if isinstance(item, dict) and key in item and fn(item[key], value)]

    def _sort(self, data, config):
        if not isinstance(data, list): raise ValueError(f"sort requires a list, got {type(data).__name__}")
        key, ascending = config.get("key", ""), config.get("ascending", True)
        keys = config.get("keys", [])
        if not key and not keys: raise ValueError("sort requires 'key' or 'keys' in config")
        def _sk(item):
            if keys: return tuple(item.get(k, "") for k in keys)
            return item.get(key, "")
        return sorted(data, key=_sk, reverse=not ascending)

    def _aggregate(self, data, config):
        if not isinstance(data, list): raise ValueError(f"aggregate requires a list, got {type(data).__name__}")
        aggregation = config.get("aggregation", "count")
        value_field = config.get("value_field", "")
        group_by = config.get("group_by", "")
        if aggregation in ("sum", "avg", "min", "max") and not value_field:
            raise ValueError(f"aggregate '{aggregation}' requires 'value_field'")
        if group_by: return self._aggregate_grouped(data, aggregation, value_field, group_by)
        values = [item[value_field] for item in data if isinstance(item, dict) and value_field in item]
        if aggregation == "count": return {"count": len(data)}
        elif aggregation == "sum": return {"sum": sum(values)}
        elif aggregation == "avg": return {"avg": sum(values)/len(values) if values else 0}
        elif aggregation == "min": return {"min": min(values) if values else None}
        elif aggregation == "max": return {"max": max(values) if values else None}
        raise ValueError(f"Unknown aggregation: {aggregation}")

    def _aggregate_grouped(self, data, aggregation, value_field, group_by):
        groups = {}
        for item in data:
            if isinstance(item, dict) and group_by in item:
                groups.setdefault(str(item[group_by]), []).append(item)
        result = {}
        for gk, items in groups.items():
            vals = [item[value_field] for item in items if value_field in item and isinstance(item[value_field], (int, float))]
            if aggregation == "count": result[gk] = len(items)
            elif aggregation == "sum": result[gk] = sum(vals)
            elif aggregation == "avg": result[gk] = sum(vals)/len(vals) if vals else 0
            elif aggregation == "min": result[gk] = min(vals) if vals else None
            elif aggregation == "max": result[gk] = max(vals) if vals else None
        return {"groups": result, "group_by": group_by, "aggregation": aggregation}

    def _format_convert(self, data, config):
        fmt = config.get("format", "json_to_csv").lower()
        sep = config.get("separator", ",")
        if fmt == "json_to_csv": return self._json_to_csv(data, sep)
        elif fmt == "csv_to_json": return self._csv_to_json(data, sep)
        elif fmt == "flatten": return self._flatten(data)
        elif fmt == "nest": return self._nest(data, config.get("nest_key", ""))
        raise ValueError(f"Unknown format conversion: {fmt}")

    def _json_to_csv(self, data, sep):
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise ValueError("json_to_csv requires a non-empty list of dicts")
        fields = list(data[0].keys())
        lines = [sep.join(fields)]
        for item in data:
            row = []
            for f in fields:
                v = str(item.get(f, ""))
                if sep in v or '"' in v or "\n" in v: v = f'"{v.replace(chr(34), chr(34)+chr(34))}"'
                row.append(v)
            lines.append(sep.join(row))
        return "\n".join(lines)

    def _csv_to_json(self, data, sep):
        if not isinstance(data, str): raise ValueError("csv_to_json requires a CSV string")
        return [row for row in csv.DictReader(data.strip().split("\n"), delimiter=sep)]

    def _flatten(self, data, prefix=""):
        if not isinstance(data, dict): raise ValueError("flatten requires a dict")
        result = {}
        for k, v in data.items():
            fk = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict): result.update(self._flatten(v, fk))
            else: result[fk] = v
        return result

    def _nest(self, data, nest_key=""):
        if not isinstance(data, dict): raise ValueError("nest requires a dict")
        result = {}
        for k, v in data.items():
            parts = k.split(".")
            current = result
            for p in parts[:-1]: current = current.setdefault(p, {})
            current[parts[-1]] = v
        return result

    def _merge(self, data, config):
        merge_data, merge_on = config.get("merge_data", []), config.get("merge_on", "")
        if not isinstance(data, list) or not isinstance(merge_data, list): raise ValueError("merge requires two lists")
        if not merge_on: raise ValueError("merge requires 'merge_on' field")
        right_idx = {str(item[merge_on]): item for item in merge_data if isinstance(item, dict) and merge_on in item}
        result = []
        for item in data:
            if isinstance(item, dict) and merge_on in item:
                merged = {**item}
                for k, v in right_idx.get(str(item[merge_on]), {}).items():
                    if k != merge_on and k not in merged: merged[k] = v
                result.append(merged)
        return result

    def _deduplicate(self, data, config):
        if not isinstance(data, list): raise ValueError("deduplicate requires a list")
        keys = config.get("keys", [])
        key = config.get("key", "")
        if isinstance(keys, str): keys = [keys]
        if key and not keys: keys = [key]
        if not keys: raise ValueError("deduplicate requires 'key' or 'keys'")
        seen, result = set(), []
        for item in data:
            if not isinstance(item, dict): continue
            composite = tuple(str(item.get(k, "")) for k in keys)
            if composite not in seen: seen.add(composite); result.append(item)
        return {"items": result, "removed_count": len(data) - len(result)}

    def _pivot(self, data, config):
        if not isinstance(data, list): raise ValueError("pivot requires a list of dicts")
        idx_f, col_f, val_f = config.get("index_field", ""), config.get("column_field", ""), config.get("value_field", "")
        if not all([idx_f, col_f, val_f]):
            raise ValueError("pivot requires 'index_field', 'column_field', and 'value_field'")
        pivoted, columns = {}, set()
        for item in data:
            if not isinstance(item, dict): continue
            idx, col = str(item.get(idx_f, "")), str(item.get(col_f, ""))
            if idx not in pivoted: pivoted[idx] = {idx_f: idx}
            pivoted[idx][col] = item.get(val_f, "")
            columns.add(col)
        return {"data": list(pivoted.values()), "columns": sorted(columns), "index_field": idx_f}
