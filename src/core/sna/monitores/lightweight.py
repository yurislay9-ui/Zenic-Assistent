"""
Zenic-Agents Asistente - SNA Lightweight Monitors

Fast monitors (<100ms) that perform simple DB queries or value checks.
Examples: stock bajo, factura vencida, cita manana, disk space, etc.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

from .base import MonitorBase, register_monitor
from ..types import MonitorResult, MonitorWeight


# ──────────────────────────────────────────────────────────────
#  LOW STOCK MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class LowStockMonitor(MonitorBase):
    """Detects products with stock below a configurable threshold."""

    @property
    def monitor_id(self) -> str:
        return "low_stock"

    @property
    def monitor_name(self) -> str:
        return "Stock Bajo"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.LIGHTWEIGHT

    @property
    def description(self) -> str:
        return "Detecta productos con inventario por debajo del minimo configurado"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        threshold = params.get("min_stock", 5)
        db_name = params.get("db_name", "sna_data.sqlite")
        table = params.get("table", "inventory")

        try:
            rows = self._execute_query(
                f"SELECT name, quantity FROM {table} WHERE quantity < ?",
                (threshold,),
                db_name=db_name,
            )
            low_items = [{"name": r[0], "quantity": r[1]} for r in rows]
            triggered = len(low_items) > 0
            detail = (
                f"{len(low_items)} productos con stock < {threshold}"
                if triggered else "Todos los productos con stock suficiente"
            )
            return self._make_result(
                triggered=triggered,
                value=len(low_items),
                detail=detail,
                severity="warning" if triggered else "info",
                metadata={"low_items": low_items[:20], "threshold": threshold},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}",
                start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  OVERDUE INVOICE MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class OverdueInvoiceMonitor(MonitorBase):
    """Detects invoices that are past their due date and unpaid."""

    @property
    def monitor_id(self) -> str:
        return "overdue_invoice"

    @property
    def monitor_name(self) -> str:
        return "Factura Vencida"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.LIGHTWEIGHT

    @property
    def description(self) -> str:
        return "Detecta facturas vencidas sin pagar"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        db_name = params.get("db_name", "sna_data.sqlite")
        table = params.get("table", "invoices")
        days_overdue = params.get("days_overdue", 0)

        try:
            now_ts = time.time()
            overdue_cutoff = now_ts - (days_overdue * 86400)
            rows = self._execute_query(
                f"SELECT id, client, amount, due_date FROM {table} "
                f"WHERE status = 'pending' AND due_date < ?",
                (overdue_cutoff,),
                db_name=db_name,
            )
            overdue = [
                {"id": r[0], "client": r[1], "amount": r[2], "due_date": r[3]}
                for r in rows
            ]
            total_amount = sum(item.get("amount", 0) for item in overdue)
            triggered = len(overdue) > 0
            detail = (
                f"{len(overdue)} facturas vencidas, total: {total_amount:.2f}"
                if triggered else "No hay facturas vencidas"
            )
            return self._make_result(
                triggered=triggered,
                value={"count": len(overdue), "total_amount": total_amount},
                detail=detail,
                severity="critical" if total_amount > 1000 else "warning",
                metadata={"overdue_invoices": overdue[:20]},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}",
                start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  TOMORROW APPOINTMENT MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class TomorrowAppointmentMonitor(MonitorBase):
    """Reminds about appointments scheduled for tomorrow."""

    @property
    def monitor_id(self) -> str:
        return "tomorrow_appointment"

    @property
    def monitor_name(self) -> str:
        return "Cita Manana"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.LIGHTWEIGHT

    @property
    def description(self) -> str:
        return "Notifica sobre citas programadas para manana"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        db_name = params.get("db_name", "sna_data.sqlite")
        table = params.get("table", "appointments")

        try:
            now_ts = time.time()
            tomorrow_start = now_ts + 86400
            tomorrow_end = now_ts + (2 * 86400)
            rows = self._execute_query(
                f"SELECT id, client, date, description FROM {table} "
                f"WHERE date >= ? AND date < ?",
                (tomorrow_start, tomorrow_end),
                db_name=db_name,
            )
            appointments = [
                {"id": r[0], "client": r[1], "date": r[2], "desc": r[3]}
                for r in rows
            ]
            triggered = len(appointments) > 0
            detail = (
                f"{len(appointments)} citas programadas para manana"
                if triggered else "No hay citas para manana"
            )
            return self._make_result(
                triggered=triggered,
                value=len(appointments),
                detail=detail,
                severity="info",
                metadata={"appointments": appointments[:20]},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}",
                start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  DISK SPACE MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class DiskSpaceMonitor(MonitorBase):
    """Monitors available disk space on the data partition."""

    @property
    def monitor_id(self) -> str:
        return "disk_space"

    @property
    def monitor_name(self) -> str:
        return "Espacio en Disco"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.LIGHTWEIGHT

    @property
    def description(self) -> str:
        return "Monitorea espacio disponible en disco"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        min_free_mb = params.get("min_free_mb", 500)
        path = params.get("path", os.path.expanduser("~"))

        try:
            stat = os.statvfs(path)
            free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
            total_mb = (stat.f_blocks * stat.f_frsize) / (1024 * 1024)
            pct_free = (free_mb / total_mb * 100) if total_mb > 0 else 0
            triggered = free_mb < min_free_mb
            detail = (
                f"Espacio bajo: {free_mb:.0f}MB libre de {total_mb:.0f}MB ({pct_free:.1f}%)"
                if triggered else f"Espacio OK: {free_mb:.0f}MB libre ({pct_free:.1f}%)"
            )
            return self._make_result(
                triggered=triggered,
                value={"free_mb": round(free_mb, 1), "pct_free": round(pct_free, 1)},
                detail=detail,
                severity="critical" if free_mb < 100 else "warning",
                metadata={"path": path, "min_free_mb": min_free_mb},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}",
                start_time=start,
            )


# ──────────────────────────────────────────────────────────────
#  SYSTEM HEALTH MONITOR
# ──────────────────────────────────────────────────────────────

@register_monitor
class SystemHealthMonitor(MonitorBase):
    """Monitors CPU and RAM usage via ResourceGovernor."""

    @property
    def monitor_id(self) -> str:
        return "system_health"

    @property
    def monitor_name(self) -> str:
        return "Salud del Sistema"

    @property
    def weight(self) -> MonitorWeight:
        return MonitorWeight.LIGHTWEIGHT

    @property
    def description(self) -> str:
        return "Monitorea uso de CPU y RAM del sistema"

    async def check(self, params: Dict[str, Any],
                    tenant_id: str = "") -> MonitorResult:
        start = time.monotonic()
        cpu_threshold = params.get("cpu_threshold_pct", 90)
        ram_threshold = params.get("ram_threshold_pct", 90)

        try:
            from src.core.shared.resource_governor import get_governor
            gov = get_governor()
            if gov is None:
                return self._make_result(
                    triggered=False, detail="ResourceGovernor not available",
                    start_time=start,
                )
            status = gov.get_status()
            cpu = status.get("cpu_usage_pct", 0)
            ram_mb = status.get("ram_usage_mb", 0)
            ram_limit = status.get("ram_limit_mb", 1)
            ram_pct = (ram_mb / ram_limit * 100) if ram_limit > 0 else 0
            triggered = cpu > cpu_threshold or ram_pct > ram_threshold
            detail = (
                f"Recursos altos: CPU={cpu:.1f}% RAM={ram_pct:.1f}%"
                if triggered else f"Recursos OK: CPU={cpu:.1f}% RAM={ram_pct:.1f}%"
            )
            return self._make_result(
                triggered=triggered,
                value={"cpu_pct": round(cpu, 1), "ram_pct": round(ram_pct, 1)},
                detail=detail,
                severity="critical" if cpu > 95 or ram_pct > 95 else "warning",
                metadata={"ram_mb": ram_mb, "ram_limit_mb": ram_limit},
                start_time=start,
            )
        except Exception as e:
            return self._make_result(
                triggered=False, detail=f"Error: {e}",
                start_time=start,
            )
