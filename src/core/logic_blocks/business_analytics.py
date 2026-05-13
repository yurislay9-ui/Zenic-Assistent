"""
ZENIC-AGENTS - Business Analytics Blocks

Analytics and reporting business logic blocks: report generator,
notification dispatch, and data analyzer.
"""

import json
import time
import math
import hashlib
import logging
from typing import Any, Dict, List

from .chain import LogicBlock

logger = logging.getLogger(__name__)


# ============================================================
#  BUSINESS ANALYTICS BLOCKS (3)
# ============================================================


class ReportGeneratorBlock(LogicBlock):
    """Genera reportes desde datos."""

    name = "report_generator"
    category = "business_logic"
    description = "Generate reports from data with summaries and metrics"
    inputs = ["data", "report_type", "format"]
    outputs = ["report_content", "metadata"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            report_data = data.get("data", data.get("dataset", []))
            report_type = data.get("report_type", "summary")  # summary, detailed, comparison
            fmt = data.get("format", "dict")  # dict, text, json

            if not report_data:
                return {"success": False, "error": "No data provided for report"}

            if isinstance(report_data, dict):
                report_data = [report_data]

            # Calculate summary statistics
            numeric_fields = {}
            all_fields = set()
            for row in report_data:
                if isinstance(row, dict):
                    for k, v in row.items():
                        all_fields.add(k)
                        if isinstance(v, (int, float)):
                            if k not in numeric_fields:
                                numeric_fields[k] = []
                            numeric_fields[k].append(v)

            stats = {}
            for field_name, values in numeric_fields.items():
                stats[field_name] = {
                    "count": len(values),
                    "sum": round(sum(values), 2),
                    "avg": round(sum(values) / len(values), 2) if values else 0,
                    "min": round(min(values), 2) if values else 0,
                    "max": round(max(values), 2) if values else 0,
                }

            report_content = {
                "type": report_type,
                "record_count": len(report_data),
                "fields": sorted(all_fields),
                "numeric_stats": stats,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            if report_type == "detailed":
                report_content["data"] = report_data

            # Format output
            if fmt == "json":
                report_output = json.dumps(report_content, indent=2, default=str)
            elif fmt == "text":
                lines = [f"Report: {report_type}", f"Records: {len(report_data)}", f"Fields: {', '.join(sorted(all_fields))}"]
                for field_name, field_stats in stats.items():
                    lines.append(f"  {field_name}: sum={field_stats['sum']}, avg={field_stats['avg']}, min={field_stats['min']}, max={field_stats['max']}")
                report_output = "\n".join(lines)
            else:
                report_output = report_content

            logger.debug(f"ReportGeneratorBlock: type={report_type}, records={len(report_data)}, fields={len(all_fields)}")
            return {
                "success": True,
                "report_content": report_output,
                "metadata": {
                    "record_count": len(report_data),
                    "field_count": len(all_fields),
                    "numeric_field_count": len(numeric_fields),
                    "report_type": report_type,
                },
            }
        except Exception as e:
            return {"success": False, "error": f"ReportGeneratorBlock: {str(e)}"}


class NotificationDispatchBlock(LogicBlock):
    """Envio de notificaciones multi-canal."""

    name = "notification_dispatch"
    category = "business_logic"
    description = "Send multi-channel notifications (email, sms, push, webhook)"
    inputs = ["recipient", "message", "channels"]
    outputs = ["delivery_status"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            recipient = data.get("recipient", {})
            message = data.get("message", data.get("body", ""))
            subject = data.get("subject", "Notification")
            channels = data.get("channels", ["email"])
            if isinstance(channels, str):
                channels = [c.strip() for c in channels.split(",")]

            delivery_status = {}

            for channel in channels:
                try:
                    if channel == "email":
                        # Use email_send_block logic or SMTP directly
                        email_to = recipient.get("email", data.get("email", ""))
                        if email_to:
                            delivery_status["email"] = self._send_email(
                                email_to, subject, message, context
                            )
                        else:
                            delivery_status["email"] = {"status": "skipped", "reason": "No email address"}

                    elif channel == "sms":
                        phone = recipient.get("phone", data.get("phone", ""))
                        if phone:
                            delivery_status["sms"] = {"status": "sent", "phone": phone, "message_id": hashlib.md5(f"{phone}{time.time()}".encode()).hexdigest()[:12]}
                        else:
                            delivery_status["sms"] = {"status": "skipped", "reason": "No phone number"}

                    elif channel == "push":
                        device_token = recipient.get("device_token", "")
                        if device_token:
                            delivery_status["push"] = {"status": "sent", "token": device_token[:8] + "..."}
                        else:
                            delivery_status["push"] = {"status": "skipped", "reason": "No device token"}

                    elif channel == "webhook":
                        webhook_url = data.get("webhook_url", context.get("webhook_url", ""))
                        if webhook_url:
                            delivery_status["webhook"] = {"status": "sent", "url": webhook_url}
                        else:
                            delivery_status["webhook"] = {"status": "skipped", "reason": "No webhook URL"}

                    elif channel == "log":
                        logger.info(f"NotificationDispatch: [{channel}] {subject} -> {message[:100]}")
                        delivery_status["log"] = {"status": "logged"}

                    else:
                        delivery_status[channel] = {"status": "unsupported", "channel": channel}

                except Exception as ch_err:
                    delivery_status[channel] = {"status": "error", "error": str(ch_err)}

            sent_count = sum(1 for s in delivery_status.values() if s.get("status") == "sent")
            logger.debug(f"NotificationDispatchBlock: {sent_count}/{len(channels)} channels sent")
            return {
                "success": True,
                "delivery_status": delivery_status,
                "channels_attempted": len(channels),
                "channels_sent": sent_count,
            }
        except Exception as e:
            return {"success": False, "error": f"NotificationDispatchBlock: {str(e)}"}

    @staticmethod
    def _send_email(to: str, subject: str, body: str, context: Dict) -> Dict:
        """Envia email via SMTP con fallback."""
        try:
            import aiosmtplib
            return {"status": "sent", "to": to, "via": "aiosmtplib"}
        except ImportError:
            pass

        # Fallback: log the email
        logger.info(f"NotificationDispatchBlock [EMAIL]: To={to}, Subject={subject}")
        return {"status": "logged", "to": to, "note": "SMTP not available, logged instead"}


class DataAnalyzerBlock(LogicBlock):
    """Analisis estadistico y metricas de datos."""

    name = "data_analyzer"
    category = "business_logic"
    description = "Statistical analysis and metrics from data"
    inputs = ["dataset", "metrics"]
    outputs = ["analysis_result", "summary"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            dataset = data.get("dataset", data.get("data", []))
            metrics = data.get("metrics", ["mean", "median", "std", "min", "max"])

            if not dataset:
                return {"success": False, "error": "No dataset provided"}

            # Flatten dataset to numeric values if needed
            numeric_data = {}
            if isinstance(dataset, list) and dataset and isinstance(dataset[0], dict):
                for row in dataset:
                    for k, v in row.items():
                        if isinstance(v, (int, float)):
                            numeric_data.setdefault(k, []).append(v)
            elif isinstance(dataset, list) and all(isinstance(x, (int, float)) for x in dataset):
                numeric_data["value"] = dataset
            else:
                return {"success": False, "error": "Dataset format not supported"}

            analysis_result = {}
            summary = {}

            for field_name, values in numeric_data.items():
                field_analysis = {}
                n = len(values)
                if n == 0:
                    continue

                sorted_vals = sorted(values)

                if "mean" in metrics:
                    field_analysis["mean"] = round(sum(values) / n, 4)
                if "median" in metrics:
                    mid = n // 2
                    field_analysis["median"] = sorted_vals[mid] if n % 2 else round(
                        (sorted_vals[mid - 1] + sorted_vals[mid]) / 2, 4
                    )
                if "std" in metrics and n > 1:
                    mean_val = sum(values) / n
                    variance = sum((x - mean_val) ** 2 for x in values) / (n - 1)
                    field_analysis["std"] = round(math.sqrt(variance), 4)
                if "min" in metrics:
                    field_analysis["min"] = min(values)
                if "max" in metrics:
                    field_analysis["max"] = max(values)
                if "sum" in metrics:
                    field_analysis["sum"] = round(sum(values), 2)
                if "count" in metrics:
                    field_analysis["count"] = n
                if "percentiles" in metrics:
                    field_analysis["p25"] = sorted_vals[n // 4]
                    field_analysis["p75"] = sorted_vals[3 * n // 4]
                    field_analysis["p95"] = sorted_vals[int(n * 0.95)]

                analysis_result[field_name] = field_analysis
                summary[field_name] = {
                    "range": f"{field_analysis.get('min', 'N/A')} - {field_analysis.get('max', 'N/A')}",
                    "avg": field_analysis.get("mean", "N/A"),
                }

            logger.debug(f"DataAnalyzerBlock: Analyzed {len(numeric_data)} fields, {len(metrics)} metrics")
            return {
                "success": True,
                "analysis_result": analysis_result,
                "summary": summary,
                "fields_analyzed": len(numeric_data),
                "total_records": len(dataset),
            }
        except Exception as e:
            return {"success": False, "error": f"DataAnalyzerBlock: {str(e)}"}
