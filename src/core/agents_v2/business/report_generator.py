"""
A13 ReportGenerator — SINGLE RESPONSIBILITY: Generate business reports from data aggregations.

Deterministic report generation: data aggregation, formatting, summary statistics.
No AI. Pure data transformation and summarization.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import ReportResult


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

REPORT_TYPES = frozenset({"summary", "detailed", "comparison", "trend"})
MAX_RECORDS = 1000
DEFAULT_FORMAT = "text"


class ReportGenerator(BaseAgent[ReportResult]):
    """
    A13: Generate business reports from data aggregations.

    Single Responsibility: Report generation ONLY.
    Method: Deterministic data aggregation + template formatting.
    Fallback: Empty ReportResult with no content.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A13_ReportGenerator", **kwargs)

    def execute(self, input_data: Any) -> ReportResult:
        """
        Generate report: aggregate data and format output.

        Input (BusinessData.data dict):
            - data / items: list or dict of data to report on
            - type: "summary"|"detailed"|"comparison"|"trend"
            - title: str (report title)
            - format: "text"|"json" (output format)

        Output: ReportResult with content, format, charts metadata.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        report_data = data.get("data", data.get("items", []))
        report_type = str(data.get("type", "summary")).lower()
        title = str(data.get("title", data.get("description", "Generated Report")[:50]))
        output_format = str(data.get("format", DEFAULT_FORMAT)).lower()

        if report_type not in REPORT_TYPES:
            report_type = "summary"

        # ── Aggregate data ──
        if isinstance(report_data, list):
            record_count = len(report_data)
            field_count = len(report_data[0]) if report_data and isinstance(report_data[0], dict) else 0

            # Numeric field statistics
            numeric_stats = self._compute_numeric_stats(report_data)

        elif isinstance(report_data, dict):
            record_count = 1
            field_count = len(report_data)
            numeric_stats = {}
        else:
            record_count = 0
            field_count = 0
            numeric_stats = {}

        # ── Build report content ──
        lines = [
            f"REPORT: {title}",
            f"Type: {report_type}",
            f"Records: {record_count}",
            f"Fields: {field_count}",
            "",
        ]

        if numeric_stats:
            lines.append("NUMERIC SUMMARY:")
            for field_name, stats in numeric_stats.items():
                lines.append(
                    f"  {field_name}: min={stats['min']}, "
                    f"max={stats['max']}, avg={stats['avg']}, "
                    f"count={stats['count']}"
                )
            lines.append("")

        if report_type == "detailed" and isinstance(report_data, list) and report_data:
            lines.append("DATA SAMPLE (first 5):")
            for idx, item in enumerate(report_data[:5]):
                if isinstance(item, dict):
                    lines.append(f"  [{idx}] {item}")
                else:
                    lines.append(f"  [{idx}] {item}")
            lines.append("")

        content = "\n".join(lines)

        # ── Charts metadata (names of available charts, not actual charts) ──
        charts: list[str] = []
        if numeric_stats:
            charts.append(f"{title}_distribution")
            if len(numeric_stats) > 1:
                charts.append(f"{title}_correlation")
        if report_type in ("trend", "comparison"):
            charts.append(f"{title}_trend")

        return ReportResult(
            content=content,
            format=output_format,
            charts=charts,
            source="deterministic",
        )

    @staticmethod
    def _compute_numeric_stats(data: list) -> dict[str, dict[str, Any]]:
        """Compute min/max/avg/count for numeric fields in a list of dicts."""
        if not data or not isinstance(data[0], dict):
            return {}

        stats: dict[str, dict[str, Any]] = {}
        for key in data[0]:
            values = [
                item[key] for item in data
                if isinstance(item, dict) and isinstance(item.get(key), (int, float))
            ]
            if values:
                stats[key] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": round(sum(values) / len(values), 2),
                    "count": len(values),
                }
        return stats

    def fallback(self, input_data: Any) -> ReportResult:
        """Safe fallback: empty report."""
        return ReportResult(
            content="", format="text", charts=[],
            source="fallback",
        )
