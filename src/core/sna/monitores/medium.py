"""
Zenic-Agents Asistente - SNA Medium Monitors

Medium-weight monitors (100ms-1s) that perform aggregations,
trend analysis, and cross-table queries.
Examples: sales trends, CRM conversion ratio, response time trends.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .base import MonitorBase, register_monitor
from ..types import MonitorResult, MonitorWeight


# ──────────────────────────────────────────────────────────────
#  SALES TREND MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class SalesTrendMonitor(MonitorBase):
    """Analyzes sales trends and detects significant drops or spikes."""

    @property
    def monitor_id(self) -> str:
        return "sales_trend"

    @property
    def monitor_name(self) -> str:
        return "Tendencia de Ventas"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.MEDIUM

    @property
    def description(self) -> str:
        return "Analiza tendencias de ventas y detecta caidas o picos significativos"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        db_name = params.get("db_name", "sna_data.sqlite")
        table = params.get("table", "sales")
        drop_threshold = params.get("drop_pct", 25.0)
        window_days = params.get("window_days", 7)

        try:
            now_ts = time.time()
            current_start = now_ts - (window_days * 86400)
            prev_start = current_start - (window_days * 86400)

            current_rows = self._execute_query(
                f"SELECT SUM(amount) FROM {table} WHERE date >= ?",
                (current_start,), db_name=db_name,
            )
            prev_rows = self._execute_query(
                f"SELECT SUM(amount) FROM {table} WHERE date >= ? AND date < ?",
                (prev_start, current_start), db_name=db_name,
            )

            current_total = float(current_rows[0][0] or 0) if current_rows else 0
            prev_total = float(prev_rows[0][0] or 0) if prev_rows else 0

            if prev_total > 0:
                change_pct = ((current_total - prev_total) / prev_total) * 100
            else:
                change_pct = 0.0 if current_total == 0 else 100.0

            triggered = change_pct < -drop_threshold
            direction = "caida" if change_pct < 0 else "aumento"
            detail = (
                f"Ventas: {direction} del {abs(change_pct):.1f}% "
                f"(actual: {current_total:.2f}, anterior: {prev_total:.2f})"
            )
            return self._make_result(
                triggered=triggered,
                value={
                    "current_total": round(current_total, 2),
                    "prev_total": round(prev_total, 2),
                    "change_pct": round(change_pct, 1),
                },
                detail=detail,
                severity="warning" if triggered else "info",
                metadata={"window_days": window_days, "drop_threshold": drop_threshold},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}", start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  CRM CONVERSION MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class CRMConversionMonitor(MonitorBase):
    """Monitors CRM lead-to-customer conversion ratio."""

    @property
    def monitor_id(self) -> str:
        return "crm_conversion"

    @property
    def monitor_name(self) -> str:
        return "Ratio Conversion CRM"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.MEDIUM

    @property
    def description(self) -> str:
        return "Monitorea el ratio de conversion de leads a clientes en el CRM"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        db_name = params.get("db_name", "sna_data.sqlite")
        table = params.get("table", "crm_leads")
        min_conversion_pct = params.get("min_conversion_pct", 10.0)

        try:
            total_rows = self._execute_query(
                f"SELECT COUNT(*) FROM {table}", (), db_name=db_name,
            )
            converted_rows = self._execute_query(
                f"SELECT COUNT(*) FROM {table} WHERE status = 'converted'",
                (), db_name=db_name,
            )
            total_leads = total_rows[0][0] if total_rows else 0
            converted = converted_rows[0][0] if converted_rows else 0
            conversion_pct = (converted / total_leads * 100) if total_leads > 0 else 0

            triggered = (total_leads > 10 and conversion_pct < min_conversion_pct)
            detail = (
                f"Conversion baja: {conversion_pct:.1f}% "
                f"({converted}/{total_leads} leads)"
                if triggered
                else f"Conversion OK: {conversion_pct:.1f}% ({converted}/{total_leads})"
            )
            return self._make_result(
                triggered=triggered,
                value={
                    "total_leads": total_leads,
                    "converted": converted,
                    "conversion_pct": round(conversion_pct, 1),
                },
                detail=detail,
                severity="warning" if triggered else "info",
                metadata={"min_conversion_pct": min_conversion_pct},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}", start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  RESPONSE TIME MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class ResponseTimeMonitor(MonitorBase):
    """Monitors average API response time from the request log."""

    @property
    def monitor_id(self) -> str:
        return "response_time"

    @property
    def monitor_name(self) -> str:
        return "Tiempo de Respuesta"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.MEDIUM

    @property
    def description(self) -> str:
        return "Monitorea el tiempo promedio de respuesta de la API"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        max_avg_ms = params.get("max_avg_ms", 5000)
        window_minutes = params.get("window_minutes", 30)

        try:
            cutoff = time.time() - (window_minutes * 60)
            rows = self._execute_query(
                "SELECT AVG(processing_time_ms), COUNT(*) FROM requests "
                "WHERE created_at >= ?",
                (cutoff,), db_name="request_log.sqlite",
            )
            avg_ms = float(rows[0][0] or 0) if rows else 0
            count = int(rows[0][1] or 0) if rows else 0

            triggered = (count > 5 and avg_ms > max_avg_ms)
            detail = (
                f"Respuesta lenta: {avg_ms:.0f}ms promedio ({count} requests)"
                if triggered
                else f"Respuesta OK: {avg_ms:.0f}ms promedio ({count} requests)"
            )
            return self._make_result(
                triggered=triggered,
                value={"avg_ms": round(avg_ms, 1), "request_count": count},
                detail=detail,
                severity="critical" if avg_ms > 10000 else "warning",
                metadata={"window_minutes": window_minutes, "max_avg_ms": max_avg_ms},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}", start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  ERROR RATE MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class ErrorRateMonitor(MonitorBase):
    """Monitors the error rate from request logs."""

    @property
    def monitor_id(self) -> str:
        return "error_rate"

    @property
    def monitor_name(self) -> str:
        return "Tasa de Errores"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.MEDIUM

    @property
    def description(self) -> str:
        return "Monitorea la tasa de errores en los requests"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        max_error_pct = params.get("max_error_pct", 15.0)
        window_minutes = params.get("window_minutes", 15)

        try:
            cutoff = time.time() - (window_minutes * 60)
            total_rows = self._execute_query(
                "SELECT COUNT(*) FROM requests WHERE created_at >= ?",
                (cutoff,), db_name="request_log.sqlite",
            )
            error_rows = self._execute_query(
                "SELECT COUNT(*) FROM requests WHERE created_at >= ? AND status = 'error'",
                (cutoff,), db_name="request_log.sqlite",
            )
            total = total_rows[0][0] if total_rows else 0
            errors = error_rows[0][0] if error_rows else 0
            error_pct = (errors / total * 100) if total > 0 else 0

            triggered = (total > 10 and error_pct > max_error_pct)
            detail = (
                f"Tasa de errores alta: {error_pct:.1f}% ({errors}/{total})"
                if triggered
                else f"Tasa de errores OK: {error_pct:.1f}% ({errors}/{total})"
            )
            return self._make_result(
                triggered=triggered,
                value={"error_pct": round(error_pct, 1), "errors": errors, "total": total},
                detail=detail,
                severity="critical" if error_pct > 30 else "warning",
                metadata={"window_minutes": window_minutes},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}", start_time=start,
            )
