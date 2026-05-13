"""
Layer 3: Business Operations — Single-Responsibility Agents.

Each agent handles EXACTLY ONE business domain.
All agents are 100% deterministic. No AI calls.

Agents:
    A09 InvoiceProcessor    — Invoice calculations and validations
    A10 InventoryManager    — Stock tracking and low-stock alerts
    A11 CRMPipeline         — Lead stage progression and probabilities
    A12 TaskScheduler       — Priority scoring and task assignment
    A13 ReportGenerator     — Data aggregation and report formatting
    A14 NotificationDispatcher — Multi-channel notification dispatch
    A15 DataAnalyzer        — Statistical analysis and trend detection
    A16 OperationRouter     — Route operations to correct processor
"""

from .invoice_processor import InvoiceProcessor
from .inventory_manager import InventoryManager
from .crm_pipeline import CRMPipeline
from .task_scheduler import TaskScheduler
from .report_generator import ReportGenerator
from .notification_dispatcher import NotificationDispatcher
from .data_analyzer import DataAnalyzer
from .operation_router import OperationRouter

__all__ = [
    "InvoiceProcessor",
    "InventoryManager",
    "CRMPipeline",
    "TaskScheduler",
    "ReportGenerator",
    "NotificationDispatcher",
    "DataAnalyzer",
    "OperationRouter",
]
