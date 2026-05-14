"""
Zenic-Agents Asistente - SNA Heavy Monitors

Heavy-weight monitors (>1s) that perform multi-source analysis,
projections, and complex data aggregation.
Examples: demand projections, multi-source analysis, capacity planning.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from .base import MonitorBase, register_monitor
from ..types import MonitorResult, MonitorWeight


# ──────────────────────────────────────────────────────────────
#  DEMAND PROJECTION MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class DemandProjectionMonitor(MonitorBase):
    """Projects future demand based on historical sales data
    using simple linear regression and detects potential stockouts."""

    @property
    def monitor_id(self) -> str:
        return "demand_projection"

    @property
    def monitor_name(self) -> str:
        return "Proyeccion de Demanda"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.HEAVY

    @property
    def description(self) -> str:
        return "Proyecta demanda futura y detecta posibles quiebres de stock"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        db_name = params.get("db_name", "sna_data.sqlite")
        sales_table = params.get("sales_table", "sales")
        inventory_table = params.get("inventory_table", "inventory")
        projection_days = params.get("projection_days", 30)
        stockout_threshold_pct = params.get("stockout_threshold_pct", 80.0)

        try:
            # Get daily sales for the last 30 days
            cutoff = time.time() - (30 * 86400)
            rows = self._execute_query(
                f"SELECT date, SUM(amount) FROM {sales_table} "
                f"WHERE date >= ? GROUP BY date ORDER BY date",
                (cutoff,), db_name=db_name,
            )
            if not rows or len(rows) < 5:
                return self._make_result(
                    triggered=False,
                    detail="Datos insuficientes para proyeccion (min 5 dias)",
                    start_time=start,
                )

            # Simple linear regression on daily sales
            daily_sales = [(r[0], float(r[1] or 0)) for r in rows]
            n = len(daily_sales)
            x_vals = list(range(n))
            y_vals = [s[1] for s in daily_sales]

            x_mean = sum(x_vals) / n
            y_mean = sum(y_vals) / n

            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, y_vals))
            denominator = sum((x - x_mean) ** 2 for x in x_vals)

            if denominator == 0:
                slope = 0
                intercept = y_mean
            else:
                slope = numerator / denominator
                intercept = y_mean - slope * x_mean

            # Project daily demand
            projected_daily = max(0, slope * n + intercept)
            total_projected = projected_daily * projection_days

            # Get current inventory
            inv_rows = self._execute_query(
                f"SELECT SUM(quantity) FROM {inventory_table}",
                (), db_name=db_name,
            )
            current_stock = float(inv_rows[0][0] or 0) if inv_rows else 0

            # Calculate stockout risk
            days_of_stock = (current_stock / projected_daily) if projected_daily > 0 else float('inf')
            stockout_risk_pct = 0
            if days_of_stock < projection_days:
                stockout_risk_pct = ((projection_days - days_of_stock) / projection_days) * 100

            triggered = stockout_risk_pct > stockout_threshold_pct
            detail = (
                f"RIESGO DE STOCKOUT: {stockout_risk_pct:.1f}% en {projection_days} dias "
                f"(stock: {current_stock:.0f}, demanda proyectada: {total_projected:.0f})"
                if triggered
                else f"Stock OK para {projection_days} dias "
                     f"(stock: {current_stock:.0f}, demanda proyectada: {total_projected:.0f})"
            )
            return self._make_result(
                triggered=triggered,
                value={
                    "current_stock": round(current_stock, 1),
                    "projected_daily_demand": round(projected_daily, 1),
                    "days_of_stock": round(days_of_stock, 1) if days_of_stock != float('inf') else -1,
                    "stockout_risk_pct": round(stockout_risk_pct, 1),
                    "slope": round(slope, 4),
                },
                detail=detail,
                severity="critical" if stockout_risk_pct > 90 else "warning",
                metadata={
                    "projection_days": projection_days,
                    "data_points": n,
                    "trend": "up" if slope > 0 else "down" if slope < 0 else "stable",
                },
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}", start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  MULTI-SOURCE ANALYSIS MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class MultiSourceAnalysisMonitor(MonitorBase):
    """Cross-references data from multiple sources to detect
    anomalies that aren't visible from a single data source."""

    @property
    def monitor_id(self) -> str:
        return "multi_source_analysis"

    @property
    def monitor_name(self) -> str:
        return "Analisis Multi-Fuente"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.HEAVY

    @property
    def description(self) -> str:
        return "Cruza datos de multiples fuentes para detectar anomalias"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        db_name = params.get("db_name", "sna_data.sqlite")
        anomaly_threshold = params.get("anomaly_threshold", 2.0)

        try:
            # Collect metrics from multiple sources
            findings: List[Dict[str, Any]] = []

            # Source 1: Request volume trend
            cutoff = time.time() - 86400
            req_rows = self._execute_query(
                "SELECT COUNT(*), AVG(processing_time_ms) FROM requests "
                "WHERE created_at >= ?",
                (cutoff,), db_name="request_log.sqlite",
            )
            req_count = req_rows[0][0] if req_rows else 0
            req_avg_ms = float(req_rows[0][1] or 0) if req_rows else 0

            # Source 2: Error rate
            err_rows = self._execute_query(
                "SELECT COUNT(*) FROM requests WHERE created_at >= ? AND status = 'error'",
                (cutoff,), db_name="request_log.sqlite",
            )
            err_count = err_rows[0][0] if err_rows else 0
            err_rate = (err_count / req_count * 100) if req_count > 0 else 0

            # Source 3: System resources
            cpu_pct = 0.0
            ram_pct = 0.0
            try:
                from src.core.shared.resource_governor import get_governor
                gov = get_governor()
                if gov:
                    status = gov.get_status()
                    cpu_pct = status.get("cpu_usage_pct", 0)
                    ram_mb = status.get("ram_usage_mb", 0)
                    ram_limit = status.get("ram_limit_mb", 1)
                    ram_pct = (ram_mb / ram_limit * 100) if ram_limit > 0 else 0
            except Exception:
                pass

            # Anomaly detection: high error rate + slow responses + high resources
            anomaly_score = 0.0
            if err_rate > 10:
                anomaly_score += 1.0
                findings.append({"source": "error_rate", "value": f"{err_rate:.1f}%"})
            if req_avg_ms > 3000:
                anomaly_score += 1.0
                findings.append({"source": "response_time", "value": f"{req_avg_ms:.0f}ms"})
            if cpu_pct > 80:
                anomaly_score += 0.5
                findings.append({"source": "cpu", "value": f"{cpu_pct:.1f}%"})
            if ram_pct > 85:
                anomaly_score += 0.5
                findings.append({"source": "ram", "value": f"{ram_pct:.1f}%"})

            triggered = anomaly_score >= anomaly_threshold
            detail = (
                f"Anomalia detectada (score={anomaly_score:.1f}): {len(findings)} indicadores"
                if triggered
                else f"Sin anomalias (score={anomaly_score:.1f})"
            )
            return self._make_result(
                triggered=triggered,
                value={
                    "anomaly_score": round(anomaly_score, 1),
                    "error_rate_pct": round(err_rate, 1),
                    "avg_response_ms": round(req_avg_ms, 1),
                    "cpu_pct": round(cpu_pct, 1),
                    "ram_pct": round(ram_pct, 1),
                },
                detail=detail,
                severity="critical" if anomaly_score >= 3 else "warning",
                metadata={"findings": findings, "anomaly_threshold": anomaly_threshold},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}", start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  CAPACITY PLANNING MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class CapacityPlanningMonitor(MonitorBase):
    """Analyzes resource usage trends and projects capacity needs."""

    @property
    def monitor_id(self) -> str:
        return "capacity_planning"

    @property
    def monitor_name(self) -> str:
        return "Planificacion de Capacidad"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.HEAVY

    @property
    def description(self) -> str:
        return "Analiza tendencias de uso de recursos y proyecta necesidades"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        max_ram_pct = params.get("max_ram_pct", 90.0)
        projection_days = params.get("projection_days", 14)

        try:
            from src.core.shared.resource_governor import get_governor
            gov = get_governor()
            if gov is None:
                return self._make_result(
                    triggered=False, detail="ResourceGovernor not available",
                    start_time=start,
                )

            status = gov.get_status()
            ram_mb = status.get("ram_usage_mb", 0)
            ram_limit = status.get("ram_limit_mb", 4096)
            ram_pct = (ram_mb / ram_limit * 100) if ram_limit > 0 else 0

            # Get request volume trend for capacity projection
            cutoff = time.time() - (7 * 86400)
            rows = self._execute_query(
                "SELECT COUNT(*), AVG(processing_time_ms) FROM requests "
                "WHERE created_at >= ?",
                (cutoff,), db_name="request_log.sqlite",
            )
            weekly_requests = rows[0][0] if rows else 0
            avg_proc_ms = float(rows[0][1] or 0) if rows else 0

            # Simple capacity projection
            daily_requests = weekly_requests / 7 if weekly_requests > 0 else 0
            projected_daily = daily_requests * 1.1  # 10% growth assumption
            projected_ram_pct = ram_pct + (daily_requests * 0.01)  # rough estimate

            triggered = projected_ram_pct > max_ram_pct or ram_pct > max_ram_pct
            detail = (
                f"CAPACIDAD CRITICA: RAM {ram_pct:.1f}% actual, "
                f"proyectada {projected_ram_pct:.1f}% en {projection_days} dias"
                if triggered
                else f"Capacidad OK: RAM {ram_pct:.1f}%, "
                     f"proyectada {projected_ram_pct:.1f}% en {projection_days} dias"
            )
            return self._make_result(
                triggered=triggered,
                value={
                    "ram_pct": round(ram_pct, 1),
                    "projected_ram_pct": round(projected_ram_pct, 1),
                    "daily_requests": round(daily_requests, 1),
                    "projected_daily_requests": round(projected_daily, 1),
                },
                detail=detail,
                severity="critical" if ram_pct > 95 else "warning",
                metadata={"ram_limit_mb": ram_limit, "projection_days": projection_days},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}", start_time=start,
            )
