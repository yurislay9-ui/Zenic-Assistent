"""
A31 ScheduleParser — SINGLE RESPONSIBILITY: Parse natural language schedule into cron/interval.

Deterministic regex + pattern matching. No AI.
Parses descriptions in EN + ES into structured ScheduleSpec
with cron expressions, interval seconds, or manual type.
"""

from __future__ import annotations

import re
from typing import Any

from ..resilience import BaseAgent
from ..schemas import ScheduleSpec

# ──────────────────────────────────────────────────────────────
# SCHEDULE PATTERNS — EN + ES bilingual
# ──────────────────────────────────────────────────────────────

SCHEDULE_PATTERNS: dict[str, list[str]] = {
    "minutely": ["cada minuto", "every minute", "minutely", "cada 1 minuto"],
    "hourly": ["cada hora", "hourly", "cada 1 hora", "every hour", "por hora"],
    "daily": ["diario", "daily", "cada día", "cada dia", "every day", "todos los días"],
    "weekly": ["semanal", "weekly", "cada semana", "lunes", "monday", "mon"],
    "monthly": ["mensual", "monthly", "cada mes", "1ro", "1st"],
    "yearly": ["anual", "yearly", "cada año", "cada ano", "every year"],
}

# Day name mappings for cron
DAY_NAME_MAP: dict[str, str] = {
    "lunes": "1", "monday": "1", "mon": "1",
    "martes": "2", "tuesday": "2", "tue": "2",
    "miércoles": "3", "wednesday": "3", "wed": "3",
    "jueves": "4", "thursday": "4", "thu": "4",
    "viernes": "5", "friday": "5", "fri": "5",
    "sábado": "6", "saturday": "6", "sat": "6",
    "domingo": "0", "sunday": "0", "sun": "0",
}

# Interval pattern: "cada/every N horas/minutos/segundos"
INTERVAL_PATTERN = re.compile(
    r"(?:cada|every)\s+(\d+)\s+(segundo|segundos|second|seconds|"
    r"minuto|minutos|minute|minutes|"
    r"hora|horas|hour|hours|"
    r"día|dia|días|dias|day|days|"
    r"semana|semanas|week|weeks|"
    r"mes|meses|month|months)",
    re.IGNORECASE,
)

# Cron pattern: direct cron expression (5 fields, last 3 can be *, ranges, etc.)
CRON_PATTERN = re.compile(
    r"(\d+\s+\d+\s+\S+\s+\S+\s+\S+)",  # "0 9 * * *" or "0 9 * * 1-5"
)


class ScheduleParser(BaseAgent[ScheduleSpec]):
    """
    A31: Parse natural language schedule into cron/interval.

    Single Responsibility: Schedule parsing ONLY.
    Method: Regex + keyword pattern matching (deterministic).
    Fallback: Return manual execution (safest default).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A31_ScheduleParser", **kwargs)

    def execute(self, input_data: Any) -> ScheduleSpec:
        """
        Parse schedule from description.

        input_data can be:
          - dict with 'description' key
          - str (the schedule description)
          - AutoDescription object
        """
        description = self._extract_description(input_data)

        if not description:
            return ScheduleSpec(
                type="manual",
                description="No description provided — manual execution",
                source="deterministic",
            )

        # 1. Check for direct cron expression
        cron_match = CRON_PATTERN.search(description)
        if cron_match:
            return ScheduleSpec(
                type="cron",
                cron=cron_match.group(1).strip(),
                description=f"Cron schedule: {cron_match.group(1).strip()}",
                source="deterministic",
            )

        # 2. Check for interval pattern ("cada N unidades")
        interval_match = INTERVAL_PATTERN.search(description.lower())
        if interval_match:
            amount = int(interval_match.group(1))
            unit = interval_match.group(2).lower()
            seconds = self._unit_to_seconds(amount, unit)
            return ScheduleSpec(
                type="interval",
                interval_seconds=seconds,
                description=f"Every {amount} {unit}",
                source="deterministic",
            )

        # 3. Check for known schedule patterns
        desc_lower = description.lower()

        for sched_type, keywords in SCHEDULE_PATTERNS.items():
            if any(kw in desc_lower for kw in keywords):
                return self._build_schedule(sched_type, description)

        # 4. Default: manual
        return ScheduleSpec(
            type="manual",
            description="Manual execution (no schedule pattern detected)",
            source="deterministic",
        )

    def _extract_description(self, input_data: Any) -> str:
        """Extract description from various input formats."""
        if hasattr(input_data, "description"):
            return input_data.description
        elif isinstance(input_data, dict):
            return input_data.get("description", "")
        elif isinstance(input_data, str):
            return input_data
        return ""

    def _build_schedule(self, sched_type: str, description: str) -> ScheduleSpec:
        """Build ScheduleSpec from a known schedule type."""
        hour = self._extract_hour(description)
        day_of_week = self._extract_day_of_week(description)

        if sched_type == "minutely":
            return ScheduleSpec(
                type="interval",
                interval_seconds=60,
                description="Every minute",
                source="deterministic",
            )

        elif sched_type == "hourly":
            return ScheduleSpec(
                type="interval",
                interval_seconds=3600,
                description="Hourly execution",
                source="deterministic",
            )

        elif sched_type == "daily":
            cron = f"0 {hour} * * *"
            return ScheduleSpec(
                type="cron",
                cron=cron,
                interval_seconds=86400,
                description=f"Daily at {hour}:00",
                source="deterministic",
            )

        elif sched_type == "weekly":
            dow = day_of_week or "1"  # Default Monday
            cron = f"0 {hour} * * {dow}"
            return ScheduleSpec(
                type="cron",
                cron=cron,
                interval_seconds=604800,
                description=f"Weekly on day {dow} at {hour}:00",
                source="deterministic",
            )

        elif sched_type == "monthly":
            day = self._extract_day_of_month(description)
            cron = f"0 {hour} {day} * *"
            return ScheduleSpec(
                type="cron",
                cron=cron,
                interval_seconds=2592000,
                description=f"Monthly on day {day} at {hour}:00",
                source="deterministic",
            )

        elif sched_type == "yearly":
            return ScheduleSpec(
                type="cron",
                cron=f"0 {hour} 1 1 *",
                interval_seconds=31536000,
                description="Yearly on January 1st",
                source="deterministic",
            )

        return ScheduleSpec(type="manual", source="deterministic")

    @staticmethod
    def _extract_hour(description: str) -> int:
        """Extract hour from description (supports AM/PM)."""
        match = re.search(
            r"(\d{1,2}):?(\d{2})?\s*(?:am|pm|de la mañana|de la tarde)?",
            description.lower(),
        )
        if match:
            hour = int(match.group(1))
            if "pm" in description.lower() and hour < 12:
                hour += 12
            elif "am" in description.lower() and hour == 12:
                hour = 0
            return hour
        return 9  # Default 9 AM

    @staticmethod
    def _extract_day_of_week(description: str) -> str:
        """Extract day of week for cron from description."""
        desc_lower = description.lower()
        for name, cron_val in DAY_NAME_MAP.items():
            if name in desc_lower:
                return cron_val
        return ""

    @staticmethod
    def _extract_day_of_month(description: str) -> str:
        """Extract day of month from description."""
        match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", description)
        if match:
            day = int(match.group(1))
            if 1 <= day <= 31:
                return str(day)
        return "1"  # Default: 1st of month

    @staticmethod
    def _unit_to_seconds(amount: int, unit: str) -> int:
        """Convert amount + unit to seconds."""
        unit = unit.lower()
        if unit in ("segundo", "segundos", "second", "seconds"):
            return amount
        elif unit in ("minuto", "minutos", "minute", "minutes"):
            return amount * 60
        elif unit in ("hora", "horas", "hour", "hours"):
            return amount * 3600
        elif unit in ("día", "dia", "días", "dias", "day", "days"):
            return amount * 86400
        elif unit in ("semana", "semanas", "week", "weeks"):
            return amount * 604800
        elif unit in ("mes", "meses", "month", "months"):
            return amount * 2592000
        return amount * 3600  # Default: treat as hours

    def fallback(self, input_data: Any) -> ScheduleSpec:
        """Fallback: Return manual execution (safest default)."""
        return ScheduleSpec(type="manual", source="fallback")
